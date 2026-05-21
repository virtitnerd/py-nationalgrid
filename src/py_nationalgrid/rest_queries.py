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
        """
        Builds a GET RestRequest for the AMI interval reads endpoint using
        this object's values.

        Includes a `startDateTime` query parameter (merged with any
        provided `params`) and validates that `startDateTime` is present
        and formatted as "YYYY-MM-DD hh:mm:ss".

        Returns:
            RestRequest: A configured GET request for the interval reads
                path with merged query parameters and optional headers.

        Raises:
            ValueError: If `start_datetime` is empty or not in the format
                "YYYY-MM-DD hh:mm:ss".
        """
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
    """
    Create a RestRequest for AMI interval reads for a specific premise
    and service point.

    Parameters:
        start_datetime (str): Start date/time for the interval read in the
            format "YYYY-MM-DD hh:mm:ss" (e.g. "2024-01-01 00:00:00").

    Returns:
        RestRequest: A GET request configured for the interval reads
            endpoint with query parameters and optional headers applied.

    Raises:
        ValueError: If `start_datetime` is empty or not in the required
            "YYYY-MM-DD hh:mm:ss" format.
    """

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
    """
    Constructs a POST RestRequest to retrieve electric bill history from
    the business portal.

    Parameters:
        account_number: The account number to include in the request body
            as `accountNumber`.
        customer_number: The customer number to include in the request
            body as `customerNumber`.
        is_pal: Whether the account is part of a payment arrangement;
            included in the request body as `isPal`.

    Returns:
        A RestRequest configured for the ElectricBillHistory endpoint with
            a JSON body containing `accountNumber`, `customerNumber`, and
            `isPal`.
    """
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
    """
    Constructs a POST request for the gas bill history business-portal
    endpoint.

    Parameters:
        account_number (str): The gas account number to include in the
            request payload.
        customer_number (str): The customer identifier to include in the
            request payload.
        is_pal (bool): Whether the account is a Payment Arrangement (PAL);
            included as `isPal` in the payload.

    Returns:
        rest_request (RestRequest): A RestRequest configured for the
            GasBillHistory endpoint with JSON body
            `{"accountNumber": account_number, "customerNumber":
            customer_number, "isPal": is_pal}`.
    """
    return RestRequest(
        method="POST",
        path_or_url=_GAS_BILL_HISTORY_URL,
        json={"accountNumber": account_number, "customerNumber": customer_number, "isPal": is_pal},
    )


def _validate_start_datetime(value: str) -> None:
    """
    Validate that `value` is a non-empty datetime string in the format
    "YYYY-MM-DD hh:mm:ss".

    Parameters:
        value (str): The datetime string to validate.

    Raises:
        ValueError: If `value` is empty or cannot be parsed as
            "YYYY-MM-DD hh:mm:ss" (example: "2024-01-01 00:00:00").
    """
    if not value:
        raise ValueError("startDateTime is required and must be YYYY-MM-DD hh:mm:ss.")
    try:
        datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise ValueError(
            "startDateTime must be YYYY-MM-DD hh:mm:ss, e.g. 2024-01-01 00:00:00"
        ) from exc
