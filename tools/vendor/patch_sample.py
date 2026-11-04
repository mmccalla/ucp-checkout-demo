"""Apply the demo patches to the vendored samples copy (rest/python/server at e7c9c12).

Run it one time on a clean copy. Each patch must match exactly one place, else it stops.
The patch list and the reason for each patch are in business/UPSTREAM.md.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
S = ROOT / "business" / "src" / "ucp_sample_server"


CHANGED: set[str] = set()
NOTICE = (
    "# Modified by the UCP demo in 2026 (Apache-2.0 section 4(b)). The changes are the\n"
    '# comments marked "UCP demo patch". See business/UPSTREAM.md.\n'
)


def sub(rel: str, old: str, new: str, count: int = 1) -> None:
    CHANGED.add(rel)
    p = S / rel
    t = p.read_text()
    n = t.count(old)
    if n != count:
        sys.exit(f"patch mismatch in {rel}: found {n}, expected {count}: {old[:70]!r}")
    p.write_text(t.replace(old, new))


# ---------------------------------------------------------------- config.py
sub(
    "config.py",
    "\n_PROFILE_CACHE = None\n",
    "\n# UCP demo patch P1: typed cache (spec T-103, code that we write).\n"
    "_PROFILE_CACHE: dict[str, Any] | None = None\n",
)
sub(
    "config.py",
    'DEFAULT_CURRENCY = "USD"',
    '# UCP demo patch P2: the demo shop trades in GBP (spec T-70).\nDEFAULT_CURRENCY = "GBP"',
)
sub(
    "config.py",
    """def _get_profile() -> dict:
  global _PROFILE_CACHE
  if _PROFILE_CACHE:
    return _PROFILE_CACHE

  current_dir = Path(__file__).resolve().parent
  profile_path = current_dir / "routes" / "discovery_profile.json"

  with profile_path.open(encoding="utf-8") as f:
    template = f.read()

  # Resolve the request independent placeholder before parsing, so callers
  # such as get_payment_handlers never hand a template value to a platform.
  _PROFILE_CACHE = json.loads(template.replace("{{SHOP_ID}}", SHOP_ID))
  return _PROFILE_CACHE
""",
    '''# UCP demo patch P1 (02-design 17.2 defects 1 to 5): the sample template
# routes/discovery_profile.json had a wrong `google_pay` handler entry, handler
# URLs that return 404, camelCase fields, arrays where the schema has objects,
# and no `environment`. The template file is removed. The host app
# (business_app) gives the profile that it serves at /.well-known/ucp, after
# the S1 checks (AC-106), through set_profile(). There is no file fallback.
def set_profile(profile: dict[str, Any]) -> None:
  """Set the served business profile (called by the host app at start)."""
  global _PROFILE_CACHE
  _PROFILE_CACHE = profile


def _get_profile() -> dict[str, Any]:
  if not _PROFILE_CACHE:
    raise RuntimeError("UCP demo patch P1: the host app must call set_profile()")
  return _PROFILE_CACHE


def get_response_capabilities() -> dict[str, list[dict[str, str]]]:
  """Return the capabilities of the served profile (UCP demo patch P1)."""
  caps: dict[str, list[dict[str, str]]] = _get_profile()["ucp"].get("capabilities", {})
  return {
    name: [{"version": e["version"]} for e in entries]
    for name, entries in caps.items()
    if name != "dev.ucp.shopping.order"
  }


# UCP demo patch P4: hooks that the host app sets.
# PAYMENT_AUTHORIZER(handler_id, credential) authorizes a payment for a real
# handler. The default fails closed (02-design 17.2 defect 6).
# PROFILE_RESOLVER(ucp_agent) returns the platform profile that the host app
# fetched under its fetch rules, or None. There is no second, unchecked fetch.
# LINKS is the list of checkout links (AC-109).
def _fail_closed(handler_id: str, credential: object) -> None:
  del credential
  raise RuntimeError(f"no payment authorizer for handler {handler_id}")


PAYMENT_AUTHORIZER: Any = _fail_closed
PROFILE_RESOLVER: Any = None
LINKS: list[dict[str, str]] = []
''',
)
sub(
    "config.py",
    "import contextlib\nimport json\nfrom pathlib import Path\nimport uuid\n",
    "import contextlib\nfrom typing import Any\nimport uuid\n",
)
# P3 (defect 7): enforce request signatures by default (spec T-04).
sub(
    "config.py",
    """    "require_signatures",
    False,""",
    """    "require_signatures",
    # UCP demo patch P3 (02-design 17.2 defect 7, spec T-04): on by default.
    True,""",
)

# ----------------------------------------------------------- dependencies.py
sub(
    "dependencies.py",
    """  headers = {k.lower(): v for k, v in request.headers.items()}
  enforcing = config.FLAGS.require_signatures
