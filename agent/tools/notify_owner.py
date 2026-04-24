"""notify_owner — Send alert notifications about quality issues via SNS."""

import json
import os

import boto3
from strands import tool

REGION = os.getenv("AWS_REGION", "us-east-1")
SNS_TOPIC_ARN = os.getenv("SNS_TOPIC_ARN", "")

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("sns", region_name=REGION)
    return _client


def _resolve_topic_arn() -> str:
    """Resolve topic ARN from env or discover by name."""
    if SNS_TOPIC_ARN:
        return SNS_TOPIC_ARN
    # Auto-discover
    client = _get_client()
    resp = client.list_topics()
    for t in resp.get("Topics", []):
        if "dq-agent-alerts" in t["TopicArn"]:
            return t["TopicArn"]
    return ""


@tool
def notify_owner(issue_id: str, severity: str, message: str) -> str:
    """Send alert notification about a quality issue and actions taken.

    Publishes to the configured SNS topic. Severity controls the subject line urgency.

    Args:
        issue_id: Reference to the quality issue
        severity: One of: critical, warning, info
        message: Human-readable summary of the issue and action taken

    Returns:
        JSON with delivery_status and message_id.
    """
    topic_arn = _resolve_topic_arn()
    if not topic_arn:
        return json.dumps({"delivery_status": "skipped", "reason": "No SNS topic configured"})

    severity_prefix = {"critical": "🚨 CRITICAL", "warning": "⚠️ WARNING", "info": "ℹ️ INFO"}.get(
        severity.lower(), severity.upper()
    )
    subject = f"[DQ Agent] {severity_prefix}: Data Quality Issue {issue_id[:8]}"
    # SNS subject max 100 chars
    subject = subject[:100]

    resp = _get_client().publish(
        TopicArn=topic_arn,
        Subject=subject,
        Message=message,
    )

    return json.dumps({
        "delivery_status": "sent",
        "message_id": resp.get("MessageId", ""),
        "topic_arn": topic_arn,
    })
