"""Behavioural evals for the chat agent.

These run REAL OpenRouter calls (gpt-4o-mini by default) and verify the
agent's tool-call decisions, argument shapes, and response sanity. They
catch prompt regressions that unit tests cannot.

Run with:  uv run pytest -m eval -v

Full suite ≈ 30 invocations, ~$0.03 in OpenRouter spend, ~2 minutes.
"""

from __future__ import annotations

import re
import zoneinfo
from datetime import date
from uuid import UUID

import pytest

from app.models.user import User
from app.services.memory_client import MemoryClientTransientError
from app.services.memory_client import SearchHit as ClientSearchHit
from tests._db import reset_db, seed_memory, seed_owner
from tests._memory_client_fake import FakeMemoryClient
from tests.evals._helpers import (
    EVAL_NOW_DATE,
    EVAL_TZ,
    EVAL_YESTERDAY_DATE,
    final_text,
    run_chat,
    tool_call_args,
    tool_call_names,
)

pytestmark = pytest.mark.eval


@pytest.fixture
def owner_id() -> UUID:
    reset_db()
    return seed_owner("eval-suite-passphrase")


# ─── greetings: no tool call ───────────────────────────────────────────────


def test_plain_greeting_emits_no_tool_call(db, owner_id):
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    pkts = run_chat(message="hi", db=db, memory_client=fake, user=user)

    assert tool_call_names(pkts) == []
    assert len(final_text(pkts)) > 0


# ─── create: time / tz / location ──────────────────────────────────────────


def test_create_resolves_last_night_to_yesterday(db, owner_id):
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    pkts = run_chat(
        message="I had pizza at Joe's in Brooklyn last night around 8pm.",
        db=db,
        memory_client=fake,
        user=user,
    )

    assert tool_call_names(pkts) == ["manage_memory"]
    args = tool_call_args(pkts, "manage_memory")[0]
    assert args["action"] == "create"
    assert args["event_date"] == EVAL_YESTERDAY_DATE
    assert args["event_tz"] == EVAL_TZ
    # 20:00 in any reasonable normalisation
    assert args["event_time"].startswith("20:")


def test_create_uses_iana_tz_not_abbreviation(db, owner_id):
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    pkts = run_chat(
        message="Had coffee at 9am EST today.",
        db=db,
        memory_client=fake,
        user=user,
    )

    args = tool_call_args(pkts, "manage_memory")
    assert len(args) == 1
    tz = args[0]["event_tz"]
    assert "/" in tz, f"expected IANA TZ, got {tz!r}"
    assert tz != "EST"


def test_create_does_not_hallucinate_lat_lng_from_place_name(db, owner_id):
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    pkts = run_chat(
        message="This morning I went for a run in Central Park.",
        db=db,
        memory_client=fake,
        user=user,
    )

    args = tool_call_args(pkts, "manage_memory")[0]
    assert args["location_lat"] is None
    assert args["location_lng"] is None
    # Label should still be set — "Central Park" is what the user said.
    assert args["location_label"] is not None
    assert "central park" in args["location_label"].lower()


def test_create_today_uses_correct_date(db, owner_id):
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    pkts = run_chat(
        message="I had a stand-up meeting this morning at 10.",
        db=db,
        memory_client=fake,
        user=user,
    )

    args = tool_call_args(pkts, "manage_memory")[0]
    assert args["action"] == "create"
    assert args["event_date"] == EVAL_NOW_DATE


# ─── recall must search first ──────────────────────────────────────────────


def test_recall_question_calls_search_first(db, owner_id):
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    pkts = run_chat(
        message="What did I eat yesterday?",
        db=db,
        memory_client=fake,
        user=user,
    )

    names = tool_call_names(pkts)
    assert names and names[0] == "search_memories"


def test_summarize_today_calls_search(db, owner_id):
    """Regression: previously the model claimed 'no memories' without searching."""
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    pkts = run_chat(
        message="Summarize my day so far.",
        db=db,
        memory_client=fake,
        user=user,
    )

    assert "search_memories" in tool_call_names(pkts)


def test_zero_hit_search_does_not_hallucinate(db, owner_id):
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()  # no seeded memories, no search results
    pkts = run_chat(
        message="Do I have any memories about scuba diving?",
        db=db,
        memory_client=fake,
        user=user,
    )

    assert "search_memories" in tool_call_names(pkts)
    text = final_text(pkts).lower()
    # The model should acknowledge no hits — not invent diving stories.
    assert any(p in text for p in ("no", "don't", "haven't", "any")), text


# ─── update / delete must search first ─────────────────────────────────────


