# Architecture

## Overview

The Data Quality Agent follows a **receive → diagnose → act → log** workflow. AWS Glue Data Quality handles detection via DQDL rulesets. A Strands Agent deployed on Amazon Bedrock AgentCore orchestrates 5 custom tools to autonomously diagnose, remediate, and audit data quality violations.

## Data Flow

```
1. INGEST     NYC TLC Parquet → raw/ zone (via download + upload scripts)
2. DETECT     Glue DQ evaluates DQDL ruleset against raw data → passes/failures
3. ROUTE      EventBridge captures Glue DQ failure events → Lambda bridge
4. INVOKE     Lambda formats event and calls AgentCore HTTP endpoint
5. RECEIVE    Agent parses Glue DQ violations via parse_dq_event
6. DIAGNOSE   For each violation: agent calls diagnose_issue → separate Bedrock LLM call
7. ACT        Based on diagnosis:
              - CRITICAL: quarantine_records → notify_owner
              - WARNING:  notify_owner with recommended next steps
8. LOG        Every decision auto-recorded to DynamoDB + CloudWatch metrics
9. OBSERVE    Dashboard reads DDB + CloudWatch for visualization
```

## S3 Data Lake Zones

| Zone | Purpose | Mutability |
|------|---------|------------|
| `raw/` | Landing zone — data arrives here | Append-only (immutable) |
| `staging/` | Intermediate processing zone | Future use |
| `curated/` | Clean data ready for consumption | Future use |
| `quarantine/` | Bad records isolated by the agent | Agent-managed, 90-day TTL |

## Agent Tools

| Tool | Purpose | AWS Services |
|------|---------|-------------|
| `parse_dq_event` | Normalize Glue DQ evaluation event into structured violations | DynamoDB, CloudWatch |
| `diagnose_issue` | Separate Bedrock LLM call for focused root cause analysis per violation | Bedrock (Haiku 4.5) |
| `quarantine_records` | Isolate bad records via Athena UNLOAD to quarantine S3 zone. Auto-logs remediation_executed. | Athena, S3, DynamoDB |
| `notify_owner` | Send alerts via SNS with severity levels. Auto-logs notification_sent. | SNS, DynamoDB |
| `log_decision` | Record additional reasoning for audit trail | DynamoDB, CloudWatch |

**Design decision:** Glue DQ handles detection (completeness, freshness, distribution, schema). The agent handles response (diagnosis, quarantine, notification). This separation means customers use a supported first-party service for detection while getting autonomous remediation from the agent.

## Glue DQ Integration

- **DQDL Ruleset** (`cdk/glue_dq_ruleset.dqdl`) — Defines completeness, row count, distribution (Mean) bounds, and schema existence rules, with thresholds calibrated to the dataset's organic baseline
- **EventBridge Rule** — Matches all `aws.glue-dataquality` "Data Quality Evaluation Results Available" events; the Lambda decides whether to invoke the agent (rule-failure state is only reliably determined from the full result, and passing runs are cheap no-ops)
- **Lambda Bridge** (`cdk/lambda/dq_event_bridge/`) — Fetches the full evaluation result via `GetDataQualityResult`, recovers the partition scope from the run's pushdown predicate, formats the structured payload, invokes AgentCore synchronously (no retries — agent actions are not idempotent)

## DynamoDB Tables

| Table | PK | SK | Purpose |
|-------|----|----|---------|
| `quality-scan-results` | `table#partition` | timestamp | Evaluation history (90-day TTL) |
| `agent-decisions` | decision UUID | timestamp | Audit trail (90-day TTL) |
| `schema-baselines` | `database#table` | version | Expected schemas (no TTL) |
| `remediation-history` | `table#partition` | timestamp | Quarantine log (90-day TTL) |

## Observability

- **OpenTelemetry** — Strands SDK traces every LLM call, tool invocation, and agent reasoning step. On AgentCore, traces flow to X-Ray via ADOT collector. Disabled locally (no collector).
- **CloudWatch Metrics** — Custom namespace `DataQualityAgent` with quality scores, anomaly counts, remediation actions, token costs, tool durations.
- **CloudWatch Alarms** — Quality score < 50 (critical), anomalies > 10 (warning), token cost > $1 (cost). All wired to SNS.
- **CloudWatch Dashboard** — `DataQualityAgentDashboard` with 6 widgets.
- **Dashboard** — React/Cloudscape UI: Control Panel (evaluate/simulate/chaos/restore), Dashboard (scores/violations/quarantine), Agent Activity (decision timeline).

## Deployment

| Mode | How | Use Case |
|------|-----|----------|
| AgentCore (primary) | EventBridge → Lambda → AgentCore, or Simulate Event button | Demos, production |
| Local | `python -m agent.agent --prompt '...'` | Development, debugging |

The same `agent.py` code runs in both modes. AgentCore is detected via `bedrock_agentcore` import. Tool imports use `try/except` to support both the local package layout (`agent.tools.X`) and the container flat layout (`tools.X`).

## Design Decisions

1. **Glue DQ for detection** — Native AWS service handles quality profiling; agent focuses on response (diagnosis, remediation, audit)
2. **Event-driven architecture** — EventBridge decouples detection from response; agent is invoked only when violations occur
3. **Standard Parquet over Iceberg** — Simpler CDK; CTAS partition rewrites sufficient for demo
4. **Single model (Haiku 4.5)** — Simplifies traces and cost tracking at demo scale
5. **AgentCore from start** — Production-patterned deployment from day one
6. **Quarantine over auto-transform** — Data remediation is a business decision; agent isolates and alerts, humans decide the fix
7. **Auto-logged decisions** — parse_dq_event, quarantine_records, and notify_owner auto-log to DDB regardless of LLM behavior, ensuring consistent audit trail