""",
    """  # UCP demo patch P5: the host app (business_app.gate) verifies the RFC 9421
  # signature before routing, with keys from the platform profile that it
  # fetched under its own fetch rules. Do not verify a second time.
  if getattr(request.state, "ucp_signature_checked", False):
    return
  headers = {k.lower(): v for k, v in request.headers.items()}
  enforcing = config.FLAGS.require_signatures
""",
)

# ------------------------------------------------ routes/ucp_implementation.py
sub(
    "routes/ucp_implementation.py",
    '''  """Extract webhook URL from UCP-Agent header."""
  match = re.search(r'profile="([^"]+)"', ucp_agent)
  if not match:
    return None
''',
    '''  """Extract webhook URL from UCP-Agent header."""
  # UCP demo patch P6: use the platform profile that the host app fetched
  # under its fetch rules (HTTPS, no redirects, address check). The original
  # code below made a second fetch without those checks. With no resolver,
  # return None (fail closed).
  if sample_config.PROFILE_RESOLVER is None:
    return None
  resolved = sample_config.PROFILE_RESOLVER(ucp_agent)
  if not isinstance(resolved, dict):
    return None
  for c_list in resolved.get("ucp", {}).get("capabilities", {}).values():
    for cap in c_list if isinstance(c_list, list) else []:
      cfg = cap.get("config", {}) if isinstance(cap, dict) else {}
      if isinstance(cfg, dict) and cfg.get("webhook_url"):
        try:
          UcpConfig(webhook_url=cfg["webhook_url"])
        except ValidationError:
          return None
        return str(cfg["webhook_url"])
  return None
  match = re.search(r'profile="([^"]+)"', ucp_agent)  # unreachable (P6)
  if not match:
    return None
''',
)
sub(
    "routes/ucp_implementation.py",
    "import logging\nimport re\n",
    "import logging\nimport re\n\nimport config as sample_config  # UCP demo patch P6\n",
)

# --------------------------------------------------------------- models.py
sub(
    "models.py",
    """  fulfillment: Fulfillment | None = None
  discounts: DiscountsObject | None = None
  buyer_consent: Any | None = None


UnifiedCheckout.model_rebuild()""",
    """  # UCP demo patch P12 (02-design 17.2 defect 8, spec T-05): the update
  # request used the response model `Fulfillment`, where
  # `groups[].line_item_ids` is required. The schema removes that field from
  # requests (fulfillment_group.json line 19, "ucp_request": "omit") and
  # requires `methods[].line_item_ids` on update (fulfillment_method.json
  # line 25). The request model `FulfillmentUpdateRequest` (ucp-sdk 0.4.6)
  # follows the schema.
  fulfillment: FulfillmentUpdateRequest | None = None
  discounts: DiscountsObject | None = None
  buyer_consent: Any | None = None


UnifiedCheckout.model_rebuild()""",
)
sub(
    "models.py",
    """from ucp_sdk.models.schemas.shopping.types.fulfillment_create_request import (
  FulfillmentCreateRequest,
)
""",
    """from ucp_sdk.models.schemas.shopping.types.fulfillment_create_request import (
  FulfillmentCreateRequest,
)
# UCP demo patch P12. ucp-sdk 0.4.6 has no py.typed marker (ADR 0007, T-103 item 5).
from ucp_sdk.models.schemas.shopping.types.fulfillment_update_request import (  # type: ignore[import-untyped]
  FulfillmentUpdateRequest,
)
""",
)
sub(
    "models.py",
    "  Checkout as FulfillmentCheckout,\n  Fulfillment,\n)",
    "  Checkout as FulfillmentCheckout,\n)",
)

# ------------------------------------------------ services/checkout_service.py
CS = "services/checkout_service.py"
# P7: unknown root fields are accepted but not copied into the checkout (T-86, AC-38).
sub(
    CS,
    """        "ap2",
      }
    )
