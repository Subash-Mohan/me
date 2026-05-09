from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.agents.emitter import Emitter
from app.models.user import User
from app.services.memory_client import MemoryClient


@dataclass(frozen=True, slots=True)
class AgentContext:
    db: Session
    memory_client: MemoryClient
    user: User
    emitter: Emitter
