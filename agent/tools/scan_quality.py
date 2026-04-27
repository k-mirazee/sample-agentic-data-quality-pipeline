"""scan_quality — Run data quality checks on a table partition via Athena."""

import json
import os
import time
from pathlib import Path

import yaml
from strands import tool

try:
    from agent.utils import athena_client, dynamodb_client, metrics
except ImportError:
    from utils import athena_client, dynamodb_client, metrics

DATABASE = os.getenv("GLUE_DATABASE", "dq_agent_demo")

# Load thresholds
_cfg_path = Path(__file__).parent.parent / "config" / "quality_thresholds.yaml"
with open(_cfg_path) as f:
    THRESHOLDS = yaml.safe_load(f)["thresholds"]


def _status(score: float) -> str:
    if score >= 95:
        return "OK"
    if score >= 80:
        return "WARNING"
    return "CRITICAL"


def _check_completeness(table: str, partition: str) -> dict:
    """Check null rates for required columns."""
    cols = THRESHOLDS["completeness"]["required_columns"]
    parts = partition.split("/")
    where = " AND ".join(f"{p.split('=')[0]}='{p.split('=')[1]}'" for p in parts)

    col_exprs = ", ".join(
        f"COUNT(*) - COUNT({c}) AS {c}_nulls, "
        f"ROUND((COUNT(*) - COUNT({c})) * 100.0 / COUNT(*), 2) AS {c}_null_pct"
        for c in cols
    )
    sql = f"SELECT COUNT(*) AS total_rows, {col_exprs} FROM {DATABASE}.{table} WHERE {where}"
    rows, _ = athena_client.run_query(sql)
    if not rows:
        return {"score": 0, "status": "CRITICAL", "violations": [], "error": "No data returned"}

    row = rows[0]
    total = row.get("total_rows", 0)
    violations = []
    worst_pct = 0.0

    for c in cols:
        null_pct = row.get(f"{c}_null_pct", 0) or 0
        if null_pct > THRESHOLDS["completeness"]["warning"]:
            violations.append({"column": c, "null_pct": null_pct,
                               "threshold": THRESHOLDS["completeness"]["critical"]})
        worst_pct = max(worst_pct, null_pct)

    score = max(0, 100 - worst_pct * 2)
    return {"score": round(score, 1), "status": _status(score), "violations": violations, "row_count": total}


def _check_freshness(table: str, partition: str) -> dict:
    """Check data staleness via max timestamp."""
    parts = partition.split("/")
    where = " AND ".join(f"{p.split('=')[0]}='{p.split('=')[1]}'" for p in parts)

    sql = f"SELECT MAX(tpep_pickup_datetime) AS latest FROM {DATABASE}.{table} WHERE {where}"
    rows, _ = athena_client.run_query(sql)
    if not rows or not rows[0].get("latest"):
        return {"score": 0, "status": "CRITICAL", "violations": [{"issue": "no timestamp data"}]}

    from datetime import datetime, timezone
    latest_str = rows[0]["latest"]
    latest = datetime.fromisoformat(latest_str.replace(" ", "T"))
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    staleness_hours = (datetime.now(timezone.utc) - latest).total_seconds() / 3600

    violations = []
    if staleness_hours > THRESHOLDS["freshness"]["critical_hours"]:
        violations.append({"staleness_hours": round(staleness_hours, 1), "threshold": "critical"})
    elif staleness_hours > THRESHOLDS["freshness"]["warning_hours"]:
        violations.append({"staleness_hours": round(staleness_hours, 1), "threshold": "warning"})

    # Score: 100 if fresh, degrades with staleness
    score = max(0, 100 - (staleness_hours / THRESHOLDS["freshness"]["critical_hours"]) * 100)
    return {"score": round(score, 1), "status": _status(score), "violations": violations,
            "latest_record": latest_str, "staleness_hours": round(staleness_hours, 1)}


