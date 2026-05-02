import pytest

from app.cli import _read_passphrase_interactively


def test_returns_phrase_when_both_prompts_match(monkeypatch: pytest.MonkeyPatch) -> None:
    inputs = iter(["my phrase", "my phrase"])
    monkeypatch.setattr("getpass.getpass", lambda _prompt="": next(inputs))
    assert _read_passphrase_interactively() == "my phrase"


def test_exits_with_code_2_on_mismatch(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    inputs = iter(["one", "two"])
    monkeypatch.setattr("getpass.getpass", lambda _prompt="": next(inputs))
    with pytest.raises(SystemExit) as exc_info:
        _read_passphrase_interactively()
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "do not match" in captured.err.lower()
