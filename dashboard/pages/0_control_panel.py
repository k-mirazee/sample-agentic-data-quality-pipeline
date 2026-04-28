"""Page 0: Control Panel — Trigger scans, inject chaos, restore data from the UI."""

import json
import os
import subprocess
import sys

import streamlit as st

st.set_page_config(page_title="Control Panel", page_icon="🎮", layout="wide")
st.title("🎮 Control Panel")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUCKET = os.getenv("S3_BUCKET", "dq-agent-demo-015331669295")
UV = os.path.expanduser("~/.local/bin/uv")

AGENT_ARN = "arn:aws:bedrock-agentcore:us-east-1:015331669295:runtime/dq_agent-dl3UfNEcb1"

PARTITIONS = [
    "year=2025/month=09",
    "year=2025/month=08",
    "year=2025/month=07",
    "year=2024/month=01",
]

# --- Scan Now ---
st.subheader("🔍 Run Agent Scan")
st.caption("Agent runs on **Amazon Bedrock AgentCore** — not locally.")
scan_partition = st.selectbox("Partition to scan", PARTITIONS, key="scan_part")
if st.button("🚀 Scan Now", type="primary"):
    prompt = (
        f"Scan the table raw_yellow_taxi partition {scan_partition} for all quality issues. "
        f"For any violations found, diagnose the root cause. "
        f"For distribution outliers, quarantine the bad records. "
        f"Notify the owner about all findings with severity and recommended next steps. "
        f"Log every decision."
    )
    status = st.empty()
    status.info(f"🚀 **Agent running on Bedrock AgentCore...**\n\n`{AGENT_ARN}`\n\nThis typically takes 30-60 seconds.")

    import json as _json
    payload = _json.dumps({"prompt": prompt})
    result = subprocess.run(
        ["agentcore", "invoke", "--agent", "dq_agent", payload],
        capture_output=True, text=True,
        cwd=os.path.join(PROJECT_ROOT, "agent"), timeout=300,
    )

    if result.returncode == 0:
        status.success("✅ **Agent completed on AgentCore.** Check Dashboard and Agent Activity pages.")
        with st.expander("Agent response"):
            # Extract just the response text
            output = result.stdout
            if "Response:" in output:
                output = output.split("Response:", 1)[1].strip()
            st.markdown(output[:5000])
    else:
        stderr = result.stderr or result.stdout
        if "RuntimeClientError" in stderr:
            status.error("❌ AgentCore runtime error — check CloudWatch logs")
        else:
            status.error("❌ Invocation failed")
        with st.expander("Error details"):
            st.text(stderr[-2000:])

st.markdown("---")

# --- Inject Chaos ---
st.subheader("💥 Inject Chaos")
chaos_partition = st.selectbox("Partition to corrupt", PARTITIONS, key="chaos_part")

# Derive filename from partition
_parts = dict(p.split("=") for p in chaos_partition.split("/"))
_filename = f"yellow_tripdata_{_parts['year']}-{_parts['month']}.parquet"
_input = os.path.join(PROJECT_ROOT, "data", "raw", _filename)
_output = os.path.join(PROJECT_ROOT, "data", "chaos", _filename)

if st.button("💥 Inject Chaos & Upload", type="secondary"):
    if not os.path.exists(_input):
        st.error(f"Source file not found: {_filename}. Download it first.")
    else:
        with st.spinner("Injecting chaos..."):
            r1 = subprocess.run(
                [UV, "run", "python", "data/chaos_injector.py",
                 "--input", _input, "--output", _output,
                 "--config", "data/chaos_config.yaml"],
                capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=120,
            )
        if r1.returncode != 0:
            st.error("Chaos injection failed")
            st.text(r1.stderr)
        else:
            with st.spinner("Uploading chaos data to S3..."):
                r2 = subprocess.run(
                    [UV, "run", "python", "data/upload_to_s3.py",
                     "--source", os.path.dirname(_output),
                     "--bucket", BUCKET, "--prefix", "raw/yellow_taxi", "--overwrite"],
                    capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=120,
                )
            if r2.returncode == 0:
                st.success("✅ Chaos injected and uploaded! Run a scan to see the agent detect it.")
                with st.expander("Chaos injector output"):
                    st.text(r1.stdout)
            else:
                st.error("Upload failed")
                st.text(r2.stderr)

st.markdown("---")

# --- Restore Clean Data ---
st.subheader("🔄 Restore Clean Data")
clear_ddb = st.checkbox("Also clear all scan history, decisions, and quarantine records", value=True)
if st.button("🔄 Restore Everything"):
    with st.spinner("Restoring clean data..."):
        result = subprocess.run(
            [UV, "run", "python", "data/upload_to_s3.py",
             "--source", "data/raw", "--bucket", BUCKET,
             "--prefix", "raw/yellow_taxi", "--overwrite"],
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=120,
        )
    if result.returncode == 0:
        if clear_ddb:
            with st.spinner("Clearing DynamoDB tables..."):
                subprocess.run(
                    [UV, "run", "python", "-c", """
import boto3
region = "us-east-1"
ddb = boto3.resource("dynamodb", region_name=region)
for name in ["quality-scan-results", "agent-decisions", "schema-baselines", "remediation-history"]:
    table = ddb.Table(name)
    scan = table.scan(ProjectionExpression="PK, SK")
    with table.batch_writer() as batch:
        for item in scan.get("Items", []):
            batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
    print(f"Cleared {name}: {len(scan.get('Items', []))} items")
"""],
                    capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=60,
                    env={**os.environ, "PYTHONPATH": PROJECT_ROOT},
                )
            st.success("✅ Clean data restored and all history cleared. Fresh start!")
        else:
            st.success("✅ Clean data restored (history preserved).")
    else:
        st.error("Restore failed")
        st.text(result.stderr)
