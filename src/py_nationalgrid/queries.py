"""GraphQL query builders for National Grid."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from textwrap import dedent, indent
from typing import Any

from .graphql import GraphQLRequest, compose_query

DEFAULT_SELECTION_SET = "__typename"
LINKED_BILLING_ENDPOINT = "https://myaccount.nationalgrid.com/api/user-cu-uwp-gql"
PREMISE_ENDPOINT = "https://myaccount.nationalgrid.com/api/premise-cu-uwp-gql"
BILLING_ACCOUNT_INFO_ENDPOINT = "https://myaccount.nationalgrid.com/api/billingaccount-cu-uwp-gql"
ENERGY_USAGE_ENDPOINT = "https://myaccount.nationalgrid.com/api/energyusage-cu-uwp-gql"
BILL_ENDPOINT = "https://myaccount.nationalgrid.com/api/bill-cu-uwp-gql"
PAYMENT_ENDPOINT = "https://myaccount.nationalgrid.com/api/payment-cu-uwp-gql"
PAPERLESS_BILLING_ENDPOINT = "https://myaccount.nationalgrid.com/api/paperlessbilling-cu-uwp-gql"
BALANCED_BILLING_ENDPOINT = "https://myaccount.nationalgrid.com/api/balancedbilling-cu-uwp-gql"
PAYMENT_PLANS_ENDPOINT = "https://myaccount.nationalgrid.com/api/payplan-cu-uwp-gql"
COLLECTION_ARRANGEMENTS_ENDPOINT = "https://myaccount.nationalgrid.com/api/collections-cu-uwp-gql"
METER_READING_ENDPOINT = "https://myaccount.nationalgrid.com/api/submitmeterreading-cu-uwp-gql"
LINKED_BILLING_SELECTION_SET = """
accountLinks {
    totalCount
    nodes {
        accountLinkId
        billingAccountId
        billingAccount {
            nextSchedReadingDate
        }
    }
}
"""
BILLING_ACCOUNT_INFO_SELECTION_SET = """
region
regionAbbreviation
type
fuelTypes {
    type
}
status
serviceAddress {
    serviceAddressCompressed
}
customerInfo {
    customerType
}
customerNumber
premiseNumber
meter {
    nodes {
        isSmartMeter
        hasAmiSmartMeter
        deviceCode
        fuelType
        meterPointTypeCode
        meterPointNumber
        servicePointNumber
        meterNumber
    }
}
"""
ENERGY_USAGE_COSTS_SELECTION_SET = """
nodes {
    date
    fuelType
    amount
    month
}
"""
ENERGY_USAGES_SELECTION_SET = """
nodes {
    usage
    usageType
    usageYearMonth
}
"""
AMI_ENERGY_USAGES_SELECTION_SET = """
nodes {
    date
    fuelType
    quantity
}
"""
BILLS_SELECTION_SET = """
nodes {
    dueDate
    statementDate
    status
    accountNumber
    totalDueAmount
    currentChargesAmount
}
"""
PAYMENTS_SELECTION_SET = """
nodes {
    paymentDate
    processedDate
    amount
    status
    type
    method
    source
    accountNumber
    errorCode
    errorMessage
}
"""
ACCOUNT_DASHBOARD_SELECTION_SET = """
firstName
lastName
accountLinks(where: {billingAccountId: {eq: $accountNumber}}) {
    nodes {
        billingAccount {
            accountNumber
            currentBalance
            currentBalanceRefreshDate
            status
            collectionStatus
            isCashOnly
            isEnrolledInPaymentPlan
            isEnrolledInRecurringPay
            paperlessBilling {
                accountNumber
                status
                enrolledVia
            }
            balancedBilling {
                status
                billingAccountNumber
                amountBilledToDate
                actualUsageToDate
                planStartDate
                currentMonthlyPayment
                difference
            }
            recurringPayDetails {
                amountType
                amount
                status
                planStartDate
                paymentType
            }
            scheduledPayments: payments(
                where: {and: [
                    {status: {in: [SCHEDULED, PROCESSING, PENDING]}},
                    {type: {neq: ONE_TIME_PAYMENT}}
                ]}
            ) {
                nodes {
                    amount
                    paymentDate
                    status
                    method
                    type
                    paymentSequenceNumber
                }
            }
            recentBills: bills(first: 2, order: [{dueDate: DESC}]) {
                nodes {
                    currentChargesAmount
                    totalDueAmount
                    statementDate
                    dueDate
                }
            }
        }
    }
}
"""
METER_READING_SELECTION_SET = """
meterReadingStatus
isEligible
transactionDate
reading
submitMeterReadingInEligibleReason
errorMessage
"""
PAPERLESS_BILLING_SELECTION_SET = """
accountNumber
status
enrolledVia
"""
BALANCED_BILLING_SELECTION_SET = """
status
billingAccountNumber
amountBilledToDate
actualUsageToDate
planStartDate
currentMonthlyPayment
difference
"""
PAYMENT_PLANS_SELECTION_SET = """
nodes {
    paymentAgreementStatus
    monthlyInstallmentAmount
    totalNumberOfInstallments
    totalNumberOfInstallmentsRemaining
    currentInstallmentStatus
    finalInstallmentAmount
    requiredDownPaymentAmount
    downPaymentStatus
    downPaymentDueDate
    planSequenceNumber
    reactivationFee
    planCompletedDate
}
"""
PREMISE_SELECTION_SET = """
nodes {
    premiseSummaryKey
    premiseNumber
    premiseStatus
    isCrisAddress
    streetNumber
    streetName
    streetAddress
    apartment
    city
    buildingNumber
    notes
    zipcode
    state
    compressedAddress
    companyCode
    region
    meter {
        nodes {
            meterNumber
            premiseNumber
            fuelType
            meterStatus
        }
    }
}
"""
COLLECTION_ARRANGEMENTS_SELECTION_SET = """
nodes {
    totalAmountDue
    numberOfInstallments
    agreementDate
    arrangementStatus
    statusUpdateDate
    completedDate
    addedOn
    details {
        nodes {
            sequenceNumber
            installmentAmount
            installmentDueDate
            installmentStatus
        }
    }
}
"""


@dataclass(slots=True)
class StandardQuery:
    """Generic query definition for building GraphQL operations."""

    operation_name: str
    root_field: str
    selection_set: str = DEFAULT_SELECTION_SET
    variables: Mapping[str, Any] | None = None
    variable_definitions: str | Sequence[str] | None = None
    field_arguments: str | None = None
    endpoint: str | None = None

    def to_request(self) -> GraphQLRequest:
        """Convert this query definition into a `GraphQLRequest`."""

        selection_set = dedent(self.selection_set).strip() or DEFAULT_SELECTION_SET
        selection_block = indent(selection_set, "  ")
        field_args = f"({self.field_arguments})" if self.field_arguments else ""
        selection = dedent(
            f"""
            {self.root_field}{field_args} {{
            {selection_block}
            }}
            """
        ).strip()
        variable_definitions = _normalize_variable_definitions(self.variable_definitions)
        query = compose_query(self.operation_name, selection, variables=variable_definitions)
        return GraphQLRequest(
            query=query,
            variables=self.variables,
            operation_name=self.operation_name,
            endpoint=self.endpoint,
        )


def linked_billing_accounts_request(
    *,
    selection_set: str = LINKED_BILLING_SELECTION_SET,
    variables: Mapping[str, Any] | None = None,
    variable_definitions: str | Sequence[str] | None = "$userId: String!",
    field_arguments: str | None = "userId: $userId",
    operation_name: str = "AccountIdentifiers",
) -> GraphQLRequest:
    """Build a linked billing accounts query.

    This request targets the user-cu-uwp-gql GraphQL endpoint.
    """

    return StandardQuery(
        operation_name=operation_name,
        root_field="user",
        selection_set=selection_set,
        variables=variables,
        variable_definitions=variable_definitions,
        field_arguments=field_arguments,
        endpoint=LINKED_BILLING_ENDPOINT,
    ).to_request()


def billing_account_info_request(
    *,
    selection_set: str = BILLING_ACCOUNT_INFO_SELECTION_SET,
    variables: Mapping[str, Any] | None = None,
    variable_definitions: str | Sequence[str] | None = "$accountNumber: String!",
    field_arguments: str | None = "accountNumber: $accountNumber",
    operation_name: str = "OpowerAccount",
) -> GraphQLRequest:
    """Build a billing account information query.

    This request targets the billingaccount-cu-uwp-gql GraphQL endpoint.
    """

    return StandardQuery(
        operation_name=operation_name,
        root_field="billingAccount",
        selection_set=selection_set,
        variables=variables,
        variable_definitions=variable_definitions,
        field_arguments=field_arguments,
        endpoint=BILLING_ACCOUNT_INFO_ENDPOINT,
    ).to_request()


def energy_usage_costs_request(
    *,
    selection_set: str = ENERGY_USAGE_COSTS_SELECTION_SET,
    variables: Mapping[str, Any] | None = None,
    variable_definitions: str | Sequence[str] | None = (
        "$accountNumber: String!",
        "$date: Date!",
        "$companyCode: CompanyCodeValue!",
    ),
    field_arguments: str | None = (
        "accountNumber: $accountNumber, date: $date, companyCode: $companyCode"
    ),
    operation_name: str = "EnergyUsageCosts",
) -> GraphQLRequest:
    """Build an energy usage costs query.

    This request targets the energyusage-cu-uwp-gql GraphQL endpoint.
    """
    return StandardQuery(
        operation_name=operation_name,
        root_field="energyUsageCosts",
        selection_set=selection_set,
        variables=variables,
        variable_definitions=variable_definitions,
        field_arguments=field_arguments,
        endpoint=ENERGY_USAGE_ENDPOINT,
    ).to_request()


def energy_usages_request(
    *,
    selection_set: str = ENERGY_USAGES_SELECTION_SET,
    variables: Mapping[str, Any] | None = None,
    variable_definitions: str | Sequence[str] | None = (
        "$accountNumber: String!",
        "$from: Int!",
        "$first: Int!",
    ),
    field_arguments: str | None = (
        "accountNumber: $accountNumber, "
        "where: {usageYearMonth: {gte: $from}}, "
        "order: [{usageYearMonth: DESC}], "
        "first: $first"
    ),
    operation_name: str = "EnergyUsages",
) -> GraphQLRequest:
    """Build an energy usages query.

    This request targets the energyusage-cu-uwp-gql GraphQL endpoint.
    """
    return StandardQuery(
        operation_name=operation_name,
        root_field="energyUsages",
        selection_set=selection_set,
        variables=variables,
        variable_definitions=variable_definitions,
        field_arguments=field_arguments,
        endpoint=ENERGY_USAGE_ENDPOINT,
    ).to_request()


def ami_energy_usages_request(
    *,
    selection_set: str = AMI_ENERGY_USAGES_SELECTION_SET,
    variables: Mapping[str, Any] | None = None,
    variable_definitions: str | Sequence[str] | None = (
        "$meterNumber: String!",
        "$premiseNumber: String!",
        "$servicePointNumber: String!",
        "$meterPointNumber: String!",
        "$dateFrom: Date!",
        "$dateTo: Date!",
    ),
    field_arguments: str | None = (
        "meterNumber: $meterNumber, "
        "premiseNumber: $premiseNumber, "
        "servicePointNumber: $servicePointNumber, "
        "meterPointNumber: $meterPointNumber, "
        "dateFrom: $dateFrom, "
        "dateTo: $dateTo"
    ),
    operation_name: str = "NrtDailyUsage",
    root_field: str = "amiEnergyUsages",
) -> GraphQLRequest:
    """Build an AMI energy usages query.

    This request targets the energyusage-cu-uwp-gql GraphQL endpoint.

    Defaults to the standard ``amiEnergyUsages`` / ``NrtDailyUsage`` operation.
    Pass ``root_field="amiEnergyUsages15Min"`` and
    ``operation_name="NrtDailyUsage15Min"`` for the 15-minute interval variant
    (used as the primary path by ``get_ami_energy_usages_15min()`` for both
    ELECTRIC and GAS meters, with automatic fallback to the defaults when the
    15-minute endpoint returns GraphQL errors).
    """
    return StandardQuery(
        operation_name=operation_name,
        root_field=root_field,
        selection_set=selection_set,
        variables=variables,
        variable_definitions=variable_definitions,
        field_arguments=field_arguments,
        endpoint=ENERGY_USAGE_ENDPOINT,
    ).to_request()


def bills_request(
    *,
    selection_set: str = BILLS_SELECTION_SET,
    variables: Mapping[str, Any] | None = None,
    variable_definitions: str | Sequence[str] | None = "$accountNumber: String!",
    field_arguments: str | None = "accountNumber: $accountNumber, order: [{statementDate: DESC}]",
    operation_name: str = "BillList",
) -> GraphQLRequest:
    """Build a bill history query.

    This request targets the bill-cu-uwp-gql GraphQL endpoint.
    """
    return StandardQuery(
        operation_name=operation_name,
        root_field="bills",
        selection_set=selection_set,
        variables=variables,
        variable_definitions=variable_definitions,
        field_arguments=field_arguments,
        endpoint=BILL_ENDPOINT,
    ).to_request()


def payments_request(
    *,
    selection_set: str = PAYMENTS_SELECTION_SET,
    variables: Mapping[str, Any] | None = None,
    variable_definitions: str | Sequence[str] | None = "$accountNumber: String!",
    field_arguments: str | None = "accountNumber: $accountNumber",
    operation_name: str = "PaymentHistory",
) -> GraphQLRequest:
    """Build a payment history query.

    This request targets the payment-cu-uwp-gql GraphQL endpoint.
    """
    return StandardQuery(
        operation_name=operation_name,
        root_field="payments",
        selection_set=selection_set,
        variables=variables,
        variable_definitions=variable_definitions,
        field_arguments=field_arguments,
        endpoint=PAYMENT_ENDPOINT,
    ).to_request()


def account_dashboard_request(
    *,
    selection_set: str = ACCOUNT_DASHBOARD_SELECTION_SET,
    variables: Mapping[str, Any] | None = None,
    variable_definitions: str | Sequence[str] | None = (
        "$userId: String!",
        "$accountNumber: String!",
    ),
    field_arguments: str | None = "userId: $userId",
    operation_name: str = "AccountDashboard",
) -> GraphQLRequest:
    """Build an account dashboard query.

    This request targets the user-cu-uwp-gql GraphQL endpoint.
    """
    return StandardQuery(
        operation_name=operation_name,
        root_field="user",
        selection_set=selection_set,
        variables=variables,
        variable_definitions=variable_definitions,
        field_arguments=field_arguments,
        endpoint=LINKED_BILLING_ENDPOINT,
    ).to_request()


def meter_reading_request(
    account_number: str,
    *,
    selection_set: str = METER_READING_SELECTION_SET,
    operation_name: str = "MeterReading",
) -> GraphQLRequest:
    """Build a meter reading query.

    This request targets the submitmeterreading-cu-uwp-gql GraphQL endpoint.
    Uses inline account number (no GraphQL variables) to avoid server-side
    HC0011 parse errors on this endpoint.
    """
    return StandardQuery(
        operation_name=operation_name,
        root_field="meterReading",
        selection_set=selection_set,
        variables=None,
        variable_definitions=None,
        field_arguments=f'accountNumber: "{account_number}"',
        endpoint=METER_READING_ENDPOINT,
    ).to_request()


def paperless_billing_request(
    account_number: str,
    *,
    selection_set: str = PAPERLESS_BILLING_SELECTION_SET,
    operation_name: str = "PaperlessBilling",
) -> GraphQLRequest:
    """Build a paperless billing query.

    This request targets the paperlessbilling-cu-uwp-gql GraphQL endpoint.
    Uses inline account number (no GraphQL variables) to avoid server-side
    HC0011 parse errors on this endpoint.
    """
    return StandardQuery(
        operation_name=operation_name,
        root_field="paperlessBilling",
        selection_set=selection_set,
        variables=None,
        variable_definitions=None,
        field_arguments=f'accountNumber: "{account_number}"',
        endpoint=PAPERLESS_BILLING_ENDPOINT,
    ).to_request()


def balanced_billing_request(
    account_number: str,
    *,
    selection_set: str = BALANCED_BILLING_SELECTION_SET,
    operation_name: str = "BalancedBilling",
) -> GraphQLRequest:
    """Build a balanced billing query.

    This request targets the balancedbilling-cu-uwp-gql GraphQL endpoint.
    Uses inline account number (no GraphQL variables) to avoid server-side
    HC0011 parse errors on this endpoint.
    """
    return StandardQuery(
        operation_name=operation_name,
        root_field="balancedBilling",
        selection_set=selection_set,
        variables=None,
        variable_definitions=None,
        field_arguments=f'accountNumber: "{account_number}"',
        endpoint=BALANCED_BILLING_ENDPOINT,
    ).to_request()


def payment_plans_request(
    account_number: str,
    *,
    selection_set: str = PAYMENT_PLANS_SELECTION_SET,
    operation_name: str = "PaymentPlans",
) -> GraphQLRequest:
    """Build a payment plans query.

    This request targets the payplan-cu-uwp-gql GraphQL endpoint.
    Uses inline account number (no GraphQL variables) to avoid server-side
    HC0011 parse errors on this endpoint.
    """
    return StandardQuery(
        operation_name=operation_name,
        root_field="paymentPlans",
        selection_set=selection_set,
        variables=None,
        variable_definitions=None,
        field_arguments=f'accountNumber: "{account_number}"',
        endpoint=PAYMENT_PLANS_ENDPOINT,
    ).to_request()


def collection_arrangements_request(
    account_number: str,
    *,
    selection_set: str = COLLECTION_ARRANGEMENTS_SELECTION_SET,
    operation_name: str = "CollectionArrangements",
) -> GraphQLRequest:
    """
    Builds a collection arrangements GraphQL request for a given account.
    
    The provided `account_number` is embedded directly into the root field arguments (no GraphQL variables are sent). The returned request targets the collection arrangements endpoint.
    
    Parameters:
        account_number (str): Account number to embed in the query root field.
    
    Returns:
        GraphQLRequest: A request object containing the composed query, variables (None), operation name, and endpoint.
    """
    return StandardQuery(
        operation_name=operation_name,
        root_field="collectionArrangements",
        selection_set=selection_set,
        variables=None,
        variable_definitions=None,
        field_arguments=f'accountNumber: "{account_number}"',
        endpoint=COLLECTION_ARRANGEMENTS_ENDPOINT,
    ).to_request()


def premise_request(
    *,
    selection_set: str = PREMISE_SELECTION_SET,
    variables: Mapping[str, Any] | None = None,
    variable_definitions: str | Sequence[str] | None = (
        "$apartment: String",
        "$city: String!",
        "$state: String!",
        "$streetName: String!",
        "$zipCode: String!",
        "$allowCrisAddresses: Boolean",
    ),
    field_arguments: str | None = (
        "allowCrisAddresses: $allowCrisAddresses, "
        "where: {state: {eq: $state}, city: {eq: $city}, zipcode: {eq: $zipCode}, "
        "streetName: {eq: $streetName}, apartment: {eq: $apartment}}"
    ),
    operation_name: str = "Premise",
) -> GraphQLRequest:
    """
    Builds a GraphQL request to look up a premise by address.
    
    Targets the premise-cu-uwp-gql endpoint (PREMISE_ENDPOINT) and does not require authentication.
    
    Parameters:
    	variables (Mapping[str, Any] | None): Optional mapping of GraphQL variable values. Common keys: `apartment`, `city`, `state`, `streetName`, `zipCode`, `allowCrisAddresses`.
    	variable_definitions (str | Sequence[str] | None): GraphQL variable definitions to include in the operation signature (defaults include definitions for the address fields and `allowCrisAddresses`).
    	field_arguments (str | None): Arguments passed to the root `premise` field; by default this builds a `where` filter using the address variables and `allowCrisAddresses`.
    
    Returns:
    	GraphQLRequest: The composed GraphQL request containing the query, variables, operation name, and endpoint.
    """
    return StandardQuery(
        operation_name=operation_name,
        root_field="premise",
        selection_set=selection_set,
        variables=variables,
        variable_definitions=variable_definitions,
        field_arguments=field_arguments,
        endpoint=PREMISE_ENDPOINT,
    ).to_request()


def _normalize_variable_definitions(value: str | Sequence[str] | None) -> str | None:
    """
    Normalize GraphQL variable definition fragments into a single comma-separated declaration string.
    
    Parameters:
        value (str | Sequence[str] | None): A variable definition, multiple definitions, or None. If a string, leading/trailing whitespace is removed. If a sequence, each item is stripped and empty items are ignored.
    
    Returns:
        str | None: A single comma-separated string of cleaned variable definitions, or `None` when `value` is `None` or yields no non-empty definitions.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    parts = [item.strip() for item in value if item.strip()]
    return ", ".join(parts) if parts else None
