from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: UUID
    client_message_id: UUID = Field(
        description=(
            "Client-supplied UUID per chat send. The user-message row's PK. "
            "Retrying with the same UUID after a successful turn replays the "
            "stored assistant reply over SSE; retrying after a failed turn "
            "re-runs the agent."
        ),
    )
    message: str = Field(min_length=1, max_length=8000)
    client_tz: str = Field(
        "UTC",
        description=(
            "IANA timezone the message originated in (e.g. 'America/New_York'). "
            "Defaults to UTC. Threaded into the system prompt so the agent can "
            "resolve 'today' / 'last night' / 'tomorrow' correctly."
        ),
    )
