"""Observability stack — DynamoDB tables, CloudWatch alarms, CloudWatch dashboard."""

import aws_cdk as cdk
from aws_cdk import RemovalPolicy, aws_cloudwatch as cw, aws_cloudwatch_actions as cw_actions, aws_dynamodb as ddb, aws_sns as sns
from constructs import Construct

TTL_ATTRIBUTE = "ttl"
NAMESPACE = "DataQualityAgent"


class ObservabilityStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- DynamoDB Tables ---
        table_defs = [
            ("quality-scan-results", "PK", "SK"),
            ("agent-decisions", "PK", "SK"),
            ("schema-baselines", "PK", "SK"),
            ("remediation-history", "PK", "SK"),
        ]

        self.tables = {}
        for name, pk, sk in table_defs:
            table = ddb.Table(
                self,
                name,
                table_name=name,
                partition_key=ddb.Attribute(name=pk, type=ddb.AttributeType.STRING),
                sort_key=ddb.Attribute(name=sk, type=ddb.AttributeType.STRING),
                billing_mode=ddb.BillingMode.PAY_PER_REQUEST,
                removal_policy=RemovalPolicy.DESTROY,
                time_to_live_attribute=TTL_ATTRIBUTE if name != "schema-baselines" else None,
            )
            self.tables[name] = table
            cdk.CfnOutput(self, f"{name}-arn", value=table.table_arn)

        # --- Import SNS topic for alarm actions ---
        alert_topic = sns.Topic.from_topic_arn(
            self, "AlertTopic",
            f"arn:aws:sns:{self.region}:{self.account}:dq-agent-alerts",
        )

        # --- CloudWatch Alarms ---
        quality_alarm = cw.Alarm(
            self, "LowQualityScore",
            alarm_name="DqAgent-LowQualityScore",
            metric=cw.Metric(namespace=NAMESPACE, metric_name="OverallQualityScore",
                             dimensions_map={"TableName": "raw_yellow_taxi"}, period=cdk.Duration.minutes(5),
                             statistic="Minimum"),
            threshold=50, evaluation_periods=1,
            comparison_operator=cw.ComparisonOperator.LESS_THAN_THRESHOLD,
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
        )
        quality_alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))

        anomaly_alarm = cw.Alarm(
            self, "HighAnomalyCount",
            alarm_name="DqAgent-HighAnomalyCount",
            metric=cw.Metric(namespace=NAMESPACE, metric_name="AnomaliesDetected",
                             dimensions_map={"TableName": "raw_yellow_taxi", "Severity": "CRITICAL"},
                             period=cdk.Duration.minutes(5), statistic="Sum"),
            threshold=10, evaluation_periods=1,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
        )
        anomaly_alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))

        cost_alarm = cw.Alarm(
            self, "HighTokenCost",
            alarm_name="DqAgent-HighTokenCost",
            metric=cw.Metric(namespace=NAMESPACE, metric_name="AgentTokenCost",
                             period=cdk.Duration.minutes(5), statistic="Sum"),
            threshold=1.0, evaluation_periods=1,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
        )
        cost_alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))

        # --- CloudWatch Dashboard ---
        dashboard = cw.Dashboard(self, "AgentDashboard", dashboard_name="DataQualityAgentDashboard")

        dashboard.add_widgets(
            cw.TextWidget(width=24, height=1, markdown="# Data Quality Agent Dashboard"),
        )

        dashboard.add_widgets(
            cw.GraphWidget(
                title="Overall Quality Score", width=8, height=6,
                left=[cw.Metric(namespace=NAMESPACE, metric_name="OverallQualityScore",
                                dimensions_map={"TableName": "raw_yellow_taxi"}, statistic="Average")],
                left_annotations=[cw.HorizontalAnnotation(value=50, color="#d13212", label="Critical")],
            ),
            cw.GraphWidget(
                title="Anomalies Detected", width=8, height=6,
                left=[
                    cw.Metric(namespace=NAMESPACE, metric_name="AnomaliesDetected",
                              dimensions_map={"TableName": "raw_yellow_taxi", "Severity": "CRITICAL"},
                              statistic="Sum", label="Critical"),
                    cw.Metric(namespace=NAMESPACE, metric_name="AnomaliesDetected",
                              dimensions_map={"TableName": "raw_yellow_taxi", "Severity": "WARNING"},
                              statistic="Sum", label="Warning"),
                ],
            ),
            cw.GraphWidget(
                title="Remediation Actions", width=8, height=6,
                left=[
                    cw.Metric(namespace=NAMESPACE, metric_name="RemediationActions",
                              dimensions_map={"TableName": "raw_yellow_taxi", "ActionType": "quarantine"},
                              statistic="Sum", label="Quarantine"),
                    cw.Metric(namespace=NAMESPACE, metric_name="RemediationActions",
                              dimensions_map={"TableName": "raw_yellow_taxi", "ActionType": "transform_clip_outliers"},
                              statistic="Sum", label="Transform"),
                ],
            ),
        )

        dashboard.add_widgets(
            cw.GraphWidget(
                title="Quality by Dimension", width=12, height=6,
                left=[
                    cw.Metric(namespace=NAMESPACE, metric_name="QualityScore",
                              dimensions_map={"TableName": "raw_yellow_taxi", "CheckType": "completeness"},
                              statistic="Average", label="Completeness"),
                    cw.Metric(namespace=NAMESPACE, metric_name="QualityScore",
                              dimensions_map={"TableName": "raw_yellow_taxi", "CheckType": "freshness"},
                              statistic="Average", label="Freshness"),
                    cw.Metric(namespace=NAMESPACE, metric_name="QualityScore",
                              dimensions_map={"TableName": "raw_yellow_taxi", "CheckType": "distribution"},
                              statistic="Average", label="Distribution"),
                ],
            ),
            cw.GraphWidget(
                title="Agent Decisions & Tool Calls", width=12, height=6,
                left=[
                    cw.Metric(namespace=NAMESPACE, metric_name="DecisionCount", statistic="Sum", label="Decisions"),
                    cw.Metric(namespace=NAMESPACE, metric_name="ToolCallDuration", statistic="Average",
                              label="Avg Tool Duration (ms)"),
                ],
            ),
        )
