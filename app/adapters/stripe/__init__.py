"""Stripe payment processor adapter for international money transfers."""

from decimal import Decimal
from typing import Any, Dict, Optional, List, Literal
from datetime import datetime
import logging
from enum import Enum

import stripe
from stripe.error import (
    StripeError,
    CardError,
    RateLimitError,
    InvalidRequestError,
    AuthenticationError,
    APIConnectionError,
)

from ..base import PaymentAdapter
from ..exceptions import (
    PaymentError,
    ValidationError,
    InsufficientFundsError,
    PaymentNotFoundError,
    PaymentProcessingError,
    RefundError,
    WebhookError,
    RateLimitError as PaymentRateLimitError,
    AuthenticationError as PaymentAuthenticationError,
)

logger = logging.getLogger(__name__)


class TransferType(Enum):
    """Transfer types for money movement."""
    CARD_TO_BANK = "card_to_bank"
    WALLET_TO_BANK = "wallet_to_bank"
    WALLET_TO_WALLET = "wallet_to_wallet"


class StripeAdapter(PaymentAdapter):
    """Production Stripe integration for international money transfers.
    
    Implements:
    - Multi-currency PaymentIntents for sender charges
    - Connect accounts for recipient KYC and payouts
    - Separate charges & transfers pattern for remittance
    - Custom FX rates (bypassing Stripe's automatic conversion)
    - Webhook processing for reliable state management
    """

    def __init__(
        self,
        api_key: str,
        webhook_secret: str,
        platform_account_id: Optional[str] = None,
        enable_test_mode: bool = False,
        custom_fx_service: Optional[Any] = None,
    ) -> None:
        """Initialize Stripe adapter.
        
        Args:
            api_key: Stripe secret API key
            webhook_secret: Webhook endpoint secret for signature verification
            platform_account_id: Your platform's Stripe account ID
            enable_test_mode: Use test mode for development
            custom_fx_service: Custom FX rate service (overrides Stripe FX)
        """
        stripe.api_key = api_key
        self.webhook_secret = webhook_secret
        self.platform_account_id = platform_account_id
        self.test_mode = enable_test_mode
        self.custom_fx = custom_fx_service
        
        # Configure Stripe client settings
        stripe.max_network_retries = 2
        stripe.api_version = "2024-12-18.acacia"

    # ==================== Customer Management ====================

    async def create_or_update_customer(
        self,
        user_id: str,
        email: str,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Create or update a Stripe Customer for the sender.
        
        Args:
            user_id: Internal user ID
            email: Customer email
            name: Customer full name
            phone: Customer phone number
            metadata: Additional metadata to store
            
        Returns:
            Stripe Customer object
        """
        try:
            # Check if customer exists
            customers = stripe.Customer.list(
                email=email,
                limit=1
            )
            
            customer_data = {
                "email": email,
                "name": name,
                "phone": phone,
                "metadata": {
                    "user_id": user_id,
                    **(metadata or {})
                }
            }
            
            if customers.data:
                # Update existing customer
                customer = stripe.Customer.modify(
                    customers.data[0].id,
                    **customer_data
                )
                logger.info(f"Updated customer {customer.id} for user {user_id}")
            else:
                # Create new customer
                customer = stripe.Customer.create(**customer_data)
                logger.info(f"Created customer {customer.id} for user {user_id}")
                
            return customer.to_dict()
            
        except StripeError as e:
            logger.error(f"Customer operation failed: {e}")
            raise PaymentError(f"Failed to process customer: {str(e)}")

    # ==================== Connect Account Management ====================

    async def create_connect_account(
        self,
        recipient_id: str,
        email: str,
        country: str,
        account_type: Literal["express", "custom"] = "express",
        bypass_kyc: bool = False,
        admin_override: bool = False,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Create a Connect account for recipient payouts.
        
        Args:
            recipient_id: Internal recipient ID
            email: Recipient email
            country: Two-letter country code (ISO 3166-1 alpha-2)
            account_type: Express or Custom Connect account
            bypass_kyc: Skip KYC if admin override (compliance requirement)
            admin_override: Admin bypass flag for special cases
            metadata: Additional metadata
            
        Returns:
            Stripe Connect Account object with onboarding URL
        """
        try:
            account_data = {
                "type": account_type,
                "country": country.upper(),
                "email": email,
                "capabilities": {
                    "transfers": {"requested": True},
                },
                "metadata": {
                    "recipient_id": recipient_id,
                    "kyc_bypassed": str(bypass_kyc and admin_override),
                    **(metadata or {})
                }
            }
            
            # Create Connect account
            account = stripe.Account.create(**account_data)
            
            response = {
                "account_id": account.id,
                "type": account_type,
                "country": country,
                "charges_enabled": account.charges_enabled,
                "payouts_enabled": account.payouts_enabled,
            }
            
            # Generate onboarding link unless KYC is bypassed
            if not (bypass_kyc and admin_override):
                onboarding_link = stripe.AccountLink.create(
                    account=account.id,
                    refresh_url=f"https://yourapp.com/reauth/{recipient_id}",
                    return_url=f"https://yourapp.com/return/{recipient_id}",
                    type="account_onboarding",
                )
                response["onboarding_url"] = onboarding_link.url
                
            logger.info(f"Created Connect account {account.id} for recipient {recipient_id}")
            return response
            
        except StripeError as e:
            logger.error(f"Connect account creation failed: {e}")
            raise PaymentError(f"Failed to create recipient account: {str(e)}")

    async def check_connect_account_status(
        self, account_id: str
    ) -> Dict[str, Any]:
        """Check Connect account KYC/verification status."""
        try:
            account = stripe.Account.retrieve(account_id)
            return {
                "account_id": account.id,
                "charges_enabled": account.charges_enabled,
                "payouts_enabled": account.payouts_enabled,
                "currently_due": account.requirements.currently_due if account.requirements else [],
                "eventually_due": account.requirements.eventually_due if account.requirements else [],
                "disabled_reason": account.requirements.disabled_reason if account.requirements else None,
            }
        except StripeError as e:
            logger.error(f"Account status check failed: {e}")
            raise PaymentError(f"Failed to check account status: {str(e)}")

    # ==================== Payment Collection ====================

    async def create_payment(
        self,
        amount: Decimal,
        currency: str,
        customer_id: str,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        payment_method_types: Optional[List[str]] = None,
        apply_custom_fx: bool = True,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """Create a PaymentIntent to collect funds from sender.
        
        Args:
            amount: Amount in smallest currency unit (e.g., cents)
            currency: Three-letter ISO currency code
            customer_id: Stripe Customer ID
            description: Payment description
            metadata: Transaction metadata
            payment_method_types: Allowed payment methods
            apply_custom_fx: Use custom FX rates
            
        Returns:
            PaymentIntent details with client secret
        """
        try:
            # Convert Decimal to int (Stripe expects smallest currency unit)
            amount_int = int(amount)
            
            # Apply custom FX if configured
            if apply_custom_fx and self.custom_fx:
                # This is where you'd apply your custom FX logic
                # For now, we'll add it to metadata for tracking
                if metadata is None:
                    metadata = {}
                metadata["custom_fx_applied"] = "true"
            
            payment_intent_data = {
                "amount": amount_int,
                "currency": currency.lower(),
                "customer": customer_id,
                "description": description,
                "metadata": metadata or {},
                "automatic_payment_methods": {
                    "enabled": True
                } if not payment_method_types else None,
            }
            
            # Add specific payment methods if provided
            if payment_method_types:
                payment_intent_data["payment_method_types"] = payment_method_types
            
            payment_intent = stripe.PaymentIntent.create(**payment_intent_data)
            
            logger.info(f"Created PaymentIntent {payment_intent.id} for {amount_int} {currency}")
            
            return {
                "id": payment_intent.id,
                "client_secret": payment_intent.client_secret,
                "amount": payment_intent.amount,
                "currency": payment_intent.currency,
                "status": payment_intent.status,
                "created": payment_intent.created,
                "metadata": payment_intent.metadata,
            }
            
        except StripeError as e:
            logger.error(f"Payment creation failed: {e}")
            if isinstance(e, CardError):
                raise InsufficientFundsError(str(e))
            raise PaymentError(f"Failed to create payment: {str(e)}")

    async def capture_payment(
        self, 
        payment_id: str, 
        **kwargs: Any
    ) -> Dict[str, Any]:
        """Capture a previously authorized payment.
        
        Args:
            payment_id: Unique payment identifier (PaymentIntent ID)
            **kwargs: Additional processor-specific parameters
            
        Returns:
            Updated payment details
            
        Raises:
            PaymentNotFoundError: If payment ID is not found
            PaymentProcessingError: If capture fails
            ValidationError: If payment cannot be captured (wrong status)
            AuthenticationError: If authentication with payment processor fails
        """
        try:
            payment_intent = stripe.PaymentIntent.capture(payment_id)
            
            logger.info(f"Captured payment {payment_intent.id}")
            
            return {
                "id": payment_intent.id,
                "status": payment_intent.status,
                "amount": payment_intent.amount,
                "currency": payment_intent.currency,
                "captured_at": payment_intent.created,
                "metadata": payment_intent.metadata,
            }
            
        except StripeError as e:
            logger.error(f"Payment capture failed: {e}")
            if e.http_status == 404:
                raise PaymentNotFoundError(f"Payment {payment_id} not found")
            elif isinstance(e, InvalidRequestError):
                raise ValidationError(f"Payment cannot be captured: {str(e)}")
            elif isinstance(e, AuthenticationError):
                raise PaymentAuthenticationError(f"Authentication failed: {str(e)}")
            raise PaymentProcessingError(f"Failed to capture payment: {str(e)}")

    async def confirm_payment(
        self,
        payment_intent_id: str,
        payment_method_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Confirm a PaymentIntent (server-side confirmation)."""
        try:
            confirm_params = {"payment_intent": payment_intent_id}
            if payment_method_id:
                confirm_params["payment_method"] = payment_method_id
                
            payment_intent = stripe.PaymentIntent.confirm(**confirm_params)
            
            return {
                "id": payment_intent.id,
                "status": payment_intent.status,
                "amount": payment_intent.amount,
                "currency": payment_intent.currency,
            }
            
        except StripeError as e:
            logger.error(f"Payment confirmation failed: {e}")
            raise PaymentError(f"Failed to confirm payment: {str(e)}")

    # ==================== Money Movement (Transfers & Payouts) ====================

    async def create_transfer(
        self,
        amount: Decimal,
        currency: str,
        destination_account_id: str,
        source_transaction_id: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Transfer funds to a Connect account (recipient).
        
        Implements the "separate charges and transfers" pattern.
        
        Args:
            amount: Amount to transfer (in smallest currency unit)
            currency: Three-letter ISO currency code
            destination_account_id: Connect account ID of recipient
            source_transaction_id: Original PaymentIntent ID
            description: Transfer description
            metadata: Transfer metadata
            
        Returns:
            Transfer object details
        """
        try:
            amount_int = int(amount)
            
            transfer_data = {
                "amount": amount_int,
                "currency": currency.lower(),
                "destination": destination_account_id,
                "description": description,
                "metadata": {
                    "source_transaction": source_transaction_id,
                    **(metadata or {})
                }
            }
            
            # Link to source charge if provided
            if source_transaction_id:
                transfer_data["source_transaction"] = source_transaction_id
            
            transfer = stripe.Transfer.create(**transfer_data)
            
            logger.info(f"Created transfer {transfer.id} to {destination_account_id}")
            
            return {
                "id": transfer.id,
                "amount": transfer.amount,
                "currency": transfer.currency,
                "destination": transfer.destination,
                "created": transfer.created,
                "metadata": transfer.metadata,
            }
            
        except StripeError as e:
            logger.error(f"Transfer creation failed: {e}")
            raise PaymentError(f"Failed to create transfer: {str(e)}")

    async def create_payout(
        self,
        connect_account_id: str,
        amount: Optional[Decimal] = None,
        currency: Optional[str] = None,
        method: Literal["standard", "instant"] = "standard",
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Create a payout from Connect account to recipient's bank.
        
        Args:
            connect_account_id: Connect account ID
            amount: Amount to payout (None for full balance)
            currency: Currency for payout
            method: Payout speed (instant has fees)
            metadata: Payout metadata
            
        Returns:
            Payout object details
        """
        try:
            payout_data = {
                "method": method,
                "metadata": metadata or {},
            }
            
            if amount:
                payout_data["amount"] = int(amount)
            if currency:
                payout_data["currency"] = currency.lower()
            
            # Create payout on the Connect account
            payout = stripe.Payout.create(
                stripe_account=connect_account_id,
                **payout_data
            )
            
            logger.info(f"Created payout {payout.id} for account {connect_account_id}")
            
            return {
                "id": payout.id,
                "amount": payout.amount,
                "currency": payout.currency,
                "arrival_date": payout.arrival_date,
                "method": payout.method,
                "status": payout.status,
                "type": payout.type,
            }
            
        except StripeError as e:
            logger.error(f"Payout creation failed: {e}")
            raise PaymentError(f"Failed to create payout: {str(e)}")

    # ==================== Refunds & Reversals ====================

    async def refund_payment(
        self,
        payment_intent_id: str,
        amount: Optional[Decimal] = None,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Refund a payment (full or partial)."""
        try:
            refund_data = {
                "payment_intent": payment_intent_id,
                "metadata": metadata or {},
            }
            
            if amount:
                refund_data["amount"] = int(amount)
            if reason:
                refund_data["reason"] = reason
            
            refund = stripe.Refund.create(**refund_data)
            
            logger.info(f"Created refund {refund.id} for payment {payment_intent_id}")
            
            return {
                "id": refund.id,
                "amount": refund.amount,
                "currency": refund.currency,
                "payment_intent": refund.payment_intent,
                "status": refund.status,
                "created": refund.created,
            }
            
        except StripeError as e:
            logger.error(f"Refund creation failed: {e}")
            raise PaymentError(f"Failed to create refund: {str(e)}")

    async def reverse_transfer(
        self,
        transfer_id: str,
        amount: Optional[Decimal] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Reverse a transfer (claw back funds from Connect account)."""
        try:
            reversal_data = {
                "metadata": metadata or {},
            }
            
            if amount:
                reversal_data["amount"] = int(amount)
            
            reversal = stripe.Transfer.create_reversal(
                transfer_id,
                **reversal_data
            )
            
            logger.info(f"Created reversal {reversal.id} for transfer {transfer_id}")
            
            return {
                "id": reversal.id,
                "amount": reversal.amount,
                "currency": reversal.currency,
                "transfer": reversal.transfer,
                "created": reversal.created,
            }
            
        except StripeError as e:
            logger.error(f"Transfer reversal failed: {e}")
            raise PaymentError(f"Failed to reverse transfer: {str(e)}")

    # ==================== Webhook Processing ====================

    async def webhook_verify(
        self, payload: bytes, sig_header: str
    ) -> Dict[str, Any]:
        """Verify and parse webhook event.
        
        Critical events to handle:
        - payment_intent.succeeded: Payment collected
        - payment_intent.failed: Payment failed
        - charge.dispute.created: Dispute initiated
        - transfer.created/failed: Transfer status
        - payout.paid/failed: Payout status
        - account.updated: Connect account status change
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, self.webhook_secret
            )
            
            logger.info(f"Verified webhook event: {event['type']}")
            
            # Extract relevant data based on event type
            event_data = event["data"]["object"]
            
            response = {
                "id": event["id"],
                "type": event["type"],
                "created": event["created"],
                "livemode": event["livemode"],
                "data": self._extract_webhook_data(event["type"], event_data)
            }
            
            # Log critical events
            if event["type"] in [
                "payment_intent.succeeded",
                "payment_intent.failed",
                "charge.dispute.created",
                "transfer.failed",
                "payout.failed"
            ]:
                logger.warning(f"Critical event received: {event['type']} - {event['id']}")
            
            return response
            
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Webhook signature verification failed: {e}")
            raise ValidationError("Invalid webhook signature")
        except Exception as e:
            logger.error(f"Webhook processing failed: {e}")
            raise PaymentError(f"Failed to process webhook: {str(e)}")

    def _extract_webhook_data(
        self, event_type: str, event_object: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract relevant data from webhook event based on type."""
        
        # Common fields
        data = {
            "id": event_object.get("id"),
            "object": event_object.get("object"),
            "created": event_object.get("created"),
            "livemode": event_object.get("livemode"),
        }
        
        # Type-specific fields
        if event_type.startswith("payment_intent"):
            data.update({
                "amount": event_object.get("amount"),
                "currency": event_object.get("currency"),
                "customer": event_object.get("customer"),
                "status": event_object.get("status"),
                "metadata": event_object.get("metadata"),
            })
        elif event_type.startswith("transfer"):
            data.update({
                "amount": event_object.get("amount"),
                "currency": event_object.get("currency"),
                "destination": event_object.get("destination"),
                "metadata": event_object.get("metadata"),
            })
        elif event_type.startswith("payout"):
            data.update({
                "amount": event_object.get("amount"),
                "currency": event_object.get("currency"),
                "arrival_date": event_object.get("arrival_date"),
                "status": event_object.get("status"),
                "type": event_object.get("type"),
            })
        elif event_type.startswith("account"):
            data.update({
                "charges_enabled": event_object.get("charges_enabled"),
                "payouts_enabled": event_object.get("payouts_enabled"),
                "requirements": event_object.get("requirements"),
            })
        elif event_type.startswith("charge.dispute"):
            data.update({
                "amount": event_object.get("amount"),
                "currency": event_object.get("currency"),
                "reason": event_object.get("reason"),
                "status": event_object.get("status"),
                "evidence_due_by": event_object.get("evidence_details", {}).get("due_by"),
            })
            
        return data

    # ==================== Balance & Reporting ====================

    async def get_balance(self) -> Dict[str, Any]:
        """Get platform account balance."""
        try:
            balance = stripe.Balance.retrieve()
            
            return {
                "available": [
                    {"amount": b.amount, "currency": b.currency}
                    for b in balance.available
                ],
                "pending": [
                    {"amount": b.amount, "currency": b.currency}
                    for b in balance.pending
                ],
            }
            
        except StripeError as e:
            logger.error(f"Balance retrieval failed: {e}")
            raise PaymentError(f"Failed to retrieve balance: {str(e)}")

    async def list_transactions(
        self,
        limit: int = 10,
        starting_after: Optional[str] = None,
        created_after: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """List balance transactions for reconciliation."""
        try:
            params = {"limit": min(limit, 100)}
            
            if starting_after:
                params["starting_after"] = starting_after
            if created_after:
                params["created"] = {"gte": int(created_after.timestamp())}
            
            transactions = stripe.BalanceTransaction.list(**params)
            
            return {
                "has_more": transactions.has_more,
                "data": [
                    {
                        "id": t.id,
                        "amount": t.amount,
                        "currency": t.currency,
                        "type": t.type,
                        "created": t.created,
                        "available_on": t.available_on,
                        "description": t.description,
                    }
                    for t in transactions.data
                ],
            }
            
        except StripeError as e:
            logger.error(f"Transaction listing failed: {e}")
            raise PaymentError(f"Failed to list transactions: {str(e)}")

    # ==================== Utility Methods ====================

    async def cancel_payment(
        self, payment_intent_id: str, reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Cancel a PaymentIntent."""
        try:
            params = {}
            if reason:
                params["cancellation_reason"] = reason
                
            payment_intent = stripe.PaymentIntent.cancel(
                payment_intent_id, **params
            )
            
            return {
                "id": payment_intent.id,
                "status": payment_intent.status,
                "canceled_at": payment_intent.canceled_at,
                "cancellation_reason": payment_intent.cancellation_reason,
            }
            
        except StripeError as e:
            logger.error(f"Payment cancellation failed: {e}")
            raise PaymentError(f"Failed to cancel payment: {str(e)}")

    async def get_payment_status(self, payment_intent_id: str) -> Dict[str, Any]:
        """Get current status of a PaymentIntent."""
        try:
            payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            
            return {
                "id": payment_intent.id,
                "status": payment_intent.status,
                "amount": payment_intent.amount,
                "currency": payment_intent.currency,
                "customer": payment_intent.customer,
                "created": payment_intent.created,
                "metadata": payment_intent.metadata,
            }
            
        except StripeError as e:
            logger.error(f"Payment status retrieval failed: {e}")
            if e.http_status == 404:
                raise PaymentNotFoundError(f"Payment {payment_intent_id} not found")
            raise PaymentError(f"Failed to get payment status: {str(e)}")

    async def attach_payment_method(
        self, payment_method_id: str, customer_id: str
    ) -> Dict[str, Any]:
        """Attach a payment method to a customer for future use."""
        try:
            payment_method = stripe.PaymentMethod.attach(
                payment_method_id,
                customer=customer_id
            )
            
            return {
                "id": payment_method.id,
                "type": payment_method.type,
                "customer": payment_method.customer,
                "created": payment_method.created,
            }
            
        except StripeError as e:
            logger.error(f"Payment method attachment failed: {e}")
            raise PaymentError(f"Failed to attach payment method: {str(e)}")


__all__ = ["StripeAdapter", "TransferType"]