""",
    """        "ap2",
      }
    )
    # UCP demo patch P7: accept unknown root fields but do not show them
    # (spec T-86). A field such as `risk_signals` is logged by the host app
    # and is not copied into the checkout (AC-38).
    for extra in list((checkout_req.model_extra or {}).keys()):
      checkout_data.pop(extra, None)
""",
)
# P1: capabilities and links in the response.
sub(
    CS,
    """        capabilities={
          "dev.ucp.shopping.checkout": [
            Response(
              name="dev.ucp.shopping.checkout",
              version=config.get_server_version(),
            )
          ]
        },
        payment_handlers=config.get_payment_handlers(),
      ),""",
    """        # UCP demo patch P1: the capabilities that the business serves.
        capabilities=config.get_response_capabilities(),
        payment_handlers=config.get_payment_handlers(),
      ),""",
)
sub(CS, "      links=[],\n", "      links=list(config.LINKS),  # UCP demo patch P10 (AC-109)\n")
# P8: business outcomes are messages (AC-14), not exceptions.
sub(
    CS,
    '''    """Validate that all items in the checkout have sufficient stock."""
    for line in checkout.line_items:
      product_id = line.item.id
      qty_avail = await db.get_inventory(self.transactions_session, product_id)
      if qty_avail is None or qty_avail < line.quantity:
        raise OutOfStockError(f"Insufficient stock for item {product_id}")
''',
    '''    """Validate that all items in the checkout have sufficient stock."""
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
''',
)
sub(
    CS,
    '''    """Create a new checkout session."""
    logger.info("Creating checkout session")
''',
    '''    """Create a new checkout session."""
    logger.info("Creating checkout session")
    self._creating = True  # UCP demo patch P8
''',
)
sub(
    CS,
    '''    """Update a checkout session."""
    logger.info("Updating checkout session %s", checkout_id)
''',
    '''    """Update a checkout session."""
    logger.info("Updating checkout session %s", checkout_id)
    self._creating = False  # UCP demo patch P8
''',
)
sub(
    CS,
    "    self.fulfillment_service = fulfillment_service\n",
    "    self.fulfillment_service = fulfillment_service\n    self._creating = False  # UCP demo patch P8\n",
)
# P10: address check (AC-14 address_undeliverable).
sub(
    CS,
    """              calculated_options = calculated_options_resp
            except (ValueError, TypeError) as e:""",
    """              calculated_options = calculated_options_resp
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
            except (ValueError, TypeError) as e:""",
)
sub(
    CS,
    '''    """Enrich items from catalog and recalculate totals."""
    grand_total = 0
''',
    '''    """Enrich items from catalog and recalculate totals."""
    grand_total = 0
    # UCP demo patch P10: the business recomputes its messages each time.
    checkout.messages = None
''',
)
# P8/P10: an error message blocks ready_for_complete.
sub(
    CS,
    '''    """Status to report: ready only if Complete Checkout would accept it."""
    if self._has_fulfillment_selection(checkout):''',
    '''    """Status to report: ready only if Complete Checkout would accept it."""
    # UCP demo patch P8: an error message keeps the checkout incomplete.
    if any(getattr(m, "type", "") == "error" for m in (checkout.messages or [])):
      return CheckoutStatus.IN_PROGRESS
    if self._has_fulfillment_selection(checkout):''',
)
# D6: google_pay accepted any token.
sub(
    CS,
    """    elif handler_id == "google_pay":
      # Accept any token for now, or specific ones
      return""",
    """    elif handler_id == "google_pay" or handler_id.startswith("gpay"):
      # UCP demo patch D6 (02-design 17.2 defect 6): the sample accepted any
      # token here. A real handler goes to the payment processor hook. The
      # default hook fails closed until the PSP mock (slice S4).
      config.PAYMENT_AUTHORIZER(handler_id, credential)
      return""",
)
sub(
    CS,
    "from ucp_sdk.models.schemas.shopping.types.fulfillment_group import (\n",
    "# UCP demo patch P8. ucp-sdk 0.4.6 has no py.typed marker (ADR 0007, T-103 item 5).\n"
    "from ucp_sdk.models.schemas.shopping.types.message_error import MessageError  # type: ignore[import-untyped]\n"
    "from ucp_sdk.models.schemas.shopping.types.fulfillment_group import (\n",
)

# P14: a client-sent group `line_item_ids` or `options` is ignored, never echoed, and logged
# by field path only (spec v1.1.4 T-104, ACCEPTED).
sub(
    CS,
    """          if m_req.groups:
            for g_req in m_req.groups:
              g_id = getattr(g_req, "id", None) or f"group_{uuid.uuid4()}"
              g_li_ids = getattr(g_req, "line_item_ids", None) or [
                li.id for li in existing.line_items
              ]
