"""Page 1: Dashboard — Quality scores, violations, quarantine summary, alarms."""

import json

import streamlit as st
import pandas as pd

from dashboard.utils.dynamodb import get_all_scans, get_all_remediations, get_recent_decisions
from dashboard.utils.cloudwatch import get_alarm_states

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
st.title("📊 Dashboard")

# --- Check for recent failed scans (schema mismatch etc) ---
decisions = get_recent_decisions(limit=10)
recent_failures = [d for d in decisions if d.get("decision_type") in ("schema_check_initiated", "diagnosis_complete")
                   and "mismatch" in str(d.get("reasoning", "")).lower()]
if recent_failures:
    latest_failure = recent_failures[0]
    st.error(
        f"⚠️ **Latest scan failed — schema mismatch detected**\n\n"
        f"{latest_failure.get('reasoning', '')[:300]}\n\n"
        f"See **Agent Activity** for full details."
    )

# --- Alarm Status ---
alarms = get_alarm_states()
if alarms:
    cols = st.columns(len(alarms))
    for i, alarm in enumerate(alarms):
        color = {"OK": "🟢", "ALARM": "🔴", "INSUFFICIENT_DATA": "⚪"}.get(alarm["state"], "⚪")
        cols[i].metric(alarm["name"].replace("DqAgent-", ""), f"{color} {alarm['state']}")

# --- Latest Scan ---
scans = get_all_scans(limit=20)
if scans:
    latest = scans[0]
    st.subheader("Latest Scan")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Score", f"{latest.get('overall_score', 0)}/100")
    col2.metric("Status", latest.get("overall_status", ""))
    col3.metric("Violations", latest.get("violation_count", 0))
    col4.metric("Partition", latest.get("partition", ""))

    # Dimension breakdown
    dimensions = latest.get("dimensions", {})
    if dimensions:
        dim_df = pd.DataFrame([
            {"Dimension": name, "Score": d.get("score", 0), "Status": d.get("status", ""),
             "Violations": len(d.get("violations", []))}
            for name, d in dimensions.items()
        ])
        st.dataframe(dim_df, use_container_width=True, hide_index=True)

    # Violation details
    for dim_name, dim in dimensions.items():
        violations = dim.get("violations", [])
        if violations:
            with st.expander(f"**{dim_name}** — {len(violations)} violation(s)"):
                for v in violations:
                    st.json(v)

    # Scan history
    if len(scans) > 1:
        st.subheader("Scan History")
        hist_df = pd.DataFrame([{
            "Timestamp": s.get("SK", "")[:19],
            "Partition": s.get("partition", ""),
            "Score": s.get("overall_score", 0),
            "Status": s.get("overall_status", ""),
            "Violations": s.get("violation_count", 0),
        } for s in scans])
        st.dataframe(hist_df, use_container_width=True, hide_index=True)
else:
    st.info("No scan results yet. Go to Control Panel and run a scan.")

# --- Quarantine Summary ---
remediations = get_all_remediations(limit=50)
quarantines = [r for r in remediations if r.get("action_type") == "quarantine"]
if quarantines:
    st.subheader("🔒 Quarantined Records")
    total_quarantined = sum(r.get("records_affected", 0) for r in quarantines)
    col1, col2 = st.columns(2)
    col1.metric("Quarantine Actions", len(quarantines))
    col2.metric("Total Records Isolated", f"{total_quarantined:,}")

    q_df = pd.DataFrame([{
        "Timestamp": r.get("SK", "")[:19],
        "Records": r.get("records_affected", 0),
        "Issue": r.get("issue_id", "")[:20],
    } for r in quarantines])
    st.dataframe(q_df, use_container_width=True, hide_index=True)
