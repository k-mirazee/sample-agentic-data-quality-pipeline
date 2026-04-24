# Project Tracking: sample-agentic-data-quality-pipeline

**Spec:** `~/Desktop/SPEC-agentic-data-quality-pipeline.md`
**Account:** 015331669295
**Region:** us-east-1
**Package Manager:** uv
**Python:** 3.11+
**Started:** 2026-04-23

---

## Session Log

### Session 1 — 2026-04-23
- Read and understood full spec
- Discussed build approach: vertical slices, checkpoint after each
- Created this tracking document
- Resolved all 7 design decisions
- Completed Slice 1: project scaffolding (uv, pyproject.toml, directory structure)
- Completed Slice 2: data scripts (download, chaos injector, upload)
- **Discovery:** Real data has `Airport_fee` (capital A), `passenger_count`/`RatecodeID` are float64 (nulls in source)
- Completed Slice 3a: CDK data infra deployed, data uploaded, Athena query verified (2.96M rows)
- **Note:** Must use `isengardcli credentials 015331669295` for AWS access
- Completed Slice 4: Agent core — agent.py, system prompt, all utility modules, configs
- Completed Slice 3b: CDK agent infra — 4 DDB tables + SNS topic deployed
- Completed Slice 5: First tools — scan_quality, check_schema, log_decision wired in
- **First agent run:** Score 62.7/100 CRITICAL. Freshness 0 (812 days old), completeness 90.5 (4.73% null passenger_count), distribution 97.5 (negative fares). Agent called scan_quality + 2x log_decision. 8.8s scan.
- **Next:** Slice 6 — Smoke test (clean vs chaos data)
- **Session ended:** 2026-04-23 ~16:15 CDT

### Session 2 — 2026-04-24
- Completed Slice 6: Smoke test — chaos data broke Athena (VendorID int→string), agent detected via check_schema, logged 3 decisions, flagged CRITICAL. Clean data restored.
- **Next:** Slice 7 — Remaining tools (diagnose_issue, quarantine_records, apply_transform, notify_owner)

### Pickup Instructions for Next Session
1. Read this file: `~/sample-agentic-data-quality-pipeline/TRACKING.md`
2. Read the spec: `~/Desktop/SPEC-agentic-data-quality-pipeline.md`
3. AWS access: `eval "$(isengardcli credentials 015331669295)"`
4. Project dir: `cd ~/sample-agentic-data-quality-pipeline`
5. Activate env: `source .venv/bin/activate` or use `uv run`
6. Resume at Slice 6 (smoke test) or Slice 7 (remaining tools)

### Deployed AWS Resources
- **S3 bucket:** `dq-agent-demo-015331669295` (has Jan 2024 clean data in raw/yellow_taxi/year=2024/month=01/)
- **Glue DB:** `dq_agent_demo` with 4 tables (raw/staging/curated/quarantine_yellow_taxi)
- **Athena workgroup:** `dq-agent-workgroup`
- **DynamoDB tables:** quality-scan-results, agent-decisions, schema-baselines, remediation-history
- **SNS topic:** dq-agent-alerts
- **CDK stacks:** DqAgentDataLake, DqAgentObservability, DqAgentNotification

### What Works Right Now
- Agent runs locally: `uv run python -m agent.agent --table raw_yellow_taxi --partition "year=2024/month=01"`
- 3 tools wired: scan_quality, check_schema, log_decision
- Chaos injector tested locally: `data/chaos/` has corrupted Jan 2024 data ready to upload
- Download script: can fetch more months with `uv run python data/download_data.py --num-months 3`

### What's Left (Slices 6-10)
- Slice 6: Smoke test — upload chaos data, re-scan, verify agent detects new issues
- Slice 7: Remaining 4 tools — diagnose_issue, quarantine_records, apply_transform, notify_owner
- Slice 8: Observability — OpenTelemetry, CloudWatch alarms/dashboard
- Slice 9: Streamlit dashboard — 5 pages
- Slice 10: Polish — README, DEMO_GUIDE, ARCHITECTURE.md, integration tests

---

## Design Decisions

| # | Question | Decision | Rationale | Date |
|---|----------|----------|-----------|------|
| 1 | Glue DQDL vs Athena SQL | **Athena SQL** | Agent needs visible control over queries; more educational for blog readers; DQDL hides the interesting reasoning | 2026-04-23 |
| 2 | Trigger: schedule vs S3 event | **Schedule (EventBridge)** | Simpler to implement/demo; manual CLI for dev; S3 event adds Lambda complexity without demo value | 2026-04-23 |
| 3 | Model selection (Haiku vs Nova Micro) | **Claude Haiku 4.5 only** | Single model simplifies traces, cost tracking, and blog narrative; cost difference negligible at demo scale | 2026-04-23 |
| 4 | Dashboard: Streamlit vs Cloudscape | **Streamlit** | Python-native, faster to build, standard for data-focused AWS Samples; avoids separate React/npm toolchain | 2026-04-23 |
| 5 | Iceberg vs standard Parquet | **Standard Parquet everywhere** | Reduces CDK complexity; CTAS partition rewrites sufficient for demo; Iceberg mentioned as production upgrade in blog | 2026-04-23 |
| 6 | Agent invocation: local vs AgentCore | **AgentCore from the start** | Build directly for AgentCore deployment; agent code structured for AgentCore runtime from day 1 | 2026-04-23 |
| 7 | Multi-table support from day 1 | **Yes, lightweight** | table_name parameterized everywhere; baselines per table in DDB; only demo with yellow taxi; free to do now, painful to retrofit | 2026-04-23 |

