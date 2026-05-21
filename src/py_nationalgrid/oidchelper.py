"""OIDC Login Helper and its constituent functions."""

import asyncio
import base64
import hashlib
import json
import logging
import re
import secrets
import ssl
from typing import Any, TypedDict
from urllib.parse import parse_qs, urlparse

import aiohttp
import jwt
from jwt import PyJWKClient

from .exceptions import CannotConnectError, InvalidAuthError
from .helpers import create_cookie_jar

logger = logging.getLogger(__name__)

# Module-level cache so the JWKS signing keys are fetched once and reused across
# logins rather than making a fresh HTTPS round-trip on every authentication call.
_jwks_clients: dict[str, PyJWKClient] = {}


def _get_jwks_client(jwks_uri: str) -> PyJWKClient:
    if jwks_uri not in _jwks_clients:
        _jwks_clients[jwks_uri] = PyJWKClient(jwks_uri)
    return _jwks_clients[jwks_uri]


class LoginData(TypedDict, total=False):
    """Dictionary to store login session data.

    Attributes:
        sub: User subject identifier from OIDC ID token (JWT 'sub' claim).
    """

    sub: str


async def async_auth_oidc(
    session: aiohttp.ClientSession | None,
    username: str,
    password: str,
    base_url: str,
    tenant_id: str,
    policy: str,
    client_id: str,
    redirect_uri: str,
    scope_auth: str,
    scope_access: str,
    self_asserted_endpoint: str,
    policy_confirm_endpoint: str,
    login_data: LoginData | None = None,
    timeout: float = 30.0,
    extra_auth_params: dict[str, str] | None = None,
) -> tuple[str, str, int] | tuple[None, None, None]:
    """Perform the login process and return an access token with expiry time.

    Args:
        session: Optional client session to use for OIDC authentication. If not
            provided (None), creates an internal session with proper cookie
            handling for Azure AD B2C.

            **Important**: If providing your own session, ensure it uses a
            CookieJar with quote_cookie=False for Azure AD B2C compatibility::

                from py_nationalgrid import create_cookie_jar
                cookie_jar = create_cookie_jar()
                session = aiohttp.ClientSession(cookie_jar=cookie_jar)

        username: National Grid account username/email.
        password: National Grid account password.
        base_url: Azure AD B2C base URL.
        tenant_id: Azure AD B2C tenant ID.
        policy: Azure AD B2C policy name.
        client_id: OAuth client ID.
        redirect_uri: OAuth redirect URI.
        scope_auth: OAuth scopes for authorization request.
        scope_access: OAuth scopes for token request.
        self_asserted_endpoint: Azure AD B2C self-asserted endpoint path.
        policy_confirm_endpoint: Azure AD B2C policy confirm endpoint path.
        login_data: Optional dict to store login session data (e.g., 'sub' claim).
        timeout: Request timeout in seconds for authentication requests (default: 30.0)

    Returns:
        Tuple of (access_token, id_token, expires_in_seconds) on success,
        (None, None, None) on failure.
    """
    # Use provided session or create one with proper SSL and cookie handling
    # Azure AD B2C requires specific cookie handling (quote_cookie=False)
    owns_session = session is None
    active_session: aiohttp.ClientSession
    if owns_session:
        ssl_context = await asyncio.get_running_loop().run_in_executor(
            None, ssl.create_default_context
        )
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        active_session = aiohttp.ClientSession(connector=connector, cookie_jar=create_cookie_jar())
    else:
        # session is guaranteed non-None here since owns_session = (session is None)
        if session is None:
            raise RuntimeError("session cannot be None when owns_session is False")
        active_session = session

    try:
        code_verifier = _generate_code_verifier()
        code_challenge = _generate_code_challenge(code_verifier)
        logger.debug("Generated PKCE code verifier and challenge")
        config = await _get_config(active_session, base_url, tenant_id, policy, timeout=timeout)
        logger.debug("Retrieved OAuth configuration")
        auth_code, sub_value = await _get_auth(
            active_session,
            config,
            code_challenge,
            username,
            password,
            client_id,
            redirect_uri,
            scope_auth,
            policy,
            self_asserted_endpoint,
            policy_confirm_endpoint,
            timeout,
            extra_auth_params,
        )
        if sub_value and login_data is not None:
            login_data["sub"] = sub_value
        if auth_code is None:
            logger.error("Failed to obtain authorization code")
            raise CannotConnectError("Failed to obtain authorization code")
        logger.debug("Obtained authorization code")

        tokens = await _get_access(
            active_session,
            config,
            auth_code,
            code_verifier,
            client_id,
            redirect_uri,
            scope_access,
            timeout,
        )

        if tokens and "access_token" in tokens:
            logger.debug("Successfully obtained access token")
            # Default to 3600 seconds (1 hour) if not provided
            expires_in = tokens.get("expires_in", 3600)
            # Guard against server returning nonsensical values (zero, negative,
            # or an impossibly large lifetime that would prevent refresh).
            if not isinstance(expires_in, int) or not (60 <= expires_in <= 86400):
                logger.warning(
                    "Unexpected expires_in value %r from token endpoint, defaulting to 3600",
                    expires_in,
                )
                expires_in = 3600
            access_token = str(tokens["access_token"])
            id_token = str(tokens.get("id_token", ""))

            if login_data is not None and not login_data.get("sub"):
                sub_value = _extract_sub_from_token(access_token)
                if sub_value:
                    login_data["sub"] = sub_value
                    logger.debug("Extracted sub from access token: %s", sub_value)

            return access_token, id_token, expires_in
        logger.error("Failed to obtain access token")
        raise CannotConnectError("Failed to obtain access token")

    except aiohttp.ClientError as err:
        logger.exception("Connection error during login")
        raise CannotConnectError(f"Connection error: {err}") from err
    finally:
        if owns_session:
            await active_session.close()