""",
    """          if m_req.groups:
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
""",
)

# ---------------------------------------------------------------- P15 (spec v1.1.4 T-105, S4)
# P15: payment failure on Complete is a business outcome (T-105). HTTP 200, the checkout body,
# status unchanged (ready_for_complete), no order, one recoverable `payment_failed` message
# with neutral content. The failed result is stored for the Idempotency-Key, so a replay makes
# no second PSP call. The fulfillment and the stock are checked before the charge. The handler_id
# must be declared (AC-32). Google Pay credential types are known (no "Unknown credential type").
sub(
    "exceptions.py",
    '''    code: str = "PAYMENT_FAILED",
    status_code: int = 402,
  ):
    """Initialize PaymentFailedError."""
    super().__init__(
      message,
      code=code,
      status_code=status_code,
      severity=ErrorSeverity.REQUIRES_BUYER_INPUT,
    )''',
    '''    code: str = "payment_failed",
    status_code: int = 200,
  ):
    """Initialize PaymentFailedError."""
    # UCP demo patch P15 (spec T-105): a payment failure is a business outcome,
    # HTTP 200 with the checkout body. Lower-case code, severity recoverable.
    # The message text is for the log only. The response content is neutral.
    super().__init__(
      message,
      code=code,
      status_code=status_code,
      severity=ErrorSeverity.RECOVERABLE,
    )''',
)
sub(
    "config.py",
    """# PAYMENT_AUTHORIZER(handler_id, credential) authorizes a payment for a real""",
    """# PAYMENT_AUTHORIZER(handler_id, credential, checkout) authorizes a payment for a real""",
)
sub(
    "config.py",
    """def _fail_closed(handler_id: str, credential: object) -> None:
  del credential""",
    """def _fail_closed(handler_id: str, credential: object, checkout: object) -> None:
  del credential, checkout""",
)
sub(
    "services/checkout_service.py",
    """    # Process Payment
    await self._process_payment(payment)

    # Validate Fulfillment (Required for completion in this implementation)
    if not self._has_fulfillment_selection(checkout):
      raise InvalidRequestError(
        "Fulfillment address and option must be selected before completion."
      )
""",
    """    # UCP demo patch P15 (spec T-105): check the fulfillment and the stock
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
""",
)
sub(
    "services/checkout_service.py",
    """  async def _notify_webhook(self, checkout: Checkout, event_type: str) -> None:""",
    '''  async def _payment_failed(
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

  async def _notify_webhook(self, checkout: Checkout, event_type: str) -> None:''',
)
sub(
    "services/checkout_service.py",
    """  async def _process_payment(self, payment: PaymentCreateRequest) -> None:""",
    """  async def _process_payment(
    self, payment: PaymentCreateRequest, checkout: Checkout | None = None
  ) -> None:""",
)
sub(
    "services/checkout_service.py",
    """    handler_id = getattr(selected_instrument, "handler_id", None)
    if not handler_id:
      raise InvalidRequestError("Missing handler_id in instrument")
""",
    """    handler_id = getattr(selected_instrument, "handler_id", None)
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
""",
)
sub(
    "services/checkout_service.py",
    """      elif type_val == "token":
        token = credential.get("token")
    else:""",
    """      elif type_val == "token":
        token = credential.get("token")
    elif credential.type in ("PAYMENT_GATEWAY", "DIRECT"):
      # UCP demo patch P15: the com.google.pay credential type is the Google
      # Pay tokenizationData.type. It is not unknown. The token is not logged.
      token = getattr(credential, "token", None)
    else:""",
)
sub(
    "services/checkout_service.py",
    """        raise PaymentFailedError(
          "Payment Failed: Insufficient Funds (Mock)",
          code="INSUFFICIENT_FUNDS",
        )""",
    """        # UCP demo patch P15 (T-105): one lower-case code, HTTP 200.
        raise PaymentFailedError("Payment Failed: Insufficient Funds (Mock)")""",
)
sub(
    "services/checkout_service.py",
    """        raise PaymentFailedError(
          "Payment Failed: Fraud Detected (Mock)",
          code="FRAUD_DETECTED",
          status_code=403,
        )""",
    """        raise PaymentFailedError("Payment Failed: Fraud Detected (Mock)")""",
)
sub(
    "services/checkout_service.py",
    """        raise PaymentFailedError(
          f"Unknown mock token: {token}", code="UNKNOWN_TOKEN"
        )""",
    """        raise PaymentFailedError("Unknown mock token")""",
)
sub(
    "services/checkout_service.py",
    """      config.PAYMENT_AUTHORIZER(handler_id, credential)""",
    """      config.PAYMENT_AUTHORIZER(handler_id, credential, checkout)""",
)

