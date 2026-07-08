#!/usr/bin/env bash
set -euo pipefail

echo "RUNNING RUFF"
if ! ruff check src; then
    echo "Ruff found errors. Stopping the build and deploy process."
    exit 1
fi

echo "Starting build and deploy process..."
echo

echo "RUNNING BUILD"
if ! sam build; then
    echo "Build failed at: $(date)"
    exit 1
fi

echo "RUNNING DEPLOY"
if ! sam deploy; then
    echo "Deploy failed at: $(date)"
    exit 1
fi

echo "Deploy completed successfully at: $(date)"
