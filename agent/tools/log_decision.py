"""log_decision — Record agent reasoning and actions for observability."""

import json

from strands import tool

from agent.utils import dynamodb_client, metrics


@tool
def log_decision(decision_type: str, context: dict, reasoning: str, action_taken: str, outcome: str) -> str:
    """Record the agent's reasoning, tool selection, and outcomes for audit trail.

    Must be called at every major decision point. This is mandatory, not optional.

    Args:
        decision_type: E.g. 'scan_initiated', 'violation_detected', 'diagnosis_complete', 'remediation_executed', 'notification_sent'
        context: Relevant context (table, partition, violation details)
        reasoning: The agent's explanation of why it chose this action
        action_taken: What the agent did
        outcome: Result of the action

    Returns:
        JSON with decision_id and timestamp.
    """
    table_name = context.get("table", context.get("table_name", "unknown"))
    partition = context.get("partition", "unknown")

    result = dynamodb_client.put_decision(
        decision_type=decision_type,
        table_name=table_name,
        partition=partition,
        context=context,
        reasoning=reasoning,
        action_taken=action_taken,
        outcome=outcome,
    )

    metrics.put_metric("DecisionCount", 1, "Count", {"DecisionType": decision_type})

    return json.dumps(result)
