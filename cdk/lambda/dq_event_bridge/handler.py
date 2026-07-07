"""Lambda bridge: EventBridge Glue DQ event → AgentCore invocation."""

import json
import os
import re
import uuid

import boto3
from botocore.config import Config

AGENT_ID = os.environ.get("AGENTCORE_AGENT_ID", "")
REGION = os.environ.get("AWS_REGION", "us-east-1")

# invoke_agent_runtime holds the HTTP connection until the agent finishes, which
# can take minutes. Retries would re-run quarantine/notify actions, so make a
# single attempt with a read timeout just under the 900s function timeout.
AGENTCORE_CONFIG = Config(read_timeout=850, connect_timeout=10, retries={"total_max_attempts": 1})


def _partition_from_predicate(predicate: str) -> str:
    """Convert an Athena pushdown predicate into a partition spec.

    "year='2025' AND month='09'" → "year=2025/month=09"
    """
    pairs = re.findall(r"(\w+)\s*=\s*'([^']*)'", predicate or "")
    return "/".join(f"{k}={v}" for k, v in pairs)


def handler(event, context):
    """Receive a Glue DQ EventBridge event and invoke the AgentCore agent."""
    print(f"Received event: {json.dumps(event)}")

    detail = event.get("detail", {})
    ctx = detail.get("context", {})

    # AWS's documented sample event uses "resultID"; other sources show "resultId".
    result_id = detail.get("resultID") or detail.get("resultId")
    state = detail.get("state", "UNKNOWN")
    score = detail.get("score", "n/a")

    if not result_id:
        raise ValueError(f"No result ID in event detail: {json.dumps(detail)[:500]}")

    glue = boto3.client("glue", region_name=REGION)
    result = glue.get_data_quality_result(ResultId=result_id)

    table_meta = result.get("DataSource", {}).get("GlueTable", {})
    database = table_meta.get("DatabaseName") or ctx.get("databaseName", "dq_agent_demo")
    table = table_meta.get("TableName") or ctx.get("tableName", "raw_yellow_taxi")
    # Catalog evaluation events carry no partition info; recover the scan scope
    # from the pushdown predicate the evaluation run was started with.
    partition = _partition_from_predicate(table_meta.get("AdditionalOptions", {}).get("pushDownPredicate", ""))

    normalized_results = []
    for rr in result.get("RuleResults", []):
        if rr.get("Result", "").upper() != "FAIL":
            continue
        normalized_results.append(
            {
                "rule": rr.get("Description", rr.get("Name", "")),
                "state": "FAILED",
                "evaluated_metrics": {
                    k: float(v) if v is not None else 0.0 for k, v in rr.get("EvaluatedMetrics", {}).items()
                },
                "description": rr.get("EvaluationMessage") or rr.get("Description", ""),
            }
        )

    print(
        f"Evaluation {result_id}: run_state={state}, score={score}, "
        f"table={database}.{table}, partition={partition or '(all)'}, failures={len(normalized_results)}"
    )

    if not normalized_results:
        print("No failed rules — skipping agent invocation")
        return {"statusCode": 200, "body": "No failures to process", "evaluation_id": result_id}

    payload = {
        "evaluation_id": result_id,
        "database": database,
        "table": table,
        "partition": partition,
        "overall_state": "FAILED",
        "rule_results": normalized_results,
    }

    prompt = (
        f"Glue DQ evaluation {result_id} on {table} partition {partition or '(unscoped)'} has FAILED. "
        f"Process the following evaluation results:\n\n"
        f"{json.dumps(payload)}"
    )

    if not AGENT_ID:
        raise ValueError("AGENTCORE_AGENT_ID env var is not set — cannot invoke agent")

    account_id = os.environ.get("AWS_ACCOUNT_ID") or context.invoked_function_arn.split(":")[4]
    agent_arn = f"arn:aws:bedrock-agentcore:{REGION}:{account_id}:runtime/{AGENT_ID}"
    print(f"Invoking agent {agent_arn} with {len(normalized_results)} violations")

    client = boto3.client("bedrock-agentcore", region_name=REGION, config=AGENTCORE_CONFIG)
    session_id = str(uuid.uuid4())

    response = client.invoke_agent_runtime(
        agentRuntimeArn=agent_arn,
        runtimeSessionId=session_id,
        payload=json.dumps({"prompt": prompt}).encode("utf-8"),
    )

    body = response.get("response", b"")
    if hasattr(body, "read"):
        body = body.read()
    result_text = body.decode("utf-8") if isinstance(body, bytes) else str(body)

    print(f"Agent response: {result_text[:500]}")

    return {
        "statusCode": 200,
        "body": result_text[:1000],
        "evaluation_id": result_id,
        "violations_forwarded": len(normalized_results),
    }
