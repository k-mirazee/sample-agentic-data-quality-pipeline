"""DynamoDB read/write helpers for the 4 agent tables."""

import os
import time
import uuid
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

REGION = os.getenv("AWS_REGION", "us-east-1")
TABLE_SCAN_RESULTS = os.getenv("DDB_TABLE_SCAN_RESULTS", "quality-scan-results")
TABLE_DECISIONS = os.getenv("DDB_TABLE_DECISIONS", "agent-decisions")
TABLE_BASELINES = os.getenv("DDB_TABLE_BASELINES", "schema-baselines")
TABLE_REMEDIATION = os.getenv("DDB_TABLE_REMEDIATION", "remediation-history")
TTL_DAYS = int(os.getenv("DATA_RETENTION_DAYS", "90"))

_resource = None


def _get_table(name: str):
    global _resource
    if _resource is None:
        _resource = boto3.resource("dynamodb", region_name=REGION)
    return _resource.Table(name)


def _ttl() -> int:
    return int(time.time()) + TTL_DAYS * 86400


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _sanitize(obj):
    """Convert floats to Decimal for DynamoDB."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(i) for i in obj]
    return obj


# --- Scan Results ---

def put_scan_result(table_name: str, partition: str, result: dict) -> dict:
    ts = _now_iso()
    item = {
        "PK": f"{table_name}#{partition}",
        "SK": ts,
        **_sanitize(result),
        "ttl": _ttl(),
    }
    _get_table(TABLE_SCAN_RESULTS).put_item(Item=item)
    return {"PK": item["PK"], "SK": ts}


def get_recent_scans(table_name: str, partition: str, limit: int = 5) -> list[dict]:
    resp = _get_table(TABLE_SCAN_RESULTS).query(
        KeyConditionExpression=Key("PK").eq(f"{table_name}#{partition}"),
        ScanIndexForward=False,
        Limit=limit,
    )
    return resp.get("Items", [])


# --- Decisions ---

def put_decision(decision_type: str, table_name: str, partition: str, context: dict,
                 reasoning: str, action_taken: str, outcome: str, **extra) -> dict:
    decision_id = str(uuid.uuid4())
    ts = _now_iso()
    item = {
        "PK": decision_id,
        "SK": ts,
        "decision_type": decision_type,
        "table_name": table_name,
        "partition": partition,
        "context": _sanitize(context),
        "reasoning": reasoning,
        "action_taken": action_taken,
        "outcome": outcome,
        "ttl": _ttl(),
        **_sanitize(extra),
    }
    _get_table(TABLE_DECISIONS).put_item(Item=item)
    return {"decision_id": decision_id, "timestamp": ts}


# --- Schema Baselines ---

def get_baseline(database: str, table_name: str) -> dict | None:
    resp = _get_table(TABLE_BASELINES).query(
        KeyConditionExpression=Key("PK").eq(f"{database}#{table_name}"),
        ScanIndexForward=False,
        Limit=1,
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def put_baseline(database: str, table_name: str, columns: list[dict], created_by: str = "agent") -> dict:
    # Auto-increment version
    existing = get_baseline(database, table_name)
    version = "v1"
    if existing:
        prev = existing.get("SK", "v0")
        num = int(prev.replace("v", "")) + 1
        version = f"v{num}"

    item = {
        "PK": f"{database}#{table_name}",
        "SK": version,
        "columns": columns,
        "created_at": _now_iso(),
        "created_by": created_by,
    }
    _get_table(TABLE_BASELINES).put_item(Item=item)
    return {"PK": item["PK"], "version": version}


# --- Remediation History ---

def put_remediation(table_name: str, partition: str, issue_id: str, action_type: str,
                    records_affected: int, before_score: float, after_score: float, details: dict) -> dict:
    ts = _now_iso()
    item = {
        "PK": f"{table_name}#{partition}",
        "SK": ts,
        "issue_id": issue_id,
        "action_type": action_type,
        "records_affected": records_affected,
        "before_score": _sanitize(before_score),
        "after_score": _sanitize(after_score),
        "details": _sanitize(details),
        "ttl": _ttl(),
    }
    _get_table(TABLE_REMEDIATION).put_item(Item=item)
    return {"PK": item["PK"], "SK": ts}
