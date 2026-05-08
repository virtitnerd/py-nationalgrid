"""Public package exports for py_nationalgrid."""

from importlib.metadata import version as _pkg_version

from .client import NationalGridClient
from .config import NationalGridConfig, RetryConfig
from .exceptions import (
    CannotConnectError,
    DataExtractionError,
    GraphQLError,
    InvalidAuthError,
    NationalGridError,
    RestAPIError,
    RetryExhaustedError,
)
from .helpers import create_cookie_jar
from .models import (
    AccountLink,
    AccountLinkBillingAccount,
    AccountLinksConnection,
    AmiEnergyUsage,
    AmiEnergyUsagesConnection,
    Bill,
    BillingAccount,
    CustomerInfo,
    EnergyUsage,
    EnergyUsageCost,
    EnergyUsageCostsConnection,
    EnergyUsagesConnection,
    FuelType,
    IntervalRead,
    Meter,
    MeterConnection,
    ServiceAddress,
)
from .oidchelper import LoginData

__version__: str = _pkg_version("py-nationalgrid")

__all__ = [
    "__version__",
    "NationalGridClient",
    "NationalGridConfig",
    "RetryConfig",
    "LoginData",
    "create_cookie_jar",
    # Exceptions
    "NationalGridError",
    "GraphQLError",
    "RestAPIError",
    "RetryExhaustedError",
    "DataExtractionError",
    "CannotConnectError",
    "InvalidAuthError",
    # TypedDict models
    "AccountLink",
    "AccountLinkBillingAccount",
    "AccountLinksConnection",
    "AmiEnergyUsage",
    "AmiEnergyUsagesConnection",
    "Bill",
    "BillingAccount",
    "CustomerInfo",
    "EnergyUsage",
    "EnergyUsageCost",
    "EnergyUsageCostsConnection",
    "EnergyUsagesConnection",
    "FuelType",
    "IntervalRead",
    "Meter",
    "MeterConnection",
    "ServiceAddress",
]