class ConfigDict(TypedDict):
    """Dictionary to store configuration details for OAuth."""

    authorization_endpoint: str
    issuer: str
    token_endpoint: str
    jwks_uri: str


class TokenDict(TypedDict, total=False):
    """Dictionary to store OAuth tokens."""

    access_token: str
    expires_in: int  # Token lifetime in seconds


def _generate_code_verifier() -> str:
    """Generate a code verifier for PKCE."""
    return secrets.token_urlsafe(32)


def _generate_code_challenge(code_verifier: str) -> str:
    """Generate a code challenge for PKCE."""
    code_challenge_digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(code_challenge_digest).decode("utf-8").rstrip("=")


def _extract_sub_from_token(token: str) -> str | None:
    """Extract the sub claim from a JWT access token without signature verification.

    Signature verification is intentionally skipped: the token is received
    directly from the Azure AD B2C token endpoint over TLS, so its origin is
    already trusted.  Attempting to verify against the JWKS endpoint fails with
    403 because B2C restricts JWKS access for access tokens differently from ID
    tokens.  We only read the sub claim — no authorization decisions are made on
    this value alone.
    """
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
        sub = claims.get("sub")
        return str(sub) if sub else None
    except jwt.InvalidTokenError as e:
        logger.warning("Failed to decode token for sub extraction: %s", e)
        return None


