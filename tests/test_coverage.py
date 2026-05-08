"""Tests targeting uncovered lines for 100% coverage."""

import time
from typing import Self
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from py_nationalgrid.auth import NationalGridAuth
from py_nationalgrid.client import NationalGridClient, _is_gateway_timeout
from py_nationalgrid.config import NationalGridConfig, RetryConfig
from py_nationalgrid.exceptions import (
    DataExtractionError,
    GraphQLError,
    RestAPIError,
    RetryExhaustedError,
)
from py_nationalgrid.extractors import (
    extract_ami_energy_usages,
    extract_bills,
    extract_interval_reads,
)
from py_nationalgrid.graphql import GraphQLRequest, GraphQLResponse
from py_nationalgrid.helpers import create_cookie_jar
from py_nationalgrid.queries import _normalize_variable_definitions
from py_nationalgrid.rest import RestResponse

# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------


def _make_client_response_error(status: int) -> aiohttp.ClientResponseError:
    return aiohttp.ClientResponseError(
        request_info=MagicMock(),
        history=(),
        status=status,
        message=f"HTTP {status}",
    )


class _MockResponse:
    def __init__(
        self,
        payload: object,
        *,
        status: int = 200,
        raise_on_status: bool = False,
        json_raises: bool = False,
        text_raises: bool = False,
    ) -> None:
        self._payload = payload
        self.status = status
        self._raise_on_status = raise_on_status
        self._json_raises = json_raises
        self._text_raises = text_raises
        self.headers: dict[str, str] = {}

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # type: ignore[override]
        return False

    async def json(self, content_type: str | None = None) -> object:
        if self._json_raises:
            raise ValueError("not json")
        return self._payload

    async def text(self) -> str:
        if self._text_raises:
            raise aiohttp.ClientConnectionError("text() failed")
        return str(self._payload)

    def raise_for_status(self) -> None:
        if self._raise_on_status:
            raise _make_client_response_error(self.status)


# ---------------------------------------------------------------------------
# auth.py
# ---------------------------------------------------------------------------


def test_auth_timezone() -> None:
    assert NationalGridAuth.timezone() == "America/New_York"


@pytest.mark.asyncio
async def test_auth_async_login_delegates_to_oidc() -> None:
    auth = NationalGridAuth()
    session = MagicMock(spec=aiohttp.ClientSession)
    login_data: dict = {}

    with patch(
        "py_nationalgrid.auth.async_auth_oidc",
        new_callable=AsyncMock,
        return_value=("tok", 3600),
    ):
        result = await auth.async_login(session, "user@x.com", "pw", login_data)

    assert result == ("tok", 3600)


# ---------------------------------------------------------------------------
# config.py
# ---------------------------------------------------------------------------


def test_config_with_overrides() -> None:
    config = NationalGridConfig(timeout=30.0)
    updated = config.with_overrides(timeout=60.0)
    assert updated.timeout == 60.0
    assert config.timeout == 30.0  # original unchanged


# ---------------------------------------------------------------------------
# exceptions.py
# ---------------------------------------------------------------------------


def test_retry_exhausted_str() -> None:
    err = RetryExhaustedError("all retries failed", attempts=3, last_error=ValueError("root"))
    s = str(err)
    assert "3" in s
    assert "root" in s


# ---------------------------------------------------------------------------
# helpers.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_cookie_jar_returns_jar() -> None:
    jar = create_cookie_jar()
    assert isinstance(jar, aiohttp.CookieJar)


# ---------------------------------------------------------------------------
# queries.py
# ---------------------------------------------------------------------------


def test_normalize_variable_definitions_none() -> None:
    result = _normalize_variable_definitions(None)
    assert result is None


# ---------------------------------------------------------------------------
# extractors.py
# ---------------------------------------------------------------------------


def test_extract_ami_energy_usages_data_none() -> None:
    response = GraphQLResponse(data=None)
    with pytest.raises(DataExtractionError, match="data is null"):
        extract_ami_energy_usages(response)


def test_extract_ami_energy_usages_nodes_none() -> None:
    response = GraphQLResponse(data={"amiEnergyUsages": {}})
    with pytest.raises(DataExtractionError, match="nodes"):
        extract_ami_energy_usages(response)


