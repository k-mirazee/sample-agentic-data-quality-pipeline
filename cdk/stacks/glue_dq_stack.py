"""Glue DQ stack — Ruleset, EventBridge rule, and Lambda bridge to AgentCore."""

import os
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    Duration,
)
from aws_cdk import (
    aws_events as events,
)
from aws_cdk import (
    aws_events_targets as targets,
)
from aws_cdk import (
    aws_glue as glue,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from aws_cdk import (
    aws_logs as logs,
)
from constructs import Construct

DATABASE_NAME = "dq_agent_demo"
TABLE_NAME = "raw_yellow_taxi"
RULESET_NAME = "dq-agent-ruleset"


class GlueDqStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        account_id = cdk.Stack.of(self).account

        # --- Load DQDL ruleset from file ---
        dqdl_path = Path(os.path.dirname(__file__)).parent / "glue_dq_ruleset.dqdl"
        dqdl_body = dqdl_path.read_text()

        # --- Glue Data Quality Ruleset ---
        self.ruleset = glue.CfnDataQualityRuleset(
            self,
            "DqRuleset",
            name=RULESET_NAME,
            ruleset=dqdl_body,
            target_table=glue.CfnDataQualityRuleset.DataQualityTargetTableProperty(
                database_name=DATABASE_NAME,
                table_name=TABLE_NAME,
            ),
        )

        # --- Lambda bridge function ---
        agentcore_agent_id = self.node.try_get_context("agentcore_agent_id")
        if not agentcore_agent_id:
            raise ValueError(
                "Missing CDK context 'agentcore_agent_id'. Deploy the agent first "
                "(agent/ac_deploy.sh), then pass its runtime ID: "
                "cdk deploy DqAgentGlueDq -c agentcore_agent_id=<name-XXXXXXXXXX>"
            )

        self.bridge_fn = lambda_.Function(
            self,
            "DqEventBridge",
            function_name="dq-agent-event-bridge",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.handler",
            code=lambda_.Code.from_asset(str(Path(os.path.dirname(__file__)).parent / "lambda" / "dq_event_bridge")),
            timeout=Duration.seconds(900),
            memory_size=256,
            environment={
                "AGENTCORE_AGENT_ID": agentcore_agent_id,
                "AWS_ACCOUNT_ID": account_id,
            },
            log_retention=logs.RetentionDays.TWO_WEEKS,
        )

        # --- EventBridge rule: Glue DQ results → Lambda ---
        # No detail.state filter: for catalog evaluation runs the event's "state"
        # is the RUN state (SUCCEEDED even when rules fail). The Lambda fetches
        # the full result and only invokes the agent when rules actually failed.
        self.rule = events.Rule(
            self,
            "DqFailureRule",
            rule_name="dq-agent-glue-dq-failures",
            event_pattern=events.EventPattern(
                source=["aws.glue-dataquality"],
                detail_type=["Data Quality Evaluation Results Available"],
            ),
        )
        # No retries: the agent run is not idempotent (quarantine, SNS, audit log).
        self.rule.add_target(targets.LambdaFunction(self.bridge_fn, retry_attempts=0))

        # --- IAM: allow Lambda to invoke AgentCore and read Glue DQ results ---
        self.bridge_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:InvokeAgentRuntime",
                    "bedrock:InvokeAgent",
                    "glue:GetDataQualityResult",
                ],
                resources=["*"],
            )
        )

        # --- IAM Role for Glue DQ evaluation runs ---
        bucket_name = f"dq-agent-demo-{account_id}"
        self.glue_role = iam.Role(
            self,
            "GlueDqRole",
            role_name="dq-agent-glue-role",
            assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSGlueServiceRole"),
            ],
            inline_policies={
                "DqAgentDataAccess": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["s3:GetObject", "s3:ListBucket"],
                            resources=[
                                f"arn:aws:s3:::{bucket_name}",
                                f"arn:aws:s3:::{bucket_name}/*",
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=["s3:PutObject"],
                            resources=[f"arn:aws:s3:::{bucket_name}/athena-results/*"],
                        ),
                    ]
                )
            },
        )

        # --- Outputs ---
        cdk.CfnOutput(self, "RulesetName", value=RULESET_NAME)
        cdk.CfnOutput(self, "BridgeFunctionArn", value=self.bridge_fn.function_arn)
        cdk.CfnOutput(self, "EventRuleName", value=self.rule.rule_name)
        cdk.CfnOutput(self, "GlueRoleArn", value=self.glue_role.role_arn)
