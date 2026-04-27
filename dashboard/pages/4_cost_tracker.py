"""Page 4: Cost Tracker — Token spend, Athena bytes scanned, projected costs."""

import streamlit as st
import pandas as pd

from dashboard.utils.dynamodb import get_all_scans, get_recent_decisions
from dashboard.utils.cloudwatch import get_metric_data

st.set_page_config(page_title="Cost Tracker", page_icon="💰", layout="wide")
st.title("💰 Cost Tracker")

# --- Token Cost from CloudWatch ---
st.subheader("Token Cost Over Time")
token_data = get_metric_data("AgentTokenCost", hours=168, stat="Sum", period=3600)
if token_data:
    df = pd.DataFrame(token_data)
    df["Time"] = pd.to_datetime(df["Timestamp"])
    st.line_chart(df.set_index("Time")["Sum"])
else:
    st.info("No token cost data yet.")

# --- Athena Bytes Scanned ---
st.subheader("Athena Scan Costs")
scans = get_all_scans(limit=100)
if scans:
    total_bytes = sum(s.get("bytes_scanned", 0) or s.get("query_cost_bytes_scanned", 0) for s in scans)
    total_mb = total_bytes / 1e6
    athena_cost = (total_bytes / 1e12) * 5.0  # $5 per TB

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Bytes Scanned", f"{total_mb:.1f} MB")
    col2.metric("Estimated Athena Cost", f"${athena_cost:.4f}")
    col3.metric("Total Scans", len(scans))

    # Per-scan breakdown
    scan_costs = pd.DataFrame([{
        "Timestamp": s.get("SK", "")[:19],
        "Table": s.get("table", ""),
        "Score": s.get("overall_score", 0),
        "Duration (ms)": s.get("scan_duration_ms", 0),
    } for s in scans])
    st.dataframe(scan_costs, use_container_width=True, hide_index=True)
else:
    st.info("No scan data yet.")

# --- Agent Invocation Summary ---
st.subheader("Agent Activity Cost")
decisions = get_recent_decisions(limit=200)
if decisions:
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Decisions Logged", len(decisions))
    col2.metric("Diagnose Calls", sum(1 for d in decisions if "diagnos" in d.get("decision_type", "").lower()))
    col3.metric("Notifications Sent", sum(1 for d in decisions if "notif" in d.get("decision_type", "").lower()))

# --- Projected Monthly ---
st.subheader("Projected Monthly Cost")
st.markdown("""
| Component | Estimate |
|-----------|----------|
| Bedrock (Haiku 4.5) | ~$0.50/month at current usage |
| Athena | ~$2.50/scan × scans/month |
| DynamoDB | Free tier |
| CloudWatch | Free tier (10 custom metrics) |
| SNS | Free tier |
""")
