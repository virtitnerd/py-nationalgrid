# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Development Setup
```bash
uv sync                    # Install dependencies (creates .venv)
```

**Note**: This project uses a virtual environment at `.venv/`. If `uv` is not available in PATH, run tools directly from the venv:
```bash
.venv/bin/pytest           # Run tests
.venv/bin/ruff check .     # Lint code
.venv/bin/mypy src         # Type-check
```

### Testing and Quality
```bash
uv run pytest              # Run all tests
uv run pytest tests/test_client.py::test_execute_returns_response_payload  # Run single test
uv run ruff check .        # Lint code
uv run ruff format .       # Format code
uv run mypy src            # Type-check source code
```

### Running Examples
```bash
uv run python examples/list-accounts.py --username user@example.com --password secret
uv run python examples/account-info.py --username user@example.com --password secret
uv run python examples/billing-info.py --username user@example.com --password secret
uv run python examples/interval-reads.py --username user@example.com --password secret
uv run python examples/energy-usage.py --username user@example.com --password secret
uv run python examples/ami-usage.py --username user@example.com --password secret
uv run python examples/ami-usage.py --username user@example.com --password secret --fuel-type ELECTRIC --days 45
uv run python examples/ami-usage.py --username user@example.com --password secret --15min  # explicit 15-min endpoint
```

### Makefile Shortcuts
```bash
make install    # Same as uv sync
make test       # Same as uv run pytest
make lint       # Same as uv run ruff check .
make format     # Same as uv run ruff format .
make type       # Same as uv run mypy src
make example    # Same as uv run python examples/list-accounts.py
make clean      # Remove cache directories
```

## Architecture Overview

### Core Client Design
The package is built around `NationalGridClient` (src/py_nationalgrid/client.py), an async context manager that:
- Manages a single reusable `aiohttp.ClientSession` with configurable timeouts
- Handles OIDC authentication via Azure AD B2C (configured in auth.py with tenant/policy constants)
- Caches access tokens with thread-safe locking (`_auth_lock`) to prevent duplicate login requests
- Supports both GraphQL and REST endpoints with shared authentication headers

### Multi-Endpoint GraphQL Architecture
National Grid uses **separate GraphQL endpoints** for different data domains:
- `user-cu-uwp-gql`: User account links (queries.py:LINKED_BILLING_ENDPOINT)
- `billingaccount-cu-uwp-gql`: Account metadata (queries.py:BILLING_ACCOUNT_INFO_ENDPOINT)
- `energyusage-cu-uwp-gql`: Usage data (queries.py:ENERGY_USAGE_ENDPOINT)

Each typed client method (e.g., `get_linked_accounts()`, `get_billing_account()`) automatically routes to the correct endpoint via the `endpoint` field in `GraphQLRequest`.

### Query Builder Pattern
The `StandardQuery` dataclass (queries.py) builds GraphQL operations:
- Composes selection sets with proper indentation
- Handles variable definitions (single string or sequence)
- Supports field arguments for parameterized queries
- Automatically generates properly formatted GraphQL query strings via `compose_query()`

Internal helper functions like `linked_billing_accounts_request()` provide pre-configured query templates with sensible defaults for selection sets and variable definitions. These are used by the typed client methods and are not part of the public API.

### Authentication Flow
1. First API call triggers `_get_access_token()` with double-checked locking
2. Before using cached token, checks if it's expired (with 5-minute buffer for safety)
3. `NationalGridAuth.async_login()` delegates to `oidchelper.async_auth_oidc()`
4. OIDC helper performs Azure AD B2C flow using the client's existing session (no duplicate sessions created)
5. Returns tuple of `(access_token, expires_in_seconds)` instead of just the token
6. Token and expiry timestamp cached in `_access_token` and `_token_expires_at`
7. Automatic token refresh before expiration prevents 401 errors
8. `login_data` dict accumulates session info (e.g., `sub` claim for userId extracted from verified JWT)

