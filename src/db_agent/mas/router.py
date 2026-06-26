"""MAS top-level intent router: classify a request into one worker.

This sits ABOVE the existing domain router. It decides *which agent/workflow*
handles the request (explore | recommend | vdr), not which data domain. It is a
single cheap `qwen-fast` call and **fails open to `explore`** (the current full
agent) so an unexpected reply never strands a user.
"""

from __future__ import annotations

from db_agent.config import Settings
from db_agent.llm import prompts
from db_agent.llm.client import LLMClient

# The three workers the supervisor can dispatch to. `explore` is the safe default.
WORKER_KINDS: tuple[str, ...] = ("explore", "recommend", "vdr")
DEFAULT_KIND = "explore"


async def classify_intent(client: LLMClient, settings: Settings, question: str) -> str:
    """Return one of WORKER_KINDS. Unrecognized output → DEFAULT_KIND (explore)."""
    raw = await client.complete(settings.model_fast, prompts.intent_messages(question))
    text = raw.strip().lower()
    for kind in WORKER_KINDS:
        if text.startswith(kind):
            return kind
    # Tolerate a wordier reply ("vdr_qa", "this is a recommend request"): pick the
    # first non-default kind that appears, else fall open to explore.
    for kind in ("recommend", "vdr"):
        if kind in text:
            return kind
    return DEFAULT_KIND
