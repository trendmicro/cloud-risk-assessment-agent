import json

# Common SQL schema for the results table
RESULTS_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS results (
    "type" TEXT,
    "id" TEXT,
    "resource_name" TEXT,
    "service_name" TEXT,
    "avdid" TEXT,
    "title" TEXT,
    "description" TEXT,
    "resolution" TEXT,
    "severity" TEXT,
    "message" TEXT,
    "cvss_strings" TEXT,
    "risk_score" REAL,
    "cause_metadata" TEXT,
    PRIMARY KEY (type, id, resource_name)
);
"""

CHAT_HISTORY_TABLE_SCHEMA = """
CREATE TABLE users (
    "id" UUID PRIMARY KEY,
    "identifier" TEXT NOT NULL UNIQUE,
    "metadata" JSONB NOT NULL,
    "createdAt" TEXT
);

CREATE TABLE IF NOT EXISTS threads (
    "id" UUID PRIMARY KEY,
    "createdAt" TEXT,
    "name" TEXT,
    "userId" UUID,
    "userIdentifier" TEXT,
    "tags" TEXT[],
    "metadata" JSONB,
    FOREIGN KEY ("userId") REFERENCES users("id") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS steps (
    "id" UUID PRIMARY KEY,
    "name" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "threadId" UUID NOT NULL,
    "parentId" UUID,
    "streaming" BOOLEAN NOT NULL,
    "waitForAnswer" BOOLEAN,
    "isError" BOOLEAN,
    "metadata" JSONB,
    "tags" TEXT[],
    "input" TEXT,
    "output" TEXT,
    "createdAt" TEXT,
    "command" TEXT,
    "start" TEXT,
    "end" TEXT,
    "generation" JSONB,
    "showInput" TEXT,
    "language" TEXT,
    "indent" INT,
    "defaultOpen" BOOLEAN,
    FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS elements (
    "id" UUID PRIMARY KEY,
    "threadId" UUID,
    "type" TEXT,
    "url" TEXT,
    "chainlitKey" TEXT,
    "name" TEXT NOT NULL,
    "display" TEXT,
    "objectKey" TEXT,
    "size" TEXT,
    "page" INT,
    "language" TEXT,
    "forId" UUID,
    "mime" TEXT,
    "props" JSONB,
    FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS feedbacks (
    "id" UUID PRIMARY KEY,
    "forId" UUID NOT NULL,
    "threadId" UUID NOT NULL,
    "value" INT NOT NULL,
    "comment" TEXT,
    FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
);
"""

# Updated data based on provided information
SAMPLE_DATA = [
    {
        "type": "KUBERNETES",
        "id": "KSV041",
        "resource_name": "admin",
        "service_name": "Default",
        "avdid": "AVD-KSV-0041",
        "title": "Manage secrets",
        "description": "Viewing secrets at the cluster-scope is akin to cluster-admin in most clusters as there are typically at least one service accounts (their token stored in a secret) bound to cluster-admin directly or a role/clusterrole that gives similar permissions.",
        "resolution": "Manage secrets are not allowed. Remove resource 'secrets' from cluster role",
        "severity": "CRITICAL",
        "message": "ClusterRole 'admin' shouldn't have access to manage resource 'secrets'",
        "cvss_strings": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
        "risk_score": 10.0,
        "cause_metadata": json.dumps({"root_cause": "excessive_permissions", "affected_line": "Line 39: XXXXXX"})
    },
    {
        "type": "KUBERNETES",
        "id": "KSV044",
        "resource_name": "argocd-application-controller",
        "service_name": "Default",
        "avdid": "AVD-KSV-0044",
        "title": "No wildcard verb and resource roles",
        "description": "Check whether role permits wildcard verb on wildcard resource",
        "resolution": "Create a role which does not permit wildcard verb on wildcard resource",
        "severity": "CRITICAL",
        "message": "Role permits wildcard verb on wildcard resource",
        "cvss_strings": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
        "risk_score": 10.0,
        "cause_metadata": json.dumps({"root_cause": "wildcard_permissions", "affected_line": "Line 39: XXXXXX"})
    },
    {
        "type": "KUBERNETES",
        "id": "KSV046",
        "resource_name": "argocd-application-controller",
        "service_name": "Default",
        "avdid": "AVD-KSV-0046",
        "title": "Manage all resources",
        "description": "Full control of the cluster resources, and therefore also root on all nodes where workloads can run and has access to all pods, secrets, and data.",
        "resolution": "Remove '*' from 'rules.resources'. Provide specific list of resources to be managed by cluster role",
        "severity": "CRITICAL",
        "message": "ClusterRole 'argocd-application-controller' shouldn't manage all resources",
        "cvss_strings": "CVSS:3.1/AV:N/AC:L/PR:H/UI:N/S:C/C:H/I:H/A:H",
        "risk_score": 9.1,
        "cause_metadata": json.dumps({"root_cause": "excessive_permissions", "affected_line": "Line 36: XXXXXX"})
    },
    {
        "type": "KUBERNETES",
        "id": "KSV047",
        "resource_name": "cloudwatch-agent-role",
        "service_name": "Default",
        "avdid": "AVD-KSV-0047",
        "title": "Do not allow privilege escalation from node proxy",
        "description": "Check whether role permits privilege escalation from node proxy",
        "resolution": "Create a role which does not permit privilege escalation from node proxy",
        "severity": "HIGH",
        "message": "Role permits privilege escalation from node proxy",
        "cvss_strings": "CVSS:3.1/AV:N/AC:L/PR:H/UI:N/S:U/C:N/I:N/A:N",
        "risk_score": 0.0,
        "cause_metadata": json.dumps({"root_cause": "privilege_escalation", "affected_line": "Line 31: XXXXXX"})
    },
    {
        "type": "AWS",
        "id": "AVD-AWS-0006",
        "resource_name": "arn:aws:athena:us-west-2:749345143977:workgroup/primary",
        "service_name": "Athena",
        "avdid": "AVD-AWS-0006",
        "title": "Athena databases and workgroup configurations are created unencrypted at rest by default, they should be encrypted",
        "description": "Athena databases and workspace result sets should be encrypted at rests. These databases and query sets are generally derived from data in S3 buckets and should have the same level of at rest protection.",
        "resolution": "Enable encryption at rest for Athena databases and workgroup configurations",
        "severity": "HIGH",
        "message": "Database does not have encryption configured.",
        "cvss_strings": "CVSS:3.1/AV:L/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "risk_score": 8.4,
        "cause_metadata": json.dumps({"root_cause": "missing_encryption", "affected_line": "Line 58: XXXXXX"})
    },
    {
        "type": "AWS",
        "id": "AVD-AWS-0007",
        "resource_name": "arn:aws:athena:us-west-2:749345143977:workgroup/primary",
        "service_name": "Athena",
        "avdid": "AVD-AWS-0007",
        "title": "Athena workgroups should enforce configuration to prevent client disabling encryption",
        "description": "Athena workgroup configuration should be enforced to prevent client side changes to disable encryption settings.",
        "resolution": "Enforce the configuration to prevent client overrides",
        "severity": "HIGH",
        "message": "The workgroup configuration is not enforced.",
        "cvss_strings": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "risk_score": 9.8,
        "cause_metadata": json.dumps({"root_cause": "configuration_not_enforced", "affected_line": "Line 49: XXXXXX"})
    },
    {
        "type": "CODE",
        "id": "CVE-2024-47874",
        "resource_name": "starlette",
        "service_name": "Default",
        "avdid": None,
        "title": "starlette: Starlette Denial of service (DoS) via multipart/form-data",
        "description": "A vulnerability in Starlette package that can lead to denial of service attacks through multipart/form-data manipulation.",
        "resolution": "Update package starlette from 0.36.3 to 0.40.0",
        "severity": "HIGH",
        "message": "Vulnerable starlette package version detected",
        "cvss_strings": None,
        "risk_score": 7.5,
        "cause_metadata": json.dumps({"root_cause": "outdated_package", "affected_line": "Line 28: XXXXXX"})
    },
    {
        "type": "CONTAINER",
        "id": "CVE-2023-24538",
        "resource_name": "golang",
        "service_name": "Default",
        "avdid": None,
        "title": "golang: html/template: backticks not treated as string delimiters",
        "description": "A vulnerability in the html/template package where backticks are not properly treated as string delimiters.",
        "resolution": "Update package stdlib from v1.17.13 to 1.20.3",
        "severity": "CRITICAL",
        "message": "Vulnerable golang package detected",
        "cvss_strings": None,
        "risk_score": 9.8,
        "cause_metadata": json.dumps({"root_cause": "outdated_package", "affected_line": "Line 19: XXXXXX"})
    }
]

# Default database path
DEFAULT_DB_PATH = "/sqlite/chainlit.db"