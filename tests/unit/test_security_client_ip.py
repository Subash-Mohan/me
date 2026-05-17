from fastapi import Request

from app.core.config import Settings
from app.core.security import client_ip


def _settings(*, trust_proxy_headers: bool) -> Settings:
    return Settings(
        database_url="postgresql+psycopg://me:me@localhost:5435/me_test",
        env="test",
        log_level="WARNING",
        jwt_secret="x" * 32,
        supermemory_api_key="test-key",
        supermemory_base_url="http://supermemory.test",
        supermemory_timeout_ms=50,
        openrouter_api_key="test-openrouter-key",
        openrouter_default_model="openai/gpt-5.4-mini",
        trust_proxy_headers=trust_proxy_headers,
    )


def _request(*, forwarded_for: str | None, client_host: str | None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode("ascii")))

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
    }
    if client_host is not None:
        scope["client"] = (client_host, 12345)
    return Request(scope)


def test_client_ip_ignores_forwarded_header_by_default() -> None:
    request = _request(forwarded_for="203.0.113.9", client_host="198.51.100.7")
    assert client_ip(request, _settings(trust_proxy_headers=False)) == "198.51.100.7"


def test_client_ip_uses_forwarded_header_when_trusted_proxy_mode_enabled() -> None:
    request = _request(
        forwarded_for="203.0.113.9, 198.51.100.7",
        client_host="198.51.100.7",
    )
    assert client_ip(request, _settings(trust_proxy_headers=True)) == "203.0.113.9"


def test_client_ip_returns_unknown_when_client_tuple_missing() -> None:
    request = _request(forwarded_for=None, client_host=None)
    assert client_ip(request, _settings(trust_proxy_headers=False)) == "unknown"
