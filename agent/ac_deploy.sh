#!/usr/bin/env bash
set -euo pipefail

# Deploy the Data Quality Agent to Bedrock AgentCore
# Usage: ./agent/ac_deploy.sh

cd "$(dirname "$0")"

echo "🚀 Deploying dq_agent to AgentCore..."
agentcore launch \
    --agent dq_agent \
    --env "GLUE_DATABASE=dq_agent_demo" \
    --env "ATHENA_WORKGROUP=dq-agent-workgroup" \
    --env "S3_BUCKET=dq-agent-demo-015331669295" \
    --env "MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0" \
    --env "OTEL_ENABLED=true" \
    --auto-update-on-conflict
