"""REST request builders for National Grid."""

from .rest import RestRequest

# Business portal (accountservice-cu-mba-exp) — uses idToken auth
BUSINESS_BASE_URL = "https://gridapi-cm-prod-appgw.dpit.nationalgrid.com/api"
BUSINESS_SUBSCRIPTION_KEY = "f1098e143d4c4d5b81eb0a86667d0ddf"
_ELECTRIC_BILL_HISTORY_URL = (
    f"{BUSINESS_BASE_URL}/accountservice-cu-mba-exp/v1/account/service/ElectricBillHistory"
)
_GAS_BILL_HISTORY_URL = (
    f"{BUSINESS_BASE_URL}/accountservice-cu-mba-exp/v1/account/service/GasBillHistory"
)


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
