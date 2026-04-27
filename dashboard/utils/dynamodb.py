"""DynamoDB query helpers for the Streamlit dashboard."""

import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

REGION = os.getenv("AWS_REGION", "us-east-1")
TABLE_SCAN_RESULTS = os.getenv("DDB_TABLE_SCAN_RESULTS", "quality-scan-results")
TABLE_DECISIONS = os.getenv("DDB_TABLE_DECISIONS", "agent-decisions")
TABLE_BASELINES = os.getenv("DDB_TABLE_BASELINES", "schema-baselines")
TABLE_REMEDIATION = os.getenv("DDB_TABLE_REMEDIATION", "remediation-history")

_resource = None


def _get_table(name: str):
    global _resource
    if _resource is None:
        _resource = boto3.resource("dynamodb", region_name=REGION)
    return _resource.Table(name)


def _deserialize(obj):
    """Convert Decimals back to floats for display."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _deserialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deserialize(i) for i in obj]
    return obj


def get_recent_scans(table_name: str, partition: str, limit: int = 20) -> list[dict]:
    resp = _get_table(TABLE_SCAN_RESULTS).query(
        KeyConditionExpression=Key("PK").eq(f"{table_name}#{partition}"),
        ScanIndexForward=False, Limit=limit,
    )
    return [_deserialize(i) for i in resp.get("Items", [])]


def get_all_scans(limit: int = 100) -> list[dict]:
    resp = _get_table(TABLE_SCAN_RESULTS).scan(Limit=limit)
    return sorted([_deserialize(i) for i in resp.get("Items", [])], key=lambda x: x.get("SK", ""), reverse=True)


def get_recent_decisions(limit: int = 50) -> list[dict]:
    resp = _get_table(TABLE_DECISIONS).scan(Limit=limit)
    return sorted([_deserialize(i) for i in resp.get("Items", [])], key=lambda x: x.get("SK", ""), reverse=True)


def get_remediation_history(table_name: str | None = None, limit: int = 50) -> list[dict]:
    if table_name:
        # Can't query without full PK, so scan with filter
        resp = _get_table(TABLE_REMEDIATION).scan(
            FilterExpression=boto3.dynamodb.conditions.Attr("table_name").eq(table_name) if table_name else None,
            Limit=limit,
        )
    else:
        resp = _get_table(TABLE_REMEDIATION).scan(Limit=limit)
    return sorted([_deserialize(i) for i in resp.get("Items", [])], key=lambda x: x.get("SK", ""), reverse=True)


def get_all_remediations(limit: int = 100) -> list[dict]:
    resp = _get_table(TABLE_REMEDIATION).scan(Limit=limit)
    return sorted([_deserialize(i) for i in resp.get("Items", [])], key=lambda x: x.get("SK", ""), reverse=True)
