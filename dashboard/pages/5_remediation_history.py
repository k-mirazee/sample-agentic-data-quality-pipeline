"""Page 5: Remediation History — Timeline of agent actions, before/after scores."""

import json

import streamlit as st
import pandas as pd

from dashboard.utils.dynamodb import get_all_remediations

st.set_page_config(page_title="Remediation History", page_icon="🔧", layout="wide")
st.title("🔧 Remediation History")

remediations = get_all_remediations(limit=100)
if not remediations:
    st.info("No remediation actions yet. Run the agent with violations to generate data.")
    st.stop()

# --- Summary ---
col1, col2, col3 = st.columns(3)
col1.metric("Total Actions", len(remediations))
quarantines = [r for r in remediations if r.get("action_type") == "quarantine"]
transforms = [r for r in remediations if r.get("action_type") == "transform"]
col2.metric("Quarantines", len(quarantines))
col3.metric("Transforms", len(transforms))

# --- Timeline ---
st.subheader("Action Timeline")
rem_df = pd.DataFrame([{
    "Timestamp": r.get("SK", "")[:19],
    "Table": r.get("PK", "").split("#")[0],
    "Action": r.get("action_type", ""),
    "Records Affected": r.get("records_affected", 0),
    "Before Score": r.get("before_score", "N/A"),
    "After Score": r.get("after_score", "N/A"),
    "Issue ID": r.get("issue_id", "")[:12],
} for r in remediations])
st.dataframe(rem_df, use_container_width=True, hide_index=True)

# --- Before/After Comparison ---
scored = [r for r in remediations if r.get("before_score", 0) > 0 and r.get("after_score", 0) > 0]
if scored:
    st.subheader("Before/After Quality Scores")
    compare_df = pd.DataFrame([{
        "Action": f"{r.get('action_type', '')} ({r.get('SK', '')[:10]})",
        "Before": r.get("before_score", 0),
        "After": r.get("after_score", 0),
    } for r in scored])
    st.bar_chart(compare_df.set_index("Action"))

# --- Detail Viewer ---
st.subheader("Action Details")
for r in remediations[:15]:
    ts = r.get("SK", "")[:19]
    action = r.get("action_type", "")
    with st.expander(f"**{action}** — {ts} ({r.get('records_affected', 0)} records)"):
        details = r.get("details", {})
        if details:
            st.json(json.loads(json.dumps(details, default=str)))
        else:
            st.write("No additional details.")
