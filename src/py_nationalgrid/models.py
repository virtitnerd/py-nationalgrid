"""TypedDict models for National Grid API responses."""

from typing import TypedDict


# Linked Billing Accounts (user-cu-uwp-gql)
class AccountLinkBillingAccount(TypedDict):
    """Billing account summary embedded in an account link.

    Attributes:
        nextSchedReadingDate: Next scheduled meter reading date (ISO string), or
            None when no scheduled read is applicable for this account/meter type.
    """

    nextSchedReadingDate: str | None


class AccountLink(TypedDict):
    """A linked billing account identifier.

    Attributes:
        accountLinkId: Unique identifier for the account link
        billingAccountId: The billing account number
        billingAccount: Summary billing account data including next scheduled read date
    """

    accountLinkId: str
    billingAccountId: str
    billingAccount: AccountLinkBillingAccount


class AccountLinksConnection(TypedDict):
    """Connection type for account links.

    Attributes:
        totalCount: Total number of linked accounts
        nodes: List of account link records
    """

    totalCount: int
    nodes: list[AccountLink]


# Billing Account Info (billingaccount-cu-uwp-gql)
class FuelType(TypedDict):
    """Fuel type information.

    Attributes:
        type: Fuel type name (e.g., "ELECTRIC", "GAS")
    """

    type: str


class ServiceAddress(TypedDict):
    """Service address information.

    Attributes:
        serviceAddressCompressed: Single-line formatted service address
    """

    serviceAddressCompressed: str


class CustomerInfo(TypedDict):
    """Customer information.

    Attributes:
        customerType: Type of customer (e.g., "RESIDENTIAL", "COMMERCIAL")
    """

    customerType: str


class Meter(TypedDict):
    """Meter information.

    Attributes:
        isSmartMeter: Whether this is a smart meter
        hasAmiSmartMeter: Whether this meter has AMI smart meter capability
        deviceCode: Device code identifier
        fuelType: Fuel type served by this meter (e.g., "ELECTRIC", "GAS")
        meterPointTypeCode: Meter point type classification code
        meterPointNumber: Meter point number
        servicePointNumber: Service point number
        meterNumber: Meter number identifier
    """

    isSmartMeter: bool
    hasAmiSmartMeter: bool
    deviceCode: str
    fuelType: str
    meterPointTypeCode: str
    meterPointNumber: int
    servicePointNumber: int
    meterNumber: str


class MeterConnection(TypedDict):
    """Connection type for meters.

    Attributes:
        nodes: List of meter records
    """

    nodes: list[Meter]


class BillingAccount(TypedDict):
    """Billing account information.

    Attributes:
        region: Service region name
        regionAbbreviation: Abbreviated region code
        type: Account type
        fuelTypes: Fuel types associated with this account
        status: Account status (e.g., "ACTIVE")
        serviceAddress: Service address for the account
        customerInfo: Customer information
        customerNumber: Customer number
        premiseNumber: Premise number
        meter: Connected meters for the account
    """

    region: str
    regionAbbreviation: str
    type: str
    fuelTypes: list[FuelType]
    status: str
    serviceAddress: ServiceAddress
    customerInfo: CustomerInfo
    customerNumber: int
    premiseNumber: int
    meter: MeterConnection


# Energy Usage Costs (energyusage-cu-uwp-gql)
class EnergyUsageCost(TypedDict):
    """Energy usage cost data.

    Attributes:
        date: Date of usage in YYYY-MM-DD format
        fuelType: Fuel type (e.g., "ELECTRIC", "GAS")
        amount: Cost amount in dollars
        month: Billing month in YYYYMM format
    """

    date: str
    fuelType: str
    amount: float
    month: int


class EnergyUsageCostsConnection(TypedDict):
    """Connection type for energy usage costs.

    Attributes:
        nodes: List of energy usage cost records
    """

    nodes: list[EnergyUsageCost]


# Energy Usages (energyusage-cu-uwp-gql)
class EnergyUsage(TypedDict):
    """Historical energy usage data.

    Attributes:
        usage: Energy usage quantity
        usageType: Type of usage measurement
        usageYearMonth: Year and month in YYYYMM format (e.g., 202401)
    """

    usage: float
    usageType: str
    usageYearMonth: int


class EnergyUsagesConnection(TypedDict):
    """Connection type for energy usages.

    Attributes:
        nodes: List of energy usage records
    """

    nodes: list[EnergyUsage]


# AMI Energy Usages (energyusage-cu-uwp-gql)
class AmiEnergyUsage(TypedDict):
    """AMI hourly energy usage data.

    Attributes:
        date: Date of usage in YYYY-MM-DD format
        fuelType: Fuel type (e.g., "ELECTRIC", "GAS")
        quantity: Energy usage quantity for the day
    """

    date: str
    fuelType: str
    quantity: float


class AmiEnergyUsagesConnection(TypedDict):
    """Connection type for AMI energy usages.

    Attributes:
        nodes: List of AMI energy usage records
    """

    nodes: list[AmiEnergyUsage]


