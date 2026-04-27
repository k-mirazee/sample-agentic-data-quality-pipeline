"""Page 1: Overview — Quality scores, anomalies timeline, agent activity feed."""

import streamlit as st
import pandas as pd

from dashboard.utils.dynamodb import get_all_scans, get_recent_decisions
from dashboard.utils.cloudwatch import get_alarm_states

st.set_page_config(page_title="Overview", page_icon="📊", layout="wide")
st.title("📊 Overview")

# --- Alarm Status ---
st.subheader("🚨 Alarm Status")
alarms = get_alarm_states()
if alarms:
    cols = st.columns(len(alarms))
    for i, alarm in enumerate(alarms):
        color = {"OK": "🟢", "ALARM": "🔴", "INSUFFICIENT_DATA": "⚪"}.get(alarm["state"], "⚪")
        cols[i].metric(alarm["name"].replace("DqAgent-", ""), f"{color} {alarm['state']}")
else:
    st.info("No alarms found.")

# --- Recent Scans ---
st.subheader("📈 Recent Quality Scans")
scans = get_all_scans(limit=50)
if scans:
    scan_df = pd.DataFrame([{
        "Timestamp": s.get("SK", ""),
        "Table": s.get("table", s.get("PK", "").split("#")[0]),
        "Partition": s.get("partition", ""),
        "Score": s.get("overall_score", 0),
        "Status": s.get("overall_status", ""),
        "Violations": s.get("violation_count", 0),
    } for s in scans])
    st.dataframe(scan_df, use_container_width=True, hide_index=True)

    # Score chart
    if len(scan_df) > 1:
        st.line_chart(scan_df.set_index("Timestamp")["Score"])
else:
    st.info("No scan results yet. Run the agent to generate data.")

# --- Agent Activity Feed ---
st.subheader("🤖 Agent Activity Feed")
decisions = get_recent_decisions(limit=20)
if decisions:
    for d in decisions[:10]:
        with st.expander(f"**{d.get('decision_type', '')}** — {d.get('SK', '')[:19]}"):
            st.write(f"**Table:** {d.get('table_name', '')}")
            st.write(f"**Action:** {d.get('action_taken', '')}")
            st.write(f"**Reasoning:** {d.get('reasoning', '')}")
            st.write(f"**Outcome:** {d.get('outcome', '')}")
else:
    st.info("No agent decisions yet.")

# --- Summary Stats ---
st.subheader("📋 Summary")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Scans", len(scans))
col2.metric("Total Decisions", len(decisions))
col3.metric("Avg Score", f"{sum(s.get('overall_score', 0) for s in scans) / max(len(scans), 1):.1f}" if scans else "N/A")
col4.metric("Active Alarms", sum(1 for a in alarms if a["state"] == "ALARM"))