sub(
    "services/checkout_service.py",
    """      checkout.order = OrderConfirmation(
        id=order_id, permalink_url=order_permalink_url
      )
      response_body = checkout.model_dump(
        mode="json", by_alias=True, exclude_none=True
      )
""",
    """      checkout.order = OrderConfirmation(
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
""",
)

sub(
    "services/checkout_service.py",
    """      await self._notify_webhook(checkout, "order_placed")

    except Exception as e:
      await self.transactions_session.rollback()
      raise e

    return checkout
""",
    """      await self._notify_webhook(checkout, "order_placed")

    except Exception as e:
      await self.transactions_session.rollback()
      raise e

    # UCP demo patch P15 (AC-112, AC-46): return the stored response body, so a
    # replay with the same key gets the same body.
    return Checkout(**response_body)
""",
)

sub(
    "services/checkout_service.py",
    """      url=f"/checkout-sessions/{checkout_id}/complete",
      checkout_id=checkout_id,
      payload=combined_data,
    )""",
    """      url=f"/checkout-sessions/{checkout_id}/complete",
      checkout_id=checkout_id,
      # UCP demo patch P15 (AC-54): the request log keeps no credential.
      payload=_without_credentials(combined_data),
    )""",
)
sub(
    "services/checkout_service.py",
    """class CheckoutService:""",
    '''def _without_credentials(data: dict[str, Any]) -> dict[str, Any]:
  """UCP demo patch P15 (AC-54): a copy with each instrument credential masked."""
  out: dict[str, Any] = json.loads(json.dumps(data))
  parts = [out.get("payment"), (out.get("checkout_complete") or {}).get("payment")]
  for part in parts:
    for inst in (part or {}).get("instruments") or []:
      if isinstance(inst, dict) and "credential" in inst:
        inst["credential"] = "[REDACTED]"
  return out


class CheckoutService:''',
)

sub(
    "config.py",
    "PAYMENT_AUTHORIZER: Any = _fail_closed\n",
    "PAYMENT_AUTHORIZER: Any = _fail_closed\n"
    "\n"
    "# UCP demo patch P15 (tests only): an httpx.AsyncBaseTransport for webhook deliveries.\n"
    "# None uses the network. Tests set it, so no test delivery leaves the process.\n"
    "WEBHOOK_TRANSPORT: Any = None\n",
)
sub(
    "services/checkout_service.py",
    "      async with httpx.AsyncClient() as client:\n        for attempt in range(1, attempts + 1):",
    "      # UCP demo patch P15: config.WEBHOOK_TRANSPORT is a test seam.\n"
    "      async with httpx.AsyncClient(transport=config.WEBHOOK_TRANSPORT) as client:\n"
    "        for attempt in range(1, attempts + 1):",
)

