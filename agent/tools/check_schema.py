"""check_schema — Compare current Glue table schema against stored baseline."""

import json
import os
from difflib import SequenceMatcher
from pathlib import Path

import boto3
from strands import tool

from agent.utils import dynamodb_client

REGION = os.getenv("AWS_REGION", "us-east-1")
DATABASE = os.getenv("GLUE_DATABASE", "dq_agent_demo")

_glue = None


def _get_glue():
    global _glue
    if _glue is None:
        _glue = boto3.client("glue", region_name=REGION)
    return _glue


def _load_file_baseline(table_name: str) -> list[dict] | None:
    """Load baseline from local JSON file as fallback."""
    # Map table names to baseline files
    name = table_name.replace("raw_", "").replace("staging_", "").replace("curated_", "").replace("quarantine_", "")
    path = Path(__file__).parent.parent / "config" / "schema_baselines" / f"{name}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)["columns"]
    return None


def _get_baseline(database: str, table_name: str) -> list[dict]:
    """Get baseline from DDB, falling back to file, auto-seeding DDB if needed."""
    stored = dynamodb_client.get_baseline(database, table_name)
    if stored:
        return stored["columns"]

    # Fallback to file
    file_cols = _load_file_baseline(table_name)
    if file_cols:
        dynamodb_client.put_baseline(database, table_name, file_cols, created_by="file_seed")
        return file_cols

    return []


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


@tool
def check_schema(database: str, table_name: str) -> str:
    """Compare the current Glue Catalog table schema against a stored baseline to detect drift.

    Detects added columns, removed columns, type changes, and possible renames.
    Flags breaking changes (removals, type changes) vs non-breaking (additions).

    Args:
        database: Glue database name (e.g. 'dq_agent_demo')
        table_name: Glue table name (e.g. 'raw_yellow_taxi')

    Returns:
        JSON schema diff with added/removed/renamed/type-changed columns and breaking change flag.
    """
    # Get current schema from Glue
    resp = _get_glue().get_table(DatabaseName=database, Name=table_name)
    current_cols = [
        {"name": c["Name"], "type": c["Type"]}
        for c in resp["Table"]["StorageDescriptor"]["Columns"]
    ]

    # Get baseline
    baseline_cols = _get_baseline(database, table_name)
    if not baseline_cols:
        # No baseline — auto-generate from current and return clean
        dynamodb_client.put_baseline(database, table_name, current_cols, created_by="auto_generated")
        return json.dumps({
            "is_breaking_change": False,
            "added_columns": [], "removed_columns": [], "renamed_columns": [], "type_changes": [],
            "note": "No baseline existed. Current schema saved as v1.",
            "current_column_count": len(current_cols),
        })

    current_map = {c["name"]: c["type"] for c in current_cols}
    baseline_map = {c["name"]: c["type"] for c in baseline_cols}

    current_names = set(current_map.keys())
    baseline_names = set(baseline_map.keys())

    added_names = current_names - baseline_names
    removed_names = baseline_names - current_names

    # Detect renames (removed + added with similar names)
    renamed = []
    used_added = set()
    for rem in list(removed_names):
        best_match, best_score = None, 0
        for add in added_names - used_added:
            score = _similarity(rem, add)
            if score > best_score and score > 0.6:
                best_match, best_score = add, score
        if best_match:
            renamed.append({"from": rem, "to": best_match, "confidence": round(best_score, 2)})
            removed_names.discard(rem)
            used_added.add(best_match)

    added = [{"name": n, "type": current_map[n]} for n in added_names - used_added]
    removed = [{"name": n, "type": baseline_map[n]} for n in removed_names]

    # Type changes (columns present in both)
    type_changes = []
    for name in current_names & baseline_names:
        if current_map[name] != baseline_map[name]:
            type_changes.append({"column": name, "from": baseline_map[name], "to": current_map[name]})

    is_breaking = bool(removed or type_changes)

    result = {
        "is_breaking_change": is_breaking,
        "added_columns": added,
        "removed_columns": removed,
        "renamed_columns": renamed,
        "type_changes": type_changes,
        "current_column_count": len(current_cols),
        "baseline_column_count": len(baseline_cols),
    }

    return json.dumps(result, default=str)
