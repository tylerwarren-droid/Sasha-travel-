"""
Shared LLM configuration: one async Anthropic client + centralized model ids.

Why this exists:
- A single `AsyncAnthropic()` instance reuses one HTTP/2 connection pool across the whole
  process instead of each service opening its own — fewer TLS handshakes, lower per-call
  latency.
- Model ids live in ONE place (env-overridable) so a model bump is a config change, not a
  find-replace across ten agent files.

Latency note: the Conductor + merge run on FAST_MODEL (Haiku) because spoken replies are
1–2 sentences and time-to-first-audio dominates the felt delay. Tool-using specialists use
SMART_MODEL.

SMART_MODEL defaults to the currently-shipped `claude-sonnet-4-5`. `claude-sonnet-4-6` is a
drop-in current-gen bump — set `SMART_MODEL=claude-sonnet-4-6` in the env after a regression
pass rather than changing code, so investor-demo behavior is never altered untested.
"""

import os

import anthropic
from dotenv import load_dotenv

# Ensure the API key is loaded regardless of import order (this module creates the client
# at import time, so it must not depend on another module having called load_dotenv first).
load_dotenv()

# One client, one connection pool, process-wide.
client = anthropic.AsyncAnthropic()

FAST_MODEL = os.getenv("FAST_MODEL", "claude-haiku-4-5")
SMART_MODEL = os.getenv("SMART_MODEL", "claude-sonnet-4-5")

# Model for the tool-using specialist agents (golf, restaurant, health, etc.). These were on
# Sonnet and ran 5-6.5s per turn (Sonnet + multi-step tool loops). Defaulting them to Haiku
# cuts ~30-40% off the model time for a big drop in perceived voice lag. If a specialist's
# answer quality regresses, revert with SPECIALIST_MODEL=claude-sonnet-4-5 (no code change).
SPECIALIST_MODEL = os.getenv("SPECIALIST_MODEL", "claude-haiku-4-5")


def cached_system(text: str):
    """Wrap a system prompt with Anthropic prompt caching (ephemeral, 5-min TTL).

    The Conductor's system prompts are static and re-sent every turn. Marking them
    cacheable lets Anthropic reuse the processed prefix instead of re-encoding it, which
    trims input-processing time on repeat turns. Caching only engages once a prompt clears
    Anthropic's minimum cacheable length, so this is a no-op for today's short prompts and
    a free win the moment the system prompt grows (e.g. injected knowledge/persona).
    """
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]
