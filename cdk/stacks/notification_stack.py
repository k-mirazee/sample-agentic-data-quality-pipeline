"""Notification stack — SNS topic for agent alerts."""

import aws_cdk as cdk
from aws_cdk import aws_sns as sns, aws_sns_subscriptions as subs
from constructs import Construct


class NotificationStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.topic = sns.Topic(self, "AlertsTopic", topic_name="dq-agent-alerts")

        email = self.node.try_get_context("notification_email")
        if email:
            self.topic.add_subscription(subs.EmailSubscription(email))

        cdk.CfnOutput(self, "TopicArn", value=self.topic.topic_arn)