def _check_distribution(table: str, partition: str) -> dict:
    """Check numeric column distributions against expected bounds."""
    parts = partition.split("/")
    where = " AND ".join(f"{p.split('=')[0]}='{p.split('=')[1]}'" for p in parts)

    # Check numeric bounded columns
    bounded = {k: v for k, v in THRESHOLDS["distribution"].items() if "min" in v}
    if not bounded:
        return {"score": 100, "status": "OK", "violations": []}

    checks = []
    for col, bounds in bounded.items():
        checks.append(
            f"SUM(CASE WHEN {col} < {bounds['min']} OR {col} > {bounds['max']} THEN 1 ELSE 0 END) AS {col}_outliers, "
            f"MIN({col}) AS {col}_min, MAX({col}) AS {col}_max"
        )

    sql = f"SELECT COUNT(*) AS total, {', '.join(checks)} FROM {DATABASE}.{table} WHERE {where}"
    rows, _ = athena_client.run_query(sql)
    if not rows:
        return {"score": 0, "status": "CRITICAL", "violations": []}

    row = rows[0]
    total = row.get("total", 1)
    violations = []
    worst_ratio = 0.0

    for col, bounds in bounded.items():
        outliers = row.get(f"{col}_outliers", 0) or 0
        ratio = outliers / total if total else 0
        if ratio > 0.01:  # >1% outliers
            violations.append({
                "column": col, "outlier_count": outliers, "outlier_pct": round(ratio * 100, 2),
                "min_found": row.get(f"{col}_min"), "max_found": row.get(f"{col}_max"),
                "expected_min": bounds["min"], "expected_max": bounds["max"],
            })
        worst_ratio = max(worst_ratio, ratio)

    score = max(0, 100 - worst_ratio * 200)
    return {"score": round(score, 1), "status": _status(score), "violations": violations}


@tool
def scan_quality(table_name: str, partition: str, check_types: list[str] | None = None) -> str:
    """Run data quality checks on a table partition and return a quality report.

    Executes completeness, freshness, and distribution checks via Athena SQL queries.
    Results are scored 0-100 per dimension and stored in DynamoDB.

    Args:
        table_name: Glue Catalog table name (e.g. 'raw_yellow_taxi')
        partition: Partition spec (e.g. 'year=2024/month=01')
        check_types: Optional subset of checks. Default: all. Options: completeness, freshness, distribution

    Returns:
        JSON quality report with overall score, per-dimension scores, and violations.
    """
    start = time.time()
    checks = check_types or ["completeness", "freshness", "distribution"]
    dimensions = {}
    total_bytes = 0

    if "completeness" in checks:
        dimensions["completeness"] = _check_completeness(table_name, partition)

    if "freshness" in checks:
        dimensions["freshness"] = _check_freshness(table_name, partition)

    if "distribution" in checks:
        dimensions["distribution"] = _check_distribution(table_name, partition)

    # Compute overall score (average of dimension scores)
    scores = [d["score"] for d in dimensions.values()]
    overall_score = round(sum(scores) / len(scores), 1) if scores else 0
    overall_status = _status(overall_score)

    # Count violations
    all_violations = []
    for dim_name, dim in dimensions.items():
        for v in dim.get("violations", []):
            v["dimension"] = dim_name
            all_violations.append(v)

    report = {
        "table": table_name,
        "partition": partition,
        "overall_score": overall_score,
        "overall_status": overall_status,
        "dimensions": dimensions,
        "violation_count": len(all_violations),
        "scan_duration_ms": round((time.time() - start) * 1000),
    }

    # Persist to DynamoDB
    dynamodb_client.put_scan_result(table_name, partition, report)

    # Emit CloudWatch metrics
    metrics.put_overall_score(table_name, overall_score)
    for dim_name, dim in dimensions.items():
        metrics.put_quality_score(table_name, dim_name, dim["score"])
    if all_violations:
        metrics.put_anomalies(table_name, overall_status, len(all_violations))

    return json.dumps(report, default=str)
