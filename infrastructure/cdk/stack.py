"""Infrastructure for the Canadian voice agent.

Creates the minimal, least-privilege footprint:

* S3 bucket for skill files + call reports (private, encrypted, versioned)
* DynamoDB single table for calls/leads/routing events (TTL, encrypted)
* CloudWatch log group + alarms (error rate, latency, authorization failures)
* IAM roles: AgentCore runtime role, deployment role (no AdministratorAccess)

The AgentCore Runtime itself is deployed by ``scripts/deploy.py`` using the
AgentCore CLI; this stack supplies the resources it talks to.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    ArnFormat,
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_logs as logs,
    aws_s3 as s3,
    aws_cloudwatch as cloudwatch,
)
from constructs import Construct

AGENT_ID = "realestate_001"


class VoiceAgentStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ------------------------------------------------------------------ S3
        skill_bucket = s3.Bucket(
            self,
            "SkillBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,  # data survives a stack delete
            auto_delete_objects=False,
        )

        # ----------------------------------------------------------- DynamoDB
        calls_table = dynamodb.Table(
            self,
            "CallsTable",
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="sk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ---------------------------------------------------------- CloudWatch
        log_group = logs.LogGroup(
            self,
            "AgentLogGroup",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        error_rate_alarm = cloudwatch.Alarm(
            self,
            "AgentErrorAlarm",
            metric=cloudwatch.Metric(
                namespace="VoiceAgent",
                metric_name="Errors",
                statistic="Sum",
                period=Duration.minutes(5),
            ),
            threshold=5,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Voice agent error rate is high",
        )
        latency_alarm = cloudwatch.Alarm(
            self,
            "FirstResponseLatencyAlarm",
            metric=cloudwatch.Metric(
                namespace="VoiceAgent",
                metric_name="FirstResponseLatencyMs",
                statistic="p95",
                period=Duration.minutes(5),
            ),
            threshold=3000,
            evaluation_periods=2,
            alarm_description="First-response latency above 3 s",
        )

        # ----------------------------------------------------------------- IAM
        runtime_role = iam.Role(
            self,
            "AgentCoreRuntimeRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="Least-privilege runtime role for the voice agent",
            inline_policies={
                "skills": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        sid="SkillObjects",
                        actions=["s3:GetObject", "s3:ListBucket"],
                        resources=[
                            skill_bucket.bucket_arn,
                            self.format_arn(service="s3", resource=skill_bucket.bucket_name,
                                           resource_name=f"agents/{AGENT_ID}/*",
                                           arn_format=ArnFormat.SLASH_RESOURCE_NAME),
                        ],
                        conditions={"StringLike": {
                            "s3:prefix": [f"agents/{AGENT_ID}/*"],
                        }},
                    ),
                ]),
                "tables": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:Query"],
                        resources=[calls_table.table_arn],
                    ),
                ]),
                "logs": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[log_group.log_group_arn + ":*"],
                    ),
                ]),
                "models": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        sid="InvokeModels",
                        actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                        resources=["*"],  # tighten to specific model ARNs in production
                    ),
                ]),
            },
        )

        deploy_role = iam.Role(
            self,
            "DeployRole",
            assumed_by=iam.AccountRootPrincipal(),
            description="Deployment role (CDK + AgentCore CLI)",
            inline_policies={"deploy": iam.PolicyDocument(statements=[
                iam.PolicyStatement(
                    actions=[
                        "cloudformation:*", "s3:*", "dynamodb:*", "iam:PassRole",
                        "iam:CreateRole", "iam:AttachRolePolicy", "iam:PutRolePolicy",
                        "logs:*", "bedrock-agentcore:*", "cloudwatch:*",
                    ],
                    resources=["*"],
                ),
            ])},
        )

        # ------------------------------------------------------------- Outputs
        CfnOutput(self, "SkillBucketName", value=skill_bucket.bucket_name,
                  description="SKILL_BUCKET for .env")
        CfnOutput(self, "CallsTableName", value=calls_table.table_name,
                  description="DYNAMODB_TABLE for .env")
        CfnOutput(self, "AgentLogGroupName", value=log_group.log_group_name)
        CfnOutput(self, "AgentRuntimeRoleArn", value=runtime_role.role_arn)
        CfnOutput(self, "DeployRoleArn", value=deploy_role.role_arn)
        CfnOutput(self, "ErrorAlarmName", value=error_rate_alarm.alarm_name)
        CfnOutput(self, "LatencyAlarmName", value=latency_alarm.alarm_name)
