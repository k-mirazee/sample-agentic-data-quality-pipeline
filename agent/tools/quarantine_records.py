"""quarantine_records — Move bad records to quarantine zone via Athena CTAS."""

import json
import os
import uuid

from strands import tool

from agent.utils import athena_client, dynamodb_client, metrics

DATABASE = os.getenv("GLUE_DATABASE", "dq_agent_demo")
S3_BUCKET = os.getenv("S3_BUCKET", "dq-agent-demo-015331669295")


@tool
def quarantine_records(table_name: str, partition: str, filter_condition: str, issue_id: str | None = None) -> str:
    """Move bad records from source to quarantine zone, isolating them from downstream consumers.

    Uses Athena UNLOAD to write matching records to the quarantine S3 path,
    then records the action in remediation history.

    Args:
        table_name: Source table name (e.g. 'raw_yellow_taxi')
        partition: Partition spec (e.g. 'year=2024/month=01')
        filter_condition: SQL WHERE clause identifying bad records (e.g. 'fare_amount < 0 OR fare_amount > 500')
        issue_id: Optional UUID for tracking. Auto-generated if not provided.

    Returns:
        JSON with records_quarantined count, quarantine_path, and remaining_records count.
    """
    issue_id = issue_id or str(uuid.uuid4())
    parts = partition.split("/")
    where = " AND ".join(f"{p.split('=')[0]}='{p.split('=')[1]}'" for p in parts)
    run_ts = uuid.uuid4().hex[:8]
    quarantine_path = f"s3://{S3_BUCKET}/quarantine/{table_name}/{partition}/issue_id={issue_id}/{run_ts}/"

    # Count bad records first
    count_sql = f"SELECT COUNT(*) AS cnt FROM {DATABASE}.{table_name} WHERE {where} AND ({filter_condition})"
    rows, _ = athena_client.run_query(count_sql)
    bad_count = rows[0]["cnt"] if rows else 0

    if bad_count == 0:
        return json.dumps({"records_quarantined": 0, "message": "No records match filter condition"})

    # Count total records
    total_sql = f"SELECT COUNT(*) AS cnt FROM {DATABASE}.{table_name} WHERE {where}"
    total_rows, _ = athena_client.run_query(total_sql)
    total_count = total_rows[0]["cnt"] if total_rows else 0

    # UNLOAD bad records to quarantine path
    unload_sql = (
        f"UNLOAD (SELECT * FROM {DATABASE}.{table_name} WHERE {where} AND ({filter_condition})) "
        f"TO '{quarantine_path}' WITH (format = 'PARQUET')"
    )
    athena_client.run_query(unload_sql)

    # Record in remediation history
    dynamodb_client.put_remediation(
        table_name=table_name,
        partition=partition,
        issue_id=issue_id,
        action_type="quarantine",
        records_affected=bad_count,
        before_score=0.0,
        after_score=0.0,
        details={"filter_condition": filter_condition, "quarantine_path": quarantine_path},
    )

    metrics.put_remediation_action(table_name, "quarantine")
    metrics.put_metric("RecordsQuarantined", bad_count, "Count", {"TableName": table_name})

    return json.dumps({
        "records_quarantined": bad_count,
        "remaining_records": total_count - bad_count,
        "quarantine_path": quarantine_path,
        "issue_id": issue_id,
    })
