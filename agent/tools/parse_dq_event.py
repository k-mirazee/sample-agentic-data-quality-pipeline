"""parse_dq_event — Normalize a Glue Data Quality event into the agent's violation format."""

import json
import re
import time

from strands import tool

try:
    from agent.utils import dynamodb_client, metrics
except ImportError:
    from utils import dynamodb_client, metrics


def _classify_rule(rule_text: str) -> str:
    """Determine violation type from a DQDL rule string."""
    rule_lower = rule_text.lower()
    if "completeness" in rule_lower:
        return "completeness"
    if "freshness" in rule_lower:
        return "freshness"
    if "columnvalues" in rule_lower or "between" in rule_lower:
        return "distribution"
    if "columnexists" in rule_lower:
        return "schema"
    return "unknown"


def _extract_column(rule_text: str) -> str:
    """Extract the quoted column name from a DQDL rule string."""
    match = re.search(r'"([^"]+)"', rule_text)
    return match.group(1) if match else "unknown"


def _determine_severity(rule_type: str, evaluated_metrics: dict) -> str:
    """Determine severity based on violation type and observed metrics."""
    if rule_type == "completeness":
        for val in evaluated_metrics.values():
            completeness = float(val)
            missing_pct = (1 - completeness) * 100
            if missing_pct > 5:
                return "CRITICAL"
            if missing_pct > 2:
                return "WARNING"
        return "WARNING"

    if rule_type == "freshness":
        for val in evaluated_metrics.values():
            hours = float(val)
            if hours > 72:
                return "CRITICAL"
            if hours > 24:
                return "WARNING"
        return "WARNING"

    if rule_type == "distribution":
        for key, val in evaluated_metrics.items():
            if "outlier" in key.lower():
                ratio = float(val)
                if ratio > 0.01:
                    return "CRITICAL"
        return "WARNING"

    if rule_type == "schema":
        return "CRITICAL"

    return "WARNING"


@tool
def parse_dq_event(dq_event: dict) -> str:
    """Parse and normalize a Glue Data Quality evaluation event into structured violations.

    Transforms the Glue DQ event payload (from EventBridge via the Lambda bridge)
    into normalized violations that downstream tools (diagnose_issue, quarantine_records) expect.
    No external API calls — pure parsing and mapping.

    Args:
        dq_event: Glue DQ evaluation payload containing evaluation_id, database, table,
                  partition, overall_state, and rule_results with evaluated_metrics.

    Returns:
        JSON with overall_state, violation_count, and a list of normalized violations.
    """
    start = time.time()

    evaluation_id = dq_event.get("evaluation_id", "unknown")
    database = dq_event.get("database", "dq_agent_demo")
    table = dq_event.get("table", "unknown")
    partition = dq_event.get("partition", "unknown")
    overall_state = dq_event.get("overall_state", "UNKNOWN")
    rule_results = dq_event.get("rule_results", [])

    violations = []
    for rule_result in rule_results:
        state = rule_result.get("state", "").upper()
        if state not in ("FAILED", "FAIL"):
            continue

        rule_text = rule_result.get("rule", rule_result.get("description", ""))
        evaluated_metrics = rule_result.get("evaluated_metrics", {})

        rule_type = _classify_rule(rule_text)
        column = _extract_column(rule_text)
        severity = _determine_severity(rule_type, evaluated_metrics)

        violation = {
            "type": rule_type,
            "severity": severity,
            "table": table,
            "partition": partition,
            "affected_columns": [column],
            "observed_values": {k: float(v) for k, v in evaluated_metrics.items()},
            "rule": rule_text,
            "evaluation_id": evaluation_id,
        }
        violations.append(violation)

    # Compute overall score (simple: 100 - penalty per violation)
    score_penalty = len([v for v in violations if v["severity"] == "CRITICAL"]) * 20
    score_penalty += len([v for v in violations if v["severity"] == "WARNING"]) * 10
    overall_score = max(0, 100 - score_penalty)

    overall_status = "CRITICAL" if overall_score < 50 else "WARNING" if overall_score < 80 else "OK"

    result = {
        "evaluation_id": evaluation_id,
        "database": database,
        "table": table,
        "partition": partition,
        "overall_state": overall_state,
        "overall_score": overall_score,
        "overall_status": overall_status,
        "violation_count": len(violations),
        "violations": violations,
        "parse_duration_ms": round((time.time() - start) * 1000),
    }

    # Persist to DynamoDB for audit continuity
    dynamodb_client.put_scan_result(table, partition, {
        "overall_score": overall_score,
        "overall_status": overall_status,
        "source": "glue_dq",
        "evaluation_id": evaluation_id,
        "violation_count": len(violations),
    })

    # Emit CloudWatch metrics
    metrics.put_overall_score(table, overall_score)
    if violations:
        metrics.put_anomalies(table, overall_status, len(violations))

    return json.dumps(result, default=str)
