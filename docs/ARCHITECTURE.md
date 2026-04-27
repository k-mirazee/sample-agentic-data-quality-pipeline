# Architecture

## Overview

The Data Quality Agent follows a **scan → assess → diagnose → act → log** workflow. A Strands Agent deployed on Amazon Bedrock AgentCore orchestrates 7 custom tools to autonomously monitor, diagnose, and remediate data quality issues in an S3 data lake.

## Data Flow

```
1. INGEST     NYC TLC Parquet → raw/ zone (via download + upload scripts)
2. TRIGGER    Manual CLI, AgentCore invoke, or EventBridge schedule
3. SCAN       Agent calls scan_quality → Athena SQL queries → quality scores
4. ASSESS     Agent evaluates scores against thresholds (quality_thresholds.yaml)
5. DIAGNOSE   For violations: agent calls diagnose_issue → separate Bedrock LLM call
6. ACT        Based on diagnosis:
              - CRITICAL: quarantine_records → notify_owner
              - WARNING:  apply_transform → notify_owner
              - INFO:     log_decision only
7. LOG        Every decision recorded to DynamoDB + CloudWatch metrics
8. OBSERVE    Streamlit dashboard reads DDB + CloudWatch for visualization
```

## S3 Data Lake Zones

| Zone | Purpose | Mutability |
|------|---------|------------|
| `raw/` | Landing zone — data arrives here | Append-only (immutable) |
| `staging/` | Agent copies data after initial validation | Agent-managed |
| `curated/` | Clean, remediated data for consumption | Agent-managed |
| `quarantine/` | Bad records isolated by the agent | Agent-managed, 90-day TTL |

## Agent Tools

| Tool | Purpose | AWS Services |
|------|---------|-------------|
| `scan_quality` | Run completeness, freshness, distribution checks | Athena, DynamoDB, CloudWatch |
| `check_schema` | Compare Glue schema against stored baseline | Glue, DynamoDB |
| `diagnose_issue` | LLM reasoning for root cause analysis | Bedrock (Haiku 4.5) |
| `quarantine_records` | Isolate bad records via Athena UNLOAD | Athena, S3, DynamoDB |
| `apply_transform` | Fix data (fill nulls, clip outliers, deduplicate) | Athena, S3, DynamoDB |
| `notify_owner` | Send alerts via SNS | SNS |
| `log_decision` | Record reasoning for audit trail | DynamoDB, CloudWatch |

## DynamoDB Tables

| Table | PK | SK | Purpose |
|-------|----|----|---------|
| `quality-scan-results` | `table#partition` | timestamp | Scan history (90-day TTL) |
| `agent-decisions` | decision UUID | timestamp | Audit trail (90-day TTL) |
| `schema-baselines` | `database#table` | version | Expected schemas (no TTL) |
| `remediation-history` | `table#partition` | timestamp | Action log (90-day TTL) |

## Observability

- **OpenTelemetry** — Strands SDK traces every LLM call, tool invocation, and agent reasoning step. In AgentCore, traces flow to X-Ray via ADOT collector.
- **CloudWatch Metrics** — Custom namespace `DataQualityAgent` with quality scores, anomaly counts, remediation actions, token costs, tool durations.
- **CloudWatch Alarms** — Quality score < 50 (critical), anomalies > 10 (warning), token cost > $1 (cost). All wired to SNS.
- **CloudWatch Dashboard** — 5 widgets: overall score, anomalies, remediation, dimension breakdown, decisions.
- **Streamlit Dashboard** — 5 pages for demo-friendly visualization of DDB + CloudWatch data.

## Deployment Modes

| Mode | Command | Use Case |
|------|---------|----------|
| Local | `uv run python -m agent.agent` | Development, debugging |
| AgentCore | `agentcore invoke '{"prompt": "..."}'` | Production, demos |

The same `agent.py` code runs in both modes. AgentCore is detected via `bedrock_agentcore` import availability.

## Design Decisions

1. **Athena SQL over Glue DQDL** — Agent controls queries directly; more visible and educational
2. **Standard Parquet over Iceberg** — Simpler CDK; CTAS partition rewrites sufficient for demo
3. **Single model (Haiku 4.5)** — Simplifies traces and cost tracking at demo scale
4. **Streamlit over Cloudscape** — Python-native, faster to build, standard for data demos
5. **AgentCore from start** — Production-patterned deployment from day one
