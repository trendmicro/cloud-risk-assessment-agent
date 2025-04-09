# Scan Usage Documentation

This guide explains how to use the security scan agent to analyze four types of resources: code repositories, container images, AWS infrastructure, and Kubernetes configurations. The agent can scan one resource of each type at a time.

**Note:** Resources and credentials are volume-mounted into the agent's repository, except for AWS credentials which are passed via the environment file.


## Configuration Setup

### Environment File
Create and configure the `.env` file in the code directory:

```bash
# Create or edit the .env file
vi .env
```

Add the following content:

```plaintext
OPENAI_API_BASE=https://dev.cybertron.ailab.trendops.co
OPENAI_API_KEY={API Key from AILAB}
OPENAI_MODEL=Primus-Christmas-128k
SERVICE_HOST=http://localhost

# AWS credentials for scanning AWS resources
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_SESSION_TOKEN=
AWS_SECURITY_TOKEN=
```

## Resource Setup for Scanning

Locate the source code, container under specific folder for scan. More detail of code preparation please see [Trivy code scan guide](https://trivy.dev/v0.47/docs/coverage/language/)

### AWS Permissions

Ensure AWS permissions are properly configured:
- Use the ReadOnlyAccess policy for minimal required access
- For more information, refer to:
  - [AWS Access Key Documentation](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html)
  - [Creating Read-Only Access](https://medium.com/ankercloud-engineering/how-to-grant-read-only-access-to-your-aws-account-8dd582f2544c)


### Docker Image Scanning

Prepare a Docker image for scanning:

```bash
# Create the directory for Docker image files
mkdir -p /tmp/tmcybertron/image_file

# Pull an image (using httpd as an example)
docker pull httpd

# Save the image as a tar file
docker save httpd -o /tmp/tmcybertron/image_file/httpd.tar
```

Replace `httpd` with your own container image as needed.

### Kubernetes Configuration

Copy your Kubernetes configuration file:

```bash
# Create the directory for Kubernetes config
mkdir -p /tmp/tmcybertron/.kube

# Copy your kubeconfig file
cp ~/.kube/config /tmp/tmcybertron/.kube/config
```

For more information on Kubernetes configuration:
- [Kubernetes Config Documentation](https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/)
- [AWS EKS Config Guide](https://docs.aws.amazon.com/eks/latest/userguide/create-kubeconfig.html)

### Code Repository Setup

Prepare a code repository for scanning:

```bash
# Create the directory for code repositories
mkdir -p /tmp/tmcybertron/repo

# Clone a repository (example)
git clone https://github.com/mem0ai/mem0.git /tmp/tmcybertron/repo/mem0
```

Replace the example repository with your own code repository.

## Running Scans

### Generate Scan Configuration

Generate the scan configuration interactively:

```bash
make gen_config
```

This creates a configuration file at `/tmp/tmcybertron/agent.yaml` which you can manually edit if needed.

### Execute Scan

Run the scan using your configuration:

```bash
make scan
```

**Results Location:**
- Raw scan results: `/tmp/tmcybertron/results`
- Processed results: Stored in the SQLite database at `sqlite/chainlit.db`


## Accessing Results

### Start the Agent

Ensure the agent is running:

```bash
make run
```

### View and Analyze Results

1. Access the web interface at [http://localhost](http://localhost)
2. Use the chat interface to:
   - Query scan results
   - Generate security reports
   - Get insights about detected vulnerabilities
