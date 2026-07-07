# Demo Guide

Step-by-step walkthrough for demonstrating the Data Quality Agent. Expected duration: 15–20 minutes. Expected cost: <$5.

## Prerequisites

- AWS account with CDK deployed and AgentCore agent running
- Bedrock model access enabled (Claude Haiku 4.5)
- NYC TLC data downloaded (Jul–Sep 2025)
- AWS credentials configured (`aws configure` or environment variables)

## Startup Sequence

Every time you sit down to demo:

```bash
cd ~/sample-agentic-data-quality-pipeline

# Backend
PYTHONPATH=. uv run uvicorn dashboard.api:app --reload --port 8000 &

# Frontend
cd dashboard/ui && npm run dev &
```

Open `http://localhost:3000` in your browser.

## Demo Flow (All from the UI)

### Step 1: Reset (Control Panel)

Click **Restore Everything** (with "clear all history" checked). This gives you a clean slate.

### Step 2: Simulate Glue DQ Failure (Control Panel)

Select `year=2025/month=09` → click **Simulate Event**.

This sends a pre-built Glue DQ failure event directly to the agent — simulating what happens in production when Glue DQ detects violations. Fast for demos (~30 seconds).

**What the agent does:**
1. Receives Glue DQ evaluation results (3 rule failures)
2. Parses violations: 7% null pickup timestamps (CRITICAL), 96 hours stale (CRITICAL), 5% fare outliers (CRITICAL)
3. Diagnoses each violation with a separate LLM call
4. Quarantines outlier records to S3 quarantine zone
5. Sends SNS notifications for all findings
6. Logs every decision to DynamoDB

### Step 3: Review Results (Dashboard)

Go to **Dashboard**:
- **Score: ~40/100 CRITICAL** — driven by multiple CRITICAL violations
- **LowQualityScore alarm: ALARM** — CloudWatch alarm fired
- **Quarantined Records**: fare outliers isolated to quarantine zone

### Step 4: Review Agent Reasoning (Agent Activity)

Go to **Agent Activity**:
- **violation_detected** → 3 violations parsed from Glue DQ evaluation
- **diagnosis_complete** → root cause analysis for each violation
- **remediation_executed** → quarantined outlier records with S3 paths
- **notification_sent** → CRITICAL alerts delivered via SNS

Each entry shows the agent's reasoning, action taken, and outcome.

### Step 5: Inject Chaos (Control Panel)

Go back to **Control Panel** → select `year=2025/month=09` → click **Inject Chaos and Upload**.

This injects: 15% additional nulls, outlier fares (-$1000 to $50K), schema drift (column renames, type changes, dropped columns), 5% duplicate records.

### Step 6: Run Full Evaluation (Control Panel)

Click **Run Evaluation** on the same partition.

**What happens in production:** Glue DQ evaluates the DQDL ruleset against the corrupted data → detects violations → emits EventBridge event → Lambda bridge invokes AgentCore → Agent diagnoses and remediates.

Note: This takes 2-3 minutes as Glue DQ runs a real evaluation. Use **Simulate Event** for faster demos.

### Step 7: Review Results

Go to **Dashboard** and **Agent Activity** to see:
- The full detection → response chain
- Agent reasoning about each Glue DQ rule failure
- Quarantine and notification actions

### Step 8: Restore (Control Panel)

Click **Restore Everything** to reset for the next demo.

## Key Talking Points

- **"Glue DQ handles detection — the agent handles response."** Separation of concerns: native AWS service for profiling, agent for diagnosis and remediation.
- **"It's event-driven."** The agent only runs when Glue DQ finds something wrong. No polling, no wasted compute.
- **"The agent reasons about WHY the data is bad."** Not just "5% outliers" but "upstream vendor started including negative fare adjustments in trip records."
- **"Every decision is logged and auditable."** Show Agent Activity — reasoning, actions, outcomes.
- **"It quarantined bad records automatically."** Show Quarantined Records on Dashboard.
- **"Full observability via OpenTelemetry."** Every tool call traced end-to-end.

## Production Flow vs Demo Flow

| | Production | Demo (Simulate Event) |
|---|---|---|
| Detection | Glue DQ evaluates DQDL ruleset | Skipped (pre-built payload) |
| Routing | EventBridge → Lambda → AgentCore | Direct AgentCore invoke |
| Response | Identical | Identical |
| Speed | 2-3 minutes (Glue evaluation) | ~30 seconds |

## AgentCore CLI Demo (Optional)

To show AgentCore directly from the terminal:

```bash
cd ~/sample-agentic-data-quality-pipeline/agent
agentcore invoke '{"prompt": "Glue DQ evaluation dq-demo-001 on raw_yellow_taxi partition year=2025/month=09 has FAILED. Process the following evaluation results:\n\n{\"evaluation_id\":\"dq-demo-001\",\"database\":\"dq_agent_demo\",\"table\":\"raw_yellow_taxi\",\"partition\":\"year=2025/month=09\",\"overall_state\":\"FAILED\",\"rule_results\":[{\"rule\":\"Completeness \\\"tpep_pickup_datetime\\\" > 0.98\",\"state\":\"FAILED\",\"evaluated_metrics\":{\"Column.tpep_pickup_datetime.Completeness\":0.93}}]}"}'
```

## Cleanup

```bash
cd ~/sample-agentic-data-quality-pipeline/cdk
uv run --extra cdk -- npx cdk destroy --app "python3 app.py" --all
cd ../agent
agentcore destroy --agent dq_agent
```