def test_extract_bills_data_none() -> None:
    response = GraphQLResponse(data=None)
    with pytest.raises(DataExtractionError, match="data is null"):
        extract_bills(response)


def test_extract_bills_nodes_none() -> None:
    response = GraphQLResponse(data={"bills": {}})
    with pytest.raises(DataExtractionError, match="nodes"):
        extract_bills(response)


def test_extract_interval_reads_data_none() -> None:
    response = RestResponse(status=200, headers={}, data=None)
    with pytest.raises(DataExtractionError, match="data is null"):
        extract_interval_reads(response)


# ---------------------------------------------------------------------------
# client.py — pure/sync helpers
# ---------------------------------------------------------------------------


def test_is_gateway_timeout_returns_false_for_non_exc() -> None:
    assert _is_gateway_timeout(ValueError("nope")) is False


def test_config_property() -> None:
    config = NationalGridConfig(endpoint="https://x.test/graphql")
    client = NationalGridClient(config=config)
    assert client.config is config


def test_resolve_rest_url_absolute_passthrough() -> None:
    client = NationalGridClient(config=NationalGridConfig())
    assert client._resolve_rest_url("https://example.com/path") == "https://example.com/path"


def test_resolve_rest_url_raises_without_base() -> None:
    client = NationalGridClient(config=NationalGridConfig(rest_base_url=""))
    with pytest.raises(ValueError, match="rest_base_url"):
        client._resolve_rest_url("relative/path")


def test_should_retry_asyncio_timeout() -> None:
    client = NationalGridClient(config=NationalGridConfig())
    retry_config = RetryConfig(max_attempts=3, retry_on_timeout=True)
    assert client._should_retry(TimeoutError(), 0, retry_config) is True


def test_should_retry_graphql_error_status_in_retry_on_status() -> None:
    client = NationalGridClient(config=NationalGridConfig())
    retry_config = RetryConfig(max_attempts=3, retry_on_status=(500,))
    err = GraphQLError("fail", endpoint="https://x.test", status=500)
    assert client._should_retry(err, 0, retry_config) is True


def test_should_retry_graphql_error_status_401_first_attempt() -> None:
    client = NationalGridClient(config=NationalGridConfig())
    retry_config = RetryConfig(max_attempts=3)
    err = GraphQLError("fail", endpoint="https://x.test", status=401)
    assert client._should_retry(err, 0, retry_config) is True


# ---------------------------------------------------------------------------
# client.py — _read_rest_payload ContentTypeError branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_rest_payload_content_type_error_falls_back_to_text() -> None:
    config = NationalGridConfig()
    client = NationalGridClient(config=config)

    mock_response = MagicMock(spec=aiohttp.ClientResponse)

    async def _bad_json(content_type=None):
        raise aiohttp.ContentTypeError(MagicMock(), ())

    mock_response.json = _bad_json
    mock_response.text = AsyncMock(return_value="plain text body")

    result = await client._read_rest_payload(mock_response)
    assert result == "plain text body"


# ---------------------------------------------------------------------------
# client.py — token caching paths (lines 482-484, 492-493, 508-509)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_access_token_returns_fresh_cached_token() -> None:
    """Fast-path return when token is still fresh (line 483)."""
    session = MagicMock(spec=aiohttp.ClientSession)
    client = NationalGridClient(config=NationalGridConfig())
    client._access_token = "cached-token"
    client._token_expires_at = time.time() + 7200  # expires far in future

    token = await client._get_access_token(session)
    assert token == "cached-token"


