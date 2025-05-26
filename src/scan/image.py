import subprocess
import os
import yaml
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

IMAGE_REPORT_PATH = "/tmp/trivy_container_full.json"
DOCKER_HOST = os.environ.get("DOCKER_HOST", "unix:///var/run/docker.sock")

def scan_image(
    image_path: str = "",  # Path to scan; defaults to the current directory
    report: str = IMAGE_REPORT_PATH,  # Output file for scan results
    scanners: List[
        str
    ] = [],  # Scanners to use; defaults to vuln, secret, and misconfig
    severity_level: str = "HIGH",  # Minimum severity level to include in the report
    bg: bool = False,  # Run the scan in the background (default: False)
):
    ###chainlit###
    if not os.path.exists(image_path):
        print(f"Error: The image '{image_path}' does not exist.")
        return False
    if not scanners:
        scanners = ["vuln", "secret", "misconfig"]

    severity = ",".join(get_severity(severity_level))
    # Construct the trivy command for scanning the filesystem
    command = [
        "trivy",
        "image",
        "--scanners",
        ",".join(scanners),  # Join the scanner types as a single string
        "--format",
        "json",              # Set the output format to JSON
        "--db-repository",
        "public.ecr.aws/aquasecurity/trivy-db",
        "--java-db-repository",
        "public.ecr.aws/aquasecurity/trivy-java-db",
        "--output",
        report,              # Specify the output file for the scan results
        "--severity",
        severity,
        "--input",
        image_path,         # Path to the image to scan
    ]# Specify the severity levels to include

    print(command)
    # Run the command and return the parsed output
    if bg:
        result = run_command_bg(command)
    else:
        result = run_command_and_read_output(command=command, output_file=report)
    return result

def read_image_full_report():
    with open(IMAGE_REPORT_PATH, "r") as file:
        try:
            return json.load(file)
        except json.JSONDecodeError:
            raise JSONParseError(IMAGE_REPORT_PATH)

def get_image_summary():
    table = PrettyTable()
    table.field_names = ["ID", "PkgName", "Installed Version", "Fixed Version", ]
    report = read_image_full_report()
    oyaml = {
            "ArtifactName": report["ArtifactName"],
            "CreatedAt": report["CreatedAt"],
            "OS_Family": report["Metadata"]["OS"]["Family"],
            "OS_Name": report["Metadata"]["OS"]["Name"]
            }
    meta = yaml.dump(oyaml)
    table = get_image_cve_table()
    output =f"{meta}\n{table}"
    return output

def get_image_cve_table():
    table = PrettyTable()
    table.field_names = ["ID", "Severity", "Package", "Cur Ver.", "Fixed Ver.", "CVSS", "title"]
    report = read_image_full_report()
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

def container_info(report: dict):
    oyaml = {
            "ArtifactName": report["ArtifactName"],
            "CreatedAt": report["CreatedAt"],
            "OS_Family": report["Metadata"]["OS"]["Family"],
            "OS_Name": report["Metadata"]["OS"]["Name"]
            }
    meta = yaml.dump(oyaml)
    output =f"{meta}\n"
    return output

def container_footprint(report: dict, output_format="table"):
    """
    Generate a report of container vulnerabilities in the specified output format.
    
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

