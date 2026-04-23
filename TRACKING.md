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
- **Next:** Resolve Section 13 open design decisions, then begin Slice 1

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
| 1 | Project scaffolding — pyproject.toml, directory structure, uv setup, .gitignore | NOT STARTED | |
| 2 | Data foundation — download script, chaos injector, chaos_config.yaml | NOT STARTED | |
| 3 | CDK stacks — S3, Glue, Athena, DynamoDB, SNS, IAM, AgentCore runtime | NOT STARTED | Decision 6: AgentCore from start |
| 4 | Agent core — agent.py with AgentCore app, system prompt, Athena/DDB utils | NOT STARTED | |
| 5 | First tools — scan_quality + check_schema + log_decision, deploy & test | NOT STARTED | Checkpoint: prove agent can scan and log |
| 6 | Remaining tools — diagnose_issue, quarantine_records, apply_transform, notify_owner | NOT STARTED | |
| 7 | Observability — OpenTelemetry setup, CloudWatch metrics/alarms/dashboard | NOT STARTED | |
| 8 | Streamlit dashboard — 5 pages reading from DDB + CloudWatch | NOT STARTED | |
| 9 | Polish — README, DEMO_GUIDE, ARCHITECTURE.md, integration tests | NOT STARTED | |

---

## Files Created / Modified

| File | Slice | Status | Notes |
|------|-------|--------|-------|
| `TRACKING.md` | — | ✅ Created | This file |

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
