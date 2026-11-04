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

"""Shared configuration and startup logic for UCP servers."""

import contextlib
from typing import Any
import uuid
from absl import flags
import db
from fastapi import FastAPI

FLAGS = flags.FLAGS

# UCP demo patch P1: typed cache (spec T-103, code that we write).
_PROFILE_CACHE: dict[str, Any] | None = None

# The shop id this server instance advertises. discovery_profile.json is a
# template, and this is the one value substituted into it that does not depend
# on the request, so it is resolved here where every reader of the profile sees
# the same value. routes/discovery.py substitutes {{ENDPOINT}} per request.
SHOP_ID = str(uuid.uuid4())

# checkout.json annotates `currency` with `ucp_request: omit` and describes
# it as "reflecting the merchant's market determination ... buyers provide
# signals, merchants determine currency". A conformant platform therefore does
# not send it, and the generated CheckoutCreateRequest has no such field. This
# sample serves a single market, so the determination is a constant.
# UCP demo patch P2: the demo shop trades in GBP (spec T-70).
DEFAULT_CURRENCY = "GBP"


def get_default_currency() -> str:
  """Return the currency this business trades in."""
  return DEFAULT_CURRENCY


# UCP demo patch P1 (02-design 17.2 defects 1 to 5): the sample template
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
# PAYMENT_AUTHORIZER(handler_id, credential, checkout) authorizes a payment for a real
# handler. The default fails closed (02-design 17.2 defect 6).
# PROFILE_RESOLVER(ucp_agent) returns the platform profile that the host app
# fetched under its fetch rules, or None. There is no second, unchecked fetch.
# LINKS is the list of checkout links (AC-109).
def _fail_closed(handler_id: str, credential: object, checkout: object) -> None:
  del credential, checkout
  raise RuntimeError(f"no payment authorizer for handler {handler_id}")


PAYMENT_AUTHORIZER: Any = _fail_closed

# UCP demo patch P15 (tests only): an httpx.AsyncBaseTransport for webhook deliveries.
# None uses the network. Tests set it, so no test delivery leaves the process.
WEBHOOK_TRANSPORT: Any = None

# UCP demo patch P16: seams that the host app sets (S4).
# WEBHOOK_SIGNING_KEY: (private_key, kid) of the key in the published profile (AC-65).
# WEBHOOK_PROFILE_URL: the public profile URL for UCP-Agent. The app is behind a proxy.
# WEBHOOK_DEAD_LETTER: callable(event_type, webhook_id, failure) after the last failure.
WEBHOOK_SIGNING_KEY: Any = None
WEBHOOK_PROFILE_URL: Any = None
WEBHOOK_DEAD_LETTER: Any = None
PROFILE_RESOLVER: Any = None
LINKS: list[dict[str, str]] = []


def get_server_version() -> str:
  """Read and cache the server version from the discovery profile."""
  profile = _get_profile()
  return profile["ucp"]["version"]


def get_payment_handlers() -> dict:
  """Read and cache the payment handlers from the discovery profile."""
  profile = _get_profile()
  return profile["ucp"].get("payment_handlers", {})


# Define flags only if they haven't been defined yet (to avoid duplicates
# during tests or re-imports)
try:
  flags.DEFINE_string("products_db_path", None, "Path to products DB")
  flags.DEFINE_string("transactions_db_path", None, "Path to transactions DB")
  flags.DEFINE_string(
    "simulation_secret",
    str(uuid.uuid4()),
    "Secret key for simulation endpoints",
  )
  flags.DEFINE_integer("port", None, "Port to run the server on")
  flags.DEFINE_boolean(
    "require_signatures",
    # UCP demo patch P3 (02-design 17.2 defect 7, spec T-04): on by default.
    True,
    "Reject requests whose RFC 9421 signature is missing or invalid. When "
    "false (the default), signatures are still verified when present, but "
    "unsigned or invalid requests are allowed and only logged.",
  )
  flags.DEFINE_boolean(
    "allow_insecure_profile_urls",
    False,
    "Permit http and loopback/private UCP-Agent profile URLs when resolving "
    "signer keys. For localhost demos and CI only; never enable in "
    "production, as it disables SSRF protections.",
  )
  flags.DEFINE_string(
    "webhook_signing_key",
    None,
    "Path to a PEM private key (EC P-256 or Ed25519) used to sign outbound "
    "order-event webhooks as this business (order.md, Webhook Signature "
    "Verification). When unset, an ephemeral demo key is generated at "
    "startup; either way the public JWK is published in the served "
    "profile's signing_keys[].",
  )
  flags.DEFINE_integer(
    "webhook_delivery_attempts",
    3,
    "Total delivery attempts per order-event webhook (the initial attempt "
    "plus retries). order.md requires failed deliveries to be retried; the "
    "bound keeps the retry finite.",
    lower_bound=1,
  )
  flags.DEFINE_float(
    "webhook_retry_backoff_seconds",
    0.5,
    "Delay before the first webhook retry, doubling on each subsequent "
    "retry (exponential backoff).",
    lower_bound=0.0,
  )
except flags.DuplicateFlagError:
  pass


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
  """Shared lifespan manager for initializing databases."""
  del app  # Unused.
  # Load (and thereby validate) the webhook-signing identity up front: a
  # misconfigured --webhook_signing_key must abort the boot loudly, not
  # surface as a swallowed per-delivery error that silently degrades every
  # webhook. Imported lazily; webhook_signer imports this module.
  import webhook_signer

  webhook_signer.signing_key()
  # In tests or if flags aren't set, these might be None, handled by caller
  if FLAGS.products_db_path and FLAGS.transactions_db_path:
    await db.manager.init_dbs(
      FLAGS.products_db_path, FLAGS.transactions_db_path
    )
  yield
  await db.manager.close()
