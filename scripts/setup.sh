#!/usr/bin/env bash
# Simple setup helper for the Cloud Risk Assessment Agent
set -e

# Check prerequisites
for cmd in docker "docker compose" make; do
    if ! command -v ${cmd%% *} >/dev/null 2>&1; then
        echo "Error: $cmd is not installed." >&2
        exit 1
    fi
done

# Create .env from example if missing
if [ ! -f .env ]; then
    echo "Creating .env from env.example. Please update it with your API endpoint, key and model."
    cp env.example .env
fi

echo "Building and starting containers..."
make run

echo "\nService started on http://localhost"
echo "Use 'make gen_config' to configure scans and 'make scan' to run them."
