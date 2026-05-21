"""Data extraction helpers for converting raw responses to typed models."""

from typing import cast

from .exceptions import DataExtractionError
from .graphql import GraphQLResponse
from .models import (
    AccountDashboard,
    AccountLink,
    AmiEnergyUsage,
    BalancedBilling,
    Bill,
    BillingAccount,
    CollectionArrangement,
    DashboardBill,
    DashboardScheduledPayment,
    ElectricBillRecord,
    EnergyUsage,
    EnergyUsageCost,
    GasBillRecord,
    IntervalRead,
    MeterReading,
    PaperlessBilling,
    Payment,
    PaymentPlan,
    PremiseNode,
)
from .rest import RestResponse


def extract_linked_accounts(response: GraphQLResponse) -> list[AccountLink]:
    """Extract linked accounts from a GraphQL response.

    Args:
        response: The GraphQL response from a linked billing accounts query

    Returns:
        List of account links

    Raises:
        ValueError: If the response contains GraphQL errors
        DataExtractionError: If the expected data path is missing
    """
    response.raise_on_errors()

    if response.data is None:
        raise DataExtractionError(
            "Response data is null",
            path="data",
            response_data=None,
        )

    user = response.data.get("user")
    if user is None:
        raise DataExtractionError(
            "Missing 'user' field in response",
            path="data.user",
            response_data=response.data,
        )

    account_links = user.get("accountLinks")
    if account_links is None:
        raise DataExtractionError(
            "Missing 'accountLinks' field in response",
            path="data.user.accountLinks",
            response_data=response.data,
        )

    nodes = account_links.get("nodes")
    if nodes is None:
        raise DataExtractionError(
            "Missing 'nodes' field in accountLinks",
            path="data.user.accountLinks.nodes",
            response_data=response.data,
        )

    return cast(list[AccountLink], nodes)


def extract_billing_account(response: GraphQLResponse) -> BillingAccount:
    """Extract billing account info from a GraphQL response.

    Args:
        response: The GraphQL response from a billing account info query

    Returns:
        Billing account information

    Raises:
        ValueError: If the response contains GraphQL errors
        DataExtractionError: If the expected data path is missing
    """
    response.raise_on_errors()

    if response.data is None:
        raise DataExtractionError(
            "Response data is null",
            path="data",
            response_data=None,
        )

    billing_account = response.data.get("billingAccount")
    if billing_account is None:
        raise DataExtractionError(
            "Missing 'billingAccount' field in response",
            path="data.billingAccount",
            response_data=response.data,
        )

    return cast(BillingAccount, billing_account)


def extract_energy_usage_costs(response: GraphQLResponse) -> list[EnergyUsageCost]:
    """Extract energy usage costs from a GraphQL response.

    Args:
        response: The GraphQL response from an energy usage costs query

    Returns:
        List of energy usage costs

    Raises:
        ValueError: If the response contains GraphQL errors
        DataExtractionError: If the expected data path is missing
    """
    response.raise_on_errors()

    if response.data is None:
        raise DataExtractionError(
            "Response data is null",
            path="data",
            response_data=None,
        )

    energy_usage_costs = response.data.get("energyUsageCosts")
    if energy_usage_costs is None:
        raise DataExtractionError(
            "Missing 'energyUsageCosts' field in response",
            path="data.energyUsageCosts",
            response_data=response.data,
        )

    nodes = energy_usage_costs.get("nodes")
    if nodes is None:
        raise DataExtractionError(
            "Missing 'nodes' field in energyUsageCosts",
            path="data.energyUsageCosts.nodes",
            response_data=response.data,
        )

    return cast(list[EnergyUsageCost], nodes)


def extract_energy_usages(response: GraphQLResponse) -> list[EnergyUsage]:
    """Extract energy usages from a GraphQL response.

    Args:
        response: The GraphQL response from an energy usages query

    Returns:
        List of energy usages

    Raises:
        ValueError: If the response contains GraphQL errors
        DataExtractionError: If the expected data path is missing
    """
    response.raise_on_errors()

    if response.data is None:
        raise DataExtractionError(
            "Response data is null",
            path="data",
            response_data=None,
        )

    energy_usages = response.data.get("energyUsages")
    if energy_usages is None:
        raise DataExtractionError(
            "Missing 'energyUsages' field in response",
            path="data.energyUsages",
            response_data=response.data,
        )

    nodes = energy_usages.get("nodes")
    if nodes is None:
        raise DataExtractionError(
            "Missing 'nodes' field in energyUsages",
            path="data.energyUsages.nodes",
            response_data=response.data,
        )

    return cast(list[EnergyUsage], nodes)