# ------------------------------------------------------------------ P16 (S4 webhooks)
# UCP demo patch P16 (S4, AC-65, AC-72, AC-74, T-42). The host app sets the seams.
sub(
    "config.py",
    "WEBHOOK_TRANSPORT: Any = None\n",
    "WEBHOOK_TRANSPORT: Any = None\n"
    "\n"
    "# UCP demo patch P16: seams that the host app sets (S4).\n"
    "# WEBHOOK_SIGNING_KEY: (private_key, kid) of the key in the published profile (AC-65).\n"
    "# WEBHOOK_PROFILE_URL: the public profile URL for UCP-Agent. The app is behind a proxy.\n"
    "# WEBHOOK_DEAD_LETTER: callable(event_type, webhook_id, failure) after the last failure.\n"
    "WEBHOOK_SIGNING_KEY: Any = None\n"
    "WEBHOOK_PROFILE_URL: Any = None\n"
    "WEBHOOK_DEAD_LETTER: Any = None\n",
)
sub(
    "webhook_signer.py",
    "  global _SIGNER\n  if _SIGNER is None:\n",
    "  global _SIGNER\n"
    "  # UCP demo patch P16: sign with the key that the profile publishes (AC-65).\n"
    "  if config.WEBHOOK_SIGNING_KEY is not None:\n"
    "    return tuple(config.WEBHOOK_SIGNING_KEY)\n"
    "  if _SIGNER is None:\n",
)
sub(
    "services/checkout_service.py",
    '      "UCP-Agent": f\'profile="{self.base_url}/.well-known/ucp"\',\n',
    "      # UCP demo patch P16: the public profile URL. request.base_url is the proxy\n"
    "      # upstream (http://127.0.0.1:8201/), which a platform cannot fetch.\n"
    '      "UCP-Agent": \'profile="%s"\'\n'
    '      % (config.WEBHOOK_PROFILE_URL or f"{self.base_url}/.well-known/ucp"),\n',
)
sub(
    "services/checkout_service.py",
    "import logging\nfrom typing import Any\n",
    "import logging\nimport random\nfrom typing import Any\n",
)
sub(
    "services/checkout_service.py",
    "            delay = backoff * (2 ** (attempt - 1))\n",
    "            # UCP demo patch P16: add jitter (T-42, 0.5 s and 1 s plus jitter).\n"
    "            delay = backoff * (2 ** (attempt - 1)) + random.uniform(0, backoff / 5)\n",
)
sub(
    "services/checkout_service.py",
    "                webhook_url,\n                failure,\n              )\n              return\n",
    "                webhook_url,\n                failure,\n              )\n"
    "              # UCP demo patch P16: dead letter (T-42).\n"
    "              if config.WEBHOOK_DEAD_LETTER is not None:\n"
    "                config.WEBHOOK_DEAD_LETTER(event_type, webhook_id, failure)\n"
    "              return\n",
)
sub(
    "services/checkout_service.py",
    "          attempts,\n          failure,\n        )\n    except Exception as e:",
    "          attempts,\n          failure,\n        )\n"
    "        # UCP demo patch P16: dead letter (T-42).\n"
    "        if config.WEBHOOK_DEAD_LETTER is not None:\n"
    "          config.WEBHOOK_DEAD_LETTER(event_type, webhook_id, failure)\n"
    "    except Exception as e:",
)
sub(
    "services/checkout_service.py",
    '        "type": "shipped",\n        "occurred_at": occurred_at,\n'
    '        "line_items": line_items,\n      }\n',
    '        "type": "shipped",\n        "occurred_at": occurred_at,\n'
    '        "line_items": line_items,\n'
    "        # UCP demo patch P16: fulfillment_event.json needs tracking_number and\n"
    "        # tracking_url when type != processing. The values are fake (AC-74).\n"
    '        "tracking_number": "SIM-" + event_id[4:12].upper(),\n'
    '        "tracking_url": f"https://tracking.invalid/{event_id}",\n'
    '        "carrier": "Simulated carrier",\n'
    "      }\n",
)
sub(
    "services/checkout_service.py",
    '      await self._notify_webhook(checkout, "order_shipped")\n',
    '      await self._notify_webhook(checkout, "order_shipped")\n'
    "\n"
    "  # UCP demo patch P16: simulated delivery (AC-74, T-23). The sample has none.\n"
    "  async def deliver_order(self, order_id: str) -> None:\n"
    '    """Simulate delivery of the last shipment and notify the webhook."""\n'
    "    order_data = await db.get_order(self.transactions_session, order_id)\n"
    "    if not order_data:\n"
    '      raise ResourceNotFoundError("Order not found")\n'
    '    events = (order_data.get("fulfillment") or {}).get("events") or []\n'
    '    shipped = [e for e in events if e.get("type") == "shipped"]\n'
    '    if not shipped or any(e.get("type") == "delivered" for e in events):\n'
    "      return\n"
    "    last = shipped[-1]\n"
    '    event_id = f"evt_{uuid.uuid4()}"\n'
    "    events.append(\n"
    "      {\n"
    '        "id": event_id,\n'
    '        "type": "delivered",\n'
    '        "occurred_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),\n'
    '        "line_items": last["line_items"],\n'
    '        "tracking_number": last.get("tracking_number"),\n'
    '        "tracking_url": last.get("tracking_url"),\n'
    '        "carrier": last.get("carrier"),\n'
    "      }\n"
    "    )\n"
    '    order_data["fulfillment"]["events"] = events\n'
    "    await db.save_order(self.transactions_session, order_id, order_data)\n"
    "    await self.transactions_session.commit()\n"
    '    checkout_id = order_data.get("checkout_id")\n'
    "    if checkout_id:\n"
    "      checkout = await self._get_and_validate_checkout(checkout_id)\n"
    '      await self._notify_webhook(checkout, "order_delivered")\n',
)

