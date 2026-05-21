"""REST request builders for National Grid."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from .rest import RestRequest

AMI_INTERVAL_READS_PATH = (
    "amiadapter-cu-uwp-sys/v1/interval/reads/{premise_number}/{service_point_number}"
)

# Business portal (accountservice-cu-mba-exp) — uses idToken auth
BUSINESS_BASE_URL = "https://gridapi-cm-prod-appgw.dpit.nationalgrid.com/api"
BUSINESS_SUBSCRIPTION_KEY = "f1098e143d4c4d5b81eb0a86667d0ddf"
_ELECTRIC_BILL_HISTORY_URL = (
    f"{BUSINESS_BASE_URL}/accountservice-cu-mba-exp/v1/account/service/ElectricBillHistory"
)
_GAS_BILL_HISTORY_URL = (
    f"{BUSINESS_BASE_URL}/accountservice-cu-mba-exp/v1/account/service/GasBillHistory"
)


@dataclass(slots=True)
class RealtimeMeterInfo:
    """Parameters for the interval reads REST endpoint."""

    premise_number: str
    service_point_number: str
    start_datetime: str
    params: Mapping[str, str] | None = None
    headers: Mapping[str, str] | None = None

    def to_request(self) -> RestRequest:
        if not self.start_datetime:
            raise ValueError("start_datetime is required for interval reads requests.")
        merged_params: dict[str, str] = {"startDateTime": self.start_datetime}
        if self.params:
            merged_params.update(self.params)
        _validate_start_datetime(merged_params.get("startDateTime", ""))
        path = AMI_INTERVAL_READS_PATH.format(
            premise_number=self.premise_number,
            service_point_number=self.service_point_number,
        )
        return RestRequest(
            method="GET",
            path_or_url=path,
            params=merged_params,
            headers=self.headers,
        )


def realtime_meter_info_request(
    *,
    premise_number: str,
    service_point_number: str,
    start_datetime: str,
    params: Mapping[str, str] | None = None,
    headers: Mapping[str, str] | None = None,
) -> RestRequest:
    """Build the interval reads REST request."""

    return RealtimeMeterInfo(
        premise_number=premise_number,
        service_point_number=service_point_number,
        start_datetime=start_datetime,
        params=params,
        headers=headers,
    ).to_request()


def electric_bill_history_request(
    *,
    account_number: str,
    customer_number: str,
    is_pal: bool = False,
) -> RestRequest:
    """Build the ElectricBillHistory POST request for the business portal."""
    return RestRequest(
        method="POST",
        path_or_url=_ELECTRIC_BILL_HISTORY_URL,
        json={"accountNumber": account_number, "customerNumber": customer_number, "isPal": is_pal},
    )


def gas_bill_history_request(
    *,
    account_number: str,
    customer_number: str,
    is_pal: bool = False,
) -> RestRequest:
    """Build the GasBillHistory POST request for the business portal."""
    return RestRequest(
        method="POST",
        path_or_url=_GAS_BILL_HISTORY_URL,
        json={"accountNumber": account_number, "customerNumber": customer_number, "isPal": is_pal},
    )


def _validate_start_datetime(value: str) -> None:
    if not value:
        raise ValueError("startDateTime is required and must be YYYY-MM-DD hh:mm:ss.")
    try:
        datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise ValueError(
            "startDateTime must be YYYY-MM-DD hh:mm:ss, e.g. 2024-01-01 00:00:00"
        ) from exc