async def _get_config(
    session: aiohttp.ClientSession, base_url: str, tenant_id: str, policy: str, timeout: float
) -> ConfigDict:
    """
    Retrieve the OpenID Connect discovery document for the given tenant
    and policy and return it as a parsed ConfigDict.

    Parameters:
        session (aiohttp.ClientSession): HTTP session used to make the
            request.
        base_url (str): Base issuer URL.
        tenant_id (str): Tenant identifier to include in the discovery
            path.
        policy (str): Policy name to include in the discovery path.
        timeout (float): Request timeout in seconds.

    Returns:
        ConfigDict: Parsed OpenID configuration (e.g.,
            `authorization_endpoint`, `issuer`, `token_endpoint`,
            `jwks_uri`).

    Raises:
        CannotConnectError: If the HTTP response is not 200, the response
            body is empty, or the response contains invalid JSON.
    """
    config_url = f"{base_url}/{tenant_id}/{policy}/v2.0/.well-known/openid-configuration"
    logger.debug("Fetching OAuth configuration from: %s", config_url)
    config_text, _, status = await _fetch(session, config_url, timeout)
    if status != 200 or not config_text:
        logger.error("Failed to get configuration. Status: %s", status)
        raise CannotConnectError("Failed to get configuration")
    try:
        config: ConfigDict = json.loads(config_text)
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in OpenID configuration response: %s", e)
        raise CannotConnectError(f"Invalid JSON in OpenID configuration response: {e}") from e
    return config


async def _get_auth_silent(
    session: aiohttp.ClientSession,
    authorization_endpoint: str,
    auth_params: dict[str, str],
    redirect_uri: str,
    config: ConfigDict,
    client_id: str,
    timeout: float,
) -> tuple[str | None, str | None]:
    """
    Attempt silent OIDC authorization (when `prompt=none`) and extract the
    authorization code and subject from the redirect Location header.

    Performs a GET to the authorization endpoint with `allow_redirects=False`
    to capture the Location header returned by the identity provider. If the
    response is a redirect and the Location contains an authorization result,
    extracts and returns the `(code, sub)` pair; otherwise returns
    `(None, None)`.

    Returns:
        tuple[str | None, str | None]: `code` is the authorization code if
        present, `sub` is the subject (user identifier) if available; both
        are `None` on failure.
    """
    timeout_obj = aiohttp.ClientTimeout(total=timeout)
    try:
        async with session.get(
            authorization_endpoint,
            params=auth_params,
            allow_redirects=False,
            timeout=timeout_obj,
        ) as resp:
            status = resp.status
            location = str(resp.headers.get("Location", ""))
    except aiohttp.ClientError as err:
        raise CannotConnectError(f"Silent auth network error: {err}") from err

    if status not in (301, 302, 303, 307, 308) or not location:
        logger.warning(
            "Silent auth: expected redirect, got status %d (location=%r)", status, location
        )
        return None, None

    logger.debug("Silent auth redirect location: %s", location[:120])
    return _extract_auth_result(location, redirect_uri, config, client_id)


async def _get_auth(
    session: aiohttp.ClientSession,
    config: ConfigDict,
    code_challenge: str,
    username: str,
    password: str,
    client_id: str,
    redirect_uri: str,
    scope_auth: str,
    policy: str,
    self_asserted_endpoint: str,
    policy_confirm_endpoint: str,
    timeout: float,
    extra_auth_params: dict[str, str] | None = None,
) -> tuple[str | None, str | None]:
    """
    Obtain an OpenID Connect authorization code and the authenticated subject
    ("sub") using either an interactive form flow or silent SSO.

    Parameters:
        session (aiohttp.ClientSession): HTTP session to perform requests.
        config (ConfigDict): OIDC discovery configuration containing endpoints
            (authorization_endpoint, issuer, etc.).
        code_challenge (str): PKCE code challenge corresponding to the code
            verifier.
        username (str): Username to post for interactive sign-in.
        password (str): Password to post for interactive sign-in.
        client_id (str): OAuth client identifier.
        redirect_uri (str): Registered redirect URI to validate returned
            responses.
        scope_auth (str): Scope string for the authorization request.
        policy (str): B2C policy identifier used in credential and
            confirmation endpoints.
        self_asserted_endpoint (str): Relative endpoint (under the issuer
            base) used to post credentials.
        policy_confirm_endpoint (str): Relative endpoint used to confirm
            sign-in and follow resulting redirects.
        timeout (float): Total request timeout in seconds.
        extra_auth_params (dict[str, str] | None): Additional query parameters
            merged into the authorization request; when `{"prompt":"none"}` a
            silent (no-redirect) SSO attempt is performed.

    Returns:
        tuple[str | None, str | None]: `(auth_code, sub)` where `auth_code`
        is the authorization code if obtained, otherwise `None`, and `sub` is
        the subject claim extracted from the ID token (or `None` if not
        available or verification fails).
    """
    auth_params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope_auth,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if extra_auth_params:
        auth_params.update(extra_auth_params)

    if extra_auth_params and extra_auth_params.get("prompt") == "none":
        logger.debug("Requesting authorization code (silent SSO)")
        return await _get_auth_silent(
            session,
            config["authorization_endpoint"],
            auth_params,
            redirect_uri,
            config,
            client_id,
            timeout,
        )

    logger.debug("Requesting authorization code")
    auth_content, final_url, status = await _fetch(
        session, config["authorization_endpoint"], timeout, params=auth_params
    )
    if status != 200 or not auth_content:
        logger.error("Failed to get authorization. Status: %s", status)
        raise CannotConnectError("Failed to get authorization")

    settings = _extract_settings(auth_content)
    if not settings:
        logger.debug("No settings extracted, checking for direct authorization code")
        return _extract_auth_result(final_url, redirect_uri, config, client_id)

    logger.debug("Posting credentials")
    await _post_credentials(
        session,
        config["issuer"],
        settings,
        username,
        password,
        policy,
        self_asserted_endpoint,
        timeout,
    )
    logger.debug("Confirming sign-in")
    return await _confirm_signin(
        session,
        config["issuer"],
        settings,
        policy,
        policy_confirm_endpoint,
        redirect_uri,
        config,
        client_id,
        timeout,
    )


