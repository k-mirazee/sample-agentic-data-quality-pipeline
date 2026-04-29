# Architecture

## Overview

The Data Quality Agent follows a **scan → assess → diagnose → act → log** workflow. A Strands Agent deployed on Amazon Bedrock AgentCore orchestrates 6 custom tools to autonomously monitor, diagnose, and remediate data quality issues in an S3 data lake.

## Data Flow

```
1. INGEST     NYC TLC Parquet → raw/ zone (via download + upload scripts)
2. TRIGGER    AgentCore invoke (via Streamlit UI, CLI, or EventBridge schedule)
3. SCAN       Agent calls scan_quality → Athena SQL queries → quality scores
4. ASSESS     Agent evaluates scores against thresholds (quality_thresholds.yaml)
5. DIAGNOSE   For violations: agent calls diagnose_issue → separate Bedrock LLM call
6. ACT        Based on diagnosis:
              - CRITICAL: quarantine_records → notify_owner
              - WARNING:  notify_owner with recommended next steps
              - Schema drift: check_schema → diagnose → notify_owner
7. LOG        Every decision auto-recorded to DynamoDB + CloudWatch metrics
8. OBSERVE    Streamlit dashboard reads DDB + CloudWatch for visualization
```

## S3 Data Lake Zones

| Zone | Purpose | Mutability |
|------|---------|------------|
| `raw/` | Landing zone — data arrives here | Append-only (immutable) |
| `staging/` | Agent copies data after initial validation | Agent-managed |
| `curated/` | Clean data ready for consumption | Agent-managed |
| `quarantine/` | Bad records isolated by the agent | Agent-managed, 90-day TTL |

## Agent Tools

| Tool | Purpose | AWS Services |
|------|---------|-------------|
| `scan_quality` | Completeness, freshness, distribution checks. Auto-logs scan_initiated + violation_detected. | Athena, DynamoDB, CloudWatch |
| `check_schema` | Compare Glue schema against stored baseline, detect renames via string similarity | Glue, DynamoDB |
| `diagnose_issue` | Separate Bedrock LLM call for focused root cause analysis per violation | Bedrock (Haiku 4.5) |
| `quarantine_records` | Isolate bad records via Athena UNLOAD to quarantine S3 zone. Auto-logs remediation_executed. | Athena, S3, DynamoDB |
| `notify_owner` | Send alerts via SNS with severity levels. Auto-logs notification_sent. | SNS, DynamoDB |
| `log_decision` | Record additional reasoning for audit trail | DynamoDB, CloudWatch |

**Design decision:** The agent detects, diagnoses, quarantines, and alerts — but does not auto-transform data. Data remediation (filling nulls, clipping outliers) is a business decision that should involve humans. The agent provides the diagnosis and recommended fix; humans approve the action.

## DynamoDB Tables

| Table | PK | SK | Purpose |
|-------|----|----|---------|
| `quality-scan-results` | `table#partition` | timestamp | Scan history (90-day TTL) |
| `agent-decisions` | decision UUID | timestamp | Audit trail (90-day TTL) |
| `schema-baselines` | `database#table` | version | Expected schemas (no TTL) |
| `remediation-history` | `table#partition` | timestamp | Quarantine log (90-day TTL) |

## Observability

- **OpenTelemetry** — Strands SDK traces every LLM call, tool invocation, and agent reasoning step. On AgentCore, traces flow to X-Ray via ADOT collector. Disabled locally (no collector).
- **CloudWatch Metrics** — Custom namespace `DataQualityAgent` with quality scores, anomaly counts, remediation actions, token costs, tool durations.
- **CloudWatch Alarms** — Quality score < 50 (critical), anomalies > 10 (warning), token cost > $1 (cost). All wired to SNS.
- **CloudWatch Dashboard** — `DataQualityAgentDashboard` with 5 widgets.
- **Streamlit Dashboard** — 3 pages: Control Panel (scan/chaos/restore), Dashboard (scores/violations/quarantine), Agent Activity (decision timeline).

## Deployment

| Mode | How | Use Case |
|------|-----|----------|
| AgentCore (primary) | `agentcore invoke` or Streamlit Scan Now button | Demos, production |
| Local | `python -m agent.agent` | Development, debugging |

The same `agent.py` code runs in both modes. AgentCore is detected via `bedrock_agentcore` import. Tool imports use `try/except` to support both the local package layout (`agent.tools.X`) and the container flat layout (`tools.X`).

## Design Decisions

1. **Athena SQL over Glue DQDL** — Agent controls queries directly; more visible and educational
2. **Standard Parquet over Iceberg** — Simpler CDK; CTAS partition rewrites sufficient for demo
3. **Single model (Haiku 4.5)** — Simplifies traces and cost tracking at demo scale
4. **Streamlit over Cloudscape** — Python-native, faster to build, standard for data demos
5. **AgentCore from start** — Production-patterned deployment from day one
6. **Quarantine over auto-transform** — Data remediation is a business decision; agent isolates and alerts, humans decide the fix
7. **Auto-logged decisions** — scan_quality, quarantine_records, and notify_owner auto-log to DDB regardless of LLM behavior, ensuring consistent audit trail
