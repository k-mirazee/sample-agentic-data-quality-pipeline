"""Data Quality Agent Dashboard — main Streamlit app."""

import streamlit as st

st.set_page_config(page_title="DQ Agent", page_icon="🤖", layout="wide")

st.title("🤖 Data Quality Agent")
st.markdown(
    "Autonomous data quality monitoring powered by Strands Agents and Amazon Bedrock AgentCore. "
    "Select a page from the sidebar."
)

st.markdown("---")
col1, col2, col3 = st.columns(3)
col1.info("**🎮 Control Panel**\n\nRun scans, inject chaos, restore data")
col2.info("**📊 Dashboard**\n\nQuality scores, violations, quarantine status")
col3.info("**🧠 Agent Activity**\n\nDecision timeline with reasoning")