async def _get_access(
    session: aiohttp.ClientSession,
    config: ConfigDict,
    auth_code: str,
    code_verifier: str,
    client_id: str,
    redirect_uri: str,
    scope_access: str,
    timeout: float,
) -> TokenDict | None:
    """Get the access token."""
    token_data = {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
        "scope": scope_access,
    }
    logger.debug("Requesting access token")
    token_content, _, status = await _fetch(
        session, config["token_endpoint"], timeout, method="POST", data=token_data
    )
    if status != 200 or not token_content:
        logger.error("Failed to get access token. Status: %s", status)
        raise CannotConnectError("Failed to get access token")
    try:
        tokens: TokenDict = json.loads(token_content)
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in token response: %s", e)
        raise CannotConnectError(f"Invalid JSON in token response: {e}") from e
    return tokens


async def _fetch(
    session: aiohttp.ClientSession, url: str, timeout: float, **kwargs: Any
) -> tuple[str | None, str | None, int]:
    """Fetch data from a URL."""
    method = kwargs.pop("method", "GET")
    timeout_obj = aiohttp.ClientTimeout(total=timeout)
    try:
        logger.debug("Fetching URL: %s, Method: %s", url, method)
        async with session.request(method, url, timeout=timeout_obj, **kwargs) as response:
            content = await response.text()
            logger.debug("Fetch completed. Status: %s", response.status)
            return content, str(response.url), response.status
    except aiohttp.ClientError as err:
        logger.exception("Network error occurred")
        raise CannotConnectError("Network error occurred") from err


def _extract_settings(auth_content: str) -> dict[str, Any] | None:
    """Extract settings from the authorization content using multiple strategies."""
    logger.debug("Extracting settings from authorization content")

    # Strategy 1: String slicing (original method, fastest)
    settings_start = auth_content.find("var SETTINGS = ")
    if settings_start != -1:
        settings_end = auth_content.find(";", settings_start)
        if settings_end != -1:
            settings_json = auth_content[settings_start + 15 : settings_end].strip()
            try:
                settings: dict[str, Any] = json.loads(settings_json)
                logger.debug("Settings extracted via string slicing")
                return settings
            except json.JSONDecodeError:
                logger.warning("String slicing extracted invalid JSON, trying regex")

    # Strategy 2: Regex pattern matching (more robust fallback)
    # Matches: var SETTINGS = {...}; or var SETTINGS={...};
    pattern = r"var\s+SETTINGS\s*=\s*(\{[^;]+\})\s*;"
    match = re.search(pattern, auth_content)
    if match:
        settings_json = match.group(1).strip()
        try:
            settings = json.loads(settings_json)
            logger.debug("Settings extracted via regex")
            return settings
        except json.JSONDecodeError:
            logger.exception("Failed to parse settings JSON from regex match")

    logger.debug(
        "Could not extract settings from authorization content; "
        "will fall back to checking for a direct authorization code in the redirect URL"
    )
    return None


