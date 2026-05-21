"""Authentication helpers for the National Grid API."""

import logging

import aiohttp

from .oidchelper import LoginData, async_auth_oidc

logger = logging.getLogger(__name__)


class NationalGridAuth:
    """Auth for the National Grid consumer portal (myaccount.nationalgrid.com)."""

    @staticmethod
    def timezone() -> str:
        """Return the timezone."""
        return "America/New_York"

    BASE_URL = "https://login.nationalgrid.com"
    TENANT_ID = "0e1366c5-731c-42b3-90d3-508039d9e70f"
    POLICY = "B2C_1A_UWP_NationalGrid_convert_merge_signin"
    CLIENT_ID = "36488660-e86a-4a0d-8316-3df49af8d06d"
    REDIRECT_URI = "https://myaccount.nationalgrid.com/auth-landing"
    APPLICATION_URI = f"{BASE_URL}/"
    SCOPE_AUTH = "openid profile offline_access"
    SCOPE_ACCESS = f"{CLIENT_ID} openid profile offline_access"
    SELF_ASSERTED_ENDPOINT = "SelfAsserted"
    POLICY_CONFIRM_ENDPOINT = "api/CombinedSigninAndSignup/confirmed"

    async def async_login(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        login_data: LoginData,
        timeout: float = 30.0,
    ) -> tuple[str, str, int] | tuple[None, None, None]:
        """Perform the login process and return an access token with expiry.

        Args:
            timeout: Request timeout in seconds for authentication requests (default: 30.0)

        Returns:
            Tuple of (access_token, id_token, expires_in_seconds) on success,
            (None, None, None) on failure.
        """
        logger.debug("Starting login process for National Grid")
        return await async_auth_oidc(
            session,
            username,
            password,
            NationalGridAuth.BASE_URL,
            NationalGridAuth.TENANT_ID,
            NationalGridAuth.POLICY,
            NationalGridAuth.CLIENT_ID,
            NationalGridAuth.REDIRECT_URI,
            NationalGridAuth.SCOPE_AUTH,
            NationalGridAuth.SCOPE_ACCESS,
            NationalGridAuth.SELF_ASSERTED_ENDPOINT,
            NationalGridAuth.POLICY_CONFIRM_ENDPOINT,
            login_data,
            timeout,
        )


class NationalGridBusinessAuth:
    """Auth for the National Grid business portal (accountmanager.nationalgrid.com).

    Uses prompt=none silent SSO: after the consumer portal OIDC flow has already
    established a B2C session (cookies on login.nationalgrid.com), this class
    silently acquires a business portal token with aud == BUSINESS_CLIENT_ID by
    passing prompt=none to the authorize endpoint without showing any login UI.

    The tenant path differs from the consumer portal:
    - Consumer: login.nationalgridus.com
    - Business: loginnationalgridus.onmicrosoft.com
    Both resolve to the same B2C tenant (GUID 0e1366c5-…), so SSO cookies are shared.
    """

    BASE_URL = NationalGridAuth.BASE_URL
    TENANT_ID = "loginnationalgridus.onmicrosoft.com"
    POLICY = NationalGridAuth.POLICY
    CLIENT_ID = "a26ad492-5d24-49f0-a4f7-d79e3a2bb1ef"
    REDIRECT_URI = "https://accountmanager.nationalgrid.com/mybusinessaccount"
    SCOPE_AUTH = "openid profile offline_access"
    SCOPE_ACCESS = "https://login.nationalgridus.com/uwp2.0/api.read openid profile offline_access"
    SELF_ASSERTED_ENDPOINT = NationalGridAuth.SELF_ASSERTED_ENDPOINT
    POLICY_CONFIRM_ENDPOINT = NationalGridAuth.POLICY_CONFIRM_ENDPOINT

    async def async_login(
        self,
        session: aiohttp.ClientSession | None,
        username: str,
        password: str,
        login_data: LoginData,
        timeout: float = 30.0,
    ) -> tuple[str, str, int] | tuple[None, None, None]:
        """Silently acquire a business portal token using the existing B2C SSO session.

        The session must already contain B2C cookies from a consumer portal login.
        prompt=none causes B2C to redirect immediately with a code rather than
        showing any login UI.  The returned id_token has aud == BUSINESS_CLIENT_ID.
        """
        logger.debug("Starting business portal silent SSO login")
        return await async_auth_oidc(
            session,
            username,
            password,
            NationalGridBusinessAuth.BASE_URL,
            NationalGridBusinessAuth.TENANT_ID,
            NationalGridBusinessAuth.POLICY,
            NationalGridBusinessAuth.CLIENT_ID,
            NationalGridBusinessAuth.REDIRECT_URI,
            NationalGridBusinessAuth.SCOPE_AUTH,
            NationalGridBusinessAuth.SCOPE_ACCESS,
            NationalGridBusinessAuth.SELF_ASSERTED_ENDPOINT,
            NationalGridBusinessAuth.POLICY_CONFIRM_ENDPOINT,
            login_data,
            timeout,
            extra_auth_params={"prompt": "none"},
        )
