from app.core.security import hash_passphrase, verify_passphrase


def test_hash_passphrase_produces_argon2id_hash() -> None:
    hashed = hash_passphrase("blue sky cat unicycle")
    assert hashed.startswith("$argon2id$")


def test_verify_passphrase_accepts_correct() -> None:
    hashed = hash_passphrase("blue sky cat")
    assert verify_passphrase("blue sky cat", hashed) is True


def test_verify_passphrase_rejects_wrong() -> None:
    hashed = hash_passphrase("blue sky cat")
    assert verify_passphrase("red moon dog", hashed) is False


def test_verify_passphrase_rejects_empty() -> None:
    hashed = hash_passphrase("blue sky cat")
    assert verify_passphrase("", hashed) is False


def test_hash_uses_unique_salt_per_call() -> None:
    h1 = hash_passphrase("same phrase")
    h2 = hash_passphrase("same phrase")
    assert h1 != h2