---

## Build Slices & Status

| Slice | Description | Status | Notes |
|-------|-------------|--------|-------|
| 1 | Project scaffolding — pyproject.toml, directory structure, uv setup, .gitignore | ✅ DONE | Commit 178787a |
| 2 | Data scripts — download_data.py, chaos_injector.py, chaos_config.yaml, upload_to_s3.py (all local, no AWS) | ✅ DONE | Commit 20f812a. Airport_fee capital A fix. |
| 3a | CDK data infra — S3 bucket, Glue database/tables, Athena workgroup. Deploy → upload data → manual Athena query to verify | ✅ DONE | Commit a7c0f13. Athena query: 2.96M rows OK. |
| 3b | CDK agent infra — DynamoDB tables, SNS topic, IAM roles, AgentCore runtime. Deploy after agent code exists (Step 4) | ✅ DONE | Commit bf42fd8. 4 DDB tables + SNS topic deployed. |
| 4 | Agent core — agent.py with AgentCore app, system prompt, Athena/DDB utility modules | ✅ DONE | Commit ee3a881. Local mode works, AgentCore fallback. |
| 5 | First tools — scan_quality + check_schema + log_decision. Deploy 3b → deploy agent → test | ✅ DONE | Commit bf42fd8. Agent scanned real data successfully. |
| 6 | Smoke test — clean data scan → OK. Chaos data scan → violations detected. Validates core loop before remediation | ✅ DONE | Agent detected schema drift on chaos data, pivoted to check_schema, flagged CRITICAL. |
| 7 | Remaining tools — diagnose_issue, quarantine_records, apply_transform, notify_owner | NOT STARTED | |
| 8 | Observability — OpenTelemetry, CloudWatch metrics/alarms/dashboard | NOT STARTED | |
| 9 | Streamlit dashboard — 5 pages reading from DDB + CloudWatch | NOT STARTED | |
| 10 | Polish — README, DEMO_GUIDE, ARCHITECTURE.md, integration tests | NOT STARTED | |

---

## Files Created / Modified

| File | Slice | Status | Notes |
|------|-------|--------|-------|
| `TRACKING.md` | — | ✅ Created | This file |
| `pyproject.toml` | 1 | ✅ Created | All deps, ruff/mypy/pytest config, hatch build config |
| `.gitignore` | 1 | ✅ Created | Python, uv, CDK, data, IDE, OS |
| `README.md` | 1 | ✅ Created | Placeholder — will expand in Slice 9 |
| `agent/__init__.py` | 1 | ✅ Created | Empty |
| `agent/tools/__init__.py` | 1 | ✅ Created | Empty |
| `agent/utils/__init__.py` | 1 | ✅ Created | Empty |
| `cdk/stacks/__init__.py` | 1 | ✅ Created | Empty |
| `tests/**/__init__.py` | 1 | ✅ Created | Empty |
| `data/download_data.py` | 2 | ✅ Created | Downloads NYC TLC parquet from CloudFront |
| `data/chaos_config.yaml` | 2 | ✅ Created | 6 injection types, seed 42. Fixed Airport_fee (capital A) |
| `data/chaos_injector.py` | 2 | ✅ Created | Applies chaos config to parquet files |
| `data/upload_to_s3.py` | 2 | ✅ Created | Uploads to S3 with Hive partitioning |
| `cdk/app.py` | 3a | ✅ Created | CDK entrypoint, account 015331669295 us-east-1 |
| `cdk/cdk.json` | 3a | ✅ Created | CDK config with context params |
| `cdk/stacks/data_lake_stack.py` | 3a | ✅ Created | S3 bucket, Glue DB + 4 tables, Athena workgroup |
| `agent/utils/athena_client.py` | 4 | ✅ Created | Query execution + result parsing + bytes_scanned |
| `agent/utils/dynamodb_client.py` | 4 | ✅ Created | CRUD for all 4 DDB tables, auto-versioned baselines |
| `agent/utils/metrics.py` | 4 | ✅ Created | CloudWatch metric emission (DataQualityAgent namespace) |
| `agent/config/quality_thresholds.yaml` | 4 | ✅ Created | Severity thresholds for all quality dimensions |
| `agent/config/schema_baselines/yellow_taxi.json` | 4 | ✅ Created | 19-column baseline from real 2024 parquet schema |
| `agent/system_prompt.md` | 4 | ✅ Created | Agent identity, workflow, thresholds, constraints |
| `agent/agent.py` | 4 | ✅ Created | Strands agent + AgentCore entrypoint + local CLI |
| `cdk/stacks/observability_stack.py` | 3b | ✅ Created | 4 DynamoDB tables (on-demand, TTL) |
| `cdk/stacks/notification_stack.py` | 3b | ✅ Created | SNS topic dq-agent-alerts |
| `agent/tools/scan_quality.py` | 5 | ✅ Created | Completeness, freshness, distribution checks via Athena |
| `agent/tools/check_schema.py` | 5 | ✅ Created | Glue schema vs DDB baseline drift detection |
| `agent/tools/log_decision.py` | 5 | ✅ Created | DDB + CloudWatch decision logging |

---

## Blockers & Issues

_None yet._

---

## Key Patterns & Conventions

- Tool manager: `uv`
- Linting: `ruff`
- Type checking: `mypy`
- Testing: `pytest` + `moto`
- IaC: CDK v2 (Python)
- Agent framework: Strands Agents SDK
- Observability: OpenTelemetry via `strands[otel]`
