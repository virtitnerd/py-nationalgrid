# Changelog

## [0.5.0] — 2026-04-11

First release of the **py-nationalgrid** fork (forked from the abandoned
[aionatgrid](https://github.com/RyanMorash/aionatgrid) 0.4.0).

### Added

- **AMI 15-minute chunking** (`get_ami_energy_usages_15min`): automatically splits
  date ranges exceeding 45 days into 45-day chunks to stay within the National
  Grid API's ~10,000 record cap and the Azure Application Gateway backend timeout.
- **Newest-first chunk ordering**: chunks are iterated from most-recent to oldest,
  guaranteeing that data within the hot-storage window is always collected before
  an older chunk may hit a 504.
- **Graceful 504 truncation**: when a chunk returns a 504 Gateway Timeout (cold/
  archive storage boundary), the method logs a warning and returns the records
  already collected rather than raising an exception. Callers should not assume
  the returned list covers the full requested date range.
- **504 retry short-circuit**: `_should_retry()` immediately returns `False` for
  `GraphQLError(status=504)` — cold-storage 504s are deterministic, so retrying
  wastes time.
- **Daily-endpoint fallback**: meters that don't support the 15-minute GraphQL
  operation fall back transparently to the daily `amiEnergyUsages` endpoint.
- **`__version__`** attribute on the package (`py_nationalgrid.__version__`).
- **PEP 561 `py.typed` marker** so downstream projects using mypy strict mode
  get inline type information.

### Fixed

- **`NationalGridConfig.with_overrides()` bug**: was using `dataclasses.asdict()`
  which flattened nested dataclasses (e.g. `RetryConfig`) into plain dicts,
  causing `AttributeError` on subsequent attribute access. Fixed with
  `dataclasses.replace()`.
- **JSON error boundary**: `json.loads()` calls in `oidchelper.py` now raise
  `CannotConnectError` on malformed responses instead of an unhandled
  `json.JSONDecodeError`.
- **Exception chaining**: `CannotConnectError` is now raised with `from err` so
  the original `aiohttp.ClientError` is preserved in the traceback.
- **JWKS client cache**: `PyJWKClient` instances are cached at module level in
  `oidchelper.py` to avoid a redundant HTTPS round-trip to the JWKS endpoint on
  every login.
- **`assert session is not None`** replaced with an explicit `RuntimeError` in
  `oidchelper.py` for a clear error message when the session is missing.

### Changed

- **Connection pool defaults** reduced from 100/30 to 10/10
  (`connection_limit` / `connection_limit_per_host`) — more appropriate for a
  single-API consumer.
- **Logger naming** unified to `logger` (from `_LOGGER`) throughout `auth.py`
  and `oidchelper.py`.
- Removed unused `typing-extensions` dependency.
