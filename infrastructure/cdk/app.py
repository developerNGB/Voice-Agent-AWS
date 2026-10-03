#!/usr/bin/env python3
"""CDK entry point: python3 app.py (from infrastructure/cdk)."""

import aws_cdk as cdk

from stack import VoiceAgentStack

app = cdk.App()

VoiceAgentStack(
    app,
    "RealestateVoiceAgentStack",
    env=cdk.Environment(
        account=app.node.try_get_context("account"),
        region=app.node.try_get_context("region") or "ca-central-1",
    ),
)

app.synth()
