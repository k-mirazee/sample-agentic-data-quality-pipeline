"""Lightweight FastAPI backend for the Data Quality Agent dashboard."""

import json
import os
import subprocess

import boto3
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from dashboard.utils.cloudwatch import get_alarm_states
from dashboard.utils.dynamodb import get_all_remediations, get_all_scans, get_recent_decisions

app = FastAPI(title="DQ Agent API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UV = os.path.expanduser("~/.local/bin/uv")


def _resolve_bucket() -> str:
    bucket = os.getenv("S3_BUCKET")
    if bucket:
        return bucket
    account_id = boto3.client("sts").get_caller_identity()["Account"]
    return f"dq-agent-demo-{account_id}"


BUCKET = _resolve_bucket()
GLUE_DATABASE = os.getenv("GLUE_DATABASE", "dq_agent_demo")
AGENTCORE_AGENT_NAME = os.getenv("AGENTCORE_AGENT_NAME", "dq_agent")
RULESET_NAME = os.getenv("DQ_RULESET_NAME", "dq-agent-ruleset")
REGION = os.getenv("AWS_REGION", "us-east-1")


@app.get("/api/scans")
def scans():
    return get_all_scans(limit=20)


@app.get("/api/decisions")
def decisions():
    return get_recent_decisions(limit=100)


@app.get("/api/alarms")
def alarms():
    return get_alarm_states()


@app.get("/api/remediations")
def remediations():
    return get_all_remediations(limit=50)


class ScanRequest(BaseModel):
    partition: str


@app.post("/api/scan")
def run_scan(req: ScanRequest):
    """Trigger a Glue DQ evaluation run on the specified partition."""
    parts = dict(p.split("=") for p in req.partition.split("/"))
    push_down = " AND ".join(f"{k}='{v}'" for k, v in parts.items())

    try:
        glue_client = boto3.client("glue", region_name=REGION)
        resp = glue_client.start_data_quality_ruleset_evaluation_run(
            DataSource={
                "GlueTable": {
                    "DatabaseName": GLUE_DATABASE,
                    "TableName": "raw_yellow_taxi",
                    "AdditionalOptions": {"pushDownPredicate": push_down},
                }
            },
            Role=f"arn:aws:iam::{boto3.client('sts').get_caller_identity()['Account']}:role/dq-agent-glue-role",
            RulesetNames=[RULESET_NAME],
            # Required for Glue DQ to publish the EventBridge event that
            # triggers the agent; the console enables this by default but
            # API-started runs must set it explicitly.
            AdditionalRunOptions={"CloudWatchMetricsEnabled": True},
        )
        run_id = resp.get("RunId", "unknown")
        return {
            "status": "ok",
            "message": f"Glue DQ evaluation started (run: {run_id}). Agent will be invoked when evaluation completes.",
            "run_id": run_id,
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to start Glue DQ evaluation: {e}"}


class SimulateEventRequest(BaseModel):
    partition: str


@app.post("/api/simulate-event")
def simulate_event(req: SimulateEventRequest):
    """Send a simulated Glue DQ failure event directly to the agent (fast demo mode)."""
    payload = {
        "evaluation_id": "dq-sim-demo-001",
        "database": GLUE_DATABASE,
        "table": "raw_yellow_taxi",
        "partition": req.partition,
        "overall_state": "FAILED",
        "rule_results": [
            {
                "rule": 'Completeness "tpep_pickup_datetime" > 0.98',
                "state": "FAILED",
                "evaluated_metrics": {"Column.tpep_pickup_datetime.Completeness": 0.93},
                "description": "Completeness check failed — 7% null pickup timestamps",
            },
            {
                "rule": 'DataFreshness "tpep_pickup_datetime" <= 72',
                "state": "FAILED",
                "evaluated_metrics": {"Column.tpep_pickup_datetime.Freshness.Hours": 96},
                "description": "Data freshness check failed — 96 hours stale",
            },
            {
                "rule": 'ColumnValues "fare_amount" between 0 and 500',
                "state": "FAILED",
                "evaluated_metrics": {"Column.fare_amount.OutlierRatio": 0.05},
                "description": "Column values out of expected range — 5% outliers",
            },
        ],
    }

    prompt = (
        f"Glue DQ evaluation dq-sim-demo-001 on raw_yellow_taxi partition {req.partition} has FAILED. "
        f"Process the following evaluation results:\n\n{json.dumps(payload)}"
    )

    try:
        result = subprocess.run(
            ["agentcore", "invoke", "--agent", AGENTCORE_AGENT_NAME, json.dumps({"prompt": prompt})],
            capture_output=True,
            text=True,
            cwd=os.path.join(PROJECT_ROOT, "agent"),
            timeout=300,
        )
        if result.returncode == 0:
            return {"status": "ok", "message": "Simulated event processed by agent."}
        return {"status": "error", "message": result.stderr[-500:] if result.stderr else "Unknown error"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Agent timed out after 5 minutes."}


class ChaosRequest(BaseModel):
    partition: str


@app.post("/api/chaos")
def inject_chaos(req: ChaosRequest):
    parts = dict(p.split("=") for p in req.partition.split("/"))
    filename = f"yellow_tripdata_{parts['year']}-{parts['month']}.parquet"
    input_path = os.path.join(PROJECT_ROOT, "data", "raw", filename)
    output_path = os.path.join(PROJECT_ROOT, "data", "chaos", filename)

    if not os.path.exists(input_path):
        return {"status": "error", "message": f"Source file not found: {filename}"}

    r1 = subprocess.run(
        [
            UV,
            "run",
            "python",
            "data/chaos_injector.py",
            "--input",
            input_path,
            "--output",
            output_path,
            "--config",
            "data/chaos_config.yaml",
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        timeout=120,
    )
    if r1.returncode != 0:
        return {"status": "error", "message": "Chaos injection failed."}

    # Upload only the file generated for this partition — uploading the whole
    # chaos directory would clobber other partitions with stale chaos files.
    r2 = subprocess.run(
        [
            UV,
            "run",
            "python",
            "data/upload_to_s3.py",
            "--file",
            output_path,
            "--bucket",
            BUCKET,
            "--prefix",
            "raw/yellow_taxi",
            "--overwrite",
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        timeout=120,
    )
    if r2.returncode == 0:
        return {"status": "ok", "message": "Chaos injected and uploaded."}
    return {"status": "error", "message": "Upload failed."}


class RestoreRequest(BaseModel):
    clear_history: bool = True


@app.post("/api/restore")
def restore(req: RestoreRequest):
    result = subprocess.run(
        [
            UV,
            "run",
            "python",
            "data/upload_to_s3.py",
            "--source",
            "data/raw",
            "--bucket",
            BUCKET,
            "--prefix",
            "raw/yellow_taxi",
            "--overwrite",
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        timeout=120,
    )
    if result.returncode != 0:
        return {"status": "error", "message": "Restore failed."}

    if req.clear_history:
        subprocess.run(
            [
                UV,
                "run",
                "python",
                "-c",
                """
import boto3
ddb = boto3.resource("dynamodb", region_name="us-east-1")
for name in ["quality-scan-results", "agent-decisions", "schema-baselines", "remediation-history"]:
    table = ddb.Table(name)
    scan = table.scan(ProjectionExpression="PK, SK")
    with table.batch_writer() as batch:
        for item in scan.get("Items", []):
            batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
""",
            ],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=60,
            env={**os.environ, "PYTHONPATH": PROJECT_ROOT},
        )
    return {"status": "ok", "message": "Restored." + (" History cleared." if req.clear_history else "")}
