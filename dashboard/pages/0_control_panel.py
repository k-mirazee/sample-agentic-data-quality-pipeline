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

PARTITIONS = [
    "year=2025/month=09",
    "year=2025/month=08",
    "year=2025/month=07",
    "year=2024/month=01",
]

# --- Scan Now ---
st.subheader("🔍 Run Agent Scan")
st.caption("The agent autonomously scans, diagnoses, remediates, and reports what it fixed.")
scan_partition = st.selectbox("Partition to scan", PARTITIONS, key="scan_part")
if st.button("🚀 Scan Now", type="primary"):
    prompt = (
        f"Scan the table raw_yellow_taxi partition {scan_partition} for all quality issues. "
        f"For any violations found, diagnose the root cause. Then take remediation action: "
        f"use quarantine_records for outlier records (fare_amount < 0 OR fare_amount > 500), "
        f"and use apply_transform with fill_nulls for null passenger_count (default value 1). "
        f"After remediation, notify the owner about what was found and fixed. "
        f"Log every decision."
    )
    with st.spinner(f"Agent working on {scan_partition}... (this takes ~30-60s)"):
        result = subprocess.run(
            [UV, "run", "python", "-m", "agent.agent",
             "--table", "raw_yellow_taxi", "--partition", scan_partition,
             "--prompt", prompt],
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=300,
            env={**os.environ, "PYTHONPATH": PROJECT_ROOT},
        )
    if result.returncode == 0:
        st.success("✅ Complete! Check Overview, Scan Details, and Remediation History.")
        with st.expander("Agent output"):
            st.text(result.stdout[-5000:] if len(result.stdout) > 5000 else result.stdout)
    else:
        st.error("❌ Failed")
        st.text(result.stderr[-2000:])

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
if st.button("🔄 Restore All Partitions to Clean Data"):
    with st.spinner("Restoring clean data..."):
        result = subprocess.run(
            [UV, "run", "python", "data/upload_to_s3.py",
             "--source", "data/raw", "--bucket", BUCKET,
             "--prefix", "raw/yellow_taxi", "--overwrite"],
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=120,
        )
    if result.returncode == 0:
        st.success("✅ Clean data restored to all partitions.")
    else:
        st.error("Restore failed")
        st.text(result.stderr)
