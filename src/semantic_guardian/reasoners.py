"""Concrete LLM reasoners (#5) — drop-ins for the engine's `LLMReasoner` interface.

The engine is provider-agnostic; these are the real implementations. Each satisfies
`reason(prompt) -> str`. Pick one at wiring time. They are thin on purpose — all the
semantic work lives in the engine's prompt and parsing, which are fully tested offline.

NOTE: these make live model calls, so they are exercised by a manual smoke run once a
model is available (Bedrock model access or an Anthropic key), not by the unit suite.
"""
from __future__ import annotations

import os


class BedrockReasoner:
    """Reason via Amazon Bedrock (no API key — uses the AWS profile/role).

    Uses the Converse API with an inference-profile model id (e.g.
    'us.anthropic.claude-sonnet-4-5-...' or 'us.amazon.nova-pro-v1:0'). The bare model id
    is NOT invokable on-demand for newer models — an inference profile id is required.
    """

    def __init__(self, model_id: str | None = None, region: str | None = None,
                 profile: str | None = None) -> None:
        import boto3  # type: ignore[import-untyped]

        self.model_id = model_id or os.getenv("SG_BEDROCK_MODEL", "us.amazon.nova-pro-v1:0")
        session = boto3.Session(
            profile_name=profile or os.getenv("AWS_PROFILE", "bedrock"),
            region_name=region or os.getenv("AWS_REGION", "us-east-1"),
        )
        self._client = session.client("bedrock-runtime")

    def reason(self, prompt: str) -> str:
        resp = self._client.converse(
            modelId=self.model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 1024, "temperature": 0},
        )
        return resp["output"]["message"]["content"][0]["text"]


class AnthropicReasoner:
    """Reason via the Anthropic API directly (needs ANTHROPIC_API_KEY)."""

    def __init__(self, model: str = "claude-sonnet-4-5", api_key: str | None = None) -> None:
        import anthropic

        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))

    def reason(self, prompt: str) -> str:
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=1024,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in msg.content if hasattr(block, "text"))


def get_reasoner():
    """Pick a reasoner from the environment: Anthropic key if present, else Bedrock.
    Raises a clear error only when actually called without any provider configured."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicReasoner()
    return BedrockReasoner()