### Configuration Management
`NationalGridConfig` (config.py) is a dataclass with:
- `build_headers()` method that merges authentication, subscription keys, and custom headers
- `with_overrides()` for creating modified config instances — uses `dataclasses.replace()` internally (not `asdict`, which would flatten nested dataclasses like `RetryConfig` into plain dicts)
- Hard-coded subscription key (`e674f89d7ed9417194de894b701333dd`) required for API access; this is the National Grid web portal's shared key (same for all users) and is overridable via `NationalGridConfig(subscription_key=...)`
- Credentials (username/password) must be passed explicitly; no environment variable loading
- Default connection pool: 10 total / 10 per host (tuned for single-API consumer usage)

### Request/Response Abstractions
- `GraphQLRequest`/`GraphQLResponse` (graphql.py): Internal wrappers around GraphQL payloads
- `RestRequest`/`RestResponse` (rest.py, rest_queries.py): Internal abstractions for REST endpoints
- Both support endpoint overrides at the request level
- These are used internally by the typed `get_*` methods and are not publicly exported

### Typed Public API
The public API consists of typed `get_*` methods on `NationalGridClient`:
- `get_linked_accounts()` → `list[AccountLink]`
- `get_billing_account()` → `BillingAccount`
- `get_energy_usage_costs()` → `list[EnergyUsageCost]`
- `get_energy_usages()` → `list[EnergyUsage]`
- `get_ami_energy_usages()` → `list[AmiEnergyUsage]` — **primary AMI method**; tries `NrtDailyUsage` first, falls back to `get_ami_energy_usages_15min()` on failure; see section below
- `get_ami_energy_usages_15min()` → `list[AmiEnergyUsage]` — explicit 15-min endpoint with automatic chunking; use directly when you need 15-min granularity specifically
- `get_interval_reads()` → `list[IntervalRead]` — returns `[]` on 404 (GAS meters with no interval data)

Each method builds a request internally, executes it via `execute()` or `request_rest()`, and extracts the typed result using extractors (extractors.py). All response models are TypedDicts defined in models.py.

### Primary AMI Method (`get_ami_energy_usages`)

This is the recommended method for AMI data. It tries `NrtDailyUsage` (the standard daily endpoint) first, which handles unrestricted date ranges in a single request with no chunking. If `NrtDailyUsage` fails, it falls back automatically to `get_ami_energy_usages_15min()`.

**Fallback triggers:**
- `response.has_errors` is true (GraphQL-level errors in the response body)
- 504 Gateway Timeout (`_is_gateway_timeout()` helper — wraps both bare `GraphQLError(status=504)` and `RetryExhaustedError` whose `last_error` is a 504)

All other exceptions propagate without fallback.

The `fuel_type` parameter is only used if the fallback path is taken; it controls the chunk window size in `get_ami_energy_usages_15min()`.

### AMI 15-Minute Endpoint (`get_ami_energy_usages_15min`)

Call this directly when you explicitly need 15-minute granularity. It handles three National Grid API constraints automatically.

#### 1. Record cap and chunking
The `amiEnergyUsages15Min` (`NrtDailyUsage15Min`) endpoint caps responses at ~10,000 records.
The Azure Application Gateway also enforces a backend timeout that cuts off range queries spanning more than roughly 45 days — whichever limit hits first.

The method automatically splits any date range that would exceed 45 days into chunks and concatenates results:

```python
# Constants in client.py
AMI_CHUNK_DAYS_ELECTRIC = 45  # 96 records/day × 45 = 4,320 (well inside 10k cap)
AMI_CHUNK_DAYS_GAS      = 45  # 24 records/day × 45 = 1,080
AMI_CHUNK_DAYS_DEFAULT  = 45  # conservative fallback when fuel_type is unknown
```

Chunks are built oldest-to-newest and then **reversed** before iteration so that the newest chunk is always requested first. This guarantees recent data is collected before any older chunk might hit the cold-storage boundary.

