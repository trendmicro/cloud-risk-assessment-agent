# Developer Guide

This guide explains how to run the application directly from the command line instead of building a Docker container each time, which can speed up your development workflow.

## Running the CLI Application

### Step 1: Start the PostgreSQL Database Server

First, start the Docker PostgreSQL server that will store chat history:

```bash
docker compose up -d
```

### Step 2: Set Up Environment Variables

Export the necessary environment variables, overriding those in the .env file:

```bash
export SERVICE_HOST=http://localhost:8000
export TIKTOKEN_CACHE_DIR=./cache
export PYTHONPATH=`pwd`
export CHAINLIT_AUTH_SECRET=`python scripts/chainlit_secret`
```

### Step 3: Set Up Python Environment

Install the required Python packages:

```bash
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 4: Launch the Application

Start the Chainlit application:

```bash
chainlit run src/core/app.py
```

The latest version of Chainlit supports the **MCP** tool. Our implementation uses
it to enrich user queries before the reasoning step. See [MCP Integration](MCP_Comparison.md)
for more details.

The application should now be running at http://localhost:8000