def test_update_searches_first_and_uses_correct_memory_id(db, owner_id):
    user = db.get(User, owner_id)

    mid = seed_memory(
        user_id=owner_id,
        text_body="had pizza at Joe's in Brooklyn",
        event_date=date(2026, 5, 8),
    )

    fake = FakeMemoryClient()
    fake.set_search_results(
        [ClientSearchHit(doc_id=str(mid), similarity=0.9)],
    )

    pkts = run_chat(
        message="Actually it was 9pm not 8 for the pizza last night.",
        db=db,
        memory_client=fake,
        user=user,
    )

    names = tool_call_names(pkts)
    assert names == ["search_memories", "manage_memory"]

    update_args = tool_call_args(pkts, "manage_memory")[0]
    assert update_args["action"] == "update"
    assert UUID(update_args["memory_id"]) == mid
    # Only the time should be touched.
    assert update_args["event_time"].startswith("21:")
    # text was not changed; should be null (omitted)
    assert update_args["text"] is None


# ─── multi-event in one turn ───────────────────────────────────────────────


def test_two_events_in_one_message_create_two_memories(db, owner_id):
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    pkts = run_chat(
        message=(
            "This morning I went for a run in Central Park, and at noon I had lunch at Sweetgreen."
        ),
        db=db,
        memory_client=fake,
        user=user,
    )

    creates = [a for a in tool_call_args(pkts, "manage_memory") if a["action"] == "create"]
    assert len(creates) == 2

    texts = " | ".join(c["text"].lower() for c in creates)
    assert "run" in texts or "central park" in texts
    assert "lunch" in texts or "sweetgreen" in texts
    for c in creates:
        assert c["event_date"] == EVAL_NOW_DATE
        assert c["event_tz"] == EVAL_TZ


# ─── Format compliance (cheap canary on all arg shapes) ───────────────────


def test_create_args_match_canonical_formats(db, owner_id):
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    pkts = run_chat(
        message="I had coffee this morning at 8:30am.",
        db=db,
        memory_client=fake,
        user=user,
    )

    args = tool_call_args(pkts, "manage_memory")[0]

    assert re.match(r"^\d{4}-\d{2}-\d{2}$", args["event_date"]), args["event_date"]
    assert re.match(r"^\d{2}:\d{2}(:\d{2})?$", args["event_time"]), args["event_time"]
    assert args["event_tz"] in zoneinfo.available_timezones(), args["event_tz"]
    assert args["idempotency_id"] is None
    assert args["memory_id"] is None  # not set on create


# ─── Time edge cases ──────────────────────────────────────────────────────


def test_relative_weekday_resolves_to_recent_past(db, owner_id):
    """EVAL_NOW = Sat 2026-05-09. 'Last Tuesday' resolves to either the
    Tuesday of this week (2026-05-05) or the previous week (2026-04-28).
    Both are defensible English readings; reject only clear hallucinations.
    """
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    pkts = run_chat(
        message="I went hiking last Tuesday.",
        db=db,
        memory_client=fake,
        user=user,
    )
    args = tool_call_args(pkts, "manage_memory")[0]
    assert args["action"] == "create"
    assert args["event_date"] in ("2026-05-05", "2026-04-28"), args["event_date"]


def test_around_midnight_picks_one_definite_date(db, owner_id):
    """'Around midnight last night' is genuinely ambiguous (Fri-late vs
    Sat-early). Either is acceptable; what's NOT is no event_date or a
    far-off date.
    """
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    pkts = run_chat(
        message="Got home around midnight last night.",
        db=db,
        memory_client=fake,
        user=user,
    )
    args = tool_call_args(pkts, "manage_memory")[0]
    assert args["event_date"] in ("2026-05-08", "2026-05-09"), args["event_date"]


def test_future_event_uses_tomorrow_date(db, owner_id):
    """Future-dated 'memories' are technically allowed (think reminders).
    If the model creates one, the date must be tomorrow, not 'today' or some
    hallucinated value.
    """
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    pkts = run_chat(
        message="I have a dentist appointment tomorrow at 10am.",
        db=db,
        memory_client=fake,
        user=user,
    )
    args = tool_call_args(pkts, "manage_memory")
    if args:  # model is allowed to decline future events; if it acts, the date must be right
        assert args[0]["event_date"] == "2026-05-10"


def test_user_named_tz_overrides_client_tz(db, owner_id):
    """The user explicitly says they're in Tokyo. Override client_tz."""
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    pkts = run_chat(
        message="I'm visiting Tokyo this week. Just had sushi at 7pm.",
        db=db,
        memory_client=fake,
        user=user,
        client_tz="America/New_York",
    )
    args = tool_call_args(pkts, "manage_memory")[0]
    assert args["event_tz"] == "Asia/Tokyo", args["event_tz"]


# ─── Negative tool selection (no tool when not needed) ────────────────────


def test_general_knowledge_question_does_not_call_search(db, owner_id):
    """Pure cooking-recipe question — about the world, not the user's past.
    The agent may either answer or politely redirect; either way, NO tool.
    """
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    pkts = run_chat(
        message="How do I cook spaghetti carbonara?",
        db=db,
        memory_client=fake,
        user=user,
    )
    assert tool_call_names(pkts) == []
    assert len(final_text(pkts)) > 20


