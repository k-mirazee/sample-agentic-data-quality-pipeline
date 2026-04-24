"""diagnose_issue — Use LLM reasoning to determine root cause and recommend action."""

import json
import os

import boto3
from strands import tool

from agent.utils import dynamodb_client

MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
REGION = os.getenv("AWS_REGION", "us-east-1")

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=REGION)
    return _client


DIAGNOSTIC_PROMPT = """You are a data quality diagnostic engine. Given a quality violation, determine the root cause and recommend an action.

Violation details:
{violation_json}

Historical context (previous scans):
{history_json}

Respond with ONLY valid JSON matching this schema:
{{
  "probable_cause": "string — explanation of what likely caused this issue",
  "confidence": "HIGH|MEDIUM|LOW",
  "recommended_action": "quarantine_and_notify|transform_and_promote|notify_only|auto_resolve",
  "action_details": {{
    "description": "string — specific steps to take"
  }},
  "explanation": "string — reasoning for the recommendation"
}}"""


@tool
def diagnose_issue(violation: dict, historical_context: dict | None = None) -> str:
    """Diagnose a quality violation using LLM reasoning to determine root cause and recommend action.

    This makes a separate, focused Bedrock call with a diagnostic-specific prompt.
    The diagnosis is contained and auditable.

    Args:
        violation: Contains type, severity, affected_columns, sample_values, quality_scores
        historical_context: Previous scan results for trend analysis (optional)

    Returns:
        JSON diagnosis with probable_cause, confidence, recommended_action, and explanation.
    """
    # Get historical scans if not provided
    if not historical_context:
        table = violation.get("table", "")
        partition = violation.get("partition", "")
        if table and partition:
            history = dynamodb_client.get_recent_scans(table, partition, limit=5)
            historical_context = {"previous_scans": len(history), "scans": history[:3]}
        else:
            historical_context = {"previous_scans": 0}

    prompt = DIAGNOSTIC_PROMPT.format(
        violation_json=json.dumps(violation, default=str),
        history_json=json.dumps(historical_context, default=str),
    )

    resp = _get_client().invoke_model(
        modelId=MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )

    body = json.loads(resp["body"].read())
    text = body["content"][0]["text"]

    # Parse the JSON response, handling markdown code blocks
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        diagnosis = json.loads(text)
    except json.JSONDecodeError:
        diagnosis = {
            "probable_cause": text,
            "confidence": "LOW",
            "recommended_action": "notify_only",
            "action_details": {"description": "Could not parse structured diagnosis"},
            "explanation": text,
        }

    return json.dumps(diagnosis, default=str)
