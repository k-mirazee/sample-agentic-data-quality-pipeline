#!/usr/bin/env bash
set -euo pipefail

# Deploy the Data Quality Agent to Bedrock AgentCore
# Usage: ./agent/ac_deploy.sh

cd "$(dirname "$0")"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
S3_BUCKET="dq-agent-demo-${ACCOUNT_ID}"

echo "Deploying dq_agent to AgentCore (account: ${ACCOUNT_ID})..."
REGION="${AWS_REGION:-us-east-1}"
agentcore launch \
    --agent dq_agent \
    --env "GLUE_DATABASE=dq_agent_demo" \
    --env "ATHENA_WORKGROUP=dq-agent-workgroup" \
    --env "S3_BUCKET=${S3_BUCKET}" \
    --env "SNS_TOPIC_ARN=arn:aws:sns:${REGION}:${ACCOUNT_ID}:dq-agent-alerts" \
    --env "MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0" \
    --env "OTEL_ENABLED=true" \
    --auto-update-on-conflict
