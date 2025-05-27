import subprocess
import os
import json
from typing import Optional, List
from prettytable import PrettyTable
import pandas as pd

from src.scan.util import (
    run_command_and_read_output,
    get_severity,
    run_command_bg,
    JSONParseError,
)

FS_REPORT_PATH = "/tmp/trivy_code_full.json"

def scan_filesystem(
    path: str = ".",  # Path to scan; defaults to the current directory
    report: str = FS_REPORT_PATH,  # Output file for scan results
    scanners: List[
        str
    ] = [],  # Scanners to use; defaults to vuln, secret, and misconfig
    severity_level: str = "HIGH",  # Minimum severity level to include in the report
    bg: bool = False,
):
    ###chainlit###
    if not os.path.isdir(path):
        print(f"Error: The folder '{path}' does not exist.")
        return False

    if not scanners:
        scanners = ["vuln", "secret", "misconfig"]

    severity = ",".join(get_severity(severity_level))

    # Construct the trivy command for scanning the filesystem
    command = [
        "trivy",
        "fs",
        "--scanners",
        ",".join(scanners),  # Join the scanner types as a single string
        "--format",
        "json",  # Set the output format to JSON
        "--db-repository",
        "public.ecr.aws/aquasecurity/trivy-db",
        "--java-db-repository",
        "public.ecr.aws/aquasecurity/trivy-java-db",
        "--output",
        report,  # Specify the output file for the scan results
        "--severity",
        severity,  # Specify the severity levels to include
        path,  # Path to be scanned
    ]
    print(command)
    # Run the command and return the parsed output
    if bg:
        result = run_command_bg(command)
    else:
        result = run_command_and_read_output(command=command, output_file=report)
    return result


def get_filesystem_report():
    with open(FS_REPORT_PATH, "r") as file:
        try:
            return json.load(file)
        except json.JSONDecodeError:
            raise JSONParseError(FS_REPORT_PATH)


def get_filesystem_summary_yaml():

    output = {}

    report = get_filesystem_report()
    for item in report["Results"]:
        target = item["Target"]
        #Vulnerabilities
        if "Vulnerabilities" in item:
            output[target] = {}
            output[target]["Vulnerabilities"] = []
            for vul in item["Vulnerabilities"]:
                vid = vul["VulnerabilityID"]
                iv = vul["InstalledVersion"]
                if "FixedVersion" in vul:
                    fv = vul["FixedVersion"]
                else:
                    fv = "NA"
                pkg = vul["PkgName"]
                severity = vul["Severity"]
                title = vul["Title"]
                desc = vul["Description"]
                if "CVSS" in vul:
                    if "nvd" in vul["CVSS"]:
                        cvss = vul["CVSS"]["nvd"]["V3Score"]
                    elif "ghsa" in vul["CVSS"]:
                        cvss = vul["CVSS"]["ghsa"]["V3Score"]
                    elif "redhat" in vul["CVSS"]:
                        cvss = vul["CVSS"]["redhat"]["V3Score"]
                    else:
                        cvss = 0
                else:
                    cvss = 0
                output[target]["Vulnerabilities"].append({"VulID": vid, "Severity": severity, "Package": pkg, "Score": cvss, "Install Ver": iv, "Fixed Ver": fv, "Title": title})
    
    return output

def get_filesystem_summary_table():
    table = PrettyTable()
    table.field_names = ["ID", "Severity", "Package", "Cur Ver.", "Fixed Ver.", "CVSS", "title"]

    report = get_filesystem_report()
    for item in report["Results"]:
        target = item["Target"]
        #Vulnerabilities
        if "Vulnerabilities" in item:
            for vul in item["Vulnerabilities"]:
                vid = vul["VulnerabilityID"]
                iv = vul["InstalledVersion"]
                if "FixedVersion" in vul:
                    fv = vul["FixedVersion"]
                else:
                    fv = "NA"
                pkg = vul["PkgName"]
                severity = vul["Severity"]
                title = vul["Title"]
                desc = vul["Description"]
                if "CVSS" in vul:
                    if "nvd" in vul["CVSS"]:
                        cvss = vul["CVSS"]["nvd"]["V3Score"]
                    elif "ghsa" in vul["CVSS"]:
                        cvss = vul["CVSS"]["ghsa"]["V3Score"]
                    elif "redhat" in vul["CVSS"]:
                        cvss = vul["CVSS"]["redhat"]["V3Score"]
                    else:
                        cvss = 0
                else:
                    cvss = 0
                table.add_row([vid, severity, pkg, iv, fv, cvss, title])
    return table.get_string()

