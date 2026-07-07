# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Strands Agent deployed on Amazon Bedrock AgentCore that responds to data quality violations detected by AWS Glue Data Quality. Glue DQ handles detection (DQDL ruleset), the agent handles response (diagnosis, remediation, audit). Event-driven: EventBridge routes Glue DQ failures → Lambda bridge → AgentCore invocation.

## Commands

```bash
# Install dependencies
uv sync --all-extras

# Run agent locally with a mock Glue DQ event (omit --prompt for a built-in mock event)
PYTHONPATH=. uv run python agent/agent.py --prompt '{"evaluation_id":"test","database":"dq_agent_demo","table":"raw_yellow_taxi","partition":"year=2025/month=09","overall_state":"FAILED","rule_results":[{"rule":"Completeness \"passenger_count\" >= 0.70","state":"FAILED","evaluated_metrics":{"Column.passenger_count.Completeness":0.64}}]}'

# Deploy agent to AgentCore (requires the bedrock-agentcore-starter-toolkit `agentcore` CLI, not the Node one)
cd agent && bash ac_deploy.sh

# Run dashboard backend (FastAPI)
PYTHONPATH=. uv run uvicorn dashboard.api:app --reload --port 8000

# Run dashboard frontend (React/Vite)
cd dashboard/ui && npm run dev

# Deploy CDK infrastructure (agentcore_agent_id is the AgentCore runtime ID from ac_deploy.sh;
# the GlueDq stack fails synth without it)
cd cdk && uv run --extra cdk -- npx cdk deploy --all -c agentcore_agent_id=<name-XXXXXXXXXX>

# Lint
uv run ruff check .
uv run ruff format --check .

# Type check
uv run mypy agent/

# Tests
uv run pytest
uv run pytest tests/unit/
uv run pytest tests/integration/

# Data management
uv run python data/download_data.py --start-year 2025 --start-month 7 --num-months 3
uv run python data/upload_to_s3.py --source data/raw --bucket <BUCKET> --prefix raw/yellow_taxi
uv run python data/chaos_injector.py --input data/raw/<file>.parquet --output data/chaos/<file>.parquet --config data/chaos_config.yaml
```

## Architecture

Event-driven two-tier: **Glue DQ** (detection) → **EventBridge** → **Lambda bridge** → **Agent** (response).

### Agent (`agent/`)
- `agent.py` — Strands Agent with AgentCore runtime entrypoint. Dual-mode: runs via `BedrockAgentCoreApp` in the cloud or as a local CLI.
- `system_prompt.md` — Defines the RECEIVE→DIAGNOSE→ACT→LOG workflow. Agent does NOT run detection queries; it receives pre-computed Glue DQ results.
- `tools/` — 5 tools decorated with `@tool` from `strands`:
  - `parse_dq_event` — Normalizes Glue DQ event payload into structured violations
  - `diagnose_issue` — LLM-powered root cause analysis (separate Bedrock call)
  - `quarantine_records` — Athena UNLOAD to quarantine zone
  - `notify_owner` — SNS alerts with severity
  - `log_decision` — DynamoDB audit trail
- `utils/` — Shared AWS clients (`athena_client`, `dynamodb_client`, `metrics`). Tools import these with a try/except pattern to handle both package imports (`from agent.utils...`) and flat container layout (`from utils...`).

### CDK Infrastructure (`cdk/`)
- `glue_dq_ruleset.dqdl` — DQDL rules: completeness, freshness, distribution bounds, schema existence
- `lambda/dq_event_bridge/` — Lambda that receives EventBridge Glue DQ events and invokes AgentCore
- `stacks/data_lake_stack.py` — S3, Glue catalog, Athena workgroup
- `stacks/glue_dq_stack.py` — Glue DQ ruleset, EventBridge rule, Lambda bridge
- `stacks/observability_stack.py` — DynamoDB tables, CloudWatch alarms/dashboard
- `stacks/notification_stack.py` — SNS topic

### Dashboard
- `dashboard/api.py` — FastAPI backend. `/api/scan` triggers a Glue DQ evaluation run. `/api/simulate-event` sends a mock failure directly to AgentCore (fast demo mode).
- `dashboard/ui/` — React + Cloudscape Design System (Vite/TypeScript). Three components: `ControlPanel`, `QualityDashboard`, `AgentActivity`.
- `dashboard/utils/` — DynamoDB and CloudWatch query helpers.

### Data (`data/`)
- `chaos_injector.py` — Injects quality issues upstream of Glue DQ detection. Config-driven via `chaos_config.yaml`.
- `download_data.py` / `upload_to_s3.py` — NYC TLC taxi data management.

## Key Patterns

- **PYTHONPATH=.** is required when running agent or dashboard locally.
- Agent tools use `@tool` decorator from `strands` — the docstring becomes the tool schema.
- DynamoDB tables use composite keys (`PK`, `SK`) across all four tables.
- Environment variables: `GLUE_DATABASE`, `ATHENA_WORKGROUP`, `S3_BUCKET`, `MODEL_ID`, `AWS_REGION`, `OTEL_ENABLED`.
- The Glue DQ event payload format is documented in `parse_dq_event.py` and `cdk/lambda/dq_event_bridge/handler.py`.

## Tooling

- **Package manager**: uv (pyproject.toml)
- **Linter/formatter**: ruff (line-length=120, Python 3.11+)
- **Type checker**: mypy
- **Testing**: pytest with moto for AWS mocking
- **Frontend**: Vite + TypeScript + React 18 + Cloudscape Design
- **Infrastructure**: AWS CDK v2 (Python)
