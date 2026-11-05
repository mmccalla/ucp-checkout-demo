#   Copyright 2026 UCP Authors
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
# Modified by the UCP demo in 2026 (Apache-2.0 section 4(b)). The changes are the
# comments marked "UCP demo patch". See business/UPSTREAM.md.

"""Checkout service for managing the lifecycle of checkout sessions.

This module provides the `CheckoutService` class, which encapsulates the
business logic
for creating, retrieving, updating, and completing checkout sessions. It handles
integration with the persistence layer, fulfillment calculation, payment
processing,
and inventory validation.

Key responsibilities include:
- Creating and managing checkout sessions with idempotency support.
- Calculating checkout totals, including line items, shipping, and discounts.
- Validating inventory availability.
- Processing payments via various handlers (e.g., Google Pay, Shop Pay, Mock).
- Transforming checkout sessions into completed orders.
- Supporting hierarchical fulfillment configuration.
"""

import asyncio
import datetime
import hashlib
import json
import logging
import random
from typing import Any
import uuid

import config
import db
from enums import CheckoutStatus
from exceptions import CheckoutNotModifiableError
from exceptions import IdempotencyConflictError
from exceptions import InvalidRequestError
from exceptions import OutOfStockError
from exceptions import PaymentFailedError
from exceptions import ResourceNotFoundError
import httpx2  # UCP demo patch P17: httpx2 replaces httpx
from models import UnifiedCheckout as Checkout
from models import UnifiedCheckoutCreateRequest
from models import UnifiedCheckoutUpdateRequest
from pydantic import AnyUrl
from pydantic import BaseModel
from services.fulfillment_service import FulfillmentService
from sqlalchemy.ext.asyncio import AsyncSession
import ucp_signing
import webhook_signer
from ucp_sdk.models.schemas.ucp import (
  ResponseCheckoutSchema as ResponseCheckout,
)
from ucp_sdk.models.schemas.ucp import ResponseOrderSchema as ResponseOrder
from ucp_sdk.models.schemas.capability import ResponseSchema as Response
from ucp_sdk.models.schemas.shopping.checkout_complete_request import (
  CheckoutCompleteRequest,
)
from ucp_sdk.models.schemas.shopping.discount import Allocation
from ucp_sdk.models.schemas.shopping.discount import AppliedDiscount
from ucp_sdk.models.schemas.shopping.discount import DiscountsObject
from ucp_sdk.models.schemas.shopping.order import (
  Fulfillment as OrderFulfillment,
)
from ucp_sdk.models.schemas.shopping.order import Order
from ucp_sdk.models.schemas.shopping.order import PlatformSchema
from ucp_sdk.models.schemas.shopping.payment_create_request import (
  PaymentCreateRequest,
)
from ucp_sdk.models.schemas.shopping.payment import Payment as PaymentResponse
from ucp_sdk.models.schemas.shopping.types import order_line_item
from ucp_sdk.models.schemas.shopping.types.expectation import Expectation
from ucp_sdk.models.schemas.shopping.types.expectation import (
  LineItem as ExpectationLineItem,
)
# UCP demo patch P8. ucp-sdk 0.4.6 has no py.typed marker (ADR 0007, T-103 item 5).
from ucp_sdk.models.schemas.shopping.types.message_error import MessageError  # type: ignore[import-untyped]
from ucp_sdk.models.schemas.shopping.types.fulfillment_group import (
  FulfillmentGroup,
)
from ucp_sdk.models.schemas.shopping.types.fulfillment_method import (
  FulfillmentMethod,
)
from ucp_sdk.models.schemas.shopping.types.fulfillment import (
  Fulfillment as FulfillmentResponseClass,
)
from ucp_sdk.models.schemas.shopping.types.item import Item as ItemResponse
from ucp_sdk.models.schemas.shopping.types.line_item import (
  LineItem as LineItemResponse,
)
from ucp_sdk.models.schemas.shopping.types.order_confirmation import (
  OrderConfirmation,
)
from ucp_sdk.models.schemas.shopping.types.order_line_item import OrderLineItem
from ucp_sdk.models.schemas.shopping.types.postal_address import PostalAddress
from ucp_sdk.models.schemas.shopping.types.shipping_destination import (
  ShippingDestination as ShippingDestinationResponse,
)
from ucp_sdk.models.schemas.shopping.types.total import (
  Total as TotalResponse,
)

logger = logging.getLogger(__name__)


def _without_credentials(data: dict[str, Any]) -> dict[str, Any]:
  """UCP demo patch P15 (AC-54): a copy with each instrument credential masked."""
  out: dict[str, Any] = json.loads(json.dumps(data))
  parts = [out.get("payment"), (out.get("checkout_complete") or {}).get("payment")]
  for part in parts:
    for inst in (part or {}).get("instruments") or []:
      if isinstance(inst, dict) and "credential" in inst:
        inst["credential"] = "[REDACTED]"
  return out


