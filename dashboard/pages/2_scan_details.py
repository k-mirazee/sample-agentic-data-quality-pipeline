"""Page 2: Scan Details — Drill into quality dimensions for a specific scan."""

import json

import streamlit as st
import pandas as pd

from dashboard.utils.dynamodb import get_all_scans

st.set_page_config(page_title="Scan Details", page_icon="🔍", layout="wide")
st.title("🔍 Scan Details")

scans = get_all_scans(limit=50)
if not scans:
    st.info("No scan results yet. Run the agent to generate data.")
    st.stop()

# --- Scan Selector ---
scan_options = {f"{s.get('SK', '')[:19]} | {s.get('table', '')} | Score: {s.get('overall_score', 'N/A')}": s for s in scans}
selected_label = st.selectbox("Select a scan", list(scan_options.keys()))
scan = scan_options[selected_label]

# --- Header ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("Overall Score", f"{scan.get('overall_score', 0)}/100")
col2.metric("Status", scan.get("overall_status", ""))
col3.metric("Violations", scan.get("violation_count", 0))
col4.metric("Duration", f"{scan.get('scan_duration_ms', 0)}ms")

st.markdown("---")

# --- Dimension Breakdown ---
st.subheader("Quality Dimensions")
dimensions = scan.get("dimensions", {})
if dimensions:
    dim_df = pd.DataFrame([
        {"Dimension": name, "Score": d.get("score", 0), "Status": d.get("status", ""),
         "Violations": len(d.get("violations", []))}
        for name, d in dimensions.items()
    ])
    st.dataframe(dim_df, use_container_width=True, hide_index=True)

    # Bar chart of scores
    st.bar_chart(dim_df.set_index("Dimension")["Score"])

# --- Violation Details ---
st.subheader("Violation Details")
for dim_name, dim in dimensions.items():
    violations = dim.get("violations", [])
    if violations:
        with st.expander(f"**{dim_name}** — {len(violations)} violation(s)"):
            for v in violations:
                st.json(v)

# --- Raw Scan Data ---
with st.expander("Raw scan data"):
    st.json(json.loads(json.dumps(scan, default=str)))
