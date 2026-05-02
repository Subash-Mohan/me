from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_passphrase
from app.models.user import User


class OwnerAlreadyExistsError(RuntimeError):
    pass


class EmptyPassphraseError(ValueError):
    pass


def create_owner_user(db: Session, passphrase: str) -> User:
    if not passphrase:
        raise EmptyPassphraseError("passphrase cannot be empty")
    if db.execute(select(User).limit(1)).scalar_one_or_none() is not None:
        raise OwnerAlreadyExistsError("an owner user already exists")
    user = User(passphrase_hash=hash_passphrase(passphrase))
    db.add(user)
    db.flush()
    return user