class CheckoutService:
  """Service for managing checkout sessions and orders."""

  def __init__(
    self,
    fulfillment_service: FulfillmentService,
    products_session: AsyncSession,
    transactions_session: AsyncSession,
    base_url: str,
  ):
    """Initialize CheckoutService."""
    self.fulfillment_service = fulfillment_service
    self._creating = False  # UCP demo patch P8
    self.products_session = products_session
    self.transactions_session = transactions_session
    self.base_url = base_url.rstrip("/")

  def _compute_hash(
    self,
    operation: str,
    data: Any,
    resource_id: str | None = None,
  ) -> str:
    """Compute a hash of an idempotent operation's complete identity."""
    if isinstance(data, BaseModel):
      # Pydantic's optimized JSON dump
      # sort_keys is not supported in model_dump_json in Pydantic V2.
      # We dump to dict and use standard json.dumps for deterministic sorting.
      data = data.model_dump(mode="json")
    request_identity = {
      "operation": operation,
      "resource_id": resource_id,
      "data": data,
    }
    # sort_keys=True ensures deterministic hashing for dicts.
    json_str = json.dumps(request_identity, sort_keys=True)
    return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

  async def create_checkout(
    self,
    checkout_req: UnifiedCheckoutCreateRequest,
    idempotency_key: str,
    platform_config: PlatformSchema | None = None,
  ) -> Checkout:
    """Create a new checkout session."""
    logger.info("Creating checkout session")
    self._creating = True  # UCP demo patch P8

    # Idempotency Check
    request_hash = self._compute_hash("create_checkout", checkout_req)
    existing_record = await db.get_idempotency_record(
      self.transactions_session, idempotency_key
    )

    if existing_record:
      if existing_record.request_hash != request_hash:
        raise IdempotencyConflictError(
          "Idempotency key reused with different parameters"
        )
      # Return cached response
      return Checkout(**existing_record.response_body)
    cart_id = getattr(checkout_req, "cart_id", None)

    if cart_id:
      # Check if incomplete checkout already exists for this cart_id
      existing_checkouts = await db.get_checkouts_by_cart_id(
        self.transactions_session, cart_id
      )
      for data in existing_checkouts:
        if data.get("status") not in [
          CheckoutStatus.COMPLETED,
          CheckoutStatus.CANCELED,
        ]:
          logger.info(
            "Returning existing incomplete checkout for cart %s", cart_id
          )
          return Checkout(**data)

      # Load cart to initialize checkout
      cart_data = await db.get_cart_session(self.transactions_session, cart_id)
      if not cart_data:
        raise ResourceNotFoundError(f"Cart session {cart_id} not found")

      from models import UnifiedCart as CartModel

      cart = CartModel(**cart_data)

      # Initialize from cart
      source_line_items = cart.line_items
      source_buyer = cart.buyer
      source_context = cart.context
      source_signals = cart.signals
      source_attribution = cart.attribution
      source_currency = cart.currency
      source_discounts = cart.discounts
    else:
      # Initialize from request
      source_line_items = checkout_req.line_items
      source_buyer = checkout_req.buyer
      source_context = checkout_req.context
      source_signals = checkout_req.signals
      source_attribution = checkout_req.attribution
      # `currency` carries `ucp_request: omit`, so the merchant determines it.
      source_currency = config.get_default_currency()
      source_discounts = checkout_req.discounts

    # `id` carries `ucp_request: omit`, so the server assigns it and never
    # takes it from the request. The generated CheckoutCreateRequest declares
    # no id field, but extra="allow" admits a client-sent `id` of any JSON
    # type as an extra attribute; reading it here propagated that raw value
    # into the response model, where a non-string raised an uncaught
    # ValidationError. Same defect class as the currency read fixed in #156.
    checkout_id = str(uuid.uuid4())

    # Map line items
    line_items = []
    for li in source_line_items:
      item_id = li.item.id
      quantity = li.quantity
      parent_id = getattr(li, "parent_id", None)
      # When converting from a cart, preserve the cart line item id.
      # On direct create, line item `id` carries `create: omit` so
      # the server assigns it.
      li_id = li.id if cart_id else str(uuid.uuid4())
      line_items.append(
        LineItemResponse(
          id=li_id,
          item=ItemResponse(
            id=item_id,
            title="",
            price=0,  # Will be set by recalculate_totals
          ),
          quantity=quantity,
          totals=[],
          parent_id=parent_id,
        )
      )

    # We exclude fields that the service explicitly manages or overrides, as
    # well as fields marked as `ucp_request: omit` in checkout.json
    # (continue_url, expires_at, messages, order) to ensure the server is the
    # authoritative source and client values do not bleed into the response.
    #
    # * Conflict Prevention: If we didn't exclude currency, id, or payment,
    #   passing them via **checkout_data while also specifying them as keyword
    #   arguments (e.g., currency=checkout_req.currency) would raise a
    #   TypeError: multiple values for keyword argument.
    # * Server Authority: Fields like status, totals, links, continue_url,
    #   expires_at, messages, and order are merchant-owned. We exclude them from
    #   the dumped data to ensure we start with a clean calculated state and
    #   client-supplied omit members are dropped.
    # * Model Transformation: ucp in the request is usually just version
    #   negotiation info, but in the response, it's a complex ResponseCheckout
    #   object with capability metadata. We exclude the request version to
    #   inject the full response object.
    checkout_data = checkout_req.model_dump(
      exclude={
        "line_items",
        "payment",
        "ucp",
        "currency",
        "id",
        "status",
        "totals",
        "links",
        "fulfillment",
        "buyer",
        "context",
        "signals",
        "attribution",
        "cart_id",
        "discounts",
        "continue_url",
        "expires_at",
        "messages",
        "order",
        # `platform` is derived from the UCP-Agent profile and passed as a
        # keyword below; a client-sent member would collide with it.
        "platform",
        # `ap2` reaches here for a different reason: it is not declared on the
        # create request, so a client value survives as an extra, and it IS a
        # declared field on the response model, so it is validated there. The
        # service never sets it, and the schema annotates it create: omit.
        "ap2",
      }
    )
    # UCP demo patch P7: accept unknown root fields but do not show them
    # (spec T-86). A field such as `risk_signals` is logged by the host app
    # and is not copied into the checkout (AC-38).
    for extra in list((checkout_req.model_extra or {}).keys()):
      checkout_data.pop(extra, None)

    # Initialize fulfillment response
    fulfillment_resp = None
    if checkout_req.fulfillment:
      req_fulfillment = checkout_req.fulfillment
      resp_methods = []
      all_li_ids = [li.id for li in line_items]

      if req_fulfillment.methods:
        for method_req in req_fulfillment.methods:
          # Create Method Response
          method_id = getattr(method_req, "id", None) or str(uuid.uuid4())
          method_li_ids = (
            getattr(method_req, "line_item_ids", None) or all_li_ids
          )
          method_type = getattr(method_req, "type", "shipping")

          resp_groups = []
          if method_req.groups:
            for group_req in method_req.groups:
              group_id = (
                getattr(group_req, "id", None) or f"group_{uuid.uuid4()}"
              )
              group_li_ids = (
                getattr(group_req, "line_item_ids", None) or all_li_ids
              )

              resp_groups.append(
                FulfillmentGroup(
                  id=group_id,
                  line_item_ids=group_li_ids,
                  selected_option_id=getattr(
                    group_req, "selected_option_id", None
                  ),
                )
              )

          # Convert destinations if present (usually empty on create, but
          # handled for completeness)
          resp_destinations = []
          if method_req.destinations:
            for dest_req in method_req.destinations:
              # Assuming ShippingDestinationRequest can map to Response
              # structure or needs conversion. For create, we typically accept
              # ShippingDestinationRequest inside
              # FulfillmentMethodCreateRequest. We need to convert it to
              # FulfillmentDestinationResponse.
              # The request model structure is complex
              # (FulfillmentDestinationRequest -> ShippingDestinationRequest)
              # The response model is FulfillmentDestinationResponse ->
              # ShippingDestinationResponse

              resp_destinations.append(
                ShippingDestinationResponse(
                  id=getattr(dest_req, "id", None) or str(uuid.uuid4()),
                  address_country=dest_req.address_country,
                  postal_code=dest_req.postal_code,
                  address_region=dest_req.address_region,
                  address_locality=dest_req.address_locality,
                  street_address=dest_req.street_address,
                )
              )

          resp_methods.append(
            FulfillmentMethod(
              id=method_id,
              type=method_type,
              line_item_ids=method_li_ids,
              groups=resp_groups or None,
              destinations=resp_destinations or None,
              selected_destination_id=getattr(
                method_req, "selected_destination_id", None
              ),
            )
          )

      fulfillment_resp = FulfillmentResponseClass(methods=resp_methods)

    # The SDK enforces the totals contains cardinality (exactly one subtotal
    # and one total) on the response model. The server is the authority for
    # totals and computes them in _recalculate_totals below, but that runs
    # after construction. Seed a valid placeholder so the in-progress model
    # satisfies the constraint at construction; it is overwritten with the
    # authoritative amounts immediately. See python-sdk#57.
    checkout = Checkout(
      ucp=ResponseCheckout(
        version=config.get_server_version(),
        # UCP demo patch P1: the capabilities that the business serves.
        capabilities=config.get_response_capabilities(),
        payment_handlers=config.get_payment_handlers(),
      ),
      id=checkout_id,
      status=CheckoutStatus.IN_PROGRESS,
      currency=source_currency,
      line_items=line_items,
      totals=[
        {"type": "subtotal", "amount": 0},
        {"type": "total", "amount": 0},
      ],
      links=list(config.LINKS),  # UCP demo patch P10 (AC-109)
      # Same request/response class collision as update_checkout below:
      # checkout_req.payment.instruments holds
      # payment_instrument_create_request.SelectedPaymentInstrument
      # instances, not the payment_instrument.SelectedPaymentInstrument the
      # response field declares. Dump to a dict first so PaymentResponse
      # parses it rather than rejecting a foreign model instance.
      payment=PaymentResponse(
        **checkout_req.payment.model_dump(exclude_none=True)
      )
      if checkout_req.payment
      else None,
      platform=platform_config,
      fulfillment=fulfillment_resp,
      buyer=source_buyer.model_dump(exclude_none=True)
      if source_buyer
      else None,
      context=source_context.model_dump(exclude_none=True)
      if source_context
      else None,
      signals=source_signals.model_dump(exclude_none=True)
      if source_signals
      else None,
      attribution=dict(source_attribution) if source_attribution else None,
      cart_id=cart_id,
      discounts=source_discounts.model_dump(exclude_none=True)
      if source_discounts
      else None,
      **checkout_data,
    )

    # Validate inventory and recalculate totals (Server is authority)
    await self._enrich_and_recalculate(checkout)
    await self._validate_inventory(checkout)

    checkout.status = self._readiness_status(checkout)

    response_body = checkout.model_dump(
      mode="json", by_alias=True, exclude_none=True
    )

    # Persist checkout to Transactions DB
    await db.save_checkout(
      self.transactions_session,
      checkout.id,
      checkout.status,
      response_body,
    )

    # One commit that also resolves a CONCURRENT duplicate of this
    # key: a loser of the primary-key race is answered with the
    # winner's cached response, not a 500.
    cached = await db.commit_with_idempotency(
      self.transactions_session,
      idempotency_key,
      request_hash,
      201,  # Created
      response_body,
    )
    if cached is not None:
      return Checkout(**cached)

    return checkout

  async def get_checkout(
    self,
    checkout_id: str,
  ) -> Checkout:
    """Retrieve a checkout session."""
    # Log the request
    await db.log_request(
      self.transactions_session,
      method="GET",
      url=f"/checkout-sessions/{checkout_id}",
      checkout_id=checkout_id,
    )
    await self.transactions_session.commit()

    return await self._get_and_validate_checkout(checkout_id)

  async def update_checkout(
    self,
    checkout_id: str,
    checkout_req: UnifiedCheckoutUpdateRequest,
    idempotency_key: str,
    platform_config: PlatformSchema | None = None,
  ) -> Checkout:
    """Update a checkout session."""
    logger.info("Updating checkout session %s", checkout_id)
    self._creating = False  # UCP demo patch P8

    # Idempotency Check
    request_hash = self._compute_hash(
      "update_checkout", checkout_req, resource_id=checkout_id
    )

    existing_record = await db.get_idempotency_record(
      self.transactions_session, idempotency_key
    )
    if existing_record:
      if existing_record.request_hash != request_hash:
        raise IdempotencyConflictError(
          "Idempotency key reused with different parameters"
        )
      return Checkout(**existing_record.response_body)

    # Log the request
    payload_dict = checkout_req.model_dump(mode="json")
    await db.log_request(
      self.transactions_session,
      method="PUT",
      url=f"/checkout-sessions/{checkout_id}",
      checkout_id=checkout_id,
      payload=payload_dict,
    )

    existing = await self._get_and_validate_checkout(checkout_id)
    self._ensure_modifiable(existing, "update")

    # Update existing with request data
    # This is a partial update logic
    if checkout_req.line_items:
      line_items = []
      for li_req in checkout_req.line_items:
        line_items.append(
          LineItemResponse(
            id=li_req.id or str(uuid.uuid4()),
            item=ItemResponse(
              id=li_req.item.id,
              title="",
              price=0,
            ),
            quantity=li_req.quantity,
            totals=[],
            parent_id=li_req.parent_id,
          )
        )
      existing.line_items = line_items

    # `currency` carries `ucp_request: omit`, so the business determines it
    # and an update never takes it from the request. Reading it here also
    # raised AttributeError whenever a conformant platform omitted it, which
    # is the same defect as the create path.

    if checkout_req.payment:
      # checkout_req.payment.instruments holds
      # payment_instrument_update_request.SelectedPaymentInstrument
      # instances, a sibling of the response class
      # payment_instrument.SelectedPaymentInstrument that PaymentResponse
      # declares for the same field. Passing the request instances straight
      # through fails pydantic's model-type check (a different class, not a
      # dict), which raised an unhandled ValidationError -- a bare 500 --
      # whenever an update carried a non-empty instruments array. Dumping to
      # a dict first and letting PaymentResponse parse it mirrors how buyer,
      # context, signals, and discounts already cross this same request to
      # response boundary below and in create_checkout.
      existing.payment = PaymentResponse(
        **checkout_req.payment.model_dump(exclude_none=True)
      )

    if checkout_req.buyer:
      existing.buyer = checkout_req.buyer

    if hasattr(checkout_req, "fulfillment") and checkout_req.fulfillment:
      # Hierarchical fulfillment update
      logging.info(
        "Processing hierarchical fulfillment update for %s", checkout_id
      )

      # Fetch customer addresses if buyer is known
      customer_addresses = []
      if existing.buyer and existing.buyer.email:
        customer_addresses = await db.get_customer_addresses(
          self.transactions_session, existing.buyer.email
        )

      req_fulfillment = checkout_req.fulfillment
      resp_methods = []

      if req_fulfillment.methods:
        logging.info("Request has %d methods", len(req_fulfillment.methods))
        for m_req in req_fulfillment.methods:
          # Find matching existing method to preserve state
          existing_method = None
          if existing.fulfillment and existing.fulfillment.methods:
            existing_method = next(
              (
                m
                for m in existing.fulfillment.methods
                if m.id == getattr(m_req, "id", None)
              ),
              None,
            )
            # Fallback: If no ID in request, and only 1 existing method, match
            # it
            if (
              not existing_method
              and not getattr(m_req, "id", None)
              and len(existing.fulfillment.methods) == 1
            ):
              existing_method = existing.fulfillment.methods[0]

          # Resolve ID
          method_id = getattr(m_req, "id", None)
          if existing_method and not method_id:
            method_id = existing_method.id
          if not method_id:
            method_id = str(uuid.uuid4())

          method_type = getattr(m_req, "type", "shipping")
          method_li_ids = getattr(m_req, "line_item_ids", None) or [
            li.id for li in existing.line_items
          ]

          resp_destinations = []

          # Handle destinations
          if method_type == "shipping":
            if m_req.destinations:
              # Use provided destinations
              for dest_req in m_req.destinations:
                dest_data = dest_req.model_dump(exclude_none=True)

                # Persist addresses for known customers
                if existing.buyer and existing.buyer.email:
                  # Save and update ID
                  saved_id = await db.save_customer_address(
                    self.transactions_session,
                    existing.buyer.email,
                    dest_data,
                  )
                  # Adopt the stored key only when the platform supplied no id.
                  # The row key is internal. Echoing a different id back would
                  # leave selected_destination_id pointing at no destination,
                  # which stalls the checkout more quietly than the error this
                  # change removes.
                  if not dest_data.get("id"):
                    dest_data["id"] = saved_id

                resp_destinations.append(
                  ShippingDestinationResponse(**dest_data)
                )

            elif existing_method and existing_method.destinations:
              # Preserve existing destinations
              resp_destinations = existing_method.destinations
            elif customer_addresses:
              for addr in customer_addresses:
                resp_destinations.append(
                  ShippingDestinationResponse(
                    id=addr.id,
                    street_address=addr.street_address,
                    address_locality=addr.city,
                    address_region=addr.state,  # Map state to region
                    postal_code=addr.postal_code,
                    address_country=addr.country,
                  )
                )

          # Handle groups
          resp_groups = []
          if m_req.groups:
            for g_idx, g_req in enumerate(m_req.groups):
              g_id = getattr(g_req, "id", None) or f"group_{uuid.uuid4()}"
              # UCP demo patch P14 (spec T-104, ACCEPTED): only the business
              # sets the line items and the options of a group. A client value
              # is ignored and never echoed. The log has the field path only,
              # never the value.
              for omit_field in ("line_item_ids", "options"):
                if getattr(g_req, omit_field, None) is not None:
                  logger.warning(
                    "ignored client field $.fulfillment.methods[%d].groups[%d].%s",
                    req_fulfillment.methods.index(m_req),
                    g_idx,
                    omit_field,
                  )
              g_li_ids = [li.id for li in existing.line_items]
              resp_groups.append(
                FulfillmentGroup(
                  id=g_id,
                  line_item_ids=g_li_ids,
                  selected_option_id=getattr(g_req, "selected_option_id", None),
                )
              )
          elif existing_method and existing_method.groups:
            # Preserve existing groups if not updating them
            resp_groups = existing_method.groups

          # Construct the method response
          method_resp = FulfillmentMethod(
            id=method_id,
            type=method_type,
            line_item_ids=method_li_ids,
            groups=resp_groups or None,
            destinations=resp_destinations or None,
            selected_destination_id=getattr(
              m_req, "selected_destination_id", None
            ),
          )
          resp_methods.append(method_resp)

      existing.fulfillment = FulfillmentResponseClass(
        methods=resp_methods,
      )

    if getattr(checkout_req, "discounts", None):
      existing.discounts = checkout_req.discounts

    if platform_config:
      existing.platform = platform_config

    # Validate inventory and recalculate totals (Server is authority)
    await self._enrich_and_recalculate(existing)
    await self._validate_inventory(existing)

    existing.status = self._readiness_status(existing)

    response_body = existing.model_dump(
      mode="json", by_alias=True, exclude_none=True
    )

    await db.save_checkout(
      self.transactions_session,
      checkout_id,
      existing.status,
      response_body,
    )

    # One commit that also resolves a CONCURRENT duplicate of this
    # key: a loser of the primary-key race is answered with the
    # winner's cached response, not a 500.
    cached = await db.commit_with_idempotency(
      self.transactions_session,
      idempotency_key,
      request_hash,
      200,
      response_body,
    )
    if cached is not None:
      return Checkout(**cached)
    return existing

  async def complete_checkout(
    self,
    checkout_id: str,
    payment: PaymentCreateRequest,
    idempotency_key: str,
    checkout_complete: CheckoutCompleteRequest | None = None,
  ) -> Checkout:
    """Complete a checkout session."""
    logger.info("Completing checkout session %s", checkout_id)

    # Idempotency Check
    # The whole request body is part of the request identity, so signals and
    # attribution are included through checkout_complete.
    combined_data = {
      "payment": payment.model_dump(mode="json"),
      "checkout_complete": checkout_complete.model_dump(mode="json")
      if checkout_complete
      else None,
    }
    request_hash = self._compute_hash(
      "complete_checkout", combined_data, resource_id=checkout_id
    )

    existing_record = await db.get_idempotency_record(
      self.transactions_session, idempotency_key
    )
    if existing_record:
      if existing_record.request_hash != request_hash:
        raise IdempotencyConflictError(
          "Idempotency key reused with different parameters"
        )
      return Checkout(**existing_record.response_body)

    # Log the request
    await db.log_request(
      self.transactions_session,
      method="POST",
      url=f"/checkout-sessions/{checkout_id}/complete",
      checkout_id=checkout_id,
      # UCP demo patch P15 (AC-54): the request log keeps no credential.
      payload=_without_credentials(combined_data),
    )

    checkout = await self._get_and_validate_checkout(checkout_id)
    self._ensure_modifiable(checkout, "complete")

    # UCP demo patch P15 (spec T-105): check the fulfillment and the stock
    # BEFORE the charge, so an invalid checkout gets no PSP call.
    if not self._has_fulfillment_selection(checkout):
      raise InvalidRequestError(
        "Fulfillment address and option must be selected before completion."
      )
    for line in checkout.line_items:
      qty_avail = await db.get_inventory(self.transactions_session, line.item.id)
      if qty_avail is not None and qty_avail < line.quantity:
        raise OutOfStockError(
          f"Item {line.item.id} is out of stock", status_code=409
        )

    # Process Payment
    # UCP demo patch P15 (spec T-105): a payment failure returns the checkout
    # with a payment_failed message, and the result is stored for the key.
    try:
      await self._process_payment(payment, checkout)
    except PaymentFailedError as e:
      return await self._payment_failed(
        checkout, idempotency_key, request_hash, e
      )

    # Atomic Inventory Reservation + Order Completion
    try:
      for line in checkout.line_items:
        product_id = line.item.id
        # We verify product existence again (optional but good practice)
        if await db.get_product(self.products_session, product_id):
          success = await db.reserve_stock(
            self.transactions_session, product_id, line.quantity
          )
          if not success:
            # This rollback applies to the transaction_session
            await self.transactions_session.rollback()
            raise OutOfStockError(
              f"Item {product_id} is out of stock", status_code=409
            )
        else:
          # A line item references a product that no longer exists. Fail
          # loudly instead of silently skipping inventory reservation and
          # creating an order for a non-existent product. No prices are
          # re-derived here; this only enforces fail-closed completion.
          await self.transactions_session.rollback()
          raise InvalidRequestError(f"Product {product_id} not found")

      checkout.status = CheckoutStatus.COMPLETED
      order_id = f"{uuid.uuid4()}"
      order_permalink_url = AnyUrl(f"{self.base_url}/orders/{order_id}")

      checkout.order = OrderConfirmation(
        id=order_id, permalink_url=order_permalink_url
      )
      response_body = checkout.model_dump(
        mode="json", by_alias=True, exclude_none=True
      )
      # UCP demo patch P15 (AC-112): echo the processed instrument WITHOUT its
      # credential. The token is never stored or sent back.
      echoed = payment.model_dump(mode="json", by_alias=True, exclude_none=True)
      for inst in echoed.get("instruments") or []:
        inst.pop("credential", None)
      response_body["payment"] = {"instruments": echoed.get("instruments") or []}

      # Create and persist Order
      expectations = []
      if checkout.fulfillment and checkout.fulfillment.methods:
        for method in checkout.fulfillment.methods:
          selected_dest = None
          if method.selected_destination_id and method.destinations:
            for dest in method.destinations:
              if dest.id == method.selected_destination_id:
                selected_dest = PostalAddress(
                  street_address=dest.street_address,
                  address_locality=dest.address_locality,
                  address_region=dest.address_region,
                  postal_code=dest.postal_code,
                  address_country=dest.address_country,
                )
                break

          if method.groups:
            for group in method.groups:
              if getattr(group, "selected_option_id", None):
                options = getattr(group, "options", [])
                selected_opt = next(
                  (
                    o
                    for o in (options or [])
                    if o.id == group.selected_option_id
                  ),
                  None,
                )
                expectation_id = f"exp_{uuid.uuid4()}"

                exp_line_items = []
                for li in checkout.line_items:
                  if li.id in getattr(group, "line_item_ids", []):
                    exp_line_items.append(
                      ExpectationLineItem(id=li.id, quantity=li.quantity)
                    )
                # Fallback to all line items if none match
                # (e.g. tests using item_123)
                if not exp_line_items:
                  for li in checkout.line_items:
                    exp_line_items.append(
                      ExpectationLineItem(id=li.id, quantity=li.quantity)
                    )

                expectations.append(
                  Expectation(
                    id=expectation_id,
                    line_items=exp_line_items,
                    method_type=method.type,
                    destination=selected_dest,
                    description=getattr(
                      selected_opt, "title", "Standard Shipping"
                    ),
                  )
                )

      order_line_items = []

      for li in checkout.line_items:
        # Create Quantity object for OrderLineItem
        qty = order_line_item.Quantity(total=li.quantity, fulfilled=0)

        oli = OrderLineItem(
          id=li.id,
          item=li.item,
          quantity=qty,
          totals=li.totals,
          status="processing",
          parent_id=li.parent_id,
        )
        order_line_items.append(oli)

      order = Order(
        ucp=ResponseOrder(
          version=getattr(checkout.ucp, "version", "2026-04-08"),
          capabilities=dict(checkout.ucp.capabilities)
          if hasattr(checkout.ucp, "capabilities") and checkout.ucp.capabilities
          else {},
        ),
        id=checkout.order.id,
        checkout_id=checkout.id,
        permalink_url=checkout.order.permalink_url,
        line_items=order_line_items,
        totals=checkout.totals,
        currency=checkout.currency,
        fulfillment=OrderFulfillment(expectations=expectations, events=[]),
      )

      await db.save_order(
        self.transactions_session,
        order.id,
        order.model_dump(mode="json", by_alias=True, exclude_none=True),
      )

      await db.save_checkout(
        self.transactions_session,
        checkout_id,
        checkout.status,
        response_body,
      )

      if checkout.cart_id:
        logger.info(
          "Clearing cart %s after checkout completion", checkout.cart_id
        )
        await db.delete_cart_session(
          self.transactions_session, checkout.cart_id
        )

      # Commit the inventory updates, the checkout status and the
      # idempotency record atomically, and resolve a CONCURRENT
      # duplicate of this key. A loser of the race returns the
      # WINNER's cached order and must return BEFORE the webhook
      # below: the winner has already delivered order_placed, and a
      # second delivery for one order would be worse than the 500
      # this replaces.
      cached = await db.commit_with_idempotency(
        self.transactions_session,
        idempotency_key,
        request_hash,
        200,
        response_body,
      )
      if cached is not None:
        return Checkout(**cached)

      # Notify webhook of order placement
      await self._notify_webhook(checkout, "order_placed")

    except Exception as e:
      await self.transactions_session.rollback()
      raise e

    # UCP demo patch P15 (AC-112, AC-46): return the stored response body, so a
    # replay with the same key gets the same body.
    return Checkout(**response_body)

  async def _payment_failed(
    self,
    checkout: Checkout,
    idempotency_key: str,
    request_hash: str,
    error: PaymentFailedError,
  ) -> Checkout:
    """UCP demo patch P15 (spec T-105): the response for a payment failure.

    HTTP 200 with the checkout body. The status, line items, totals and
    fulfillment do not change, and there is no order. One message: type
    error, code payment_failed, severity recoverable. The content has no
    token and no PSP reason. The checkout record is not changed. The
    response is stored for the Idempotency-Key (signatures.md line 833:
    "Return cached response, do not re-execute").
    """
    logger.info(
      "Payment failed for checkout %s (code %s)", checkout.id, error.code
    )
    checkout.messages = [
      MessageError(
        type="error",
        code="payment_failed",
        content=(
          "The payment was not accepted. You did not pay. "
          "You can try again with a new payment."
        ),
        severity="recoverable",
      )
    ]
    checkout.order = None
    response_body = checkout.model_dump(
      mode="json", by_alias=True, exclude_none=True
    )
    cached = await db.commit_with_idempotency(
      self.transactions_session,
      idempotency_key,
      request_hash,
      200,
      response_body,
    )
    if cached is not None:
      return Checkout(**cached)
    return Checkout(**response_body)

  async def _notify_webhook(self, checkout: Checkout, event_type: str) -> None:
    """Notifies the configured webhook of an order event.

    Per the UCP REST OpenAPI (``webhooks.orderEvent``), the request body is the
    order object itself (``#/components/schemas/order``). This sample also sends
    an ``X-Event-Type`` extension header, but it is not part of the UCP webhook
    contract and conforming receivers cannot require it. The body must always be
    a valid order, so no notification is sent when there is no order to deliver.

    Every delivery is RFC 9421-signed as this business (order.md, Webhook
    Signature Verification): ``UCP-Agent`` names our profile, and
    ``Content-Digest``/``Signature-Input``/``Signature`` cover the exact raw
    body bytes sent on the wire. Failed deliveries (transport errors or a
    5xx from the receiver) are retried with bounded exponential backoff
    (order.md: businesses MUST retry failed webhook deliveries); a 4xx is a
    permanent rejection and is not retried. Delivery failures are logged and
    never propagate into the order flow.
    """
    if not checkout.platform or not checkout.platform.webhook_url:
      return

    order_data = None
    if checkout.order and checkout.order.id:
      order_data = await db.get_order(
        self.transactions_session, checkout.order.id
      )

    if not order_data:
      logger.warning(
        "Skipping %s webhook for checkout %s: no order to deliver",
        event_type,
        checkout.id,
      )
      return

    webhook_url = str(checkout.platform.webhook_url)
    # Serialize exactly once: the signed Content-Digest and the wire body
    # must be the same bytes.
    body = json.dumps(order_data).encode("utf-8")
    webhook_id = str(uuid.uuid4())
    headers = {
      "Content-Type": "application/json",
      "X-Event-Type": event_type,
      "Webhook-Id": webhook_id,
      "Webhook-Timestamp": str(
        int(datetime.datetime.now(datetime.timezone.utc).timestamp())
      ),
      # A webhook POST is a state-changing request, so the signed-component
      # table requires idempotency-key (signatures.md). The event id doubles
      # as the key: retries carry the same value, letting the platform
      # deduplicate redelivered events.
      "Idempotency-Key": webhook_id,
      # Sign AS this business: the profile URL platforms fetch our
      # signing_keys[] from (order.md requires UCP-Agent on deliveries).
      # UCP demo patch P16: the public profile URL. request.base_url is the proxy
      # upstream (http://127.0.0.1:8201/), which a platform cannot fetch.
      "UCP-Agent": 'profile="%s"'
      % (config.WEBHOOK_PROFILE_URL or f"{self.base_url}/.well-known/ucp"),
    }
    attempts = config.FLAGS.webhook_delivery_attempts
    backoff = config.FLAGS.webhook_retry_backoff_seconds
    try:
      key, kid = webhook_signer.signing_key()
      # UCP demo patch P15: config.WEBHOOK_TRANSPORT is a test seam.
      async with httpx2.AsyncClient(transport=config.WEBHOOK_TRANSPORT) as client:
        for attempt in range(1, attempts + 1):
          # Re-sign per attempt so the signature's `created` timestamp
          # reflects the actual send time of each delivery attempt.
          additions = ucp_signing.sign_request(
            key,
            kid,
            "POST",
            webhook_url,
            headers,
            body,
            extra_components=(
              "webhook-id",
              "webhook-timestamp",
              "x-event-type",
            ),
          )
          try:
            response = await client.post(
              webhook_url,
              content=body,
              headers={**headers, **additions},
              timeout=5.0,
            )
          except httpx2.HTTPError as exc:
            failure = f"transport error: {exc}"
          else:
            if 200 <= response.status_code < 300:
              return
            failure = f"HTTP {response.status_code}"
            if response.status_code < 500:
              # The receiver rejected this delivery as invalid; retrying
              # the same request cannot succeed.
              logger.error(
                "Webhook delivery to %s permanently rejected (%s); "
                "not retrying",
                webhook_url,
                failure,
              )
              # UCP demo patch P16: dead letter (T-42).
              if config.WEBHOOK_DEAD_LETTER is not None:
                config.WEBHOOK_DEAD_LETTER(event_type, webhook_id, failure)
              return
          if attempt < attempts:
            # UCP demo patch P16: add jitter (T-42, 0.5 s and 1 s plus jitter).
            delay = backoff * (2 ** (attempt - 1)) + random.uniform(0, backoff / 5)
            logger.warning(
              "Webhook delivery attempt %d/%d to %s failed (%s); "
              "retrying in %.2fs",
              attempt,
              attempts,
              webhook_url,
              failure,
              delay,
            )
            await asyncio.sleep(delay)
        logger.error(
          "Failed to deliver %s webhook to %s after %d attempts (%s)",
          event_type,
          webhook_url,
          attempts,
          failure,
        )
        # UCP demo patch P16: dead letter (T-42).
        if config.WEBHOOK_DEAD_LETTER is not None:
          config.WEBHOOK_DEAD_LETTER(event_type, webhook_id, failure)
    except Exception as e:  # pylint: disable=broad-exception-caught
      logger.error("Failed to notify webhook at %s: %s", webhook_url, e)

  async def ship_order(self, order_id: str) -> None:
    """Simulate shipping an order and notifies the webhook."""
    order_data = await db.get_order(self.transactions_session, order_id)
    if not order_data:
      raise ResourceNotFoundError("Order not found")

    # Add shipping event to order
    if "fulfillment" not in order_data:
      order_data["fulfillment"] = {"events": []}
    if (
      "events" not in order_data["fulfillment"]
      or order_data["fulfillment"]["events"] is None
    ):
      order_data["fulfillment"]["events"] = []

    event_id = f"evt_{uuid.uuid4()}"
    occurred_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Ship-all-remaining (simulator policy, not a 2026-04-08 requirement):
    # each call ships every unit not yet fulfilled, so the appended event's
    # per-line quantities are exactly the counter increments for this call.
    # Lines with nothing remaining are excluded — the 2026-04-08
    # fulfillment_event.json schema requires each event quantity >= 1.
    shippable = []
    for line_item in order_data["line_items"]:
      quantity = line_item["quantity"]
      remaining = quantity["total"] - quantity.get("fulfilled", 0)
      if remaining > 0:
        shippable.append((line_item, remaining))

    # Zero-total lines can never appear in a shipment event (the 2026-04-08
    # fulfillment_event.json schema requires each event quantity >= 1), so
    # they are recorded as removed. This normalization runs even when
    # nothing ships, so an all-removed order still reflects it.
    status_changed = False
    for line_item in order_data["line_items"]:
      total = line_item["quantity"]["total"]
      if total == 0 and line_item.get("status") != "removed":
        line_item["status"] = "removed"
        status_changed = True

    if not shippable:
      # Nothing left to ship: no new shipment event and no invented
      # shipment quantities. Persist any status normalization above so the
      # stored order reflects removed lines; no webhook is emitted.
      if status_changed:
        await db.save_order(self.transactions_session, order_id, order_data)
        await self.transactions_session.commit()
      return

    line_items = [
      {
        "id": line_item["id"],
        "quantity": remaining,
      }
      for line_item, remaining in shippable
    ]

    # Keep the stored order self-consistent with its own event log: each
    # shipped line's `fulfilled` counter is incremented by exactly the
    # quantity the event records for it ("Quantity fulfilled in this
    # event", 2026-04-08 fulfillment_event.json). The 2026-04-08 status
    # derivation is descriptive text; this is reference-sample
    # self-consistency, not a spec-conformance claim.
    for line_item, remaining in shippable:
      quantity = line_item["quantity"]
      quantity["fulfilled"] = quantity.get("fulfilled", 0) + remaining
      line_item["status"] = "fulfilled"

    order_data["fulfillment"]["events"].append(
      {
        "id": event_id,
        "type": "shipped",
        "occurred_at": occurred_at,
        "line_items": line_items,
        # UCP demo patch P16: fulfillment_event.json needs tracking_number and
        # tracking_url when type != processing. The values are fake (AC-74).
        "tracking_number": "SIM-" + event_id[4:12].upper(),
        "tracking_url": f"https://tracking.invalid/{event_id}",
        "carrier": "Simulated carrier",
      }
    )

    await db.save_order(self.transactions_session, order_id, order_data)
    await self.transactions_session.commit()

    # Get checkout to find webhook_url
    checkout_id = order_data.get("checkout_id")
    if checkout_id:
      checkout = await self._get_and_validate_checkout(checkout_id)
      await self._notify_webhook(checkout, "order_shipped")

  # UCP demo patch P16: simulated delivery (AC-74, T-23). The sample has none.
  async def deliver_order(self, order_id: str) -> None:
    """Simulate delivery of the last shipment and notify the webhook."""
    order_data = await db.get_order(self.transactions_session, order_id)
    if not order_data:
      raise ResourceNotFoundError("Order not found")
    events = (order_data.get("fulfillment") or {}).get("events") or []
    shipped = [e for e in events if e.get("type") == "shipped"]
    if not shipped or any(e.get("type") == "delivered" for e in events):
      return
    last = shipped[-1]
    event_id = f"evt_{uuid.uuid4()}"
    events.append(
      {
        "id": event_id,
        "type": "delivered",
        "occurred_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "line_items": last["line_items"],
        "tracking_number": last.get("tracking_number"),
        "tracking_url": last.get("tracking_url"),
        "carrier": last.get("carrier"),
      }
    )
    order_data["fulfillment"]["events"] = events
    await db.save_order(self.transactions_session, order_id, order_data)
    await self.transactions_session.commit()
    checkout_id = order_data.get("checkout_id")
    if checkout_id:
      checkout = await self._get_and_validate_checkout(checkout_id)
      await self._notify_webhook(checkout, "order_delivered")

  async def cancel_checkout(
    self,
    checkout_id: str,
    idempotency_key: str,
  ) -> Checkout:
    """Cancel a checkout session."""
    logger.info("Canceling checkout session %s", checkout_id)

    # Idempotency Check
    # Payload is empty for cancel usually.
    request_hash = self._compute_hash(
      "cancel_checkout", {}, resource_id=checkout_id
    )

    existing_record = await db.get_idempotency_record(
      self.transactions_session, idempotency_key
    )
    if existing_record:
      if existing_record.request_hash != request_hash:
        raise IdempotencyConflictError(
          "Idempotency key reused with different parameters"
        )
      return Checkout(**existing_record.response_body)

    # Log the request
    await db.log_request(
      self.transactions_session,
      method="POST",
      url=f"/checkout-sessions/{checkout_id}/cancel",
      checkout_id=checkout_id,
    )

    checkout = await self._get_and_validate_checkout(checkout_id)
    self._ensure_modifiable(checkout, "cancel")

    checkout.status = CheckoutStatus.CANCELED
    response_body = checkout.model_dump(
      mode="json", by_alias=True, exclude_none=True
    )

    await db.save_checkout(
      self.transactions_session,
      checkout_id,
      checkout.status,
      response_body,
    )

    # One commit that also resolves a CONCURRENT duplicate of this
    # key: a loser of the primary-key race is answered with the
    # winner's cached response, not a 500.
    cached = await db.commit_with_idempotency(
      self.transactions_session,
      idempotency_key,
      request_hash,
      200,
      response_body,
    )
    if cached is not None:
      return Checkout(**cached)
    return checkout

  async def get_order(
    self,
    order_id: str,
  ) -> dict[str, Any]:
    """Retrieve an order."""
    data = await db.get_order(self.transactions_session, order_id)
    if not data:
      raise ResourceNotFoundError("Order not found")
    return data

  async def update_order(
    self,
    order_id: str,
    order: dict[str, Any],
  ) -> dict[str, Any]:
    """Update an order."""
    # Verify existence
    await self.get_order(order_id)

    # Persist
    await db.save_order(
      self.transactions_session,
      order_id,
      order,
    )
    await self.transactions_session.commit()
    return order

  async def _get_and_validate_checkout(self, checkout_id: str) -> Checkout:
    """Retrieve a checkout session and validates its existence."""
    data = await db.get_checkout_session(self.transactions_session, checkout_id)
    if not data:
      raise ResourceNotFoundError("Checkout session not found")
    return Checkout(**data)

  def _ensure_modifiable(self, checkout: Checkout, action: str) -> None:
    """Ensure that the checkout is in a state that allows modification."""
    if checkout.status in [CheckoutStatus.COMPLETED, CheckoutStatus.CANCELED]:
      raise CheckoutNotModifiableError(
        f"Cannot {action} checkout in state '{checkout.status}'"
      )

  @staticmethod
  def _has_fulfillment_selection(checkout: Checkout) -> bool:
    """Return True if a fulfillment destination and option are selected."""
    if not checkout.fulfillment or not checkout.fulfillment.methods:
      return False
    for method in checkout.fulfillment.methods:
      if method.type == "shipping" and not method.selected_destination_id:
        continue
      if method.groups and any(g.selected_option_id for g in method.groups):
        return True
    return False

  def _readiness_status(self, checkout: Checkout) -> CheckoutStatus:
    """Status to report: ready only if Complete Checkout would accept it."""
    # UCP demo patch P8: an error message keeps the checkout incomplete.
    if any(getattr(m, "type", "") == "error" for m in (checkout.messages or [])):
      return CheckoutStatus.IN_PROGRESS
    if self._has_fulfillment_selection(checkout):
      return CheckoutStatus.READY_FOR_COMPLETE
    return CheckoutStatus.IN_PROGRESS

  async def _validate_inventory(
    self,
    checkout: Checkout,
  ) -> None:
    """Validate that all items in the checkout have sufficient stock."""
    # UCP demo patch P8: a business outcome is HTTP 200 (201 for a Create
    # that makes a checkout) with one messages[] entry (checkout-rest.md
    # "Business outcomes", spec AC-14). If no line item is in stock, the
    # Create makes no checkout (OutOfStockError -> error_response, HTTP 200).
    msgs = [m for m in (checkout.messages or []) if getattr(m, "code", "") != "out_of_stock"]
    in_stock = 0
    for idx, line in enumerate(checkout.line_items):
      product_id = line.item.id
      qty_avail = await db.get_inventory(self.transactions_session, product_id)
      if qty_avail is None or qty_avail < line.quantity:
        msgs.append(MessageError(
          type="error",
          code="out_of_stock",
          path=f"$.line_items[{idx}]",
          content=f"{line.item.title or product_id} is out of stock.",
          severity="recoverable",
        ))
      else:
        in_stock += 1
    checkout.messages = msgs or None
    if in_stock == 0 and self._creating:
      raise OutOfStockError("All requested items are currently out of stock", status_code=200)

  async def _enrich_and_recalculate(
    self,
    checkout: Checkout,
  ) -> None:
    """Enrich items from catalog and recalculate totals."""
    grand_total = 0
    # UCP demo patch P10: the business recomputes its messages each time.
    checkout.messages = None

    for line in checkout.line_items:
      product_id = line.item.id
      product = await db.get_product(self.products_session, product_id)
      if not product:
        raise InvalidRequestError(f"Product {product_id} not found")

      # Use authoritative price and title from DB
      line.item.price = product.price
      line.item.title = product.title

      base_amount = product.price * line.quantity
      line.totals = [
        TotalResponse(type="subtotal", amount=base_amount),
        TotalResponse(type="total", amount=base_amount),
      ]
      grand_total += base_amount

    checkout.totals = []
    # Always include subtotal for clarity when other costs might be added
    checkout.totals.append(TotalResponse(type="subtotal", amount=grand_total))

    # Fulfillment Logic
    if checkout.fulfillment and checkout.fulfillment.methods:
      # Fetch promotions once for the loop
      promotions = await db.get_active_promotions(self.products_session)

      for method in checkout.fulfillment.methods:
        # 1. Identify Destination and Calculate Options
        calculated_options = []
        if method.type == "shipping" and method.selected_destination_id:
          selected_dest = None
          if method.destinations:
            for dest in method.destinations:
              if dest.id == method.selected_destination_id:
                selected_dest = dest
                break

          if selected_dest:
            logger.info(
              "Calculating options for country: %s (dest_id: %s)",
              selected_dest.address_country,
              method.selected_destination_id,
            )
            # Log all available destinations for debugging
            if method.destinations:
              logger.info(
                "Available destinations in method %s: %s",
                method.id,
                [f"{d.id} ({d.address_country})" for d in method.destinations],
              )
            try:
              # Map ShippingDestination to PostalAddress for service call
              # Using strong types from SDK
              address_obj = PostalAddress(
                street_address=selected_dest.street_address,
                address_locality=selected_dest.address_locality,
                address_region=selected_dest.address_region,
                postal_code=selected_dest.postal_code,
                address_country=selected_dest.address_country,
              )

              # Get options from service
              # We calculate based on the items in this method/group
              # For simplicity, passing method's line_item_ids if available,
              # else all.
              all_li_ids = [li.id for li in checkout.line_items]
              target_li_ids = method.line_item_ids or all_li_ids

              # Map Line Item IDs to Product IDs for the service
              target_product_ids = []
              for li_uuid in target_li_ids:
                li = next(
                  (item for item in checkout.line_items if item.id == li_uuid),
                  None,
                )
                if li:
                  target_product_ids.append(li.item.id)

              calculated_options_resp = (
                await self.fulfillment_service.calculate_options(
                  self.transactions_session,
                  address_obj,
                  promotions=promotions,
                  subtotal=grand_total,
                  line_item_ids=target_product_ids,
                )
              )
              calculated_options = calculated_options_resp
              # UCP demo patch P10: no delivery option for the selected
              # address means that the business cannot deliver (AC-14).
              if not calculated_options:
                m_idx = checkout.fulfillment.methods.index(method)
                d_idx = method.destinations.index(selected_dest)
                checkout.messages = (checkout.messages or []) + [MessageError(
                  type="error",
                  code="address_undeliverable",
                  path=f"$.fulfillment.methods[{m_idx}].destinations[{d_idx}]",
                  content="We cannot deliver to this address. We deliver only in the United Kingdom.",
                  severity="recoverable",
                )]
            except (ValueError, TypeError) as e:
              logging.error("Failed to calculate options: %s", e)

        # 2. Generate or Update Groups
        if method.selected_destination_id and not method.groups:
          # Generate new group
          group = FulfillmentGroup(
            id=f"group_{uuid.uuid4()}",
            line_item_ids=method.line_item_ids,
            options=calculated_options,
          )
          method.groups = [group]
        elif method.groups:
          # Update existing groups with fresh options
          for group in method.groups:
            # Refresh options if they changed due to address/item update
            if calculated_options:
              group.options = calculated_options

            # Recalculate Totals based on Group Selection
            if group.selected_option_id and group.options:
              selected_opt = next(
                (o for o in group.options if o.id == group.selected_option_id),
                None,
              )
              if selected_opt:
                # Avoid double counting if already added.
                # Multiple groups can have costs.
                # We assume each group adds to the total.
                opt_total = next(
                  (t.amount for t in selected_opt.totals if t.type == "total"),
                  0,
                )
                grand_total += opt_total
                checkout.totals.append(
                  TotalResponse(type="fulfillment", amount=opt_total)
                )

    # Discount Logic
    if not checkout.discounts:
      checkout.discounts = DiscountsObject()

    # The server is the authority for applied discounts (discount.json marks
    # applied as ucp_request:"omit"). _recalculate_totals runs on every
    # create/update, and a reloaded checkout already carries the applied
    # entries from the previous response. Rebuild the list from scratch,
    # mirroring how `totals` is rebuilt above, so entries do not accumulate
    # on every recalculation (e.g. an update that omits the discounts field).
    checkout.discounts.applied = None

    if checkout.discounts.codes:
      # Batch fetch discounts to avoid N+1 queries
      discounts = await db.get_discounts_by_codes(
        self.transactions_session, checkout.discounts.codes
      )
      # Create a map for easy lookup by code (preserving request order if
      # needed)
      # Codes are matched case-insensitively by business (discount.md);
      # the applied entry echoes the canonical stored code.
      discount_map = {d.code.upper(): d for d in discounts}

      for code in checkout.discounts.codes:
        discount_obj = discount_map.get(code.upper())
        if discount_obj:
          discount_amount = 0
          if discount_obj.type == "percentage":
            discount_amount = int(grand_total * (discount_obj.value / 100))
          elif discount_obj.type == "fixed_amount":
            discount_amount = discount_obj.value

          if discount_amount > 0:
            grand_total -= discount_amount
            if checkout.discounts.applied is None:
              checkout.discounts.applied = []
            checkout.discounts.applied.append(
              AppliedDiscount(
                code=discount_obj.code,
                title=discount_obj.description,
                amount=discount_amount,
                allocations=[
                  Allocation(
                    path="$.totals[?(@.type=='subtotal')]",
                    amount=discount_amount,
                  )
                ],
              )
            )
            # totals[] carries the signed effect on the receipt: negative for
            # a discount (total.json exclusiveMaximum: 0). applied[].amount
            # above stays positive as the magnitude (discount.md).
            checkout.totals.append(
              TotalResponse(type="discount", amount=-discount_amount)
            )

    checkout.totals.append(TotalResponse(type="total", amount=grand_total))

  async def _process_payment(
    self, payment: PaymentCreateRequest, checkout: Checkout | None = None
  ) -> None:
    """Validate and process payment instruments."""
    instruments = payment.instruments
    if not instruments:
      raise InvalidRequestError("Missing payment instruments")

    # Defensive validation: this sample has no split-payments support and
    # processes only instruments[0], so reject multi-instrument submissions
    # instead of silently ignoring the extra instruments behind a 200
    # "completed" a platform could misread as "all instruments processed".
    # Version note: the sample advertises UCP 2026-04-08 (ucp-sdk 0.4.6),
    # which imposes no normative instrument-cardinality rule; the
    # Instrument Cardinality MUST ("exactly one payment instrument unless
    # the dev.ucp.common.payment.split_payments capability is active",
    # rejected with payment_failed) was introduced by spec PR #409 and
    # first released in spec v2026-08-25. This guard is a
    # defensive-validation / newer-spec-alignment improvement, NOT
    # enforcement of a 2026-04-08 requirement.
    if len(instruments) > 1:
      raise PaymentFailedError(
        "Multiple payment instruments submitted, but split payments "
        "are not supported",
        code="payment_failed",
      )

    # In 01-23 SDK, selected_instrument_id is removed.
    # We process the first provided instrument.
    selected_instrument = instruments[0]

    handler_id = getattr(selected_instrument, "handler_id", None)
    if not handler_id:
      raise InvalidRequestError("Missing handler_id in instrument")
    # UCP demo patch P15 (AC-32, FR-11): the business validates handler_id.
    # Only a handler that this business declared in its profile is accepted.
    # A rejected request makes no PSP call.
    declared = {
      h.get("id")
      for hs in (config._get_profile()["ucp"].get("payment_handlers") or {}).values()
      for h in hs
    }
    if handler_id not in declared:
      raise InvalidRequestError("The payment handler_id is not declared")

    credential = getattr(selected_instrument, "credential", None)
    if not credential:
      raise InvalidRequestError("Missing credentials in instrument")

    # If it's a RootModel (like PaymentCredential), unwrap it to get the actual
    # credential data
    if hasattr(credential, "root"):
      credential = credential.root

    token = None

    if credential.type == "card":
      # Handle card details
      number = getattr(credential, "number", "unknown")
      if number is not None and not isinstance(number, str):
        raise InvalidRequestError("Card number must be a string")
      logger.info(
        "Processing card payment for card ending in %s",
        number[-4:] if number else "unknown",
      )
      return
    elif credential.type == "token":
      token = getattr(credential, "token", None)
    elif isinstance(credential, dict):
      type_val = credential.get("type")
      if type_val == "card":
        number = credential.get("number", "unknown")
        if number is not None and not isinstance(number, str):
          raise InvalidRequestError("Card number must be a string")
        logger.info(
          "Processing card payment for card ending in %s",
          number[-4:] if number else "unknown",
        )
        return
      elif type_val == "token":
        token = credential.get("token")
    elif credential.type in ("PAYMENT_GATEWAY", "DIRECT"):
      # UCP demo patch P15: the com.google.pay credential type is the Google
      # Pay tokenizationData.type. It is not unknown. The token is not logged.
      token = getattr(credential, "token", None)
    else:
      # Fallback for unknown types if model validation allowed extras or
      # different types
      logger.warning("Unknown credential type: %s", type(credential))
      token = getattr(credential, "token", None)

    if handler_id == "mock_payment_handler":
      if token == "success_token":
        return  # Success
      elif token == "fail_token":
        # UCP demo patch P15 (T-105): one lower-case code, HTTP 200.
        raise PaymentFailedError("Payment Failed: Insufficient Funds (Mock)")
      elif token == "fraud_token":
        raise PaymentFailedError("Payment Failed: Fraud Detected (Mock)")
      else:
        raise PaymentFailedError("Unknown mock token")
    elif handler_id == "google_pay" or handler_id.startswith("gpay"):
      # UCP demo patch D6 (02-design 17.2 defect 6): the sample accepted any
      # token here. A real handler goes to the payment processor hook. The
      # default hook fails closed until the PSP mock (slice S4).
      config.PAYMENT_AUTHORIZER(handler_id, credential, checkout)
      return
    elif handler_id == "shop_pay":
      # For shop_pay, we expect a 'shop_token' credential type.
      # Since we don't have a real backend, we accept it if present.
      # The token value validation logic is similar to mock_payment_handler
      # for this test. Or just accept any token.
      return
    else:
      # Unknown handler
      raise InvalidRequestError(f"Unsupported payment handler: {handler_id}")
