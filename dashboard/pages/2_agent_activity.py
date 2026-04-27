"""Page 2: Agent Activity — Decision timeline with reasoning."""

import json

import streamlit as st
import pandas as pd

from dashboard.utils.dynamodb import get_recent_decisions

st.set_page_config(page_title="Agent Activity", page_icon="🧠", layout="wide")
st.title("🧠 Agent Activity")

decisions = get_recent_decisions(limit=100)
if not decisions:
    st.info("No agent activity yet. Go to Control Panel and run a scan.")
    st.stop()

# --- Stats ---
col1, col2, col3 = st.columns(3)
col1.metric("Total Decisions", len(decisions))
types = pd.Series([d.get("decision_type", "") for d in decisions])
col2.metric("Decision Types", types.nunique())
col3.metric("Tables Scanned", pd.Series([d.get("table_name", "") for d in decisions]).nunique())

# --- Filter ---
all_types = ["All"] + sorted(types.unique().tolist())
selected_type = st.selectbox("Filter by type", all_types)

filtered = decisions if selected_type == "All" else [d for d in decisions if d.get("decision_type") == selected_type]

# --- Timeline ---
for d in filtered[:30]:
    ts = d.get("SK", "")[:19]
    dtype = d.get("decision_type", "")
    icon = {
        "scan_initiated": "🔍",
        "violation_detected": "⚠️",
        "remediation_executed": "🔒",
        "notification_sent": "📨",
    }.get(dtype, "📝")

    with st.expander(f"{icon} **{dtype}** — {ts}"):
        st.write(f"**Reasoning:** {d.get('reasoning', 'N/A')}")
        st.write(f"**Action:** {d.get('action_taken', 'N/A')}")
        st.write(f"**Outcome:** {d.get('outcome', 'N/A')}")
