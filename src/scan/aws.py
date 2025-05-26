import subprocess
import os
import json
import yaml
from typing import Optional, List
import pandas as pd
from src.scan.cvss_score import generate_cvss, safe_cvss_score

from src.scan.util import run_command_and_read_output, run_command_bg, JSONParseError
from prettytable import PrettyTable
AWS_REPORT_PATH = "/tmp/trivy_aws_full.json"

def scan_aws(
    region: str = "us-west-2",  # Path to scan; defaults to the current directory
    report: str = "/tmp/trivy_aws_result.json",  # Output file for scan results
    bg: bool = False
):
    ###chainlit###
    # Construct the trivy command for scanning the filesystem
    command = [
        "trivy", "aws",
        "--region", region,
        "--format", "json",  # Set the output format to JSON
        "--output", report  # Specify the output file for the scan results
    ]
    if bg:
        result = run_command_bg(command)
    else:
        # Run the command and return the parsed output
        result = run_command_and_read_output(command=command, output_file=report)
    return result

def read_aws_full_report():
    with open(AWS_REPORT_PATH, "r") as file:
        try:
            return json.load(file)
        except json.JSONDecodeError:
            raise JSONParseError(AWS_REPORT_PATH)

def aws_short_yaml(report:dict):
    output = ""
    miscs = {}
    for res in report["Results"]:
        if "Misconfigurations" in res:
            for mis in res["Misconfigurations"]:
                if mis["AVDID"] not in miscs:
                    #add AVDID as key
                    miscs[mis["AVDID"]]={"ID": mis["AVDID"], "Title": mis["Title"], "Description": mis["Description"], "Resolution": mis["Resolution"], "Severity": mis["Severity"], "Resources": []}
                if "Resource" in mis["CauseMetadata"]:
                    miscs[mis["AVDID"]]["Resources"].append(mis["CauseMetadata"]["Resource"])
                else:
                    miscs[mis["AVDID"]]["Resources"].append("")

    for k,v in miscs.items():
        v["Resources"] = len(list(dict.fromkeys(v["Resources"])))
        output = output + "\n\n" + yaml.dump(v)
    return output

def aws_short_table(report:dict):
    table = PrettyTable()
    table.field_names = ["ID","Title", "Severity", "Resolution", "Resources"]
    output = ""
    miscs = {}
    for res in report["Results"]:
        if "Misconfigurations" in res:
            for mis in res["Misconfigurations"]:
                if mis["AVDID"] not in miscs:
                    #add AVDID as key
                    miscs[mis["AVDID"]]={"ID": mis["AVDID"], "Title": mis["Title"], "Description": mis["Description"], "Resolution": mis["Resolution"], "Severity": mis["Severity"], "Resources": []}
                if "Resource" in mis["CauseMetadata"]:
                    miscs[mis["AVDID"]]["Resources"].append(mis["CauseMetadata"]["Resource"])
                else:
                    miscs[mis["AVDID"]]["Resources"].append("")

    for k,v in miscs.items():
        v["Resources"] = len(list(dict.fromkeys(v["Resources"])))
        output = output + "\n\n" + yaml.dump(v)
        table.add_row([v["ID"], v["Title"], v["Severity"], v["Resolution"], v["Resources"]])

    return table.get_string()

# Return dataframe from report
def process_aws_scan(report: dict):
    data = []
    for result in report["Results"]:
        misconfigurations = result.get("Misconfigurations", [])
        for misconfig in misconfigurations:
            cause_metadata = misconfig.get("CauseMetadata", {})
            resource_name = cause_metadata.get("Resource") or "{}_{}".format(
                cause_metadata.get("Provider", ""),
                cause_metadata.get("Service", ""),
            )
            service_name = cause_metadata.get("Service", "")
            data.append({
                "type": "AWS",
                "id": misconfig.get("ID", ""),
                "resource_name": resource_name,
                "service_name": service_name,
                "avdid": misconfig.get("AVDID", ""),
                "title": misconfig.get("Title", ""),
                "description": misconfig.get("Description", ""),
                "resolution": misconfig.get("Resolution", ""),
                "severity": misconfig.get("Severity", ""),
                "message": misconfig.get("Message", ""),
                "cause_metadata": json.dumps(cause_metadata)
            })
    df = pd.DataFrame(data)
    # Deduplicate by id and resource name
    df = df.drop_duplicates(subset=["id", "resource_name"])
    return df

async def gen_aws_score(aws_df):
    sub_aws_df = aws_df[["avdid", "title", "description", "resolution", "severity", "message"]]
    sub_aws_df = sub_aws_df.drop_duplicates(subset=["avdid"])

    # Generate CVSS strings asynchronously
    cvss_strings = []
    for _, row in sub_aws_df.iterrows():
        cvss_strings.append(await generate_cvss(row))
    sub_aws_df["cvss_strings"] = cvss_strings

    # Calculate CVSS scores
    sub_aws_df["risk_score"] = sub_aws_df["cvss_strings"].apply(safe_cvss_score)
    return sub_aws_df

# Combine the aws scan results with the CVSS scores
async def gen_aws_db_content(aws_report, cols):
    aws_df = process_aws_scan(aws_report)
    res = await gen_aws_score(aws_df)
    aws_df = aws_df.merge(res[["avdid", "cvss_strings", "risk_score"]], on="avdid", how="left")
    aws_df = aws_df[cols]
    return aws_df