def extract_ami_energy_usages(
    response: GraphQLResponse,
    *,
    root_field: str = "amiEnergyUsages",
) -> list[AmiEnergyUsage]:
    """Extract AMI energy usages from a GraphQL response.

    Args:
        response: The GraphQL response from an AMI energy usages query
        root_field: The root GraphQL field name (e.g. "amiEnergyUsages" or
            "amiEnergyUsages15Min")

    Returns:
        List of AMI energy usages

    Raises:
        ValueError: If the response contains GraphQL errors
        DataExtractionError: If the expected data path is missing
    """
    response.raise_on_errors()

    if response.data is None:
        raise DataExtractionError(
            "Response data is null",
            path="data",
            response_data=None,
        )

    ami_energy_usages = response.data.get(root_field)
    if ami_energy_usages is None:
        raise DataExtractionError(
            f"Missing '{root_field}' field in response",
            path=f"data.{root_field}",
            response_data=response.data,
        )

    nodes = ami_energy_usages.get("nodes")
    if nodes is None:
        raise DataExtractionError(
            f"Missing 'nodes' field in {root_field}",
            path=f"data.{root_field}.nodes",
            response_data=response.data,
        )

    return cast(list[AmiEnergyUsage], nodes)


def extract_bills(response: GraphQLResponse) -> list[Bill]:
    """Extract bills from a GraphQL response.

    Args:
        response: The GraphQL response from a bill history query

    Returns:
        List of bills

    Raises:
        ValueError: If the response contains GraphQL errors
        DataExtractionError: If the expected data path is missing
    """
    response.raise_on_errors()

    if response.data is None:
        raise DataExtractionError(
            "Response data is null",
            path="data",
            response_data=None,
        )

    bills = response.data.get("bills")
    if bills is None:
        raise DataExtractionError(
            "Missing 'bills' field in response",
            path="data.bills",
            response_data=response.data,
        )

    nodes = bills.get("nodes")
    if nodes is None:
        raise DataExtractionError(
            "Missing 'nodes' field in bills",
            path="data.bills.nodes",
            response_data=response.data,
        )

    return cast(list[Bill], nodes)


def extract_payments(response: GraphQLResponse) -> list[Payment]:
    """Extract payment history from a GraphQL response.

    Args:
        response: The GraphQL response from a payments query

    Returns:
        List of payments

    Raises:
        ValueError: If the response contains GraphQL errors
        DataExtractionError: If the expected data path is missing
    """
    response.raise_on_errors()

    if response.data is None:
        raise DataExtractionError(
            "Response data is null",
            path="data",
            response_data=None,
        )

    payments = response.data.get("payments")
    if payments is None:
        raise DataExtractionError(
            "Missing 'payments' field in response",
            path="data.payments",
            response_data=response.data,
        )

    nodes = payments.get("nodes")
    if nodes is None:
        raise DataExtractionError(
            "Missing 'nodes' field in payments",
            path="data.payments.nodes",
            response_data=response.data,
        )

    return cast(list[Payment], nodes)


