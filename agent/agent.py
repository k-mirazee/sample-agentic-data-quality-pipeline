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

# --- Tool imports (will be populated in Slice 5+) ---
# from agent.tools.scan_quality import scan_quality
# from agent.tools.check_schema import check_schema
# from agent.tools.log_decision import log_decision
# from agent.tools.diagnose_issue import diagnose_issue
# from agent.tools.quarantine_records import quarantine_records
# from agent.tools.apply_transform import apply_transform
# from agent.tools.notify_owner import notify_owner

TOOLS = []  # Populated as tools are built in subsequent slices

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
    parser.add_argument("--partition", default="year=2024/month=01", help="Partition spec")
    parser.add_argument("--prompt", help="Custom prompt (overrides default scan prompt)")
    args = parser.parse_args()

    prompt = args.prompt or (
        f"Scan the table {args.table} partition {args.partition} for data quality issues. "
        f"Run all check types and report your findings."
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
