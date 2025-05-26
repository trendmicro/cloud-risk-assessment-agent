import yaml
import json
import os
from importlib import resources
from prettytable import PrettyTable
from src.scan.util import (
    run_command_and_read_output,
    NoOutputError,
    filter_severity,
    count_gpt_tokens,
    run_command_bg,
    JSONParseError,
)
import pandas as pd
from tqdm import tqdm
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from src.scan.util import sanitize_input, count_gpt_tokens
from langchain.prompts import PromptTemplate
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
import logging
import uvicorn
from src.scan.cvss_score import generate_cvss, safe_cvss_score

logger = logging.getLogger('uvicorn.error')
ISSUE_SCORING_PROMPT_PATH = "issue_scoring_prompt.txt"
K8S_TEXT_REPORT_GENERATION_PROMPT_PATH = "k8s_text_report_generation_prompt.txt"
K8S_MARKDOWN_REPORT_GENERATION_PROMPT_PATH = "k8s_markdown_report_generation_prompt.txt"
K8S_MARKDOWN_REPORT_GENERATION_PROMPT_PATH2 = "k8s_markdown_report_generation_prompt_full.txt"
K8S_REPORT_PATH="/tmp/tmcybertron/results/kubernetes/default.json"

def count_key_value_in_list_compact(dicts, key, value):
    return sum(1 for d in dicts if d.get(key) == value)

def read_k8s_full_report():
    with open(K8S_REPORT_PATH, "r") as file:
        try:
            return json.load(file)
        except json.JSONDecodeError:
            raise JSONParseError(K8S_REPORT_PATH)

def k8s_resource_misconfigure(report:dict, resource:str):
    cluster_name = report["ClusterName"]
    output = f"Cluster_Name: {cluster_name}\n"
    for item in report["Resources"]:
        kind = item["Kind"]
        name = item["Name"]
        full_name = f"{kind}/{name}"
        if full_name.find(resource) != -1:
            detail = {}
            detail["Name"] = full_name
            detail["Misconfigurations"] = []
            for res in item["Results"]:
                if "Misconfigurations" in res:
                    for mis in res["Misconfigurations"]:
                        misc = {"ID": mis["AVDID"], "Title": mis["Title"], "Description": mis["Description"], "Resolution": mis["Resolution"], "Severity": mis["Severity"]}
                        if "Code" in mis["CauseMetadata"] and "Lines" in mis["CauseMetadata"]["Code"] and type(mis["CauseMetadata"]["Code"]["Lines"]) == list:
                            code = ""
                            for line in mis["CauseMetadata"]["Code"]["Lines"]:
                                code = code + line["Content"]
                        misc["Code"] = code
                        detail["Misconfigurations"].append(misc)
            output = output + yaml.dump(detail)
    #print(output)
    return output

def k8s_all_resource_misconfigure(report:dict):
    cluster_name = report["ClusterName"]
    output = f"Cluster_Name: {cluster_name}\n"
    miscs = {}
    for item in report["Resources"]:
        kind = item["Kind"]
        name = item["Name"]
        full_name = f"{kind}/{name}"
        for res in item["Results"]:
            if "Misconfigurations" in res:
                for mis in res["Misconfigurations"]:
                    if mis["AVDID"] not in miscs:
                        #add AVDID as key
                        miscs[mis["AVDID"]]={"ID": mis["AVDID"], "Title": mis["Title"], "Description": mis["Description"], "Resolution": mis["Resolution"], "Severity": mis["Severity"], "Resources": []}
                    miscs[mis["AVDID"]]["Resources"].append(full_name)

    for k,v in miscs.items():
        v["Resources"] = len(list(dict.fromkeys(v["Resources"])))
        output = output + "\n\n" + yaml.dump(v)
    return output

def k8s_compliance_all_summary(report:dict):

    summary = []
    for item in report["status"]["detailReport"]["results"]:
        sum_res = {"id": item["id"], "severity": item["severity"], "name": item["name"], "description": item["description"]}
        remediation = ""
        hit = False
        targets = []
        for res in item["checks"]:
            if res["success"] == False:
                targets.append(res["target"])
                remediation = res["remediation"]
                hit = True
        if hit == True:
            sum_res["remediation"] = res["remediation"]
            sum_res["fails"] = len(targets)
            if len(targets) == 0:
                sum_res["result"] = "PASS"
            else:
                sum_res["result"] = "FAIL"
            summary.append(sum_res)

    return yaml.dump(summary)