def extract_account_dashboard(response: GraphQLResponse) -> AccountDashboard:
    """Extract account dashboard from a GraphQL response.

    Args:
        response: The GraphQL response from an account dashboard query

    Returns:
        Account dashboard data

    Raises:
        ValueError: If the response contains GraphQL errors
        DataExtractionError: If the expected data path is missing
    """
    response.raise_on_errors()

    if response.data is None:
        raise DataExtractionError("Response data is null", path="data", response_data=None)

    user = response.data.get("user")
    if user is None:
        raise DataExtractionError(
            "Missing 'user' field in response",
            path="data.user",
            response_data=response.data,
        )

    account_links = user.get("accountLinks") or {}
    nodes = account_links.get("nodes") or []
    if not nodes:
        raise DataExtractionError(
            "No account links found in response",
            path="data.user.accountLinks.nodes",
            response_data=response.data,
        )

    billing_account = nodes[0].get("billingAccount")
    if billing_account is None:
        raise DataExtractionError(
            "Missing 'billingAccount' field in account link",
            path="data.user.accountLinks.nodes[0].billingAccount",
            response_data=response.data,
        )

    scheduled_conn = billing_account.get("scheduledPayments") or {}
    recent_bills_conn = billing_account.get("recentBills") or {}

    return cast(
        AccountDashboard,
        {
            "firstName": user.get("firstName"),
            "lastName": user.get("lastName"),
            "accountNumber": billing_account.get("accountNumber", ""),
            "currentBalance": billing_account.get("currentBalance", 0.0),
            "currentBalanceRefreshDate": billing_account.get("currentBalanceRefreshDate"),
            "status": billing_account.get("status"),
            "collectionStatus": billing_account.get("collectionStatus"),
            "isCashOnly": billing_account.get("isCashOnly"),
            "isEnrolledInPaymentPlan": billing_account.get("isEnrolledInPaymentPlan"),
            "isEnrolledInRecurringPay": billing_account.get("isEnrolledInRecurringPay"),
            "paperlessBilling": billing_account.get("paperlessBilling"),
            "balancedBilling": billing_account.get("balancedBilling"),
            "recurringPayDetails": billing_account.get("recurringPayDetails"),
            "scheduledPayments": cast(
                list[DashboardScheduledPayment],
                scheduled_conn.get("nodes") or [],
            ),
            "recentBills": cast(
                list[DashboardBill],
                recent_bills_conn.get("nodes") or [],
            ),
        },
    )


def extract_meter_reading(response: GraphQLResponse) -> MeterReading | None:
    """Extract meter reading from a GraphQL response.

    Args:
        response: The GraphQL response from a meter reading query

    Returns:
        Meter reading data, or None if not available for this account

    Raises:
        ValueError: If the response contains GraphQL errors
        DataExtractionError: If the response data is null
    """
    response.raise_on_errors()

    if response.data is None:
        raise DataExtractionError("Response data is null", path="data", response_data=None)

    meter_reading = response.data.get("meterReading")
    if meter_reading is None:
        return None

    return cast(MeterReading, meter_reading)


def extract_paperless_billing(response: GraphQLResponse) -> PaperlessBilling | None:
    """Extract paperless billing from a GraphQL response.

    Args:
        response: The GraphQL response from a paperless billing query

    Returns:
        Paperless billing status, or None if not applicable for this account

    Raises:
        ValueError: If the response contains GraphQL errors
        DataExtractionError: If the response data is null
    """
    response.raise_on_errors()

    if response.data is None:
        raise DataExtractionError("Response data is null", path="data", response_data=None)

    paperless_billing = response.data.get("paperlessBilling")
    if paperless_billing is None:
        return None

    return cast(PaperlessBilling, paperless_billing)


def extract_balanced_billing(response: GraphQLResponse) -> BalancedBilling | None:
    """Extract balanced billing from a GraphQL response.

    Args:
        response: The GraphQL response from a balanced billing query

    Returns:
        Balanced billing plan data, or None if not enrolled

    Raises:
        ValueError: If the response contains GraphQL errors
        DataExtractionError: If the response data is null
    """
    response.raise_on_errors()

    if response.data is None:
        raise DataExtractionError("Response data is null", path="data", response_data=None)

    balanced_billing = response.data.get("balancedBilling")
    if balanced_billing is None:
        return None

    return cast(BalancedBilling, balanced_billing)


def extract_payment_plans(response: GraphQLResponse) -> list[PaymentPlan]:
    """Extract payment plans from a GraphQL response.

    Args:
        response: The GraphQL response from a payment plans query

    Returns:
        List of payment plans

    Raises:
        ValueError: If the response contains GraphQL errors
        DataExtractionError: If the expected data path is missing
    """
    response.raise_on_errors()

    if response.data is None:
        raise DataExtractionError("Response data is null", path="data", response_data=None)

    payment_plans = response.data.get("paymentPlans")
    if payment_plans is None:
        raise DataExtractionError(
            "Missing 'paymentPlans' field in response",
            path="data.paymentPlans",
            response_data=response.data,
        )

    nodes = payment_plans.get("nodes")
    if nodes is None:
        raise DataExtractionError(
            "Missing 'nodes' field in paymentPlans",
            path="data.paymentPlans.nodes",
            response_data=response.data,
        )

    return cast(list[PaymentPlan], nodes)


