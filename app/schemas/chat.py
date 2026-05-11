from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    client_tz: str = Field(
        "UTC",
        description=(
            "IANA timezone the message originated in (e.g. 'America/New_York'). "
            "Defaults to UTC. Threaded into the system prompt so the agent can "
            "resolve 'today' / 'last night' / 'tomorrow' correctly."
        ),
    )