def _check_b2c_error_response(content: str) -> tuple[str, str] | None:
    """Check if a B2C response contains an error.

    Azure AD B2C sometimes returns HTTP 200 with an HTML error page instead of
    a proper error status code. This function detects such responses.

    Args:
        content: The response body text

    Returns:
        Tuple of (error_type, error_detail) if an error is detected, None otherwise.
    """
    # Check for GLOBALEX error object (indicates B2C exception)
    globalex_match = re.search(r"var GLOBALEX\s*=\s*\{([^}]+)\}", content)
    if globalex_match:
        try:
            # Parse the GLOBALEX object
            globalex_text = "{" + globalex_match.group(1) + "}"
            globalex = json.loads(globalex_text)
            detail = globalex.get("Detail", "Unknown error")
            correlation_id = globalex.get("CorrelationId", "")
            logger.debug("B2C error detected. CorrelationId: %s", correlation_id)
            return ("B2C_EXCEPTION", detail)
        except json.JSONDecodeError:
            pass

    # Check for specific error indicators in SETTINGS
    settings_match = re.search(r'"api"\s*:\s*"GlobalException"', content)
    if settings_match:
        # Try to extract error message from CONTENT object
        content_match = re.search(r'"error-title"\s*:\s*"([^"]+)"', content)
        error_title = content_match.group(1) if content_match else "Authentication error"
        # Unescape HTML entities
        error_title = error_title.replace("&#39;", "'").replace("&quot;", '"')
        return ("GLOBAL_EXCEPTION", error_title)

    # Check for common B2C error codes
    error_code_match = re.search(r'(AADB2C\d+)[:\s]+([^<"\n]+)', content)
    if error_code_match:
        return (error_code_match.group(1), error_code_match.group(2).strip())

    # Check for password-specific errors
    if "Your password is incorrect" in content:
        return ("INVALID_PASSWORD", "Your password is incorrect")
    if "We can't find an account" in content or "account with that email" in content:
        return ("ACCOUNT_NOT_FOUND", "Account not found with that email address")
    if "account is locked" in content.lower():
        return ("ACCOUNT_LOCKED", "Account is locked")

    return None


async def _post_credentials(
    session: aiohttp.ClientSession,
    issuer: str,
    settings: dict[str, Any],
    username: str,
    password: str,
    policy: str,
    self_asserted_endpoint: str,
    timeout: float,
) -> None:
    """Post credentials to the server."""
    base_url = issuer.rsplit("/", 2)[0]
    logger.debug("Posting credentials to %s", base_url)
    response_content, _, status = await _fetch(
        session,
        f"{base_url}/{policy}/{self_asserted_endpoint}",
        timeout,
        method="POST",
        data={
            "tx": settings["transId"],
            "p": policy,
            "request_type": "RESPONSE",
            "signInName": username,
            "password": password,
        },
        headers={"X-CSRF-TOKEN": settings["csrf"]},
    )
    if status != 200:
        logger.error("Failed to post credentials. Status: %s", status)
        raise InvalidAuthError("Invalid username or password")

    # Check response body for B2C errors (B2C returns 200 even on auth failures)
    if response_content:
        error_info = _check_b2c_error_response(response_content)
        if error_info:
            error_type, error_detail = error_info
            logger.error("B2C authentication error: %s - %s", error_type, error_detail)
            if "password" in error_detail.lower() or "credential" in error_detail.lower():
                raise InvalidAuthError(f"Invalid username or password: {error_detail}")
            raise CannotConnectError(f"Authentication failed: {error_detail}")

    logger.debug("Credentials posted successfully")