def test_meta_question_does_not_call_tool(db, owner_id):
    """User asks what the agent can do — pure conversational reply, no tool."""
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    pkts = run_chat(
        message="What can you help me with?",
        db=db,
        memory_client=fake,
        user=user,
    )
    assert tool_call_names(pkts) == []


# ─── Error path handling ──────────────────────────────────────────────────


def test_update_error_emits_typed_error_packets(db, owner_id, monkeypatch):
    """Tool errors re-raise out of `Tool.run` (per phase 06-07 design); the
    SDK runner halts and `runtime.drive` catches that into a framework
    `ErrorPacket`. The user does NOT get a graceful text reply — that's a
    known UX gap worth fixing later, but for now the contract is:
        manage_memory_end{status="error", error="MemoryNotFound"} → ErrorPacket
    Frontend renders the typed error from the tool packet.
    """
    from app.services import _memory_errors as memory_errors
    from app.services import memory as memory_service

    user = db.get(User, owner_id)
    mid = seed_memory(
        user_id=owner_id,
        text_body="had pizza last night",
        event_date=date(2026, 5, 8),
    )

    fake = FakeMemoryClient()
    fake.set_search_results([ClientSearchHit(doc_id=str(mid), similarity=0.9)])

    def boom(*args, **kwargs):
        raise memory_errors.MemoryNotFound(kwargs.get("memory_id", mid))

    monkeypatch.setattr(memory_service, "update_memory", boom)

    pkts = run_chat(
        message="Actually it was 9pm not 8 for the pizza last night.",
        db=db,
        memory_client=fake,
        user=user,
    )

    end_packets = [p for p in pkts if p.type == "manage_memory_end"]
    assert end_packets and end_packets[0].status == "error"
    assert end_packets[0].error == "MemoryNotFound"

    error_packets = [p for p in pkts if p.type == "error"]
    assert error_packets, "runtime should emit a framework ErrorPacket on tool failure"
    assert error_packets[0].code == "agent_failed"


def test_local_fallback_search_still_returns_hits(db, owner_id):
    """Supermemory transient → service falls back to local FTS.
    Agent should treat the result transparently and use it in the answer.
    """
    user = db.get(User, owner_id)
    seed_memory(
        user_id=owner_id,
        text_body="had pizza at the corner place last week",
        event_date=date(2026, 5, 3),
    )

    fake = FakeMemoryClient()
    fake.fail_next("search", error=MemoryClientTransientError("force fallback"))

    pkts = run_chat(
        message="Any pizza memories?",
        db=db,
        memory_client=fake,
        user=user,
    )

    assert "search_memories" in tool_call_names(pkts)
    end_packets = [p for p in pkts if p.type == "search_memories_end"]
    assert end_packets and end_packets[0].status == "ok"
    assert end_packets[0].result is not None
    assert end_packets[0].result.source == "local"
    assert len(end_packets[0].result.hits) >= 1
    assert "pizza" in final_text(pkts).lower()


# ─── Determinism: 3 reruns of the highest-value evals ─────────────────────


@pytest.mark.parametrize("attempt", range(3))
def test_repeats_create_resolves_last_night(db, owner_id, attempt):
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    pkts = run_chat(
        message="I had pizza at Joe's in Brooklyn last night around 8pm.",
        db=db,
        memory_client=fake,
        user=user,
    )
    assert tool_call_names(pkts) == ["manage_memory"]
    args = tool_call_args(pkts, "manage_memory")[0]
    assert args["action"] == "create"
    assert args["event_date"] == EVAL_YESTERDAY_DATE


@pytest.mark.parametrize("attempt", range(3))
def test_repeats_recall_calls_search_first(db, owner_id, attempt):
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    pkts = run_chat(
        message="What did I do this week?",
        db=db,
        memory_client=fake,
        user=user,
    )
    names = tool_call_names(pkts)
    assert names and names[0] == "search_memories"


@pytest.mark.parametrize("attempt", range(3))
def test_repeats_update_does_not_re_pass_text(db, owner_id, attempt):
    user = db.get(User, owner_id)
    mid = seed_memory(
        user_id=owner_id,
        text_body="had pizza at Joe's in Brooklyn",
        event_date=date(2026, 5, 8),
    )
    fake = FakeMemoryClient()
    fake.set_search_results([ClientSearchHit(doc_id=str(mid), similarity=0.9)])

    pkts = run_chat(
        message="Actually it was 9pm not 8 for the pizza last night.",
        db=db,
        memory_client=fake,
        user=user,
    )

    update_args = tool_call_args(pkts, "manage_memory")[0]
    assert update_args["action"] == "update"
    assert update_args["text"] is None, (
        f"text should be omitted on a time-only update; got {update_args['text']!r}"
    )