def extract_collection_arrangements(response: GraphQLResponse) -> list[CollectionArrangement]:
    """Extract collection arrangements from a GraphQL response.

    Args:
        response: The GraphQL response from a collection arrangements query

    Returns:
        List of collection arrangements

    Raises:
        ValueError: If the response contains GraphQL errors
        DataExtractionError: If the expected data path is missing
    """
    response.raise_on_errors()

    if response.data is None:
        raise DataExtractionError("Response data is null", path="data", response_data=None)

    collection_arrangements = response.data.get("collectionArrangements")
    if collection_arrangements is None:
        raise DataExtractionError(
            "Missing 'collectionArrangements' field in response",
            path="data.collectionArrangements",
            response_data=response.data,
        )

    nodes = collection_arrangements.get("nodes")
    if nodes is None:
        raise DataExtractionError(
            "Missing 'nodes' field in collectionArrangements",
            path="data.collectionArrangements.nodes",
            response_data=response.data,
        )

    return cast(list[CollectionArrangement], nodes)


def extract_premise(response: GraphQLResponse) -> list[PremiseNode]:
    """Extract premise nodes from a GraphQL response.

    Args:
        response: The GraphQL response from a premise lookup query

    Returns:
        List of premise nodes matching the address

    Raises:
        ValueError: If the response contains GraphQL errors
        DataExtractionError: If the expected data path is missing
    """
    response.raise_on_errors()

    if response.data is None:
        raise DataExtractionError("Response data is null", path="data", response_data=None)

    premise = response.data.get("premise")
    if premise is None:
        raise DataExtractionError(
            "Missing 'premise' field in response",
            path="data.premise",
            response_data=response.data,
        )

    nodes = premise.get("nodes")
    if nodes is None:
        raise DataExtractionError(
            "Missing 'nodes' field in premise",
            path="data.premise.nodes",
            response_data=response.data,
        )

    return cast(list[PremiseNode], nodes)


def extract_electric_bill_history(response: RestResponse) -> list[ElectricBillRecord]:
    """Extract electric bill history records from a business portal REST response.

    Args:
        response: The REST response from an ElectricBillHistory request

    Returns:
        List of electric bill records, newest first. Empty list on 204 No Content.

    Raises:
        DataExtractionError: If the response data is not in expected format
    """
    if response.status == 204 or not response.data:
        return []

    if not isinstance(response.data, dict) or "electricBillHistory" not in response.data:
        raise DataExtractionError(
            "Expected list of electric bill records",
            path="data",
            response_data=response.data,
        )

    records = response.data["electricBillHistory"]
    if not isinstance(records, list):
        raise DataExtractionError(
            "Expected list of electric bill records",
            path="data.electricBillHistory",
            response_data=records,
        )

    return cast(list[ElectricBillRecord], records)


def extract_gas_bill_history(response: RestResponse) -> list[GasBillRecord]:
    """Extract gas bill history records from a business portal REST response.

    Args:
        response: The REST response from a GasBillHistory request

    Returns:
        List of gas bill records, newest first. Empty list on 204 No Content.

    Raises:
        DataExtractionError: If the response data is not in expected format
    """
    if response.status == 204 or not response.data:
        return []

    if not isinstance(response.data, dict) or "gasBillHistory" not in response.data:
        raise DataExtractionError(
            "Expected list of gas bill records",
            path="data",
            response_data=response.data,
        )

    records = response.data["gasBillHistory"]
    if not isinstance(records, list):
        raise DataExtractionError(
            "Expected list of gas bill records",
            path="data.gasBillHistory",
            response_data=records,
        )

    return cast(list[GasBillRecord], records)


def extract_interval_reads(response: RestResponse) -> list[IntervalRead]:
    """Extract interval reads from a REST response.

    Args:
        response: The REST response from a real-time meter info request

    Returns:
        List of interval reads

    Raises:
        DataExtractionError: If the response data is not in expected format
    """
    if response.data is None:
        raise DataExtractionError(
            "Response data is null",
            path="data",
            response_data=None,
        )

    if not isinstance(response.data, list):
        raise DataExtractionError(
            "Expected list of interval reads",
            path="data",
            response_data=response.data,
        )

    return cast(list[IntervalRead], response.data)
