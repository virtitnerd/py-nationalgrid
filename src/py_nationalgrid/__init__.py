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
    AccountDashboard,
    AccountLink,
    AccountLinkBillingAccount,
    AccountLinksConnection,
    AmiEnergyUsage,
    AmiEnergyUsagesConnection,
    BalancedBilling,
    Bill,
    BillingAccount,
    CollectionArrangement,
    CollectionArrangementDetail,
    CollectionArrangementDetailsConnection,
    CustomerInfo,
    DashboardBill,
    DashboardScheduledPayment,
    EnergyUsage,
    EnergyUsageCost,
    EnergyUsageCostsConnection,
    EnergyUsagesConnection,
    FuelType,
    IntervalRead,
    Meter,
    MeterConnection,
    MeterReading,
    PaperlessBilling,
    Payment,
    PaymentPlan,
    RecurringPayDetails,
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
    "AccountDashboard",
    "AccountLink",
    "AccountLinkBillingAccount",
    "AccountLinksConnection",
    "AmiEnergyUsage",
    "AmiEnergyUsagesConnection",
    "BalancedBilling",
    "Bill",
    "BillingAccount",
    "CollectionArrangement",
    "CollectionArrangementDetail",
    "CollectionArrangementDetailsConnection",
    "CustomerInfo",
    "DashboardBill",
    "DashboardScheduledPayment",
    "EnergyUsage",
    "EnergyUsageCost",
    "EnergyUsageCostsConnection",
    "EnergyUsagesConnection",
    "FuelType",
    "IntervalRead",
    "Meter",
    "MeterConnection",
    "MeterReading",
    "PaperlessBilling",
    "Payment",
    "PaymentPlan",
    "RecurringPayDetails",
    "ServiceAddress",
]
