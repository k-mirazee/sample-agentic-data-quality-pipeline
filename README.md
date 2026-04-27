# sample-agentic-data-quality-pipeline

A Strands Agent deployed on Amazon Bedrock AgentCore that autonomously monitors data quality in an S3 data lake, detects anomalies (schema drift, null spikes, distribution shifts), diagnoses root causes via LLM reasoning, and triggers automated remediation — with full OpenTelemetry-based observability tracing every decision, tool call, and token cost.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        S3 DATA LAKE                             │
│  raw/ ──▶ staging/ ──▶ curated/     quarantine/                 │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│          🤖 DATA QUALITY AGENT (Strands + AgentCore)            │
│                                                                 │
│  Tools: scan_quality │ check_schema │ diagnose_issue            │
│         quarantine_records │ apply_transform │ notify_owner     │
│         log_decision                                            │
│                                                                 │
│  OpenTelemetry ──▶ CloudWatch / X-Ray                           │
└──────┬──────┬──────┬──────┬──────┬──────────────────────────────┘
       │      │      │      │      │
       ▼      ▼      ▼      ▼      ▼
    Athena  Glue  DynamoDB  CW    SNS
                  (4 tbls)
       │
       ▼
  Streamlit Dashboard (5 pages)
```

## Features

- **Autonomous scanning** — Athena SQL checks for completeness, freshness, and distribution anomalies
- **Schema drift detection** — Compares Glue Catalog against stored baselines, detects renames via string similarity
- **LLM-powered diagnosis** — Separate Bedrock call per violation for focused root cause analysis
- **Self-healing remediation** — Quarantine bad records, apply transforms (fill nulls, clip outliers, deduplicate)
- **Full observability** — OpenTelemetry traces, CloudWatch metrics/alarms/dashboard, DynamoDB audit trail
- **Real data** — NYC TLC yellow taxi trip data (2.96M rows/month)
- **Chaos injector** — Controlled quality issue injection for deterministic demos

## Prerequisites

- AWS account with Bedrock model access (Claude Haiku 4.5)
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- AWS CDK v2
- `agentcore` CLI (for AgentCore deployment)

## Quick Start

### 1. Clone and install

```bash
git clone <repo-url>
cd sample-agentic-data-quality-pipeline
uv sync --all-extras
```

### 2. Deploy infrastructure

```bash
cd cdk
uv run --extra cdk -- npx cdk bootstrap aws://<ACCOUNT_ID>/us-east-1
uv run --extra cdk -- npx cdk deploy --app "python3 app.py" --all --require-approval never
```

### 3. Download and upload data

```bash
uv run python data/download_data.py --start-year 2024 --start-month 1 --num-months 3
uv run python data/upload_to_s3.py --source data/raw --bucket dq-agent-demo-<ACCOUNT_ID> --prefix raw/yellow_taxi
```

Add Glue partitions for each month uploaded (see [Demo Guide](docs/DEMO_GUIDE.md)).

### 4. Run the agent locally

```bash
uv run python -m agent.agent --table raw_yellow_taxi --partition "year=2024/month=01"
```

### 5. Deploy to AgentCore

```bash
cd agent
agentcore configure --entrypoint agent.py --name dq_agent --requirements-file requirements.txt --region us-east-1 --protocol HTTP --non-interactive
bash ac_deploy.sh
agentcore invoke '{"prompt": "Scan raw_yellow_taxi partition year=2024/month=01"}'
```

### 6. Launch dashboard

```bash
PYTHONPATH=. uv run streamlit run dashboard/app.py
```

## Project Structure

```
├── agent/                    # Strands Agent
│   ├── agent.py              # Main agent + AgentCore entrypoint
│   ├── system_prompt.md      # Agent behavior definition
│   ├── tools/                # 7 custom tools
│   ├── utils/                # Athena, DynamoDB, CloudWatch helpers
│   ├── config/               # Thresholds, schema baselines
│   └── ac_deploy.sh          # AgentCore deploy script
├── cdk/                      # Infrastructure as Code
│   └── stacks/               # DataLake, Observability, Notification
├── dashboard/                # Streamlit UI (5 pages)
├── data/                     # Download, chaos injector, upload scripts
├── tests/                    # Unit and integration tests
└── docs/                     # Architecture, demo guide
```

## AWS Services Used

| Service | Purpose |
|---------|---------|
| Amazon Bedrock AgentCore | Agent runtime hosting |
| Amazon Bedrock (Claude Haiku 4.5) | LLM reasoning for diagnosis |
| Amazon S3 | Data lake (raw/staging/curated/quarantine) |
| Amazon Athena | SQL-based quality checks and transforms |
| AWS Glue Data Catalog | Schema metadata registry |
| Amazon DynamoDB | Agent state, decisions, baselines, history |
| Amazon CloudWatch | Metrics, alarms, dashboard |
| Amazon SNS | Alert notifications |
| OpenTelemetry | Agent observability traces |

## Cost Estimate

~$2.50–$3.00 per demo run (primarily Athena scan costs). See [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) for details.

## License

This project is licensed under the MIT-0 License. See [LICENSE](LICENSE).
