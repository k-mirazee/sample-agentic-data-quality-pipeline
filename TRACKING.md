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
- **Next:** Slice 3a — CDK data infra (S3, Glue, Athena)

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
| 3a | CDK data infra — S3 bucket, Glue database/tables, Athena workgroup. Deploy → upload data → manual Athena query to verify | NOT STARTED | |
| 3b | CDK agent infra — DynamoDB tables, SNS topic, IAM roles, AgentCore runtime. Deploy after agent code exists (Step 4) | NOT STARTED | |
| 4 | Agent core — agent.py with AgentCore app, system prompt, Athena/DDB utility modules | NOT STARTED | |
| 5 | First tools — scan_quality + check_schema + log_decision. Deploy 3b → deploy agent → test | NOT STARTED | |
| 6 | Smoke test — clean data scan → OK. Chaos data scan → violations detected. Validates core loop before remediation | NOT STARTED | Checkpoint: core agent loop proven |
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