@pytest.mark.asyncio
async def test_get_access_token_refreshes_when_expiring_soon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Token near expiry triggers debug log and refresh (line 484)."""
    config = NationalGridConfig(username="u@x.com", password="pw")
    session = MagicMock(spec=aiohttp.ClientSession)
    client = NationalGridClient(config=config, session=session)
    client._access_token = "stale-token"
    client._token_expires_at = time.time() + 100  # < 300s buffer → refresh

    async def _fake_login(self, sess, user, pw, login_data, timeout):
        return "new-token", 3600

    monkeypatch.setattr("py_nationalgrid.client.NationalGridAuth.async_login", _fake_login)

    token = await client._get_access_token(session)
    assert token == "new-token"


@pytest.mark.asyncio
async def test_get_access_token_double_check_finds_fresh_token_under_lock() -> None:
    """If another coroutine refreshed the token while we waited on the lock (lines 492-493)."""
    config = NationalGridConfig(username="u@x.com", password="pw")
    session = MagicMock(spec=aiohttp.ClientSession)
    client = NationalGridClient(config=config, session=session)

    # No cached token initially — goes to slow path
    client._access_token = None
    client._token_expires_at = None

    class _LockThatSetsToken:
        async def __aenter__(self):
            client._access_token = "concurrent-token"
            client._token_expires_at = time.time() + 7200
            return self

        async def __aexit__(self, *args):
            pass

    client._auth_lock = _LockThatSetsToken()  # type: ignore[assignment]

    token = await client._get_access_token(session)
    assert token == "concurrent-token"


@pytest.mark.asyncio
async def test_get_access_token_login_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """When async_login returns (None, None), token is cleared (lines 508-509)."""
    config = NationalGridConfig(username="u@x.com", password="pw")
    session = MagicMock(spec=aiohttp.ClientSession)
    client = NationalGridClient(config=config, session=session)

    async def _fake_login(self, sess, user, pw, login_data, timeout):
        return None, None

    monkeypatch.setattr("py_nationalgrid.client.NationalGridAuth.async_login", _fake_login)

    token = await client._get_access_token(session)
    assert token is None
    assert client._access_token is None
    assert client._token_expires_at is None


# ---------------------------------------------------------------------------
# client.py — _ensure_session double-check (line 535)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_session_double_check_under_lock() -> None:
    """If another coroutine created the session while we waited (line 535)."""
    client = NationalGridClient(config=NationalGridConfig())
    client._session = None  # force slow path

    mock_session = MagicMock(spec=aiohttp.ClientSession)
    mock_session.closed = False

    class _LockThatSetsSession:
        async def __aenter__(self):
            client._session = mock_session
            return self

        async def __aexit__(self, *args):
            pass

    client._session_lock = _LockThatSetsSession()  # type: ignore[assignment]

    result = await client._ensure_session()
    assert result is mock_session


# ---------------------------------------------------------------------------
# client.py — get_linked_accounts with sub (line 579)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_linked_accounts_sends_user_id_when_sub_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = NationalGridConfig(endpoint="https://example.test/graphql")
    session = MagicMock(spec=aiohttp.ClientSession)
    session.closed = False
    session.post.return_value = _MockResponse(
        {
            "data": {
                "user": {
                    "accountLinks": {
                        "nodes": [{"accountLinkId": "link-1", "billingAccountId": "acct-1"}]
                    }
                }
            }
        }
    )

    client = NationalGridClient(config=config, session=session)
    client._login_data["sub"] = "user-sub-123"

    await client.get_linked_accounts()

    _, kwargs = session.post.call_args
    variables = kwargs["json"].get("variables", {})
    assert variables.get("userId") == "user-sub-123"


# ---------------------------------------------------------------------------
# client.py — execute: body=None when json() raises after 4xx (lines 256-257)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_body_none_when_json_raises_after_error_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = NationalGridConfig(
        endpoint="https://example.test/graphql",
        retry_config=RetryConfig(max_attempts=1),
    )
    session = MagicMock(spec=aiohttp.ClientSession)
    session.closed = False
    session.post.return_value = _MockResponse(
        {}, status=500, raise_on_status=True, json_raises=True
    )

    monkeypatch.setattr(
        "py_nationalgrid.client.NationalGridAuth.async_login",
        AsyncMock(return_value=("tok", 3600)),
    )

    client = NationalGridClient(config=config, session=session)
    request = GraphQLRequest(query="query Test { value }")

    with pytest.raises((GraphQLError, RetryExhaustedError)) as exc_info:
        await client.execute(request)

    err = exc_info.value
    if isinstance(err, RetryExhaustedError):
        err = err.last_error
    assert isinstance(err, GraphQLError)
    assert err.response_body is None


# ---------------------------------------------------------------------------
# client.py — execute: non-GraphQL error wrapped in GraphQLError (line 301)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_non_graphql_error_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    config = NationalGridConfig(
        endpoint="https://example.test/graphql",
        retry_config=RetryConfig(max_attempts=2, initial_delay=0.001),
    )
    session = MagicMock(spec=aiohttp.ClientSession)
    session.closed = False
    session.post.side_effect = ValueError("unexpected")

    monkeypatch.setattr(
        "py_nationalgrid.client.NationalGridAuth.async_login",
        AsyncMock(return_value=("tok", 3600)),
    )

    client = NationalGridClient(config=config, session=session)
    request = GraphQLRequest(query="query Test { value }")

    with pytest.raises(GraphQLError) as exc_info:
        await client.execute(request)

    assert isinstance(exc_info.value.original_error, ValueError)


# ---------------------------------------------------------------------------
# client.py — request_rest: REST 401 clears token (lines 406-410)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_rest_401_clears_cached_token(monkeypatch: pytest.MonkeyPatch) -> None:
    config = NationalGridConfig(
        username="u@x.com",
        password="pw",
        retry_config=RetryConfig(max_attempts=1),
    )
    session = MagicMock(spec=aiohttp.ClientSession)
    session.closed = False
    session.request.return_value = _MockResponse({}, status=401, raise_on_status=True)

    async def _fake_login(self, sess, user, pw, login_data, timeout):
        return "tok", 3600

    monkeypatch.setattr("py_nationalgrid.client.NationalGridAuth.async_login", _fake_login)

    client = NationalGridClient(config=config, session=session)

    with pytest.raises((RestAPIError, RetryExhaustedError)):
        await client.request_rest("GET", "/api/test")

    assert client._access_token is None
    assert client._token_expires_at is None


# ---------------------------------------------------------------------------
# client.py — request_rest: response_text=None when text() raises (lines 415-416)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_rest_response_text_none_when_text_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = NationalGridConfig(
        retry_config=RetryConfig(max_attempts=1),
    )
    session = MagicMock(spec=aiohttp.ClientSession)
    session.closed = False
    session.request.return_value = _MockResponse(
        {}, status=503, raise_on_status=True, text_raises=True
    )

    monkeypatch.setattr(
        "py_nationalgrid.client.NationalGridAuth.async_login",
        AsyncMock(return_value=("tok", 3600)),
    )

    client = NationalGridClient(config=config, session=session)

    with pytest.raises((RestAPIError, RetryExhaustedError)) as exc_info:
        await client.request_rest("GET", "/api/test")

    err = exc_info.value
    if isinstance(err, RetryExhaustedError):
        err = err.last_error
    assert isinstance(err, RestAPIError)
    assert err.response_text is None


# ---------------------------------------------------------------------------
# client.py — request_rest: non-RestAPIError wrapped (lines 446-454)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_rest_non_retryable_rest_error_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RestAPIError with non-retryable status (400) is re-raised immediately (line 454)."""
    config = NationalGridConfig(
        retry_config=RetryConfig(max_attempts=2, initial_delay=0.001),
    )
    session = MagicMock(spec=aiohttp.ClientSession)
    session.closed = False
    session.request.return_value = _MockResponse({}, status=400, raise_on_status=True)

    monkeypatch.setattr(
        "py_nationalgrid.client.NationalGridAuth.async_login",
        AsyncMock(return_value=("tok", 3600)),
    )

    client = NationalGridClient(config=config, session=session)

    with pytest.raises(RestAPIError) as exc_info:
        await client.request_rest("GET", "/api/test")

    assert exc_info.value.status == 400
    assert session.request.call_count == 1  # no retry


