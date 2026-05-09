"""Async client for National Grid GraphQL and REST endpoints."""

import asyncio
import logging
import random
import time
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any, Self
from urllib.parse import urljoin

import aiohttp

from .auth import NationalGridAuth
from .config import NationalGridConfig, RetryConfig
from .exceptions import GraphQLError, RestAPIError, RetryExhaustedError
from .extractors import (
    extract_account_dashboard,
    extract_ami_energy_usages,
    extract_balanced_billing,
    extract_billing_account,
    extract_bills,
    extract_collection_arrangements,
    extract_energy_usage_costs,
    extract_energy_usages,
    extract_interval_reads,
    extract_linked_accounts,
    extract_meter_reading,
    extract_paperless_billing,
    extract_payment_plans,
    extract_payments,
)
from .graphql import GraphQLRequest, GraphQLResponse
from .models import (
    AccountDashboard,
    AccountLink,
    AmiEnergyUsage,
    BalancedBilling,
    Bill,
    BillingAccount,
    CollectionArrangement,
    EnergyUsage,
    EnergyUsageCost,
    IntervalRead,
    MeterReading,
    PaperlessBilling,
    Payment,
    PaymentPlan,
)
from .oidchelper import LoginData
from .queries import (
    account_dashboard_request,
    ami_energy_usages_request,
    balanced_billing_request,
    billing_account_info_request,
    bills_request,
    collection_arrangements_request,
    energy_usage_costs_request,
    energy_usages_request,
    linked_billing_accounts_request,
    meter_reading_request,
    paperless_billing_request,
    payment_plans_request,
    payments_request,
)
from .rest import RestResponse
from .rest_queries import realtime_meter_info_request

logger = logging.getLogger(__name__)

# Buffer time before actual expiration to refresh token (5 minutes)
TOKEN_EXPIRY_BUFFER_SECONDS = 300

# amiEnergyUsages15Min caps responses at ~10 000 records regardless of date range,
# and the Azure Application Gateway enforces a backend timeout.  Empirically the
# gateway tolerates ~60-day windows comfortably; anything larger risks a 504.
# If a chunk does return 504, the method automatically retries it split into
# AMI_CHUNK_FALLBACK_DAYS-day sub-chunks before giving up.
AMI_CHUNK_DAYS_ELECTRIC = 60
AMI_CHUNK_DAYS_GAS = 60
AMI_CHUNK_DAYS_DEFAULT = 60
# Sub-chunk size used when a full-size chunk hits a 504 Gateway Timeout.
AMI_CHUNK_FALLBACK_DAYS = 45


def _build_windows(d_from: date, d_to: date, chunk_days: int) -> list[tuple[date, date]]:
    """Return (start, end) pairs newest-first for the given date range and chunk size."""
    windows: list[tuple[date, date]] = []
    chunk_start = d_from
    while chunk_start <= d_to:
        chunk_end = min(chunk_start + timedelta(days=chunk_days - 1), d_to)
        windows.append((chunk_start, chunk_end))
        chunk_start = chunk_end + timedelta(days=1)
    windows.reverse()
    return windows


def _is_gateway_timeout(exc: Exception) -> bool:
    """Return True when exc is a 504 or an exhausted-retry TimeoutError.

    Both signal that the requested date range is too large for the server to
    handle in a single request; the caller should retry with smaller chunks.
    """
    if isinstance(exc, RetryExhaustedError):
        last = exc.last_error
        return (isinstance(last, GraphQLError) and last.status == 504) or isinstance(
            last, TimeoutError
        )
    if isinstance(exc, GraphQLError):
        return exc.status == 504
    return False


