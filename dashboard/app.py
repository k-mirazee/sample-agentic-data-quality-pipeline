"""Data Quality Agent Dashboard — main Streamlit app."""

import streamlit as st

st.set_page_config(page_title="DQ Agent Dashboard", page_icon="🤖", layout="wide")

st.title("🤖 Data Quality Agent Dashboard")
st.markdown(
    "Real-time observability for the autonomous Data Quality Guardian agent. "
    "Select a page from the sidebar to explore scan results, agent traces, costs, and remediation history."
)

st.sidebar.success("Select a page above.")

st.markdown("---")
col1, col2, col3 = st.columns(3)
col1.info("**📊 Overview** — Quality scores, anomalies, activity feed")
col2.info("**🔍 Scan Details** — Drill into quality dimensions")
col3.info("**🧠 Agent Traces** — Reasoning flow and tool calls")

col4, col5, _ = st.columns(3)
col4.info("**💰 Cost Tracker** — Token spend and Athena costs")
col5.info("**🔧 Remediation** — Actions taken and before/after scores")