@pytest.mark.asyncio
async def test_request_rest_non_rest_error_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    config = NationalGridConfig(
        retry_config=RetryConfig(max_attempts=2, initial_delay=0.001),
    )
    session = MagicMock(spec=aiohttp.ClientSession)
    session.closed = False
    session.request.side_effect = ValueError("boom")

    monkeypatch.setattr(
        "py_nationalgrid.client.NationalGridAuth.async_login",
        AsyncMock(return_value=("tok", 3600)),
    )

    client = NationalGridClient(config=config, session=session)

    with pytest.raises(RestAPIError) as exc_info:
        await client.request_rest("GET", "/api/test")

    assert isinstance(exc_info.value.original_error, ValueError)


# ---------------------------------------------------------------------------
# client.py — request_rest: retry log + sleep (lines 378, 461-469)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_rest_retries_on_500_and_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    config = NationalGridConfig(
        retry_config=RetryConfig(max_attempts=2, initial_delay=0.001),
    )
    session = MagicMock(spec=aiohttp.ClientSession)
    session.closed = False

    call_count = 0

    def _mock_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _MockResponse({}, status=500, raise_on_status=True)
        return _MockResponse({"result": "ok"})

    session.request = _mock_request

    monkeypatch.setattr(
        "py_nationalgrid.client.NationalGridAuth.async_login",
        AsyncMock(return_value=("tok", 3600)),
    )

    client = NationalGridClient(config=config, session=session)
    resp = await client.request_rest("GET", "/api/test")

    assert call_count == 2
    assert resp.data == {"result": "ok"}


