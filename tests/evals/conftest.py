"""Eval-suite fixtures.

Evals call real OpenRouter, so the conftest's stubbed `OPENROUTER_API_KEY`
("test-openrouter-key") would 401 against the real API. This conftest reads
the project's `.env` and replaces the stub with the real value before any
eval runs. If the real key is missing, every eval in this directory is
skipped at module load.

The Supermemory client is still the in-memory `FakeMemoryClient` — these
evals exercise the LLM's tool-call decisions, not the vendor index. That
means evals are deterministic w.r.t. memory state (the test seeds it) and
cost only the OpenRouter token usage (~$0.001/eval with gpt-4o-mini).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent.parent
_PLACEHOLDER_PREFIXES = ("replace-", "change-", "test-")


def _read_env_value(key: str) -> str | None:
    """Return the value of `key` from the project's `.env`, or None."""
    env_file = _ROOT / ".env"
    if not env_file.exists():
        return None
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() != key:
            continue
        v = v.strip()
        if not v or any(v.startswith(p) for p in _PLACEHOLDER_PREFIXES):
            return None
        return v
    return None


_REAL_KEY = _read_env_value("OPENROUTER_API_KEY")
_REAL_MODEL = _read_env_value("OPENROUTER_DEFAULT_MODEL")

if not _REAL_KEY or not _REAL_MODEL:
    pytest.skip(
        "evals require real OPENROUTER_API_KEY + OPENROUTER_DEFAULT_MODEL in .env",
        allow_module_level=True,
    )

# Override the package conftest's test stub so a real call goes out.
os.environ["OPENROUTER_API_KEY"] = _REAL_KEY
os.environ["OPENROUTER_DEFAULT_MODEL"] = _REAL_MODEL

# Settings is lru_cache'd; clear so the override takes effect.
from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()