def get_compliance_report(report: dict):
    compliance = compliance_report(report)
    #print(yaml.dump(compliance))
    table_str = compliance_table(compliance)
    totals = compliance["summary"]["total"]
    passes = compliance["summary"]["pass"]
    fails = compliance["summary"]["fail"]
    nas = compliance["summary"]["not_available"]
    cluster = report["ClusterName"]
    output = f"cluster: {cluster}\ntotal: {totals}\npass: {passes}\nfail: {fails}\nnot available: {nas}\n{table_str}"
    return output

def get_kubernetes_summary():
    report = read_k8s_full_report()
    return k8s_all_resource_misconfigure(report)

def get_kubernetes_resource(name: dict)-> str:
    report = read_k8s_full_report()
    return k8s_resource_misconfigure(report, name)
""
def scan_kubernetes(report: str = K8S_REPORT_PATH, config_path:str = "./kube/config", bg:bool = False):
    ###chainlit###
    if os.path.exists(report):
        return True, f"Detect existing report under {report}"

    if not os.path.exists(config_path):
        print(f"Error: The folder '{config_path}' does not exist.")
        return False
  
    # Construct the trivy command for scanning the kubernetes
    command = [
        "trivy",
        "k8s",
        "--report",
        "all",
        "--db-repository",
        "public.ecr.aws/aquasecurity/trivy-db",
        "--disable-node-collector",
        "--timeout",
        "2h",
        "--skip-images",
        "--kubeconfig" if config_path else "",
        config_path,
        "--qps",
        "40",
        "--format",
        "json",
        "--output",
        report  # Specify the output file for the scan results
    ]

    # Run the command and return the parsed output
    if bg:
        result = run_command_bg(command)
    else:
        result= run_command_and_read_output(command=command, output_file=report)
    return result


###CHAINLIT###
# Group the k8s scan results with the option to include/exclude metadata
def process_k8s_scan(k8s_report_data, exclude_metadata=True, grouping=True):
    # Extract rows
    rows = []
    for resource in k8s_report_data["Resources"]:
        kind = resource["Kind"]
        name = resource["Name"]
        for result in resource.get("Results", []):
            if result["MisconfSummary"]["Failures"] > 0:
                for misconf in result.get("Misconfigurations", []):
                    cause_metadata = misconf.get("CauseMetadata", {})
                    
                    # Conditionally remove 'Code' key from CauseMetadata
                    if exclude_metadata:
                        cause_metadata = {}
                    
                    rows.append({
                        "type": "KUBERNETES",
                        "id": misconf["ID"],
                        "resource_name": name,
                        "service_name": "general",
                        "avdid": misconf["AVDID"],
                        "title": misconf["Title"],
                        "description": misconf["Description"],
                        "resolution": misconf["Resolution"],
                        "severity": misconf["Severity"],
                        "message": misconf["Message"],
                        "cause_metadata": json.dumps(cause_metadata)
                    })

    # Create a pandas DataFrame
    df = pd.DataFrame(rows)
    if not grouping:
        return df

    # Group by specified columns and aggregate as lists
    grouped_df = (
        df.groupby(
            ["kind", "type", "id", "avdid", "title", "description", "resolution", "severity"],
            as_index=False
        )
        .agg(Details=("resource_name", lambda x: [
            {"resource_name": name, "message": msg, "cause_metadata": cm} 
            for name, msg, cm in zip(x, df.loc[x.index, "message"], df.loc[x.index, "cause_metadata"])
        ]))
    )

    return grouped_df

async def gen_k8s_score(k8s_df):
    sub_k8s_df = k8s_df[["avdid", "title", "description", "resolution", "severity", "message"]]
    sub_k8s_df = sub_k8s_df.drop_duplicates(subset=["avdid"])

    # Generate CVSS strings asynchronously
    cvss_strings = []
    for _, row in sub_k8s_df.iterrows():
        cvss_strings.append(await generate_cvss(row))
    sub_k8s_df["cvss_strings"] = cvss_strings

    # Calculate CVSS scores
    sub_k8s_df["risk_score"] = sub_k8s_df["cvss_strings"].apply(safe_cvss_score)
    return sub_k8s_df

# Combine the k8s scan results with the CVSS scores
async def gen_kubernetes_db_content(k8s_report, cols):
    k8s_df = process_k8s_scan(k8s_report, exclude_metadata=False, grouping=False)
    res = await gen_k8s_score(k8s_df)
    k8s_df = k8s_df.merge(res[["avdid", "cvss_strings", "risk_score"]], on="avdid", how="left")
    k8s_df = k8s_df[cols]
    return k8s_df
