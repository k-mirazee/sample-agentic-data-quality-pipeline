"""Page 3: Agent Traces — Timeline of agent reasoning, tool calls, and decisions."""

import json

import streamlit as st
import pandas as pd

from dashboard.utils.dynamodb import get_recent_decisions

st.set_page_config(page_title="Agent Traces", page_icon="🧠", layout="wide")
st.title("🧠 Agent Traces")

decisions = get_recent_decisions(limit=100)
if not decisions:
    st.info("No agent decisions yet. Run the agent to generate traces.")
    st.stop()

# --- Timeline ---
st.subheader("Decision Timeline")
timeline_df = pd.DataFrame([{
    "Timestamp": d.get("SK", "")[:19],
    "Type": d.get("decision_type", ""),
    "Table": d.get("table_name", ""),
    "Action": d.get("action_taken", "")[:80],
} for d in decisions])
st.dataframe(timeline_df, use_container_width=True, hide_index=True)

# --- Decision Type Distribution ---
st.subheader("Decision Types")
if not timeline_df.empty:
    type_counts = timeline_df["Type"].value_counts()
    st.bar_chart(type_counts)

# --- Decision Detail Viewer ---
st.subheader("Decision Details")
for d in decisions[:20]:
    ts = d.get("SK", "")[:19]
    dtype = d.get("decision_type", "")
    with st.expander(f"**{dtype}** — {ts}"):
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Reasoning:**")
            st.write(d.get("reasoning", "N/A"))
        with col2:
            st.write("**Action Taken:**")
            st.write(d.get("action_taken", "N/A"))
            st.write("**Outcome:**")
            st.write(d.get("outcome", "N/A"))

        ctx = d.get("context", {})
        if ctx:
            with st.expander("Context"):
                st.json(json.loads(json.dumps(ctx, default=str)))

# --- Stats ---
st.markdown("---")
col1, col2, col3 = st.columns(3)
col1.metric("Total Decisions", len(decisions))
col2.metric("Unique Types", timeline_df["Type"].nunique() if not timeline_df.empty else 0)
col3.metric("Tables Covered", timeline_df["Table"].nunique() if not timeline_df.empty else 0)