#### 2. Cold storage / 504 graceful truncation
National Grid serves approximately the last 45 days from today from hot storage. Data older than that sits in cold/archive storage. Any range query into cold storage — even a single-day request — receives a 504 Gateway Timeout from the Azure Application Gateway; this is a server-side constraint with no client-side workaround.

When a chunk returns a 504, the method:
- Detects it via `_is_gateway_timeout()` helper (checks `GraphQLError.status == 504` or `RetryExhaustedError.last_error.status == 504`)
- Logs a `WARNING` with the chunk index, date range, and record count collected so far
- **Stops iterating** (breaks the chunk loop) and returns whatever records were already collected from more-recent chunks

**Callers must not assume the returned list spans the full requested date range.** Request 180 days → receive ~45 days of records, no exception raised.

Note: `_should_retry()` in `client.py` short-circuits retries for `GraphQLError(status=504)` — cold-storage 504s are deterministic, so retrying wastes time. The `RetryConfig` still includes 504 in `retry_on_status` for transient gateway load on other endpoints.

#### 3. Daily-endpoint fallback
Some meters do not support the 15-minute operation and return a GraphQL errors response (e.g. `"Unable to cast object of type 'System.DateTime'"`). When this happens:
- **First chunk errors**: the method abandons chunking entirely and issues a single full-range request against the standard daily endpoint (`amiEnergyUsages` / `NrtDailyUsage`). This covers the full requested date range in one shot.
- **Mid-run errors** (i > 0, same endpoint, unexpected): the method switches to daily for all remaining chunks and continues.

The `fell_back` flag in the chunk loop tracks which path is active.

## Testing Patterns

Tests use mocked `aiohttp.ClientSession` objects with custom response classes (`_DummyResponse`, `_DummyRestResponse`). Key patterns:
- Monkeypatch `NationalGridAuth.async_login` to avoid real OIDC calls
- Verify header merging (auth token, subscription key, custom headers)
- Test endpoint routing for multi-endpoint queries
- Use `pytest-asyncio` for async test support (all tests marked with `@pytest.mark.asyncio`)
- 504 / graceful-truncation tests use `monkeypatch.setattr(client, "execute", AsyncMock(...))` directly on the client instance to avoid simulating the full HTTP retry machinery

Chunk-ordering tests set `mock_session.post.side_effect` in **newest-chunk-first** order because chunks are iterated newest-first after `windows.reverse()`.

## Key Constraints

- Python 3.13+ required (matches Home Assistant minimum; uses `slots=True`, `Self`, and modern type hints without `from __future__ import annotations`)
- `uv` is the required dependency manager (not pip or poetry)
- All GraphQL requests require `ocp-apim-subscription-key` header (configured in config.py)
- OIDC authentication is mandatory for production usage (username/password required)
- Session management follows context manager pattern (prefer `async with` over manual `close()`)
- Access tokens expire after ~1 hour and are automatically refreshed 5 minutes before expiration
- JWT signature verification (for the ID token) requires network access to fetch signing keys from the JWKS endpoint; `PyJWKClient` instances are cached at module level in `oidchelper.py` to avoid a HTTPS round-trip on every login

## Security

- **JWT Verification**: ID tokens are cryptographically verified using PyJWT with RS256 signature validation and full claim checks (exp, iss, aud)
- **Access Token sub Extraction**: The `sub` claim is read from the access token without signature verification — intentional, because Azure AD B2C's JWKS endpoint returns 403 for access-token key lookup; the token is received directly from the token endpoint over TLS so its origin is already trusted
- **Token Expiration**: Access tokens are tracked and automatically refreshed before expiration
- **Session Reuse**: Authentication reuses the client's session instead of creating duplicate connections
- **Robust Parsing**: Settings extraction uses dual-strategy parsing (string slicing + regex fallback)