# ---------------------------------------------------------------- server.py
sub(
    "server.py",
    'uvicorn.run(app, host="0.0.0.0", port=config.FLAGS.port)',
    '# UCP demo patch P9: loopback only (spec DM-26).\n  uvicorn.run(app, host="127.0.0.1", port=config.FLAGS.port)',
)

# ------------------------------------------------- routes/discovery_profile.json
(S / "routes" / "discovery_profile.json").unlink()

# ------------------------------------------------------------------ README.md
# UCP demo patch P13: the sample README shows the same wrong Google Pay handler entry as the
# removed template (version 2026-04-08 URLs; 02-design 17.2 defects 1 to 5). The demo pins
# handler 2026-01-23 (AC-118). The README is not code. business/UPSTREAM.md links the original.
(S / "README.md").unlink()
# ------------------------------------------------------------------ P17 (httpx2)
# UCP demo patch P17: every httpx name becomes httpx2 (the pydantic fork, same API). The host
# app and the tests use httpx2 only. Each `sub` matches an exact count. Usage first, then the import.
for _rel, _dots, _comment in [
    ("config.py", 1, None),
    ("idempotency_race_test.py", 6, ("through httpx's ASGI", "through httpx2's ASGI")),
    ("integration_test.py", 3, ("with httpx stubbed", "with httpx2 stubbed")),
    ("routes/ucp_implementation.py", 2, None),
    ("services/checkout_service.py", 2, None),
    ("ucp_signing.py", 2, None),
    ("ucp_signing_test.py", 11, ("a mocked httpx transport", "a mocked httpx2 transport")),
]:
    sub(_rel, "httpx.", "httpx2.", _dots)
    if _comment:
        sub(_rel, *_comment)
    if _rel != "config.py":
        sub(
            _rel,
            "\nimport httpx\n",
            "\nimport httpx2  # UCP demo patch P17: httpx2 replaces httpx\n",
        )
sub("pyproject.toml", '"httpx>=0.26.0"', '"httpx2>=2.16.0"', 2)

print("patches applied")


# ------------------------------------------------- change notice in each changed file
def add_notice(rel: str) -> None:
    p = S / rel
    lines = p.read_text().splitlines(keepends=True)
    i = 0
    while i < len(lines) and lines[i].startswith("#"):
        i += 1  # after the Apache-2.0 header comment block
    p.write_text("".join(lines[:i]) + NOTICE + "".join(lines[i:]))


for rel in sorted(CHANGED):
    add_notice(rel)
print("changed files:", ", ".join(sorted(CHANGED)))
