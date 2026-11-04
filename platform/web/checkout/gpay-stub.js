/* Google Pay Web API stub for CI (MODE=ci only, 04-build-plan.md S3). It is not pay.js.
   It copies the documented surface: PaymentsClient, isReadyToPay ({result}), createButton (an HTML
   button in a container, onClick required) and loadPaymentData (PaymentData or a CANCELED error).
   Sources: https://developers.google.com/pay/api/web/reference/client and
   https://developers.google.com/pay/api/web/reference/response-objects (PaymentData example).
   A test sets window.__gpayStub = {ready, outcome} before the page loads. */
(function () {
  "use strict";
  const st = window.__gpayStub = Object.assign({ ready: true, outcome: "approve", calls: [] }, window.__gpayStub || {});
  const EXAMPLE = {
    apiVersion: 2, apiVersionMinor: 0,
    paymentMethodData: {
      type: "CARD", description: "Visa \u2022\u2022\u2022\u2022 1234",
      info: { cardNetwork: "VISA", cardDetails: "1234", cardFundingSource: "CREDIT" },
      tokenizationData: { type: "PAYMENT_GATEWAY", token: "examplePaymentMethodToken" },
    },
  };
  class PaymentsClient {
    constructor(options) { st.calls.push({ fn: "PaymentsClient", environment: options && options.environment }); }
    isReadyToPay(request) {
      st.calls.push({ fn: "isReadyToPay", request: JSON.parse(JSON.stringify(request)) });
      return Promise.resolve({ result: Boolean(st.ready) });
    }
    createButton(options) {
      if (!options || typeof options.onClick !== "function") throw { statusCode: "DEVELOPER_ERROR", statusMessage: "onClick is required" };
      st.calls.push({ fn: "createButton", options: { buttonType: options.buttonType || "buy", buttonColor: options.buttonColor || "default", buttonSizeMode: options.buttonSizeMode || "static" } });
      const div = document.createElement("div");
      div.className = "gpay-stub";
      const b = document.createElement("button");
      b.type = "button";
      b.className = "gpay-stub-button";
      b.textContent = "Pay now (CI test stub)";
      b.style.cssText = "width:100%;height:100%;min-width:240px;background:#000;color:#fff;border:0;border-radius:4px;font-weight:600";
      b.addEventListener("click", options.onClick);
      div.appendChild(b);
      return div;
    }
    loadPaymentData(request) {
      const active = navigator.userActivation ? navigator.userActivation.isActive : null;
      st.calls.push({ fn: "loadPaymentData", request: JSON.parse(JSON.stringify(request)), activationActive: active, t: performance.now() });
      if (st.outcome === "cancel") return Promise.reject({ statusCode: "CANCELED", statusMessage: "User closed the Payment Request UI." });
      if (st.outcome === "developer_error") return Promise.reject({ statusCode: "DEVELOPER_ERROR", statusMessage: "Stub developer error." });
      // AC-35: each sheet approval gives a new token, like a real new Google Pay token.
      const n = st.calls.filter((c) => c.fn === "loadPaymentData").length;
      const pd = JSON.parse(JSON.stringify(EXAMPLE));
      if (n > 1) pd.paymentMethodData.tokenizationData.token += "-" + n;
      return new Promise((resolve) => setTimeout(() => resolve(pd), 50));
    }
  }
  window.google = window.google || {};
  window.google.payments = { api: { PaymentsClient } };
})();