# ---------------------------------------------------------------------------
# client.py — get_ami_energy_usages_15min: non-504 in fell_back daily (line 905)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_15min_fell_back_non_504_exception_propagates() -> None:
    """After daily fallback, a non-504 error on a later chunk propagates (line 905)."""
    from datetime import date

    config = NationalGridConfig(endpoint="https://x.test/graphql")
    session = MagicMock(spec=aiohttp.ClientSession)
    session.closed = False

    client = NationalGridClient(config=config, session=session)

    common_kwargs = dict(
        meter_number="M1",
        premise_number="P1",
        service_point_number="SP1",
        meter_point_number="MP1",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 3, 31),
        fuel_type="ELECTRIC",
    )

    call_count = 0

    async def _mock_execute(request, *, headers=None, timeout=None):
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # Chunk 3 (newest) — 15min, succeeds
            return GraphQLResponse(data={"amiEnergyUsages15Min": {"nodes": [{"value": 1}]}})
        if call_count == 2:
            # Chunk 2 — 15min returns errors → fell_back = True, switches to daily
            return GraphQLResponse(
                data={"amiEnergyUsages15Min": {"nodes": []}},
                errors=[{"message": "error"}],
            )
        if call_count == 3:
            # Chunk 2 daily re-request — succeeds
            return GraphQLResponse(data={"amiEnergyUsages": {"nodes": [{"value": 2}]}})
        # Chunk 1 daily — raises non-504 error
        raise GraphQLError("server error", endpoint="https://x.test/graphql", status=500)

    client.execute = _mock_execute  # type: ignore[method-assign]

    with pytest.raises(GraphQLError, match="server error"):
        await client.get_ami_energy_usages_15min(**common_kwargs)


# ---------------------------------------------------------------------------
# client.py — get_ami_energy_usages_15min: non-504 in first-chunk daily fallback (line 956)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_15min_first_chunk_daily_fallback_non_504_propagates() -> None:
    """First chunk errors → full-range daily fallback raises non-504 (line 956)."""
    from datetime import date

    config = NationalGridConfig(endpoint="https://x.test/graphql")
    session = MagicMock(spec=aiohttp.ClientSession)
    session.closed = False

    client = NationalGridClient(config=config, session=session)

    call_count = 0

    async def _mock_execute(request, *, headers=None, timeout=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First 15min chunk returns errors → triggers full-range daily fallback
            return GraphQLResponse(
                data={"amiEnergyUsages15Min": {"nodes": []}},
                errors=[{"message": "cast error"}],
            )
        # Full-range daily raises non-504 error
        raise GraphQLError("internal error", endpoint="https://x.test/graphql", status=500)

    client.execute = _mock_execute  # type: ignore[method-assign]

    with pytest.raises(GraphQLError, match="internal error"):
        await client.get_ami_energy_usages_15min(
            meter_number="M1",
            premise_number="P1",
            service_point_number="SP1",
            meter_point_number="MP1",
            date_from=date(2024, 3, 1),
            date_to=date(2024, 3, 31),
            fuel_type="ELECTRIC",
        )
