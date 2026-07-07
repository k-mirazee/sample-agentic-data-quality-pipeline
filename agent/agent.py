#!/usr/bin/env python3
"""Data Quality Guardian Agent — Strands agent with AgentCore runtime entrypoint."""

import json
import logging
import os

from dotenv import load_dotenv
from strands import Agent
from strands.models.bedrock import BedrockModel

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(format="%(levelname)s | %(name)s | %(message)s", level=logging.INFO)

# --- OpenTelemetry ---
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "false").lower() == "true"
if OTEL_ENABLED:
    try:
        from strands.telemetry.config import StrandsTelemetry

        os.environ.setdefault("OTEL_SERVICE_NAME", "dq-agent")
        telemetry = StrandsTelemetry()
        telemetry.setup_otlp_exporter()
        telemetry.setup_meter(enable_otlp_exporter=True)
        logger.info("OpenTelemetry initialized (service=dq-agent)")
    except Exception as e:
        logger.warning("OpenTelemetry setup failed: %s", e)
else:
    logger.info("OpenTelemetry disabled (OTEL_ENABLED=false)")

# --- Configuration ---
MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
REGION = os.getenv("AWS_REGION", "us-east-1")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "4096"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.3"))

# Load system prompt from file
_prompt_file = os.path.join(os.path.dirname(__file__), "system_prompt.md")
if os.path.isfile(_prompt_file):
    with open(_prompt_file) as f:
        SYSTEM_PROMPT = f.read().strip()
    logger.info("Loaded system prompt from %s", _prompt_file)
else:
    SYSTEM_PROMPT = "You are a Data Quality Guardian agent."
    logger.warning("system_prompt.md not found, using default")

# --- Tool imports (support both local package and container flat layout) ---
try:
    from agent.tools.diagnose_issue import diagnose_issue
    from agent.tools.log_decision import log_decision
    from agent.tools.notify_owner import notify_owner
    from agent.tools.parse_dq_event import parse_dq_event
    from agent.tools.quarantine_records import quarantine_records
except ImportError:
    from tools.diagnose_issue import diagnose_issue
    from tools.log_decision import log_decision
    from tools.notify_owner import notify_owner
    from tools.parse_dq_event import parse_dq_event
    from tools.quarantine_records import quarantine_records

TOOLS = [parse_dq_event, diagnose_issue, quarantine_records, notify_owner, log_decision]

# --- Agent ---
_agent = None


def get_agent() -> Agent:
    """Return cached Strands Agent, creating on first call."""
    global _agent
    if _agent is None:
        model = BedrockModel(
            model_id=MODEL_ID,
            region_name=REGION,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
        )
        _agent = Agent(
            model=model,
            system_prompt=SYSTEM_PROMPT,
            tools=TOOLS,
        )
        logger.info("Agent initialized: model=%s, tools=%d", MODEL_ID, len(TOOLS))
    return _agent


def _extract_response(result) -> str:
    """Extract text from Strands agent result."""
    if hasattr(result, "message") and isinstance(result.message, dict):
        content = result.message.get("content", [])
        if isinstance(content, list) and content:
            return content[0].get("text", str(result.message))
        return str(content)
    return str(result)


# --- AgentCore Runtime ---
try:
    from bedrock_agentcore.runtime import BedrockAgentCoreApp

    app = BedrockAgentCoreApp()

    @app.entrypoint
    def invoke_agent(payload, **kwargs) -> str:
        """Main entrypoint for AgentCore Runtime."""
        try:
            if isinstance(payload, dict):
                prompt = payload.get("prompt", payload.get("inputText", str(payload)))
            else:
                prompt = str(payload)

            prompt = prompt.strip()
            if not prompt:
                return json.dumps({"response": "Empty input received."})

            agent = get_agent()
            result = agent(prompt)
            return json.dumps({"response": _extract_response(result)})

        except Exception as e:
            logger.error("Error invoking agent: %s", e, exc_info=True)
            return json.dumps({"response": f"Error: {e}"})

    logger.info("AgentCore runtime registered")

except ImportError:
    app = None
    logger.info("bedrock_agentcore not installed — local mode only")


# --- Local CLI ---
def main():
    """Run agent locally via CLI for development/testing."""
    import argparse

    parser = argparse.ArgumentParser(description="Data Quality Guardian Agent")
    parser.add_argument("--table", default="raw_yellow_taxi", help="Glue table name")
    parser.add_argument("--partition", default="year=2025/month=09", help="Partition spec")
    parser.add_argument("--prompt", help="Custom prompt (overrides the default mock DQ event)")
    args = parser.parse_args()

    # The agent responds to Glue DQ results; it does not scan. Default to a
    # mock evaluation event so local runs exercise the real workflow.
    mock_event = {
        "evaluation_id": "dqresult-local-test",
        "database": os.getenv("GLUE_DATABASE", "dq_agent_demo"),
        "table": args.table,
        "partition": args.partition,
        "overall_state": "FAILED",
        "rule_results": [
            {
                "rule": 'Completeness "passenger_count" >= 0.70',
                "state": "FAILED",
                "evaluated_metrics": {"Column.passenger_count.Completeness": 0.64},
                "description": "Completeness check failed — 36% null passenger_count",
            }
        ],
    }
    prompt = args.prompt or (
        f"Glue DQ evaluation on {args.table} partition {args.partition} has FAILED. "
        f"Process the following evaluation results:\n\n{json.dumps(mock_event)}"
    )

    logger.info("Running locally: table=%s, partition=%s", args.table, args.partition)
    agent = get_agent()
    result = agent(prompt)
    print(_extract_response(result))


if __name__ == "__main__":
    if app is not None:
        app.run()
    else:
        main()