async def _confirm_signin(
    session: aiohttp.ClientSession,
    issuer: str,
    settings: dict[str, Any],
    policy: str,
    policy_confirm_endpoint: str,
    redirect_uri: str,
    config: ConfigDict,
    client_id: str,
    timeout: float,
) -> tuple[str | None, str | None]:
    """Confirm the sign-in process."""
    base_url = issuer.rsplit("/", 2)[0]
    logger.debug("Confirming sign-in at %s", base_url)
    _, final_url, status = await _fetch(
        session,
        f"{base_url}/{policy}/{policy_confirm_endpoint}",
        timeout,
        params={
            "rememberMe": "false",
            "csrf_token": settings["csrf"],
            "tx": settings["transId"],
            "p": policy,
        },
        allow_redirects=True,
    )
    if status != 200:
        logger.error("Failed to confirm signin. Status: %s", status)
        if status == 403:
            raise InvalidAuthError("Invalid username or password")
        raise CannotConnectError("Failed to confirm signin")
    if final_url:
        auth_code, sub_value = _extract_auth_result(final_url, redirect_uri, config, client_id)
        if auth_code:
            logger.debug("Sign-in confirmed, authorization code obtained")
        else:
            parsed_params = _parse_redirect_params(final_url)
            if "error" in parsed_params:
                logger.error(
                    "Sign-in failed with error: %s, %s",
                    parsed_params.get("error"),
                    parsed_params.get("error_description"),
                )
                raise InvalidAuthError("Sign-in failed")
            logger.warning("Sign-in confirmed, but no authorization code found")
        return auth_code, sub_value
    logger.warning("Sign-in confirmation did not result in a final URL")
    return None, None


def _extract_auth_result(
    final_url: str | None, redirect_uri: str, config: ConfigDict, client_id: str
) -> tuple[str | None, str | None]:
    if not final_url:
        return None, None
    # Compare scheme, host, and path exactly rather than using startswith, which
    # would incorrectly accept URLs like "…/auth-landing-other" when the expected
    # redirect_uri ends in "…/auth-landing".
    expected = urlparse(redirect_uri)
    actual = urlparse(final_url)
    if not (
        actual.scheme == expected.scheme
        and actual.netloc == expected.netloc
        and actual.path == expected.path
    ):
        return None, None
    parsed_params = _parse_redirect_params(final_url)
    auth_code = parsed_params.get("code", [None])[0]
    id_token = parsed_params.get("id_token", [None])[0]
    sub_value = _extract_sub_from_id_token(id_token, config, client_id) if id_token else None
    return auth_code, sub_value


def _parse_redirect_params(final_url: str) -> dict[str, list[str]]:
    parsed = urlparse(final_url)
    fragment = parsed.fragment
    query = parsed.query
    if fragment:
        return parse_qs(fragment)
    return parse_qs(query)


def _extract_sub_from_id_token(
    id_token: str | None, config: ConfigDict, client_id: str
) -> str | None:
    """Extract and verify the sub claim from an id_token with proper signature validation."""
    if not id_token:
        return None

    try:
        signing_key = _get_jwks_client(config["jwks_uri"]).get_signing_key_from_jwt(id_token)

        # Verify the token signature and validate claims
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=config["issuer"],
            audience=client_id,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "verify_iss": True,
                "verify_aud": True,
            },
        )

        sub_value = claims.get("sub")
        if sub_value:
            logger.debug("Extracted and verified sub from id_token")
            return str(sub_value)
        else:
            logger.warning("sub claim not found in verified id_token")
            return None

    except jwt.ExpiredSignatureError:
        logger.error("id_token has expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.error("id_token validation failed: %s", e)
        return None
    except Exception as e:
        logger.exception("Unexpected error validating id_token: %s", e)
        return None