class NationalGridClient:
    """High-level client that reuses an aiohttp session."""

    def __init__(
        self,
        config: NationalGridConfig | None = None,
        *,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._config = config or NationalGridConfig()
        self._session = session
        self._owns_session = session is None
        self._access_token: str | None = None
        self._token_expires_at: float | None = None
        self._auth_lock = asyncio.Lock()
        self._session_lock = asyncio.Lock()
        self._login_data: LoginData = {}

    @property
    def config(self) -> NationalGridConfig:
        return self._config

    async def __aenter__(self) -> Self:
        await self._ensure_session()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        if self._session and not self._session.closed and self._owns_session:
            await self._session.close()
            self._session = None

    def _calculate_retry_delay(self, attempt: int, retry_config: RetryConfig) -> float:
        """Calculate retry delay with exponential backoff and jitter.

        Args:
            attempt: Current attempt number (0-indexed)
            retry_config: Retry configuration

        Returns:
            Delay in seconds before next retry
        """
        # Exponential backoff: initial_delay * (base ^ attempt)
        delay = retry_config.initial_delay * (retry_config.exponential_base**attempt)

        # Cap at max_delay
        delay = min(delay, retry_config.max_delay)

        # Add jitter (±25% random variation) to prevent thundering herd
        jitter = delay * 0.25 * (2 * random.random() - 1)
        delay_with_jitter = delay + jitter

        return max(0, delay_with_jitter)

    def _should_retry(self, error: Exception, attempt: int, retry_config: RetryConfig) -> bool:
        """Determine if request should be retried based on error and config.

        Args:
            error: The exception that occurred
            attempt: Current attempt number (0-indexed)
            retry_config: Retry configuration

        Returns:
            True if request should be retried, False otherwise
        """
        # Check if we've exhausted attempts
        if attempt >= retry_config.max_attempts - 1:
            return False

        # GraphQL 504s signal cold-storage boundary — deterministic, never transient.
        # Retrying will always produce another 504; skip remaining attempts immediately.
        if isinstance(error, GraphQLError) and error.status == 504:
            return False

        # Extract original error from wrapped exceptions
        check_error = error
        if isinstance(error, (GraphQLError, RestAPIError)):
            if error.original_error:
                check_error = error.original_error

        # Retry on connection errors
        if retry_config.retry_on_connection_errors and isinstance(
            check_error, (aiohttp.ClientConnectionError, aiohttp.ServerDisconnectedError)
        ):
            return True

        # Retry on timeout errors
        if retry_config.retry_on_timeout and isinstance(
            check_error, (aiohttp.ServerTimeoutError, asyncio.TimeoutError)
        ):
            return True

        # Retry on specific HTTP status codes
        if isinstance(check_error, aiohttp.ClientResponseError):
            if check_error.status in retry_config.retry_on_status:
                return True
            # Also retry on 401 to trigger re-auth (but only once)
            if check_error.status == 401 and attempt == 0:
                return True

        # Also check status directly on our custom errors
        if isinstance(error, (GraphQLError, RestAPIError)):
            if error.status and error.status in retry_config.retry_on_status:
                return True
            if error.status == 401 and attempt == 0:
                return True

        return False

    async def execute(
        self,
        request: GraphQLRequest,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> GraphQLResponse:
        """Execute a GraphQL request with retry logic.

        Args:
            request: GraphQL request to execute
            headers: Additional headers to include
            timeout: Request timeout in seconds

        Returns:
            GraphQL response

        Raises:
            GraphQLError: When the request fails after all retries
            RetryExhaustedError: When all retry attempts are exhausted
        """
        retry_config = self._config.retry_config
        last_error: Exception | None = None

        for attempt in range(retry_config.max_attempts):
            try:
                session = await self._ensure_session()
                access_token = await self._get_access_token(session)
                payload = request.to_payload()
                merged_headers = self._config.build_headers(headers, access_token=access_token)
                effective_timeout = aiohttp.ClientTimeout(total=timeout or self._config.timeout)
                endpoint = request.endpoint or self._config.endpoint

                if attempt > 0:
                    logger.info(
                        "Retrying GraphQL request to %s (attempt %d/%d)",
                        endpoint,
                        attempt + 1,
                        retry_config.max_attempts,
                    )
                else:
                    logger.debug("POST %s", endpoint)

                async with session.post(
                    endpoint,
                    json=payload,
                    headers=merged_headers,
                    timeout=effective_timeout,
                    ssl=self._config.verify_ssl,
                ) as response:
                    try:
                        response.raise_for_status()
                    except aiohttp.ClientResponseError as e:
                        # Special handling for 401: only clear the cached token if it
                        # is the same token that was sent in this request. A concurrent
                        # coroutine may have already refreshed it, and we must not wipe
                        # a freshly-obtained token because of a late-arriving 401 that
                        # was generated with the previous (now-stale) token.
                        if e.status == 401:
                            async with self._auth_lock:
                                if self._access_token == access_token:
                                    logger.info("Received 401, clearing cached token")
                                    self._access_token = None
                                    self._token_expires_at = None

                        # Read response body for error context
                        try:
                            body = await response.json(content_type=None)
                        except Exception:
                            body = None

                        raise GraphQLError(
                            f"GraphQL request failed with status {e.status}",
                            endpoint=endpoint,
                            query=request.query,
                            variables=dict(request.variables) if request.variables else None,
                            status=e.status,
                            response_body=body,
                            original_error=e,
                        ) from e

                    body = await response.json(content_type=None)

                graphql_response = GraphQLResponse.from_payload(body)
                if graphql_response.errors:
                    # Log summary at warning level (safe for production)
                    error_count = len(graphql_response.errors)
                    error_codes = [
                        err.get("extensions", {}).get("code", "UNKNOWN")
                        for err in graphql_response.errors
                    ]
                    logger.warning(
                        "GraphQL request returned %d error(s): %s",
                        error_count,
                        error_codes,
                    )
                    # Full details at debug level for troubleshooting
                    logger.debug("GraphQL error details: %s", graphql_response.errors)
                return graphql_response

            except Exception as e:
                last_error = e

                # Check if we should retry this error
                should_retry = self._should_retry(e, attempt, retry_config)

                # Check if this is the last attempt
                is_last_attempt = attempt >= retry_config.max_attempts - 1

                # If not retryable, raise immediately (unless last attempt)
                if not should_retry and not is_last_attempt:
                    # Convert generic errors to GraphQLError with context
                    if not isinstance(e, GraphQLError):
                        raise GraphQLError(
                            f"GraphQL request failed: {e}",
                            endpoint=request.endpoint or self._config.endpoint,
                            query=request.query,
                            variables=dict(request.variables) if request.variables else None,
                            original_error=e,
                        ) from e
                    raise

                # Last attempt: fall through to RetryExhaustedError
                if is_last_attempt:
                    break

                # Calculate delay and retry
                delay = self._calculate_retry_delay(attempt, retry_config)
                logger.debug(
                    "GraphQL request failed (%s), retrying in %.2f seconds (attempt %d/%d)",
                    type(e).__name__,
                    delay,
                    attempt + 1,
                    retry_config.max_attempts,
                )
                await asyncio.sleep(delay)

        # All retries exhausted
        logger.warning(
            "GraphQL request failed after %d attempt(s) (%s) — giving up",
            retry_config.max_attempts,
            type(last_error).__name__ if last_error else "unknown",
        )
        raise RetryExhaustedError(
            "GraphQL request failed after all retry attempts",
            attempts=retry_config.max_attempts,
            last_error=last_error or Exception("Unknown error"),
        )

    async def request_rest(
        self,
        method: str,
        path_or_url: str,
        *,
        params: Mapping[str, str] | None = None,
        json: Any | None = None,
        data: Any | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> RestResponse:
        """Issue a REST request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            path_or_url: URL path or full URL
            params: Query parameters
            json: JSON payload
            data: Form data
            headers: Additional headers
            timeout: Request timeout in seconds

        Returns:
            REST response

        Raises:
            RestAPIError: When the request fails after all retries
            RetryExhaustedError: When all retry attempts are exhausted
        """
        retry_config = self._config.retry_config
        last_error: Exception | None = None

        for attempt in range(retry_config.max_attempts):
            try:
                session = await self._ensure_session()
                access_token = await self._get_access_token(session)
                url = self._resolve_rest_url(path_or_url)
                content_type = "application/json" if json is not None else None
                merged_headers = self._config.build_headers(
                    headers,
                    access_token=access_token,
                    content_type=content_type,
                )
                effective_timeout = aiohttp.ClientTimeout(total=timeout or self._config.timeout)

                if attempt > 0:
                    logger.info(
                        "Retrying REST request to %s (attempt %d/%d)",
                        url,
                        attempt + 1,
                        retry_config.max_attempts,
                    )
                else:
                    logger.debug("%s %s", method.upper(), url)

                async with session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json,
                    data=data,
                    headers=merged_headers,
                    timeout=effective_timeout,
                    ssl=self._config.verify_ssl,
                ) as response:
                    try:
                        response.raise_for_status()
                    except aiohttp.ClientResponseError as e:
                        # Special handling for 401: only clear the cached token if it
                        # is the same token that was sent in this request. A concurrent
                        # coroutine may have already refreshed it, and we must not wipe
                        # a freshly-obtained token because of a late-arriving 401 that
                        # was generated with the previous (now-stale) token.
                        if e.status == 401:
                            async with self._auth_lock:
                                if self._access_token == access_token:
                                    logger.info("Received 401, clearing cached token")
                                    self._access_token = None
                                    self._token_expires_at = None

                        # Read response body for error context
                        try:
                            response_text = await response.text()
                        except Exception:
                            response_text = None

                        raise RestAPIError(
                            f"REST request failed with status {e.status}",
                            url=url,
                            method=method,
                            status=e.status,
                            response_text=response_text,
                            original_error=e,
                        ) from e

                    payload = await self._read_rest_payload(response)
                    return RestResponse(
                        status=response.status,
                        headers=dict(response.headers),
                        data=payload,
                    )

            except Exception as e:
                last_error = e

                # Check if we should retry this error
                should_retry = self._should_retry(e, attempt, retry_config)

                # Check if this is the last attempt
                is_last_attempt = attempt >= retry_config.max_attempts - 1

                # If not retryable, raise immediately (unless last attempt)
                if not should_retry and not is_last_attempt:
                    # Convert generic errors to RestAPIError with context
                    if not isinstance(e, RestAPIError):
                        url = self._resolve_rest_url(path_or_url)
                        raise RestAPIError(
                            f"REST request failed: {e}",
                            url=url,
                            method=method,
                            original_error=e,
                        ) from e
                    raise

                # Last attempt: fall through to RetryExhaustedError
                if is_last_attempt:
                    break

                # Calculate delay and retry
                delay = self._calculate_retry_delay(attempt, retry_config)
                logger.debug(
                    "REST request failed (%s), retrying in %.2f seconds (attempt %d/%d)",
                    type(e).__name__,
                    delay,
                    attempt + 1,
                    retry_config.max_attempts,
                )
                await asyncio.sleep(delay)

        # All retries exhausted
        logger.warning(
            "REST request failed after %d attempt(s) (%s) — giving up",
            retry_config.max_attempts,
            type(last_error).__name__ if last_error else "unknown",
        )
        raise RetryExhaustedError(
            "REST request failed after all retry attempts",
            attempts=retry_config.max_attempts,
            last_error=last_error or Exception("Unknown error"),
        )

    async def _get_access_token(self, session: aiohttp.ClientSession) -> str | None:
        # Check if we have a valid cached token
        if self._access_token and self._token_expires_at:
            # Add buffer time to refresh before actual expiration
            if time.time() < (self._token_expires_at - TOKEN_EXPIRY_BUFFER_SECONDS):
                return self._access_token
            logger.debug("Access token expired or expiring soon, refreshing")

        if not (self._config.username and self._config.password):
            return None

        async with self._auth_lock:
            # Double-check after acquiring lock
            if self._access_token and self._token_expires_at:
                if time.time() < (self._token_expires_at - TOKEN_EXPIRY_BUFFER_SECONDS):
                    return self._access_token

            auth_client = NationalGridAuth()
            token, expires_in = await auth_client.async_login(
                session,
                self._config.username,
                self._config.password,
                self._login_data,
                timeout=self._config.timeout,
            )
            if token and expires_in:
                self._access_token = token
                self._token_expires_at = time.time() + expires_in
                logger.debug("Access token refreshed, expires in %d seconds", expires_in)
            else:
                self._access_token = None
                self._token_expires_at = None

        return self._access_token

    def _resolve_rest_url(self, path_or_url: str) -> str:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url
        if not self._config.rest_base_url:
            raise ValueError("rest_base_url is required for relative REST paths.")
        return urljoin(self._config.rest_base_url.rstrip("/") + "/", path_or_url.lstrip("/"))

    async def _read_rest_payload(self, response: aiohttp.ClientResponse) -> Any:
        try:
            return await response.json(content_type=None)
        except aiohttp.ContentTypeError:
            return await response.text()

    async def _ensure_session(self) -> aiohttp.ClientSession:
        # Fast path: check without lock if session exists and is open
        if self._session and not self._session.closed:
            return self._session

        # Slow path: acquire lock to create session
        async with self._session_lock:
            # Double-check after acquiring lock
            if self._session and not self._session.closed:
                return self._session

            timeout = aiohttp.ClientTimeout(total=self._config.timeout)
            # Create connector with configured limits
            connector = aiohttp.TCPConnector(
                limit=self._config.connection_limit,
                limit_per_host=self._config.connection_limit_per_host,
                ttl_dns_cache=self._config.dns_cache_ttl,
            )
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
            )
            return self._session

    # -------------------------------------------------------------------------
    # Typed public methods
    # -------------------------------------------------------------------------

    async def get_linked_accounts(
        self,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> list[AccountLink]:
        """Get linked billing accounts with typed response.

        Args:
            headers: Additional headers to include
            timeout: Request timeout in seconds

        Returns:
            List of account links

        Raises:
            GraphQLError: When the GraphQL request fails
            DataExtractionError: When the expected data path is missing
            ValueError: When the response contains GraphQL errors
        """
        session = await self._ensure_session()
        await self._get_access_token(session)
        variables: Mapping[str, Any] | None = None
        sub_value = self._login_data.get("sub")
        if sub_value:
            variables = {"userId": sub_value}
        request = linked_billing_accounts_request(variables=variables)
        response = await self.execute(request, headers=headers, timeout=timeout)
        return extract_linked_accounts(response)

    async def get_billing_account(
        self,
        account_number: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> BillingAccount:
        """Get billing account info with typed response.

        Args:
            account_number: The billing account number
            headers: Additional headers to include
            timeout: Request timeout in seconds

        Returns:
            Billing account information

        Raises:
            GraphQLError: When the GraphQL request fails
            DataExtractionError: When the expected data path is missing
            ValueError: When the response contains GraphQL errors
        """
        request = billing_account_info_request(
            variables={"accountNumber": account_number},
        )
        response = await self.execute(request, headers=headers, timeout=timeout)
        return extract_billing_account(response)

    async def get_bills(
        self,
        account_number: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> list[Bill]:
        """Get bill history with typed response.

        Args:
            account_number: The billing account number
            headers: Additional headers to include
            timeout: Request timeout in seconds

        Returns:
            List of bills ordered newest-first

        Raises:
            GraphQLError: When the GraphQL request fails
            DataExtractionError: When the expected data path is missing
            ValueError: When the response contains GraphQL errors
        """
        request = bills_request(variables={"accountNumber": account_number})
        response = await self.execute(request, headers=headers, timeout=timeout)
        return extract_bills(response)

    async def get_payment_history(
        self,
        account_number: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> list[Payment]:
        """Get payment history with typed response.

        Args:
            account_number: The billing account number
            headers: Additional headers to include
            timeout: Request timeout in seconds

        Returns:
            List of payments ordered by the API default (most recent first)

        Raises:
            GraphQLError: When the GraphQL request fails
            DataExtractionError: When the expected data path is missing
            ValueError: When the response contains GraphQL errors
        """
        request = payments_request(variables={"accountNumber": account_number})
        response = await self.execute(request, headers=headers, timeout=timeout)
        return extract_payments(response)

    async def get_account_dashboard(
        self,
        account_number: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> AccountDashboard:
        """Get a comprehensive account dashboard snapshot with typed response.

        Returns current balance, paperless/autopay enrollment, scheduled
        payments, recent bills, and collection status in a single API call.

        Args:
            account_number: The billing account number
            headers: Additional headers to include
            timeout: Request timeout in seconds

        Returns:
            Account dashboard data

        Raises:
            GraphQLError: When the GraphQL request fails
            DataExtractionError: When the expected data path is missing
            ValueError: When the response contains GraphQL errors
        """
        session = await self._ensure_session()
        await self._get_access_token(session)
        variables: dict[str, Any] = {"accountNumber": account_number}
        sub_value = self._login_data.get("sub")
        if sub_value:
            variables["userId"] = sub_value
        request = account_dashboard_request(variables=variables)
        response = await self.execute(request, headers=headers, timeout=timeout)
        return extract_account_dashboard(response)

    async def get_meter_reading(
        self,
        account_number: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> MeterReading | None:
        """Get meter reading eligibility and last reading with typed response.

        Returns whether a self-read can be submitted, the last reading on file,
        and the current meter reading workflow status. Returns None when the
        account has no meter reading record (e.g. AMI smart meters that read
        automatically).

        Args:
            account_number: The billing account number
            headers: Additional headers to include
            timeout: Request timeout in seconds

        Returns:
            Meter reading data, or None if not available for this account

        Raises:
            GraphQLError: When the GraphQL request fails
            DataExtractionError: When the expected data path is missing
            ValueError: When the response contains GraphQL errors
        """
        request = meter_reading_request(account_number)
        response = await self.execute(request, headers=headers, timeout=timeout)
        return extract_meter_reading(response)

    async def get_paperless_billing(
        self,
        account_number: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> PaperlessBilling | None:
        """Get paperless billing enrollment status with typed response.

        Args:
            account_number: The billing account number
            headers: Additional headers to include
            timeout: Request timeout in seconds

        Returns:
            Paperless billing status, or None if not applicable for this account

        Raises:
            GraphQLError: When the GraphQL request fails
            DataExtractionError: When the expected data path is missing
            ValueError: When the response contains GraphQL errors
        """
        request = paperless_billing_request(account_number)
        response = await self.execute(request, headers=headers, timeout=timeout)
        return extract_paperless_billing(response)

    async def get_balanced_billing(
        self,
        account_number: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> BalancedBilling | None:
        """Get balanced (budget) billing plan status with typed response.

        Returns None when the account is not enrolled in a balanced billing plan.

        Args:
            account_number: The billing account number
            headers: Additional headers to include
            timeout: Request timeout in seconds

        Returns:
            Balanced billing plan data, or None if not enrolled

        Raises:
            GraphQLError: When the GraphQL request fails
            DataExtractionError: When the expected data path is missing
            ValueError: When the response contains GraphQL errors
        """
        request = balanced_billing_request(account_number)
        response = await self.execute(request, headers=headers, timeout=timeout)
        return extract_balanced_billing(response)

    async def get_payment_plans(
        self,
        account_number: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> list[PaymentPlan]:
        """Get active payment plans with typed response.

        Args:
            account_number: The billing account number
            headers: Additional headers to include
            timeout: Request timeout in seconds

        Returns:
            List of payment plans (empty list if none active)

        Raises:
            GraphQLError: When the GraphQL request fails
            DataExtractionError: When the expected data path is missing
            ValueError: When the response contains GraphQL errors
        """
        request = payment_plans_request(account_number)
        response = await self.execute(request, headers=headers, timeout=timeout)
        return extract_payment_plans(response)

    async def get_collection_arrangements(
        self,
        account_number: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> list[CollectionArrangement]:
        """Get collection arrangements with typed response.

        Args:
            account_number: The billing account number
            headers: Additional headers to include
            timeout: Request timeout in seconds

        Returns:
            List of collection arrangements (empty list if none active)

        Raises:
            GraphQLError: When the GraphQL request fails
            DataExtractionError: When the expected data path is missing
            ValueError: When the response contains GraphQL errors
        """
        request = collection_arrangements_request(account_number)
        response = await self.execute(request, headers=headers, timeout=timeout)
        return extract_collection_arrangements(response)

    async def get_energy_usage_costs(
        self,
        account_number: str,
        query_date: date | str,
        company_code: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> list[EnergyUsageCost]:
        """Get energy usage costs with typed response.

        Args:
            account_number: The billing account number
            query_date: Date for the query (date object or ISO string YYYY-MM-DD)
            company_code: Company code value (e.g., "NECO", "KEDNE")
            headers: Additional headers to include
            timeout: Request timeout in seconds

        Returns:
            List of energy usage costs

        Raises:
            GraphQLError: When the GraphQL request fails
            DataExtractionError: When the expected data path is missing
            ValueError: When the response contains GraphQL errors
        """
        date_str = query_date.isoformat() if isinstance(query_date, date) else query_date
        request = energy_usage_costs_request(
            variables={
                "accountNumber": account_number,
                "date": date_str,
                "companyCode": company_code,
            },
        )
        response = await self.execute(request, headers=headers, timeout=timeout)
        return extract_energy_usage_costs(response)

    async def get_energy_usages(
        self,
        account_number: str,
        from_month: int,
        first: int = 12,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> list[EnergyUsage]:
        """Get historical energy usages with typed response.

        Args:
            account_number: The billing account number
            from_month: Start month in YYYYMM format (e.g., 202401)
            first: Number of records to fetch (default 12)
            headers: Additional headers to include
            timeout: Request timeout in seconds

        Returns:
            List of energy usages

        Raises:
            GraphQLError: When the GraphQL request fails
            DataExtractionError: When the expected data path is missing
            ValueError: When the response contains GraphQL errors
        """
        request = energy_usages_request(
            variables={
                "accountNumber": account_number,
                "from": from_month,
                "first": first,
            },
        )
        response = await self.execute(request, headers=headers, timeout=timeout)
        return extract_energy_usages(response)

    async def get_ami_energy_usages(
        self,
        meter_number: str,
        premise_number: str | int,
        service_point_number: str | int,
        meter_point_number: str | int,
        date_from: date | str,
        date_to: date | str,
        *,
        fuel_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> list[AmiEnergyUsage]:
        """Get AMI energy usage data — primary recommended method.

        Tries the standard ``amiEnergyUsages`` (``NrtDailyUsage``) endpoint
        first.  Unlike ``NrtDailyUsage15Min``, this endpoint handles unrestricted
        date ranges in a single request with no chunking required.

        If ``NrtDailyUsage`` fails (GraphQL errors in the response body, or a
        504 Gateway Timeout), the method automatically falls back to
        ``get_ami_energy_usages_15min()``, which targets ``NrtDailyUsage15Min``
        with automatic date-range chunking.  All other exceptions propagate.

        Args:
            meter_number: The meter number
            premise_number: The premise number (auto-converts int to str)
            service_point_number: The service point number (auto-converts int to str)
            meter_point_number: The meter point number (auto-converts int to str)
            date_from: Start date (date object or ISO string YYYY-MM-DD)
            date_to: End date (date object or ISO string YYYY-MM-DD)
            fuel_type: Meter fuel type (``"ELECTRIC"`` or ``"GAS"``).  Only used
                if the fallback to ``get_ami_energy_usages_15min()`` is triggered;
                controls the chunk window size for that path.
            headers: Additional headers to include
            timeout: Request timeout in seconds

        Returns:
            List of AMI energy usages

        Raises:
            GraphQLError: When the GraphQL request fails with a non-504 error
            DataExtractionError: When the expected data path is missing
        """
        from_str = date_from.isoformat() if isinstance(date_from, date) else date_from
        to_str = date_to.isoformat() if isinstance(date_to, date) else date_to
        request = ami_energy_usages_request(
            variables={
                "meterNumber": meter_number,
                "premiseNumber": str(premise_number),
                "servicePointNumber": str(service_point_number),
                "meterPointNumber": str(meter_point_number),
                "dateFrom": from_str,
                "dateTo": to_str,
            },
        )

        try:
            response = await self.execute(request, headers=headers, timeout=timeout)
        except (RetryExhaustedError, GraphQLError) as e:
            if not _is_gateway_timeout(e):
                raise
            logger.warning(
                "amiEnergyUsages: 504 Gateway Timeout (%s to %s) — "
                "falling back to amiEnergyUsages15Min with chunking.",
                from_str,
                to_str,
            )
            return await self.get_ami_energy_usages_15min(
                meter_number,
                premise_number,
                service_point_number,
                meter_point_number,
                date_from,
                date_to,
                fuel_type=fuel_type,
                headers=headers,
                timeout=timeout,
            )

        if response.has_errors:
            logger.warning(
                "amiEnergyUsages returned GraphQL errors — "
                "falling back to amiEnergyUsages15Min with chunking."
            )
            return await self.get_ami_energy_usages_15min(
                meter_number,
                premise_number,
                service_point_number,
                meter_point_number,
                date_from,
                date_to,
                fuel_type=fuel_type,
                headers=headers,
                timeout=timeout,
            )

        return extract_ami_energy_usages(response)

    async def get_ami_energy_usages_15min(
        self,
        meter_number: str,
        premise_number: str | int,
        service_point_number: str | int,
        meter_point_number: str | int,
        date_from: date | str,
        date_to: date | str,
        *,
        fuel_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> list[AmiEnergyUsage]:
        """Get AMI 15-minute interval energy usage data with typed response.

        Targets ``amiEnergyUsages15Min`` (``NrtDailyUsage15Min``) directly.
        Call this when you explicitly need 15-minute granularity.  For most
        use cases prefer ``get_ami_energy_usages()``, which tries the daily
        ``NrtDailyUsage`` endpoint first and falls back here automatically.

        This method automatically falls back to the standard
        ``amiEnergyUsages`` (``NrtDailyUsage``) endpoint when the 15-minute
        API returns a GraphQL errors response for a given meter.

        When the requested date range exceeds the safe window for the meter's
        fuel type, the query is automatically split into chunks and the results
        concatenated:

        - ``"ELECTRIC"``: 60-day chunks
        - ``"GAS"`` or unknown: 60-day chunks

        If a chunk returns a 504 Gateway Timeout the method automatically retries
        it split into ``AMI_CHUNK_FALLBACK_DAYS``-day (45-day) sub-chunks.  If a
        sub-chunk also returns 504 the method stops and returns whatever records
        were already collected.

        If ``fuel_type`` is ``None`` the 60-day default is used.
        When the date range fits within a single chunk, no splitting occurs and
        the request is identical to the pre-chunking behaviour.

        Args:
            meter_number: The meter number
            premise_number: The premise number (auto-converts int to str)
            service_point_number: The service point number (auto-converts int to str)
            meter_point_number: The meter point number (auto-converts int to str)
            date_from: Start date (date object or ISO string YYYY-MM-DD)
            date_to: End date (date object or ISO string YYYY-MM-DD)
            fuel_type: Meter fuel type (``"ELECTRIC"`` or ``"GAS"``).  Controls
                the chunk window size.  Pass ``None`` to use the conservative default.
            headers: Additional headers to include
            timeout: Request timeout in seconds

        Returns:
            List of AMI energy usages (15-minute interval data, or daily data
            if the 15-minute endpoint returned GraphQL errors for this meter)

        Raises:
            GraphQLError: When the GraphQL request fails
            DataExtractionError: When the expected data path is missing
            ValueError: When the response contains GraphQL errors

        Note:
            504 Gateway Timeout responses are not raised. When a 60-day chunk hits
            a 504, the method retries it as 45-day sub-chunks.  If a sub-chunk also
            returns 504 (cold-storage boundary), the method logs a warning and
            returns whatever records were collected from more-recent chunks.
            Callers should not assume the returned list covers the full requested
            date range.
        """
        # Normalise dates to date objects so arithmetic is straightforward.
        d_from = date.fromisoformat(date_from) if isinstance(date_from, str) else date_from
        d_to = date.fromisoformat(date_to) if isinstance(date_to, str) else date_to

        chunk_days = (
            AMI_CHUNK_DAYS_ELECTRIC
            if (fuel_type or "").upper() == "ELECTRIC"
            else AMI_CHUNK_DAYS_GAS
        )

        # Build windows newest-first so recent (hot-storage) data is always fetched
        # before older chunks that may hit the cold-storage 504 boundary.
        windows = _build_windows(d_from, d_to, chunk_days)

        base_vars = {
            "meterNumber": meter_number,
            "premiseNumber": str(premise_number),
            "servicePointNumber": str(service_point_number),
            "meterPointNumber": str(meter_point_number),
        }

        chunk_results: list[list[AmiEnergyUsage]] = []
        fell_back = False  # True after the first chunk triggers the daily fallback

        for i, (w_from, w_to) in enumerate(windows):
            logger.debug(
                "amiEnergyUsages15Min: chunk %d/%d (%s to %s)%s",
                i + 1,
                len(windows),
                w_from,
                w_to,
                " [daily fallback]" if fell_back else "",
            )
            variables = {
                **base_vars,
                "dateFrom": w_from.isoformat(),
                "dateTo": w_to.isoformat(),
            }

            if fell_back:
                # Meter doesn't support 15min — stay on daily for remaining chunks.
                request = ami_energy_usages_request(variables=variables)
                try:
                    response = await self.execute(request, headers=headers, timeout=timeout)
                except (RetryExhaustedError, GraphQLError) as e:
                    if _is_gateway_timeout(e):
                        logger.warning(
                            "amiEnergyUsages fallback: request failed on chunk %d/%d "
                            "(%s to %s) — data is likely beyond the ~45-day accessible "
                            "window. Returning %d record(s) collected so far.",
                            i + 1,
                            len(windows),
                            w_from,
                            w_to,
                            sum(len(c) for c in chunk_results),
                        )
                        break
                    raise
                chunk_results.append(extract_ami_energy_usages(response))
                continue

            request = ami_energy_usages_request(
                variables=variables,
                root_field="amiEnergyUsages15Min",
                operation_name="NrtDailyUsage15Min",
            )
            try:
                response = await self.execute(request, headers=headers, timeout=timeout)
            except (RetryExhaustedError, GraphQLError) as e:
                if _is_gateway_timeout(e):
                    chunk_span = (w_to - w_from).days + 1
                    if chunk_span > AMI_CHUNK_FALLBACK_DAYS:
                        logger.warning(
                            "amiEnergyUsages15Min: request failed on %d-day chunk "
                            "%d/%d (%s to %s) — retrying as %d-day sub-chunks.",
                            chunk_span,
                            i + 1,
                            len(windows),
                            w_from,
                            w_to,
                            AMI_CHUNK_FALLBACK_DAYS,
                        )
                        hit_cold = False
                        for sw_from, sw_to in _build_windows(w_from, w_to, AMI_CHUNK_FALLBACK_DAYS):
                            sub_vars = {
                                **base_vars,
                                "dateFrom": sw_from.isoformat(),
                                "dateTo": sw_to.isoformat(),
                            }
                            sub_req = ami_energy_usages_request(
                                variables=sub_vars,
                                root_field="amiEnergyUsages15Min",
                                operation_name="NrtDailyUsage15Min",
                            )
                            try:
                                sub_resp = await self.execute(
                                    sub_req, headers=headers, timeout=timeout
                                )
                            except (RetryExhaustedError, GraphQLError) as sub_e:
                                if _is_gateway_timeout(sub_e):
                                    logger.warning(
                                        "amiEnergyUsages15Min: request failed on "
                                        "sub-chunk (%s to %s) — data is likely "
                                        "beyond the ~%d-day accessible window. "
                                        "Returning %d record(s) collected so far.",
                                        sw_from,
                                        sw_to,
                                        AMI_CHUNK_FALLBACK_DAYS,
                                        sum(len(c) for c in chunk_results),
                                    )
                                    hit_cold = True
                                    break
                                raise
                            chunk_results.append(
                                extract_ami_energy_usages(
                                    sub_resp, root_field="amiEnergyUsages15Min"
                                )
                            )
                        if hit_cold:
                            break
                        continue
                    logger.warning(
                        "amiEnergyUsages15Min: request failed on chunk %d/%d "
                        "(%s to %s) — data is likely beyond the ~%d-day accessible "
                        "window. Returning %d record(s) collected so far.",
                        i + 1,
                        len(windows),
                        w_from,
                        w_to,
                        AMI_CHUNK_FALLBACK_DAYS,
                        sum(len(c) for c in chunk_results),
                    )
                    break
                raise

            if response.has_errors:
                if i == 0:
                    # First chunk failed — meter doesn't support the 15min endpoint.
                    # Abandon chunking and fetch the entire range in one daily request.
                    logger.debug(
                        "amiEnergyUsages15Min returned errors; falling back to "
                        "amiEnergyUsages for full date range"
                    )
                    full_vars = {
                        **base_vars,
                        "dateFrom": d_from.isoformat(),
                        "dateTo": d_to.isoformat(),
                    }
                    request = ami_energy_usages_request(variables=full_vars)
                    try:
                        response = await self.execute(request, headers=headers, timeout=timeout)
                    except (RetryExhaustedError, GraphQLError) as e:
                        if _is_gateway_timeout(e):
                            logger.warning(
                                "amiEnergyUsages fallback: 504 on full-range daily request "
                                "(%s to %s) — returning empty list.",
                                d_from,
                                d_to,
                            )
                            return []
                        raise
                    return extract_ami_energy_usages(response)
                else:
                    # Mid-run fallback — shouldn't normally happen (same meter, same
                    # endpoint), but handle gracefully by switching to daily for the
                    # remainder.
                    logger.warning(
                        "amiEnergyUsages15Min returned errors on chunk %d/%d; "
                        "switching to amiEnergyUsages for remaining chunks",
                        i + 1,
                        len(windows),
                    )
                    fell_back = True
                    request = ami_energy_usages_request(variables=variables)
                    response = await self.execute(request, headers=headers, timeout=timeout)
                    chunk_results.append(extract_ami_energy_usages(response))
                    continue

            chunk_results.append(
                extract_ami_energy_usages(response, root_field="amiEnergyUsages15Min")
            )

        # Restore chronological order: we iterated newest-first, so reverse the
        # chunk list before flattening. Records within each chunk keep API order.
        return [r for chunk in reversed(chunk_results) for r in chunk]

    async def get_interval_reads(
        self,
        premise_number: str | int,
        service_point_number: str | int,
        start_datetime: datetime | str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> list[IntervalRead]:
        """Get real-time meter interval reads with typed response.

        Args:
            premise_number: The premise number (auto-converts int to str)
            service_point_number: The service point number (auto-converts int to str)
            start_datetime: Start datetime (datetime object or "YYYY-MM-DD HH:MM:SS" string)
            headers: Additional headers to include
            timeout: Request timeout in seconds

        Returns:
            List of interval reads

        Raises:
            RestAPIError: When the REST request fails
            DataExtractionError: When the response is not in expected format
        """
        premise_str = str(premise_number)
        service_point_str = str(service_point_number)

        if isinstance(start_datetime, datetime):
            datetime_str = start_datetime.strftime("%Y-%m-%d %H:%M:%S")
        else:
            datetime_str = start_datetime

        rest_request = realtime_meter_info_request(
            premise_number=premise_str,
            service_point_number=service_point_str,
            start_datetime=datetime_str,
            headers=headers,
        )
        try:
            response = await self.request_rest(
                rest_request.method,
                rest_request.path_or_url,
                params=rest_request.params,
                json=rest_request.json,
                data=rest_request.data,
                headers=rest_request.headers,
                timeout=timeout,
            )
        except RestAPIError as e:
            if e.status == 404:
                # The NRT API returns 404 when a service point has no interval reads
                # (e.g. GAS meters). Treat as empty — consistent with other get_* methods.
                return []
            raise
        return extract_interval_reads(response)
