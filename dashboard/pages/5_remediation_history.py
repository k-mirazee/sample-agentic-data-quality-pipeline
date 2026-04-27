"""Page 5: Remediation History — Timeline of agent actions, before/after scores."""

import json

import streamlit as st
import pandas as pd

from dashboard.utils.dynamodb import get_all_remediations

st.set_page_config(page_title="Remediation History", page_icon="🔧", layout="wide")
st.title("🔒 Quarantine & Remediation History")

remediations = get_all_remediations(limit=100)
if not remediations:
    st.info("No remediation actions yet. Run the agent with violations to generate data.")
    st.stop()

# --- Summary ---
col1, col2 = st.columns(2)
quarantines = [r for r in remediations if r.get("action_type") == "quarantine"]
col1.metric("Total Quarantine Actions", len(quarantines))
col2.metric("Total Records Isolated", f"{sum(r.get('records_affected', 0) for r in quarantines):,}")

# --- Timeline ---
st.subheader("Action Timeline")
rem_df = pd.DataFrame([{
    "Timestamp": r.get("SK", "")[:19],
    "Table": r.get("PK", "").split("#")[0],
    "Action": r.get("action_type", ""),
    "Records Isolated": r.get("records_affected", 0),
    "Issue ID": r.get("issue_id", "")[:20],
} for r in remediations])
st.dataframe(rem_df, use_container_width=True, hide_index=True)

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
