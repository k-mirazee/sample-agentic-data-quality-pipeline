"""CloudWatch custom metric emission for the Data Quality Agent."""

import os

import boto3

REGION = os.getenv("AWS_REGION", "us-east-1")
NAMESPACE = "DataQualityAgent"

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("cloudwatch", region_name=REGION)
    return _client


def put_metric(name: str, value: float, unit: str = "None", dimensions: dict | None = None):
    """Emit a single CloudWatch metric."""
    dims = [{"Name": k, "Value": str(v)} for k, v in (dimensions or {}).items()]
    _get_client().put_metric_data(
        Namespace=NAMESPACE,
        MetricData=[{"MetricName": name, "Value": value, "Unit": unit, "Dimensions": dims}],
    )


def put_quality_score(table_name: str, check_type: str, score: float):
    put_metric("QualityScore", score, "Percent", {"TableName": table_name, "CheckType": check_type})


def put_overall_score(table_name: str, score: float):
    put_metric("OverallQualityScore", score, "Percent", {"TableName": table_name})


def put_anomalies(table_name: str, severity: str, count: int):
    put_metric("AnomaliesDetected", count, "Count", {"TableName": table_name, "Severity": severity})


def put_remediation_action(table_name: str, action_type: str):
    put_metric("RemediationActions", 1, "Count", {"TableName": table_name, "ActionType": action_type})


def put_token_cost(model_id: str, cost_usd: float):
    put_metric("AgentTokenCost", cost_usd, "None", {"ModelId": model_id})


def put_tool_duration(tool_name: str, duration_ms: float):
    put_metric("ToolCallDuration", duration_ms, "Milliseconds", {"ToolName": tool_name})
