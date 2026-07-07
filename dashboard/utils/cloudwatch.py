"""CloudWatch alarm state helpers for the dashboard backend."""

import os
from datetime import datetime, timedelta, timezone

import boto3

REGION = os.getenv("AWS_REGION", "us-east-1")
NAMESPACE = "DataQualityAgent"

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("cloudwatch", region_name=REGION)
    return _client


def get_metric_data(metric_name: str, dimensions: dict | None = None,
                    hours: int = 24, stat: str = "Average", period: int = 300) -> list[dict]:
    """Fetch metric datapoints for the given time range."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    dims = [{"Name": k, "Value": str(v)} for k, v in (dimensions or {}).items()]

    resp = _get_client().get_metric_statistics(
        Namespace=NAMESPACE, MetricName=metric_name, Dimensions=dims,
        StartTime=start, EndTime=end, Period=period, Statistics=[stat],
    )
    points = resp.get("Datapoints", [])
    return sorted(points, key=lambda x: x["Timestamp"])


def get_alarm_states() -> list[dict]:
    """Get current state of all DqAgent alarms."""
    resp = _get_client().describe_alarms(AlarmNamePrefix="DqAgent-")
    return [
        {"name": a["AlarmName"], "state": a["StateValue"], "metric": a["MetricName"],
         "threshold": a.get("Threshold"), "updated": a.get("StateUpdatedTimestamp")}
        for a in resp.get("MetricAlarms", [])
    ]
