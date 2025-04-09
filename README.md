# Trend Cybertron - Cloud Risk Assessment Agent

Welcome to the Cloud Risk Assessment Agent repository. This document provides instructions on how to set up and run the Cloud Risk Assessment Agent service on macOS or Linux-based operating systems.

## Introduction

Welcome to the **Trend Cybertron - Cloud Risk Assessment Agent** project, an open-source initiative leveraging the Trend Micro Cybertron AI model in the NIM catalog. This project is managed by the community, and while contributors may offer support, availability can vary. Please provide detailed information about your environment and steps to reproduce your issue when opening a GitHub issue.

For bug reports, please [open an issue](https://github.com/trendmicro/cloud-risk-assessment-agent/issues/new/choose).

Contributions are welcome! Learn how you can contribute by visiting our [contribution guidelines](https://github.com/trendmicro/cloud-risk-assessment-agent?tab=readme-ov-file#contributing).

> **Note:** Official support from Trend Micro is not available through this project. Contributors may include Trend Micro employees, but they do not provide official support.


## Prerequisites

Before you begin, ensure you have the following installed on your system:
- **Git**: For cloning the repository.
- **Make**: For running make commands.
- **Docker**: Version 2 or later.

Set up your inference endpoint using [Huggingface](https://huggingface.co/trendmicro-ailab/Llama-Primus-Merged):
- **Recommended Inference Endpoint**: [SGLang](https://docs.sglang.ai/)
- **Recommended GPU**: At least L40s
- **Context Length**: 128k tokens
* [SGLang Setup Guide](https://docs.sglang.ai/backend/server_arguments.html#model-and-tokenizer) (use --contex-length parameter)

```bash
python -m sglang.launch_server --model-path trendmicro-ailab/Llama-Primus-Merged --port 8000 --host 0.0.0.0 --context-length 131072 --max-prefill-tokens 131072 --max-total-tokens 131072
```

## Installation

Follow these steps to get your development environment running:

### 1. Clone the Repository

Clone the code from the Git repository:

```bash
git clone https://github.com/trendmicro/cloud-risk-assessment-agent
```

### 2. Prepare the Environment File

Create a new `.env` file in the root directory of the repository and copy the following contents into it:
Note: remember replace your OpenAI compatible API base, model and key.

```plaintext
OPENAI_API_BASE="http://localhost:8000/"
OPENAI_API_KEY="YOUR OPENAI API KEY"
OPENAI_MODEL="Llama-Primus-Merged"
SERVICE_HOST=http://localhost
# If you want to scan AWS account, please provide the access key / token in environment file here.
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_SESSION_TOKEN=
AWS_SECURITY_TOKEN=
```

### 3. Build & Start Server

To start the server:

```bash
# Enter the code folder
make run
```

### 4. Scan Your Code / Container / Kubernetes / AWS

Use this command to configure agent scan settings. You can specify which resources should be scanned.
Find more detailed instructions [here](docs/Scan.md).

```bash
make gen_config
```

After configuring the scan settings, run the scan with:

```bash
make scan
```


### 5. Access the Service

After the scan results are available, access the service at [http://localhost](http://localhost).



## Commands Overview

| Command | CLI | Purpose |
|---------|-----|---------|
| Run service | `make run` | Start the service initially |
| Restart service | `make stop && make run` | Restart after an error |
| Clean server | `make down` | Purge chat history |
| Configure scan | `make gen_config` | Configure the scan targets |
| Run scan | `make scan` | Scan the configured resources |
| Import sample data | `make sample` | Import default sample results for testing |
| Refresh and clear database | `make refresh` | Remove data but keep schema in database |

## Agent Usage Guide

For more detailed examples and use cases, see our [Usage Guide](chainlit.md).

## License

This project is licensed under the [Trend Micro Community License](LICENSE).


## Contributing

We :heart: contributions from our community. To ensure a safe and productive environment, please follow these guidelines:

### Contributor Guidelines

#### General Guidelines
- **Familiarize Yourself**: Before contributing, please read through the documentation to familiarize yourself with the project.
- **Open an Issue**: Discuss potential changes via issue discussions before starting any significant work. This helps prevent duplication of efforts and ensures that your contributions align with the project goals.
- **Pull Requests**: Submit pull requests with clear descriptions of the changes and benefits. Ensure each pull request only covers one specific issue to simplify the review process.

#### Code Contributions
- **Code Quality**: Maintain high code quality and adhere to the project's coding conventions (use language-specific linters).
- **Testing**: Add tests for new features and ensure that all tests pass.
- **Documentation**: Update documentation to reflect changes or additions to the project.

#### Security
- **No Secrets or PII**: Do not include API keys, secrets, passwords, or any personally identifiable information in your contributions.
- **Clean History**: Ensure your pull request's commit history is clean and free from any accidental inclusion of sensitive data.
