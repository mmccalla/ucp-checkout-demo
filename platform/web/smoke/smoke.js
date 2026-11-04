// S0 smoke page (spec 4.2). It maps the handler config (snake_case) to the Google Pay
// request (camelCase): https://developers.google.com/pay/api/web/reference/request-objects
// The page records no token value. It records only the type and the length.
"use strict";
window.__smoke = [];
const params = new URLSearchParams(location.search);
const CASE = params.get("case") || "valid";

function record(e) {
  const row = Object.assign({ case: CASE, origin: location.origin, secureContext: isSecureContext }, e);
  window.__smoke.push(row);
  const li = document.createElement("li");
  li.textContent = JSON.stringify(row);
  document.getElementById("events").appendChild(li);
  fetch("/smoke/event", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(row) }).catch(() => {});
}

function errorFields(err) {
  return { ok: false, statusCode: err && err.statusCode, statusMessage: err && err.statusMessage,
    errorName: err && err.name };
}

function mapMethod(m) {
  const p = m.parameters;
  const auth = CASE === "bad-request" ? ["NOT_A_METHOD"] : p.allowed_auth_methods;
  return {
    type: m.type,
    parameters: { allowedAuthMethods: auth, allowedCardNetworks: p.allowed_card_networks },
    tokenizationSpecification: { type: m.tokenization_specification.type,
      parameters: m.tokenization_specification.parameters },
  };
}

function buildRequest(cfg) {
  return {
    apiVersion: cfg.api_version,
    apiVersionMinor: cfg.api_version_minor,
    allowedPaymentMethods: cfg.allowed_payment_methods.map(mapMethod),
    merchantInfo: { merchantName: cfg.merchant_info.merchant_name,
      merchantId: cfg.merchant_info.merchant_id },
    transactionInfo: { totalPriceStatus: "FINAL", totalPrice: "19.99", currencyCode: "GBP",
      countryCode: "GB" },
  };
}

async function main() {
  const handler = await (await fetch("/smoke/handler-config.json")).json();
  const cfg = handler.config;
  if (cfg.environment !== "TEST") { record({ step: "config", ok: false, detail: "not TEST" }); return; }
  record({ step: "config", ok: true, detail: `${handler.id} ${handler.version}` });

  const client = new google.payments.api.PaymentsClient({ environment: "TEST" });
  const request = buildRequest(cfg);
  try {
    const ready = await client.isReadyToPay({ apiVersion: request.apiVersion,
      apiVersionMinor: request.apiVersionMinor, allowedPaymentMethods: request.allowedPaymentMethods });
    record({ step: "isReadyToPay", ok: true, result: ready.result });
  } catch (err) {
    record({ step: "isReadyToPay", ...errorFields(err) });
  }

  const button = client.createButton({
    buttonType: "buy",
    onClick: async () => {
      record({ step: "click", ok: true });
      try {
        const data = await client.loadPaymentData(request);
        const tok = data.paymentMethodData.tokenizationData;
        record({ step: "loadPaymentData", ok: true, tokenType: tok.type,
                 tokenLength: (tok.token || "").length,
                 cardNetwork: data.paymentMethodData.info && data.paymentMethodData.info.cardNetwork });
      } catch (err) {
        record({ step: "loadPaymentData", ...errorFields(err) });
      }
    },
  });
  document.getElementById("gpay-container").appendChild(button);
  record({ step: "createButton", ok: true });
}

const s = document.createElement("script");
s.src = "https://pay.google.com/gp/p/js/pay.js";
s.async = true;
s.onload = () => main().catch((e) => record({ step: "main", ...errorFields(e) }));
s.onerror = () => record({ step: "pay.js", ok: false, detail: "pay.js load failed" });
document.head.appendChild(s);
