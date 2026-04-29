# Demo Guide

Step-by-step walkthrough for demonstrating the Data Quality Agent. Expected duration: 15–20 minutes. Expected cost: <$5.

## Prerequisites

- AWS account with CDK deployed and AgentCore agent running
- Bedrock model access enabled (Claude Haiku 4.5)
- NYC TLC data downloaded (Jul–Sep 2025)
- Fresh AWS credentials: `mwinit && eval "$(isengardcli credentials 015331669295)"`

## Startup Sequence

Every time you sit down to demo:

```bash
mwinit
eval "$(isengardcli credentials 015331669295)"
cd ~/sample-agentic-data-quality-pipeline
PYTHONPATH=. uv run streamlit run dashboard/app.py
```

Open `http://localhost:8501` in your browser.

## Demo Flow (All from the UI)

### Step 1: Reset (Control Panel)

Go to **🎮 Control Panel** → click **🔄 Restore Everything** (with "clear all history" checked). This gives you a clean slate.

### Step 2: Scan Clean Data (Control Panel)

Select `year=2025/month=09` → click **🚀 Scan Now**.

The status shows: *"🚀 Agent running on Bedrock AgentCore..."* with the agent ARN. Wait ~30-60 seconds.

**What the agent does:**
1. Scans 4.25M records via Athena SQL
2. Finds 4 violations: 25% null passenger_count (CRITICAL), stale timestamps (CRITICAL), fare outliers (WARNING), total_amount outliers (WARNING)
3. Diagnoses each violation with a separate LLM call
4. Quarantines outlier records to S3 quarantine zone
5. Sends SNS notifications for all findings
6. Logs every decision to DynamoDB

### Step 3: Review Results (Dashboard)

Go to **📊 Dashboard**:
- **Score: ~46/100 CRITICAL** — driven by completeness and freshness
- **LowQualityScore alarm: 🔴 ALARM** — CloudWatch alarm fired
- **Dimension breakdown**: freshness 0, distribution ~88, completeness ~50
- **Quarantined Records**: ~252K fare outliers + ~78K total_amount outliers isolated

### Step 4: Review Agent Reasoning (Agent Activity)

Go to **🧠 Agent Activity**:
- **scan_initiated** → scan started with all check types
- **violation_detected** → 4 violations found, 2 CRITICAL + 2 WARNING
- **remediation_executed** → quarantined outlier records with S3 paths
- **notification_sent** → CRITICAL and WARNING alerts delivered via SNS

Each entry shows the agent's reasoning, action taken, and outcome.

### Step 5: Inject Chaos (Control Panel)

Go back to **🎮 Control Panel** → select `year=2025/month=09` → click **💥 Inject Chaos & Upload**.

This injects: 15% additional nulls, outlier fares (-$1000 to $50K), schema drift (column renames, type changes, dropped columns), 5% duplicate records.

### Step 6: Scan Chaos Data (Control Panel)

Click **🚀 Scan Now** again on the same partition.

**What happens:** The schema type mismatch (VendorID int→string) prevents Athena from reading the data. The agent:
1. Tries `scan_quality` → Athena query fails
2. Pivots to `check_schema` → detects breaking schema drift
3. Diagnoses the mismatch as a data ingestion error
4. Sends CRITICAL notification — "manual intervention required"

### Step 7: Review Chaos Results (Dashboard)

Go to **📊 Dashboard**:
- **Red error banner**: "Latest scan failed — schema mismatch detected"
- Agent Activity shows the full reasoning chain: scan failed → schema check → diagnosis → notification

### Step 8: Restore (Control Panel)

Click **🔄 Restore Everything** to reset for the next demo.

## Key Talking Points

- **"The agent runs on Bedrock AgentCore — not on my laptop."** Point to the ARN in the status message.
- **"It found real quality issues in real NYC taxi data."** 25% null passenger counts, $323K taxi fares, negative fares.
- **"When the data was too corrupted to scan, it adapted."** Pivoted from scan to schema check, diagnosed the problem, escalated.
- **"Every decision is logged and auditable."** Show Agent Activity — reasoning, actions, outcomes.
- **"It quarantined 330K bad records automatically."** Show Quarantined Records on Dashboard.

## AgentCore CLI Demo (Optional)

To show AgentCore directly from the terminal:

```bash
cd ~/sample-agentic-data-quality-pipeline/agent
agentcore invoke '{"prompt": "Scan raw_yellow_taxi partition year=2025/month=09 for all quality issues. Diagnose and quarantine outliers."}'
```

## Cleanup

```bash
cd ~/sample-agentic-data-quality-pipeline/cdk
uv run --extra cdk -- npx cdk destroy --app "python3 app.py" --all
cd ../agent
agentcore destroy --agent dq_agent
```
