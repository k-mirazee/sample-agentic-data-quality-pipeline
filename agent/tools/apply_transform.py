"""apply_transform — Apply corrective transformations and promote to curated zone."""

import json
import os

from strands import tool

try:
    from agent.utils import athena_client, dynamodb_client, metrics
except ImportError:
    from utils import athena_client, dynamodb_client, metrics

DATABASE = os.getenv("GLUE_DATABASE", "dq_agent_demo")
S3_BUCKET = os.getenv("S3_BUCKET", "dq-agent-demo-015331669295")


def _build_transform_sql(table: str, where: str, transform_type: str, config: dict) -> str:
    """Build the SELECT statement for the transform."""
    if transform_type == "fill_nulls":
        coalesces = []
        for col, fill in config.get("columns", {}).items():
            if fill == "median":
                coalesces.append(f"COALESCE({col}, APPROX_PERCENTILE({col}, 0.5) OVER ()) AS {col}")
            else:
                coalesces.append(f"COALESCE({col}, {fill}) AS {col}")
        # Select transformed columns + all others
        return f"SELECT *, {', '.join(coalesces)} FROM {DATABASE}.{table} WHERE {where}"

    if transform_type == "clip_outliers":
        clips = []
        for col, bounds in config.get("columns", {}).items():
            clips.append(
                f"GREATEST({bounds['min']}, LEAST({bounds['max']}, {col})) AS {col}_clipped"
            )
        return f"SELECT *, {', '.join(clips)} FROM {DATABASE}.{table} WHERE {where}"

    if transform_type == "deduplicate":
        keys = config.get("key_columns", [])
        key_str = ", ".join(keys)
        return (
            f"SELECT * FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY {key_str} ORDER BY tpep_pickup_datetime) AS rn "
            f"FROM {DATABASE}.{table} WHERE {where}) WHERE rn = 1"
        )

    if transform_type == "rename_columns":
        aliases = [f"{old} AS {new}" for old, new in config.get("mapping", {}).items()]
        return f"SELECT *, {', '.join(aliases)} FROM {DATABASE}.{table} WHERE {where}"

    # Default: pass-through (filter only)
    return f"SELECT * FROM {DATABASE}.{table} WHERE {where}"


@tool
def apply_transform(table_name: str, partition: str, transform_type: str, transform_config: dict) -> str:
    """Apply corrective transformations to fix data quality issues and promote to curated zone.

    Executes an Athena CTAS/UNLOAD to write transformed data to the curated S3 path.

    Args:
        table_name: Source table name (e.g. 'raw_yellow_taxi')
        partition: Partition spec (e.g. 'year=2024/month=01')
        transform_type: One of: fill_nulls, clip_outliers, deduplicate, rename_columns
        transform_config: Transform-specific parameters. Examples:
            fill_nulls: {"columns": {"passenger_count": 1, "fare_amount": "median"}}
            clip_outliers: {"columns": {"fare_amount": {"min": 0, "max": 500}}}
            deduplicate: {"key_columns": ["VendorID", "tpep_pickup_datetime", "PULocationID"]}
            rename_columns: {"mapping": {"fare_amt": "fare_amount"}}

    Returns:
        JSON with records_transformed, output_path, and transform details.
    """
    parts = partition.split("/")
    where = " AND ".join(f"{p.split('=')[0]}='{p.split('=')[1]}'" for p in parts)

    import uuid as _uuid
    run_ts = _uuid.uuid4().hex[:8]
    curated_table = table_name.replace("raw_", "curated_")
    output_path = f"s3://{S3_BUCKET}/curated/{table_name.replace('raw_', '')}/{partition}/{run_ts}/"

    # Count source records
    count_sql = f"SELECT COUNT(*) AS cnt FROM {DATABASE}.{table_name} WHERE {where}"
    rows, _ = athena_client.run_query(count_sql)
    source_count = rows[0]["cnt"] if rows else 0

    # Build and execute transform
    select_sql = _build_transform_sql(table_name, where, transform_type, transform_config)
    unload_sql = f"UNLOAD ({select_sql}) TO '{output_path}' WITH (format = 'PARQUET')"
    athena_client.run_query(unload_sql)

    # Record remediation
    dynamodb_client.put_remediation(
        table_name=table_name,
        partition=partition,
        issue_id=f"transform-{transform_type}",
        action_type="transform",
        records_affected=source_count,
        before_score=0.0,
        after_score=0.0,
        details={"transform_type": transform_type, "config": transform_config, "output_path": output_path},
    )

    metrics.put_remediation_action(table_name, f"transform_{transform_type}")
    metrics.put_metric("RecordsTransformed", source_count, "Count", {"TableName": table_name})

    return json.dumps({
        "records_transformed": source_count,
        "output_path": output_path,
        "transform_type": transform_type,
        "curated_table": curated_table,
    })