# Bills (bill-cu-uwp-gql)
class Bill(TypedDict):
    """A billing statement.

    Attributes:
        dueDate: Payment due date (ISO string YYYY-MM-DD)
        statementDate: Date the bill was issued (ISO string YYYY-MM-DD)
        status: Bill status (e.g. "PAID", "UNPAID")
        accountNumber: Billing account number
        totalDueAmount: Total amount due in dollars
        currentChargesAmount: Current period charges in dollars
    """

    dueDate: str
    statementDate: str
    status: str
    accountNumber: str
    totalDueAmount: float
    currentChargesAmount: float


# Payments (payment-cu-uwp-gql)
class Payment(TypedDict):
    """A payment record.

    Attributes:
        paymentDate: Date the payment was made (ISO string), or None for pending
        processedDate: Datetime the payment was processed (ISO 8601 with timezone)
        amount: Payment amount in dollars
        status: Payment status, or None if not applicable
        type: Payment type, or None if not applicable
        method: Payment method (e.g. "ACH_PAYMENT")
        source: Payment source (e.g. "PAYMENT")
        accountNumber: Billing account number
        errorCode: Error code if the payment failed, or None
        errorMessage: Error message if the payment failed, or None
    """

    paymentDate: str | None
    processedDate: str | None
    amount: float
    status: str | None
    type: str | None
    method: str | None
    source: str | None
    accountNumber: str
    errorCode: str | None
    errorMessage: str | None


# Account Dashboard (user-cu-uwp-gql)
class PaperlessBilling(TypedDict):
    accountNumber: str
    status: str
    enrolledVia: str | None


class BalancedBilling(TypedDict):
    status: str | None
    billingAccountNumber: str | None
    amountBilledToDate: float | None
    actualUsageToDate: float | None
    planStartDate: str | None
    currentMonthlyPayment: float | None
    difference: float | None


class RecurringPayDetails(TypedDict):
    amountType: str | None
    amount: float | None
    status: str | None
    planStartDate: str | None
    paymentType: str | None


class DashboardScheduledPayment(TypedDict):
    amount: float | None
    paymentDate: str | None
    status: str | None
    method: str | None
    type: str | None
    paymentSequenceNumber: int | None


class DashboardBill(TypedDict):
    currentChargesAmount: float
    totalDueAmount: float
    statementDate: str
    dueDate: str


class AccountDashboard(TypedDict):
    firstName: str | None
    lastName: str | None
    accountNumber: str
    currentBalance: float
    currentBalanceRefreshDate: str | None
    status: str | None
    collectionStatus: str | None
    isCashOnly: bool | None
    isEnrolledInPaymentPlan: bool | None
    isEnrolledInRecurringPay: bool | None
    paperlessBilling: PaperlessBilling | None
    balancedBilling: BalancedBilling | None
    recurringPayDetails: RecurringPayDetails | None
    scheduledPayments: list[DashboardScheduledPayment]
    recentBills: list[DashboardBill]


# Meter Reading (submitmeterreading-cu-uwp-gql)
class MeterReading(TypedDict):
    meterReadingStatus: str | None
    isEligible: bool
    transactionDate: str | None
    reading: int | None
    submitMeterReadingInEligibleReason: str | None
    errorMessage: str | None


# Payment Plans (payplan-cu-uwp-gql)
class PaymentPlan(TypedDict):
    paymentAgreementStatus: str | None
    monthlyInstallmentAmount: float | None
    totalNumberOfInstallments: int | None
    totalNumberOfInstallmentsRemaining: int | None
    currentInstallmentStatus: str | None
    finalInstallmentAmount: float | None
    requiredDownPaymentAmount: float | None
    downPaymentStatus: str | None
    downPaymentDueDate: str | None
    planSequenceNumber: int | None
    reactivationFee: float | None
    planCompletedDate: str | None


# Collection Arrangements (collections-cu-uwp-gql)
class CollectionArrangementDetail(TypedDict):
    sequenceNumber: int | None
    installmentAmount: float | None
    installmentDueDate: str | None
    installmentStatus: str | None


class CollectionArrangementDetailsConnection(TypedDict):
    nodes: list[CollectionArrangementDetail]


class CollectionArrangement(TypedDict):
    totalAmountDue: float | None
    numberOfInstallments: int | None
    agreementDate: str | None
    arrangementStatus: str | None
    statusUpdateDate: str | None
    completedDate: str | None
    addedOn: str | None
    details: CollectionArrangementDetailsConnection


# REST: Interval Reads
class IntervalRead(TypedDict):
    """Real-time meter interval read data (15-minute intervals).

    Attributes:
        startTime: Start of interval in ISO 8601 format with timezone
                   (e.g., "2026-01-22T13:00:00-05:00")
        endTime: End of interval in ISO 8601 format with timezone
                 (e.g., "2026-01-22T13:15:00-05:00")
        value: Energy usage in kWh for this interval
    """

    startTime: str
    endTime: str
    value: float
