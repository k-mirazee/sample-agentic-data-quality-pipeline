"""Athena query execution and result parsing."""

import os
import time

import boto3

REGION = os.getenv("AWS_REGION", "us-east-1")
WORKGROUP = os.getenv("ATHENA_WORKGROUP", "dq-agent-workgroup")
DATABASE = os.getenv("GLUE_DATABASE", "dq_agent_demo")

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("athena", region_name=REGION)
    return _client


def run_query(sql: str, database: str | None = None) -> list[dict]:
    """Execute an Athena SQL query and return results as list of dicts.

    Polls until complete, then parses the result set into
    [{column_name: value, ...}, ...] with type coercion.
    """
    client = _get_client()
    db = database or DATABASE

    resp = client.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": db},
        WorkGroup=WORKGROUP,
    )
    query_id = resp["QueryExecutionId"]

    # Poll for completion
    while True:
        status = client.get_query_execution(QueryExecutionId=query_id)
        state = status["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(1)

    if state != "SUCCEEDED":
        reason = status["QueryExecution"]["Status"].get("StateChangeReason", "Unknown")
        raise RuntimeError(f"Athena query {state}: {reason}")

    # Get bytes scanned for cost tracking
    stats = status["QueryExecution"].get("Statistics", {})
    bytes_scanned = stats.get("DataScannedInBytes", 0)

    # Fetch results (paginated)
    rows = []
    columns = None
    paginator = client.get_paginator("get_query_results")
    for page in paginator.paginate(QueryExecutionId=query_id):
        result_rows = page["ResultSet"]["Rows"]
        if not result_rows:
            continue
        if columns is None:
            # First row is header
            columns = [col.get("VarCharValue", f"col_{i}") for i, col in enumerate(result_rows[0]["Data"])]
            result_rows = result_rows[1:]
        for row in result_rows:
            record = {}
            for i, cell in enumerate(row["Data"]):
                val = cell.get("VarCharValue")
                record[columns[i]] = _coerce(val)
            rows.append(record)

    return rows, bytes_scanned


def _coerce(val: str | None):
    """Best-effort type coercion from Athena string results."""
    if val is None or val == "":
        return None
    try:
        if "." in val:
            return float(val)
        return int(val)
    except (ValueError, TypeError):
        return val