def code_footprint(report: dict, output_format="table"):
    """
    Generate a report of vulnerabilities in the specified output format.
    
    Parameters:
        report (dict): The input report containing vulnerability details.
        output_format (str): The output format, either "table" for PrettyTable or "dataframe" for pandas DataFrame.
    
    Returns:
        str or pandas.DataFrame: The vulnerability report in the selected format.
    """
    table = PrettyTable()
    table.field_names = ["ID", "Severity", "Package", "Cur Ver.", "Fixed Ver.", "CVSS", "Title"]
    rows = []

    for item in report.get("Results", []):
        if "Vulnerabilities" in item:
            for vul in item["Vulnerabilities"]:
                vid = vul.get("VulnerabilityID", "NA")
                iv = vul.get("InstalledVersion", "NA")
                fv = vul.get("FixedVersion", "NA")
                pkg = vul.get("PkgName", "NA")
                severity = vul.get("Severity", "NA")
                title = vul.get("Title", "NA")
                cvss = 0
                if "CVSS" in vul:
                    cvss = vul["CVSS"].get("nvd", {}).get("V3Score", 0) or \
                           vul["CVSS"].get("ghsa", {}).get("V3Score", 0) or \
                           vul["CVSS"].get("redhat", {}).get("V3Score", 0)
                row = [vid, severity, pkg, iv, fv, cvss, title]
                table.add_row(row)
                rows.append(row)

    if output_format == "table":
        return table.get_string()
    elif output_format == "dataframe":
        return pd.DataFrame(rows, columns=["ID", "Severity", "Package", "Cur Ver.", "Fixed Ver.", "CVSS", "Title"])
    else:
        raise ValueError("Invalid output_format. Choose 'table' or 'dataframe'.")

def get_purl_or_pkgid(data):
    # Check if 'PkgIdentifier' and 'PURL' exist and are not empty
    if 'PkgIdentifier' in data and 'PURL' in data['PkgIdentifier'] and data['PkgIdentifier']['PURL']:
        return data['PkgIdentifier']['PURL']
    else:
        return data['PkgID']

async def process_code_scan(report: dict, type="CODE"):
    data = []
    for result in report["Results"]:
        target = result.get("Target", "")
        vulnerabilities = result.get("Vulnerabilities", [])
        for vul in vulnerabilities:
            if "CVSS" in vul:
                if "nvd" in vul["CVSS"]:
                    risk_score = vul["CVSS"]["nvd"].get("V3Score", 0)
                    cvss_strings = vul["CVSS"]["nvd"].get("V3Vector", "")
                elif "ghsa" in vul["CVSS"]:
                    risk_score = vul["CVSS"]["ghsa"].get("V3Score", 0)
                    cvss_strings = vul["CVSS"]["ghsa"].get("V3Vector", "")
                elif "redhat" in vul["CVSS"]:
                    risk_score = vul["CVSS"]["redhat"].get("V3Score", 0)
                    cvss_strings = vul["CVSS"]["redhat"].get("V3Vector", "")
            data.append({
                "type": type,
                "id": vul.get("VulnerabilityID", ""),
                "resource_name": get_purl_or_pkgid(vul),
                "service_name": "general",
                "avdid": "",
                "title": vul.get("Title", ""),
                "description": vul.get("Description", ""),
                "resolution": f"Update to {vul.get('FixedVersion', 'NA')}",
                "severity": vul.get("Severity", ""),
                "message": "",
                "cvss_strings": cvss_strings,
                "risk_score": risk_score,
                "cause_metadata": target
            })

    df = pd.DataFrame(data)
    return df
