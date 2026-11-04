/* UCP demo checkout page (S3). Screens SC1 to SC5, the protocol inspector (SC8) and the run
   controls. Texts are the UX-8.2 key strings of 02-design.md. The browser never gets a key.
   The Google Pay token goes only to POST /api/checkout/{id}/pay. The page never shows it. */
(function () {
  "use strict";

  const S = {
    "banner.test.label": "TEST MODE.",
    "banner.test": "Google Pay TEST — dummy token, cannot be charged. Simulated payment processor. No real money moves.",
    "banner.replay": "REPLAY. These are recorded messages. No calls go out.",
    // UX gap (PROPOSAL): input-ux.md 8.2 has no strings for the replay Google Pay step (4.4).
    "replay.gpay.button": "Google Pay (recorded)",
    "replay.gpay.result": "Recorded Google Pay sheet result: {result}. The Google Pay sheet did not open.",
    "start.story": "An agent prepares a checkout with a shop over UCP. You approve the payment with Google Pay. The shop places the order.",
    "start.sheetNote": "In TEST mode, Google Pay shows test cards and the text 'Pay Unverified Merchant'. This is normal.",
    "agent.plan.discover": "I will find the shop and read what it supports.",
    "agent.plan.create": "I will start a checkout for this item.",
    "agent.plan.update": "I will send your contact and delivery details to the shop.",
    "agent.handover": "I did these steps. I cannot pay for you. Review the order and approve the payment.",
    "review.total": "Total to pay: {amount}",
    "review.wait": "Waiting for you in Google Pay.",
    "gpay.unavailable": "Google Pay is not available in this browser. Use a supported browser and sign in to a Google Account. Or select 'Use replay' to see a recorded run.",
    "cancel.buyer": "You closed Google Pay. You did not pay. Select the Google Pay button to try again.",
    "placing": "Placing your order. Do not close this page.",
    "escalation": "The shop needs more information from you. Continue on the shop website to finish.",
    "error.network": "We cannot reach the shop. Your details are safe on this page. Try again.",
    "error.protocol": "The shop did not accept the request (HTTP {code}). This is a problem in the demo setup, not a payment problem.",
    "error.unrecoverable": "This item is not available. Select a different item.",
    "canceled": "This checkout stopped. You did not pay. Start a new checkout.",
    "config.notTest": "Demo stopped. The shop is not in TEST mode.",
    "inspector.empty": "No messages yet. Select 'Start demo'.",
    "inspector.redacted": "Hidden for security. The real value is in the request.",
    "inspector.notUcp": "Not a UCP message. This is a Google Pay API call or a step inside a party.",
    "inspector.announce": "Message {n}. {name}. Response {code}. Status {status}.",
    "totals.mismatch": "The totals from the shop do not add up. The agent stopped. You did not pay.",
    "review.changed": "The order changed after your approval. Review the new order.",
    // ST13 (T-105, spec 15.5 row 10): 02-design.md UX-8.2.
    "declined.heading": "Payment declined",
    "declined.body": "The shop's payment processor declined your payment. You did not pay. The shop did not place your order. Your items and details did not change.",
    "declined.retry.hint": "To try again, select the Google Pay button. You can select a different card in Google Pay.",
    "declined.action.secondary": "Cancel checkout",
    "declined.announce": "Payment declined. You did not pay. You can try again with Google Pay.",
    "declined.simulated": "Simulated: the demo payment processor declined this payment. Google Pay did not decline it.",
    "declined.again.heading": "Payment declined again",
    "declined.again.body": "The shop's payment processor declined your payment again. You did not pay. Select a different card in Google Pay, or cancel the checkout.",
    "declined.again.announce": "Payment declined again. You did not pay.",
    "inspector.m10.declined": "The shop did not take payment. HTTP 200: this is a business result, not a protocol error. `status` stays `ready_for_complete`, so the Platform can send Complete again. `messages` has `payment_failed` with `severity` `recoverable`. The response has no `order`. The processor result is from the simulated processor (M9, `SIMULATED`). The inspector does not show the token or the processor reason.",
    "inspector.retry.newKey": "Retry with a new token from Google Pay. The request body changed, so the Platform uses a new `Idempotency-Key`. The shop sends the new token to its payment processor.",
    // S4 (AC-64, AC-73, AC-74): UX-8.2 has no strings for these. The text is from the AC rows.
    "order.events.title": "Order updates",
    "order.created": "Order confirmed",
    "order.shipped": "Shipped",
    "order.delivered": "Delivered",
    "order.simulated": "Simulated",
    "order.tracking": "Tracking number (fake): {number}",
    "order.reconcile": "Reconcile",
    "order.reconcile.same": "Reconcile: Get Order gives the same state as the webhooks ({state}).",
    "order.reconcile.differ": "Reconcile: Get Order gives {get}. The webhooks give {hook}.",
    "inspector.signature": "Response signature: {result}.",
    "escalation.noLink": "The shop did not give a link to its website.",
    "gpay.checkResult": "Google Pay check result:",
    // S7 (UX-8.2, 02-design.md): the catalog copy. Spec v1.1.18, section 7.12.
    "search.heading": "Find a product",
    "search.label": "Search the shop",
    "search.hint": "Type a word, for example a product name.",
    "search.submit": "Search",
    "search.error.empty": "Type a word to search for.",
    "search.idle": "No search yet. Type a word and select 'Search'.",
    "search.loading": "Searching the shop.",
    "search.loading.more": "Loading more products.",
    "search.count": "Products shown: {n}",
    "search.count.total": "Products shown: {n} of {total}",
    "search.none": "No products match '{query}'. Try another word.",
    "search.error.network": "We cannot reach the shop. Your search is still on this page.",
    "search.error.protocol": "The shop did not accept the search. This is a demo setup problem.",
    "search.more": "Show more results",
    "search.results.heading": "Results",
    "search.notes.heading": "Notes from the shop",
    "search.result.view": "View details",
    "detail.loading": "Getting the product details.",
    "detail.error.network": "We cannot reach the shop. Your choice is still on this page.",
    "detail.error.protocol": "The shop did not accept the request for this product. This is a demo setup problem.",
    "detail.back": "Back to results",
    "detail.unavailable": "You cannot add this item now.",
    "item.hint": "The product details change when you select another item.",
    "agent.plan.search": "I will search the shop for '{query}'.",
    "price.range": "{min} to {max}",
    "avail.in_stock": "In stock",
    "avail.backorder": "On backorder",
    "avail.preorder": "Pre-order",
    "avail.out_of_stock": "Out of stock",
    "avail.discontinued": "No longer sold",
    "avail.yes": "Available",
    "avail.no": "Not available",
    "replay.search.note": "This is a recorded search. The answers are saved.",
    "inspector.catalog.note": "This call finds products. It does not start a checkout.",
    "inspector.announce.search": "Message {n}. Search Catalog. Response {code}. Products: {count}.",
    "inspector.announce.product": "Message {n}. Get Product. Response {code}.",
    "inspector.retry.sameKey": "Same `Idempotency-Key` and same body. The shop sends its stored response again. It does not call the payment processor again.",
  };
  const fmt = (k, v) => S[k].replace(/\{(\w+)\}/g, (_, n) => (v && v[n] !== undefined ? String(v[n]) : ""));
  const esc = (s) => String(s === undefined || s === null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // UX-4.5.1 (UX-AC-33): a back-quote pair in a copy string is authoring markup. The text is escaped
  // first. Then each pair becomes one code element. The page never shows a back-quote.
  // A string with an odd number of back-quotes is an authoring error (tests/s3/unit finds it).
  const rich = (s) => esc(s).replace(/`([^`]*)`/g, "<code>$1</code>");
  const MASK = "[REDACTED]";
  // UX-4.4.1: source label icons are Material Symbols (Apache-2.0), commit 10ecc14. The path data is
  // copied from vendor/material-symbols/*.svg. tests/s4/test_icons.py checks that they are the same.
  const ICON = {
    live: '<svg class="icon" aria-hidden="true" focusable="false" viewBox="0 -960 960 960" width="16" height="16"><path d="M280-120 80-320l200-200 57 56-104 104h607v80H233l104 104-57 56Zm400-320-57-56 104-104H120v-80h607L623-784l57-56 200 200-200 200Z" fill="currentColor"/></svg>', // Material Symbols sync_alt
    recorded: '<svg class="icon" aria-hidden="true" focusable="false" viewBox="0 -960 960 960" width="16" height="16"><path d="M480-120q-138 0-240.5-91.5T122-440h82q14 104 92.5 172T480-200q117 0 198.5-81.5T760-480q0-117-81.5-198.5T480-760q-69 0-129 32t-101 88h110v80H120v-240h80v94q51-64 124.5-99T480-840q75 0 140.5 28.5t114 77q48.5 48.5 77 114T840-480q0 75-28.5 140.5t-77 114q-48.5 48.5-114 77T480-120Zm112-192L440-464v-216h80v184l128 128-56 56Z" fill="currentColor"/></svg>', // Material Symbols history
    gpaytest: '<svg class="icon" aria-hidden="true" focusable="false" viewBox="0 -960 960 960" width="16" height="16"><path d="M200-120q-51 0-72.5-45.5T138-250l222-270v-240h-40q-17 0-28.5-11.5T280-800q0-17 11.5-28.5T320-840h320q17 0 28.5 11.5T680-800q0 17-11.5 28.5T640-760h-40v240l222 270q32 39 10.5 84.5T760-120H200Zm0-80h560L520-492v-268h-80v268L200-200Zm280-280Z" fill="currentColor"/></svg>', // Material Symbols science
    simulated: '<svg class="icon" aria-hidden="true" focusable="false" viewBox="0 -960 960 960" width="16" height="16"><path d="M760-660q17 0 28.5-11.5T800-700q0-17-11.5-28.5T760-740q-17 0-28.5 11.5T720-700q0 17 11.5 28.5T760-660Zm-160 0q17 0 28.5-11.5T640-700q0-17-11.5-28.5T600-740q-17 0-28.5 11.5T560-700q0 17 11.5 28.5T600-660Zm-20 136h200q0-35-30.5-55.5T680-600q-39 0-69.5 20.5T580-524ZM280-80q-100 0-170-70T40-320v-280h480v280q0 100-70 170T280-80Zm0-80q66 0 113-47t47-113v-200H120v200q0 66 47 113t113 47Zm400-200q-26 0-51.5-5.5T580-382v-94q22 17 47.5 26.5T680-440q66 0 113-47t47-113v-200H520v140h-80v-220h480v280q0 100-70 170t-170 70Zm-480-20q17 0 28.5-11.5T240-420q0-17-11.5-28.5T200-460q-17 0-28.5 11.5T160-420q0 17 11.5 28.5T200-380Zm160 0q17 0 28.5-11.5T400-420q0-17-11.5-28.5T360-460q-17 0-28.5 11.5T320-420q0 17 11.5 28.5T360-380Zm-80 136q39 0 69.5-20.5T380-320H180q0 35 30.5 55.5T280-244Zm0-96Zm400-280Z" fill="currentColor"/></svg>', // Material Symbols theater_comedy
    local: '<svg class="icon" aria-hidden="true" focusable="false" viewBox="0 -960 960 960" width="16" height="16"><path d="M40-120v-80h880v80H40Zm120-120q-33 0-56.5-23.5T80-320v-440q0-33 23.5-56.5T160-840h640q33 0 56.5 23.5T880-760v440q0 33-23.5 56.5T800-240H160Zm0-80h640v-440H160v440Zm0 0v-440 440Z" fill="currentColor"/></svg>', // Material Symbols laptop
    warn: '<svg class="icon" aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="18" height="18"><path d="M12 2 1 21h22zm-1 7h2v6h-2zm0 8h2v2h-2z" fill="currentColor"/></svg>',
    stop: '<svg class="icon" aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="18" height="18"><path d="M7.9 2h8.2L22 7.9v8.2L16.1 22H7.9L2 16.1V7.9zM8 11v2h8v-2z" fill="currentColor"/></svg>',
    info: '<svg class="icon" aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="18" height="18"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2"/><path d="M11 10h2v7h-2zm0-4h2v2h-2z" fill="currentColor"/></svg>',
  };
  const BADGE = { "LIVE CALL": "live", "RECORDED": "recorded", "GOOGLE PAY TEST": "gpaytest", "SIMULATED": "simulated", "LOCAL STEP": "local" };
  // AC-63, UX-4.4.1 (spec 15.5 row 8): accessible name and visible detail text of LOCAL STEP.
  const LOCAL_TEXT = "Local step: the Platform did this step. No network call.";
  const $ = (id) => document.getElementById(id);

  const app = {
    cfg: null, run: "live", play: "step", paused: false, replaying: false,
    messages: [], checkout: null, review: null, paymentsClient: null, gpayLoaded: null,
    buyer: { email: "", first_name: "", last_name: "", street_address: "", address_locality: "", postal_code: "", address_country: "GB" },
    cat: null, item: "demo_tshirt", quantity: 1, screens: [], discovery: null, retryId: null, waiter: null, declines: 0,
  };
  window.__ucpDemo = app;

  // ---------------------------------------------------------------- run controls (AC-62)
  function setPending(label) {
    $("pending").textContent = label ? "Next step: " + label + "." : "No step is waiting.";
    $("next-step").disabled = !label;
    $("pause").disabled = !label || app.play !== "auto";
  }
  function waitStep(label) {
    return new Promise((resolve) => {
      setPending(label);
      let timer = null;
      const go = () => { if (timer) clearTimeout(timer); app.waiter = null; setPending(null); resolve(); };
      app.waiter = { go, arm: () => { if (timer) clearTimeout(timer); timer = (app.play === "auto" && !app.paused) ? setTimeout(go, app.cfg.auto_ms) : null; } };
      app.waiter.arm();
    });
  }
  $("next-step").addEventListener("click", () => { if (app.waiter) app.waiter.go(); });
  $("pause").addEventListener("click", () => {
    app.paused = !app.paused;
    $("pause").setAttribute("aria-pressed", String(app.paused));
    announce(app.paused ? "Paused." : "Running.");
    if (app.waiter) app.waiter.arm();
  });
  $("replay").addEventListener("click", () => replay());
  $("toggle-inspector").addEventListener("click", () => {
    const body = $("inspector-body");
    const open = body.classList.toggle("closed") === false;
    $("toggle-inspector").setAttribute("aria-expanded", String(open));
    $("toggle-inspector").textContent = open ? "Hide inspector" : "Show inspector";
  });

  function announce(text) { const a = $("announcer"); a.textContent = ""; setTimeout(() => { a.textContent = text; }, 30); }

  async function api(method, url, body) {
    const r = await fetch(url, { method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
    let data = null;
    try { data = await r.json(); } catch (e) { data = null; }
    return { status: r.status, data };
  }
  function event(kind, name, extra) {
    if (app.replaying) return;
    fetch("/api/timeline/event", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.assign({ kind, name }, extra || {})) });
  }

  // ---------------------------------------------------------------- inspector (SC8)
  const EXPLAIN = {
    "HTTP status": "The HTTP status code of the response.",
    "status": "The checkout status that the shop sets.",
    "id": "The checkout ID. The shop makes it.",
    "currency": "The currency of all amounts (ISO 4217).",
    "total": "The total in minor units. 2300 is GBP 23.00.",
    "order.id": "The order ID. The shop makes it.",
    "messages[0].code": "The code of the first message from the shop.",
    // UX-8.3: the text for `messages[].severity`, then the text for the value `recoverable`.
    "messages[0].severity": "What the agent must do about this message: fix it, ask you, or stop. `recoverable`: the Platform can fix this with a new request. The buyer does not go to the shop website.",
    "continue_url": "The shop page where the buyer can finish.",
    "ucp_version": "The UCP version of the shop profile.",
    "endpoint": "The REST endpoint of the shop.",
    "active": "The capabilities that both parties support.",
    "search_notice": "The agent cannot search the catalog.",
    "result": "The result of the Google Pay call.",
    "environment": "The Google Pay environment. TEST moves no money.",
    "merchantInfo.merchantId": "The merchant ID. TEST is the value for TEST mode.",
    "allowedAuthMethods": "The card authentication methods that the shop accepts.",
    "transactionInfo.totalPrice": "The amount that the Google Pay sheet shows.",
    "transactionInfo.checkoutOption": "COMPLETE_IMMEDIATE_PURCHASE shows 'Pay now' in the sheet.",
    "cardNetwork": "The card network that the buyer selected.",
    "tokenizationData.token": "The payment token. Hidden for security.",
    "Idempotency-Key": "A key that stops the shop from doing the same operation two times.",
    "tries": "The number of tries for this request.",
    "code": "The result code of the Platform webhook receiver.",
    "Webhook-Id": "The event ID. A retry of the same event has the same ID.",
    "Webhook-Timestamp": "The time of the event (Unix seconds).",
    "query": "The word that the buyer typed. The shop uses it to find products.",
    "products": "The number of products in the answer.",
    "pagination.has_next_page": "`true` means that the shop has more products. The buyer can select 'Show more results'.",
    "pagination.total_count": "The number of products that match. The shop may leave it out.",
    "product.variants[0].id": "The variant ID. The checkout uses it as the item ID.",
    "product.variants[0].price": "The price in minor units. 2000 is GBP 20.00.",
    "product.variants[0].availability.status": "The stock state of the first variant.",
  };
  function get(o, path) { return path.split(".").reduce((a, k) => (a === undefined || a === null ? undefined : a[k]), o); }
  function keyFields(m) {
    const f = [];
    const add = (name, value) => { if (value !== undefined && f.length < 6) f.push([name, value]); };
    if (m.kind === "ucp" && (m.op === "search" || m.op === "product")) {
      // UX-7.6: M1a and M1b. Three to six fields.
      const b = (m.response && m.response.body) || {};
      const msg = b.messages && b.messages[0];
      const st = m.response.status === null || m.response.status === undefined ? "no response" : m.response.status;
      if (m.op === "search") {
        add("query", m.request && m.request.body && m.request.body.query);
        add("HTTP status", st);
        if (Array.isArray(b.products)) add("products", b.products.length);
        add("pagination.has_next_page", b.pagination && b.pagination.has_next_page);
        add("pagination.total_count", b.pagination && b.pagination.total_count);
        add("messages[0].code", msg && msg.code);
      } else if (b.product) {
        const v = b.product.variants && b.product.variants[0];
        add("id", m.request && m.request.body && m.request.body.id);
        add("HTTP status", st);
        add("product.variants[0].id", v && v.id);
        add("product.variants[0].price", v && v.price && v.price.amount + " " + v.price.currency);
        add("product.variants[0].availability.status", v && v.availability && v.availability.status);
        add("messages[0].code", msg && msg.code);
      } else {
        add("id", m.request && m.request.body && m.request.body.id);
        add("HTTP status", st);
        add("messages[0].code", msg && msg.code);
        add("messages[0].severity", msg && msg.severity);
      }
    } else if (m.kind === "ucp" && m.op === "complete") {
      // UX-4.5.1 (UX-AC-31): HTTP status, status, order.id, messages[0].code, messages[0].severity,
      // Idempotency-Key, total. When tries is more than 1, tries replaces total. The limit of 6
      // fields keeps Idempotency-Key. id and currency stay in the raw JSON.
      const b = (m.response && m.response.body) || {};
      const msg = b.messages && b.messages[0];
      add("HTTP status", m.response.status === null ? "no response" : m.response.status);
      add("status", b.status !== undefined ? b.status : (b.ucp && b.ucp.status));
      add("order.id", b.order && b.order.id);
      add("messages[0].code", msg && msg.code);
      add("messages[0].severity", msg && msg.severity);
      add("Idempotency-Key", m.request.headers["Idempotency-Key"]);
      if (m.tries > 1) add("tries", m.tries);
      else { const t = (b.totals || []).find((e) => e.type === "total"); add("total", t && t.amount); }
    } else if (m.kind === "ucp") {
      const b = (m.response && m.response.body) || {};
      add("HTTP status", m.response.status === null ? "no response" : m.response.status);
      add("status", b.status !== undefined ? b.status : (b.ucp && b.ucp.status));
      add("id", b.id);
      add("currency", b.currency);
      const t = (b.totals || []).find((e) => e.type === "total");
      add("total", t && t.amount);
      add("messages[0].code", b.messages && b.messages[0] && b.messages[0].code);
      add("continue_url", b.continue_url);
      add("Idempotency-Key", m.request.headers["Idempotency-Key"]);
      add("tries", m.tries);
    } else if (m.kind === "webhook") {
      add("HTTP status", m.response.status);
      add("code", m.response.body && m.response.body.code);
      add("Webhook-Id", m.request.headers["Webhook-Id"]);
      add("Webhook-Timestamp", m.request.headers["Webhook-Timestamp"]);
    } else if (m.kind === "discovery") {
      const b = m.response.body || {};
      add("HTTP status", b.ok ? 200 : "failed");
      add("ucp_version", b.ucp_version);
      add("endpoint", b.endpoint);
      add("active", (b.active || []).join(", "));
      add("search_notice", b.search_notice);
    } else {
      const q = m.request || {};
      add("environment", q.environment);
      add("merchantInfo.merchantId", get(q, "paymentDataRequest.merchantInfo.merchantId"));
      add("allowedAuthMethods", JSON.stringify(get(q, "paymentDataRequest.allowedPaymentMethods.0.parameters.allowedAuthMethods") || get(q, "allowedPaymentMethods.0.parameters.allowedAuthMethods")));
      add("transactionInfo.totalPrice", get(q, "paymentDataRequest.transactionInfo.totalPrice") || get(q, "transactionInfo.totalPrice"));
      add("transactionInfo.checkoutOption", get(q, "paymentDataRequest.transactionInfo.checkoutOption") || get(q, "transactionInfo.checkoutOption"));
      add("result", m.result);
      add("cardNetwork", get(m.response || {}, "body.paymentMethodData.info.cardNetwork"));
      add("tokenizationData.token", get(m.response || {}, "body.paymentMethodData.tokenizationData.token"));
    }
    return f.filter((x) => x[1] !== undefined && x[1] !== null && x[1] !== "");
  }
  function badge(source) {
    const k = BADGE[source];
    if (source === "LOCAL STEP") { // UX-4.4.1: the accessible name starts with the visible words
      return `<span class="badge ${k}" data-source="${esc(source)}">${ICON[k]}<span aria-hidden="true">${esc(source)}</span><span class="visually-hidden">${esc(LOCAL_TEXT)}</span></span>`;
    }
    return `<span class="badge ${k}" data-source="${esc(source)}">${ICON[k]}${esc(source)}</span>`;
  }
  function addMessage(m, opts) {
    const row = opts && opts.row; // S7: a row that was added before the answer (Waiting)
    const n = row ? row.n : app.messages.length + (opts && opts.replay ? 0 : 1);
    if (!(opts && opts.replay)) app.messages.push(m);
    // UX-4.5: in a replay each label is RECORDED. NOT UCP stays.
    const shown = opts && opts.replay ? Object.assign({}, m, { source: "RECORDED", original_source: m.source }) : m;
    $("inspector-empty").hidden = true;
    const li = row ? row.li : document.createElement("li");
    if (row) li.textContent = "";
    const state = rowState(shown);
    const b = document.createElement("button");
    b.type = "button";
    b.className = "msg";
    b.innerHTML = `<span>${esc(n)}. ${esc(shown.name)}</span> ${badge(shown.source)}${shown.not_ucp ? ' <span class="badge notucp">NOT UCP</span>' : ""} <span class="phase">Phase: ${esc(shown.phase)}</span>${state ? ` <span class="row-state">${esc(state)}</span>` : ""}`;
    b.addEventListener("click", () => showDetail(shown, n, b));
    if (opts && opts.highlight) b.dataset.highlight = opts.highlight.join(" ");
    li.appendChild(b);
    if (!row) $("msg-list").appendChild(li);
    const code = shown.response && shown.response.status !== undefined ? (shown.response.status === null ? "none" : shown.response.status) : (shown.result === undefined ? "none" : shown.result);
    const st = shown.response && shown.response.body && shown.response.body.status ? shown.response.body.status : "none";
    if (shown.op === "search") {
      const body = (shown.response && shown.response.body) || {};
      announce(fmt("inspector.announce.search", { n, code, count: Array.isArray(body.products) ? body.products.length : 0 }));
    } else if (shown.op === "product") announce(fmt("inspector.announce.product", { n, code }));
    else announce(fmt("inspector.announce", { n, name: shown.name, code, status: st }));
    $("replay").disabled = app.replaying || app.messages.length === 0;
  }
  // UX-7.6: the row states of M1a and M1b. Other rows have no state text.
  function rowState(m) {
    if (!m.mid) return "";
    const st = m.response && m.response.status;
    if (st === null || st === undefined) return "No response";
    const b = (m.response && m.response.body) || {};
    return st >= 400 || (b.ucp && b.ucp.status === "error") ? "Error" : "";
  }
  function showDetail(m, n, btn) {
    document.querySelectorAll("#msg-list button[aria-current]").forEach((x) => x.removeAttribute("aria-current"));
    btn.setAttribute("aria-current", "true");
    const d = $("msg-detail");
    const raw = JSON.stringify({ request: m.request, response: m.response, result: m.result }, null, 2);
    const keys = keyFields(m).slice(0, 6);
    while (keys.length < 3) keys.push(["phase", m.phase]);
    d.innerHTML = `<h3 id="detail-title">Message ${esc(n)}: ${esc(m.name)}</h3>
      <p>${badge(m.source)}${m.not_ucp ? ' <span class="badge notucp">NOT UCP</span> ' + esc(S["inspector.notUcp"]) : ""}</p>
      ${m.source === "LOCAL STEP" ? `<p class="local-text">${esc(LOCAL_TEXT)}</p>` : ""}
      ${m.original_source ? `<p class="recorded-text">Recorded. Original source: ${esc(m.original_source)}.</p>` : ""}
      ${(m.notes || []).map((x) => `<p class="note">${rich(x)}</p>`).join("")}
      ${m.method ? `<p><code>${esc(m.method)} ${esc(m.path)}</code></p>` : ""}
      <dl class="keys">${keys.map(([k, v]) => `<dt><code>${esc(k)}</code></dt><dd><code>${esc(v)}</code><span class="explain">${rich(EXPLAIN[k] || "The phase of the demo for this message.")}</span></dd>`).join("")}</dl>
      ${raw.includes(MASK) ? `<p class="muted">${esc(MASK)}: ${esc(S["inspector.redacted"])}</p>` : ""}
      <details><summary>Raw JSON</summary><pre>${esc(raw)}</pre></details>`;
    d.hidden = false;
  }
  function ucpMessage(c) { return Object.assign({ kind: "ucp" }, c); }

  // ---------------------------------------------------------------- screens
  function screen(title, html) {
    app.screens.push(title);
    $("screen").innerHTML = `<h1 id="screen-title" tabindex="-1">${esc(title)}</h1>` + html;
    $("screen-title").focus(); // AC-80: the focus moves to the screen heading
  }
  function panel(kind, title, body, id) {
    const icon = kind === "bad" ? ICON.stop : kind === "warn" ? ICON.warn : ICON.info;
    return `<div class="panel ${kind}"${kind === "bad" ? ' role="alert"' : ""}${id ? ` id="${id}"` : ""}><p class="panel-title">${icon}<span>${esc(title)}</span></p>${body}</div>`;
  }
  function on(id, fn) { const e = $(id); if (e) e.addEventListener("click", fn); }

  function sc1() {
    app.replaying = false;
    setBanner(false);
    screen("UCP checkout with Google Pay - demo", `
      <p>${esc(S["start.story"])}</p>
      <h2>Parties</h2>
      <ul class="parties"><li>Platform (demo agent)</li><li>Business (demo shop)</li><li>Credential Provider (Google Pay)</li><li>PSP (simulated)</li></ul>
      <p>${esc(S["start.sheetNote"])}</p>
      <fieldset><legend>Run mode</legend>
        <label><input type="radio" name="run" value="live" ${app.run === "live" ? "checked" : ""}> Live calls to the demo shop</label>
        <label><input type="radio" name="run" value="replay" ${app.run === "replay" ? "checked" : ""}> Replay recording</label>
      </fieldset>
      <fieldset><legend>Play mode</legend>
        <label><input type="radio" name="play" value="step" ${app.play === "step" ? "checked" : ""}> Step - I select Next</label>
        <label><input type="radio" name="play" value="auto" ${app.play === "auto" ? "checked" : ""}> Auto - with Pause</label>
      </fieldset>
      <div class="actions"><button type="button" class="primary" id="start">Start demo</button></div>`);
    on("start", async () => {
      app.run = document.querySelector('input[name="run"]:checked').value;
      app.play = document.querySelector('input[name="play"]:checked').value;
      event("buyer_action", "Start demo", { phase: "Negotiation" });
      if (app.run === "replay") return replay();
      await discover();
    });
  }

  async function discover() {
    const p = $("screen").querySelector(".actions");
    if (p) p.insertAdjacentHTML("afterend", `<p class="muted">${esc(S["agent.plan.discover"])}</p>`);
    await waitStep("Discovery");
    const case_ = new URLSearchParams(location.search).get("case") || "live";
    const r = await api("GET", "/api/discovery?case=" + encodeURIComponent(case_));
    app.discovery = r.data;
    addMessage({ kind: "discovery", name: "Discovery (GET /.well-known/ucp)", phase: "Negotiation", source: "LIVE CALL", not_ucp: false,
      method: "GET", path: "/.well-known/ucp", request: {}, response: { status: r.status, body: r.data } });
    if (!r.data || !r.data.ok) {
      return screen("The shop did not accept the request", panel("bad", "Setup problem", `<p>${esc(fmt("error.protocol", { code: r.status }))}</p><p>Code: <code>${esc(r.data && r.data.error)}</code></p>`) + startAgain());
    }
    openItems(false);
  }

  function startAgain() { return `<div class="actions"><button type="button" id="start-again">Start again</button></div>`; }
  document.addEventListener("click", (e) => { if (e.target && e.target.id === "start-again") sc1(); });

  function sc2(messagesHtml) {
    const d = app.discovery || {};
    screen("Shop and item", `
      <p>Shop: <code>${esc(d.endpoint)}</code></p>
      <p>Active capabilities: ${esc((d.active || []).join(", "))}</p>
      ${d.search_notice ? panel("warn", "Catalog search", `<p id="search-notice">${esc(d.search_notice)}</p>`) : ""}
      <div id="top-messages"></div>
      <div class="panel"><p class="panel-title">${ICON.info}<span>Demo T-shirt</span></p>
        <p class="muted">The shop gives the price when the checkout starts.</p>
        <label for="field-line-items-0">Quantity</label>
        <input id="field-line-items-0" type="number" min="1" max="9" inputmode="numeric" value="${esc(app.quantity)}">
        <label for="item-choice">Item</label>
        <select id="item-choice"><option value="demo_tshirt"${app.item === "demo_tshirt" ? " selected" : ""}>Demo T-shirt</option><option value="demo_mug"${app.item === "demo_mug" ? " selected" : ""}>Demo mug</option></select>
      </div>
      <p class="muted">${esc(S["agent.plan.create"])}</p>
      <div class="actions"><button type="button" class="primary" id="add">Add to checkout</button></div>`);
    if (messagesHtml) messagesHtml();
    on("add", () => addToCheckout($("item-choice").value));
  }

  // ---------------------------------------------------------------- S7 catalog (SC2a, SC2, M1a, M1b)
  // Source: 02-design.md UX-4.2a and UX-8.2 (spec v1.1.18, 7.12). UCP 2026-04-08 catalog REST:
  // https://ucp.dev/2026-04-08/specification/catalog/rest/ (commit 9c9d6fc).
  const CAT = "dev.ucp.shopping.catalog.";
  const catActive = (n) => ((app.discovery && app.discovery.active) || []).includes(CAT + n);
  const catalogOn = () => catActive("search") || catActive("lookup");
  const freshCat = () => ({ query: "", typed: "", products: [], cursor: null, hasNext: false, total: null, notes: [],
    state: "idle", seq: 0, dseq: 0, pending: null, opened: null, sent: false, planText: "", statusHtml: "", detailId: null });
  ICON.none = '<svg class="icon" aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="18" height="18"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2"/><path d="M5 19 19 5" stroke="currentColor" stroke-width="2"/></svg>';

  function money(a) {
    if (!a || typeof a.amount !== "number" || !a.currency) return "";
    try {
      const f = new Intl.NumberFormat("en-GB", { style: "currency", currency: a.currency });
      return f.format(a.amount / Math.pow(10, f.resolvedOptions().maximumFractionDigits));
    } catch (e) { return a.amount + " " + a.currency; }
  }
  function priceText(p) {
    const r = p.price_range, v = (p.variants || [])[0];
    if (r && r.min && r.max) {
      if (r.min.amount === r.max.amount && r.min.currency === r.max.currency) return money(r.min);
      return fmt("price.range", { min: money(r.min), max: money(r.max) });
    }
    return v ? money(v.price) : "";
  }
  const AVAIL = ["in_stock", "backorder", "preorder", "out_of_stock", "discontinued"];
  function availText(v) {
    const a = v && v.availability;
    if (!a) return "";
    if (AVAIL.includes(a.status)) return S["avail." + a.status];
    if (a.available === true) return S["avail.yes"];
    if (a.available === false) return S["avail.no"];
    return "";
  }
  function imgHtml(p) {
    const m = p.media && p.media[0];
    if (!m || m.type !== "image" || typeof m.url !== "string" || !/^https:\/\//i.test(m.url)) return "";
    return `<img class="thumb" src="${esc(m.url)}" alt="${esc(m.alt_text || "")}">`;
  }
  function notesOf(body) {
    return ((body && body.messages) || []).filter((m) => m && typeof m.content === "string" && m.content).map((m) => m.content);
  }
  function notesHtml(notes) {
    if (!notes.length) return "";
    return `<div class="notes"><h3>${esc(S["search.notes.heading"])}</h3><ul>${notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul></div>`;
  }
  function cardHtml(p, i) {
    const v = (p.variants || [])[0];
    const av = availText(v);
    return `<li class="card" data-product="${esc(p.id)}">${imgHtml(p)}<h4>${esc(p.title)}</h4><p class="price">${esc(priceText(p))}</p>` +
      `${av ? `<p class="avail">${esc(av)}</p>` : ""}` +
      `<button type="button" class="view" data-index="${i}">${esc(S["search.result.view"])}<span class="visually-hidden"> ${esc(p.title)}</span></button></li>`;
  }

  // The inspector rows M1a and M1b. The row exists before the answer (UX-7.6: Waiting, No response, Error).
  function pendingRow(name, mid) {
    $("inspector-empty").hidden = true;
    const n = app.messages.length + 1;
    const li = document.createElement("li");
    li.dataset.mid = mid;
    li.innerHTML = `<span class="msg pending">${esc(n)}. ${esc(name)} ${badge("LIVE CALL")} <span class="phase">Phase: Find product</span> <span class="row-state">Waiting</span></span>`;
    $("msg-list").appendChild(li);
    return { li, n };
  }
  function catalogRow(row, op, ans, body) {
    const search = op === "search";
    const entry = (ans.data && ans.data.inspector && ans.data.inspector[0]) || {
      name: search ? "Search Catalog" : "Get Product", op, mid: search ? "M1a" : "M1b", phase: "Find product",
      source: "LIVE CALL", not_ucp: false, method: "POST", path: search ? "/catalog/search" : "/catalog/product",
      request: { body }, response: { status: ans.timeout || !ans.status ? null : ans.status, body: ans.data },
    };
    entry.notes = [S["inspector.catalog.note"]];
    addMessage(ucpMessage(entry), { row });
  }
  function withTimeout(promise, ms) {
    return new Promise((resolve) => {
      const t = setTimeout(() => resolve({ timeout: true }), ms);
      promise.then((r) => { clearTimeout(t); resolve(r); }, () => { clearTimeout(t); resolve({ status: 0, data: null }); });
    });
  }
  // network: no answer. protocol: an HTTP error or ucp.status error. ok: a good answer.
  function classify(ans) {
    if (ans.timeout || ans.status === 0) return { kind: "network" };
    const d = ans.data || {};
    if (ans.status !== 200 || d.http_status === undefined) return { kind: "protocol", http: ans.status };
    if (d.http_status === null || d.transport_error) return { kind: "network" };
    const b = d.body || {};
    const code = b.messages && b.messages[0] && b.messages[0].code;
    if (d.http_status !== 200) return { kind: "protocol", http: d.http_status, code };
    if (b.ucp && b.ucp.status === "error") return { kind: "protocol", http: 200, code };
    return { kind: "ok", body: b };
  }
  const catalogMs = () => (app.cfg && app.cfg.catalog_ms) || 10000;

  // ---- SC2a: find a product
  function sc2a(keep, replayMode) {
    if (!keep || !app.cat) app.cat = freshCat();
    const c = app.cat;
    screen(S["search.heading"], `
      <form id="search-form" role="search" aria-labelledby="screen-title" novalidate>
        <label for="search-q">${esc(S["search.label"])}</label>
        <input id="search-q" name="q" type="text" maxlength="100" autocomplete="off" spellcheck="false" autocapitalize="off" aria-describedby="search-hint"${replayMode ? " readonly" : ""}>
        <p id="search-hint" class="hint muted">${esc(S["search.hint"])}</p>
        <p id="search-err" class="field-msg" hidden></p>
        <button type="submit" class="primary" id="search-go"${replayMode ? ' aria-disabled="true"' : ""}>${esc(S["search.submit"])}</button>
      </form>
      ${replayMode ? `<p id="replay-search-note" class="note">${esc(S["replay.search.note"])}</p>` : ""}
      <p id="search-plan" class="muted"></p>
      <p id="search-idle" class="muted"${c.sent ? " hidden" : ""}>${ICON.info} <span>${esc(S["search.idle"])}</span></p>
      <p id="search-status" role="status" aria-atomic="true"></p>
      <div id="search-alert" role="alert" aria-atomic="true"></div>
      <div id="search-notes"></div>
      <h3 id="results-h" hidden>${esc(S["search.results.heading"])}</h3>
      <ul id="results" class="cards" aria-labelledby="results-h" hidden></ul>
      <div class="actions"><button type="button" id="more" hidden>${esc(S["search.more"])}</button></div>
      <div id="top-messages"></div>`);
    $("search-q").value = c.typed;
    $("search-plan").textContent = c.planText;
    $("search-status").innerHTML = c.statusHtml;
    renderList();
    $("search-q").addEventListener("input", (e) => { c.typed = e.target.value; });
    $("search-form").addEventListener("submit", (e) => { e.preventDefault(); if (!app.replaying) doSearch({}); });
    $("more").addEventListener("click", () => { if (!app.replaying) doSearch({ more: true }); });
    $("results").addEventListener("click", (e) => {
      const b = e.target.closest && e.target.closest("button.view");
      if (b && !app.replaying) openProduct(Number(b.dataset.index));
    });
    if (keep && !replayMode) { // focus table: back to the product that the buyer opened
      const b = c.opened && document.querySelector(`#results li[data-product="${CSS.escape(c.opened)}"] button.view`);
      (b || $("screen-title")).focus();
    }
  }
  function renderList() {
    const c = app.cat;
    if (!$("results")) return;
    const has = c.products.length > 0;
    $("results-h").hidden = !has;
    $("results").hidden = !has;
    $("results").innerHTML = c.products.map(cardHtml).join("");
    $("results").setAttribute("aria-busy", c.state === "loading" || c.state === "loading-more" ? "true" : "false");
    $("more").hidden = !(c.hasNext && !c.state.startsWith("loading"));
    $("search-notes").innerHTML = notesHtml(c.notes);
  }
  function setStatus(html) { // the status and the alert never hold text together
    const c = app.cat;
    c.statusHtml = html;
    if ($("search-status")) { $("search-alert").innerHTML = ""; $("search-status").innerHTML = html; }
  }
  function countText(c) {
    return c.total !== null && c.total >= c.products.length
      ? fmt("search.count.total", { n: c.products.length, total: c.total }) : fmt("search.count", { n: c.products.length });
  }
  function summaryHtml(c) {
    return c.products.length ? `<span>${esc(countText(c))}</span>` : `${ICON.none} <span>${esc(fmt("search.none", { query: c.query }))}</span>`;
  }
  function fieldError(show) {
    const q = $("search-q"), e = $("search-err");
    e.hidden = !show;
    e.innerHTML = show ? ICON.warn + " " + esc(S["search.error.empty"]) : "";
    if (show) { q.setAttribute("aria-invalid", "true"); q.setAttribute("aria-describedby", "search-err search-hint"); q.focus(); }
    else { q.removeAttribute("aria-invalid"); q.setAttribute("aria-describedby", "search-hint"); }
  }
  function alertHtml(kind, http, retryId, extra) {
    const text = S[extra.prefix + (kind === "network" ? ".error.network" : ".error.protocol")];
    const again = kind === "network" || http === 429 || http === 503;
    return `<p class="field-msg">${ICON.stop} <span>${esc(text)}</span></p><div class="actions">` +
      (again ? `<button type="button" class="primary" id="${retryId}">Try again</button>` : `<button type="button" id="start-again">Start again</button>`) +
      (extra.back ? `<button type="button" id="back-results">${esc(S["detail.back"])}</button>` : "") + `</div>`;
  }
  async function doSearch(opts) {
    const c = app.cat;
    let req;
    if (opts.again) req = c.pending;
    else if (opts.more) req = { query: c.query, cursor: c.cursor, more: true };
    else {
      const q = $("search-q").value.trim();
      if (!q) return fieldError(true); // no call, no live text
      req = { query: q, cursor: null, more: false };
    }
    fieldError(false);
    c.pending = req;
    const seq = ++c.seq;
    c.sent = true;
    c.state = req.more ? "loading-more" : "loading";
    if (!req.more && !opts.again) { c.planText = fmt("agent.plan.search", { query: req.query }); $("search-plan").textContent = c.planText; }
    $("search-idle").hidden = true;
    setStatus(`<span>${esc(S[req.more ? "search.loading.more" : "search.loading"])}</span>`);
    renderList();
    event("buyer_action", req.more ? "Show more results" : "Search", { phase: "Find product" });
    await waitStep("Search Catalog");
    if (seq !== c.seq) return;
    const row = pendingRow("Search Catalog", "M1a");
    const body = { query: req.query };
    if (req.cursor) body.cursor = req.cursor;
    const ans = await withTimeout(api("POST", "/api/catalog/search", body), catalogMs());
    catalogRow(row, "search", ans, { query: req.query });
    if (seq !== c.seq) return; // a late answer for an old send changes nothing
    const cls = classify(ans);
    const before = c.products.length;
    if (cls.kind === "ok") {
      const b = cls.body, pg = b.pagination || {};
      const got = Array.isArray(b.products) ? b.products : [];
      c.products = req.more ? c.products.concat(got) : got;
      c.hasNext = pg.has_next_page === true && typeof pg.cursor === "string";
      c.cursor = c.hasNext ? pg.cursor : null;
      c.total = typeof pg.total_count === "number" ? pg.total_count : null;
      c.query = req.query;
      c.notes = notesOf(b);
      c.state = c.products.length ? "results" : "none";
      setStatus(summaryHtml(c));
      renderList();
      if (req.more && c.products.length > before && $("results")) {
        $("results").querySelectorAll("button.view")[before].focus(); // the first new product
      } else if ($("search-go") && (document.activeElement === document.body || !document.activeElement)) {
        $("search-go").focus();
      }
      return;
    }
    c.state = "error";
    renderList();
    if (!$("search-alert")) return;
    c.statusHtml = "";
    $("search-status").innerHTML = "";
    $("search-alert").innerHTML = alertHtml(cls.kind, cls.http, "search-retry", { prefix: "search" });
    const rb = $("search-retry") || $("start-again");
    if (rb) rb.focus();
    if ($("search-retry")) $("search-retry").addEventListener("click", () => doSearch({ again: true }));
  }

  // ---- SC2: product detail (Get Product, M1b). Lookup-only: the Item select stays.
  function sc2c(messagesHtml) {
    const d = app.discovery || {};
    const lookupOnly = !catActive("search");
    screen("Shop and item", `
      <p>Shop: <code>${esc(d.endpoint)}</code></p>
      <p>Active capabilities: ${esc((d.active || []).join(", "))}</p>
      ${d.search_notice ? panel("warn", "Catalog search", `<p id="search-notice" role="status">${esc(d.search_notice)}</p>`) : ""}
      <div id="top-messages"></div>
      ${lookupOnly ? `<label for="item-choice">Item</label>
        <select id="item-choice" aria-describedby="item-hint"><option value="demo_tshirt"${app.item === "demo_tshirt" ? " selected" : ""}>Demo T-shirt</option><option value="demo_mug"${app.item === "demo_mug" ? " selected" : ""}>Demo mug</option></select>
        <p id="item-hint" class="hint muted">${esc(S["item.hint"])}</p>` : ""}
      <p id="detail-status" role="status" aria-atomic="true"></p>
      <div id="detail-alert" role="alert" aria-atomic="true"></div>
      <div id="detail-body"></div>`);
    if (messagesHtml) messagesHtml();
    if (lookupOnly) $("item-choice").addEventListener("change", (e) => { app.item = e.target.value; loadDetail(e.target.value); });
  }
  function openProduct(i) {
    const c = app.cat, p = c.products[i];
    if (!p) return;
    c.opened = p.id;
    event("buyer_action", "View details", { phase: "Find product" });
    sc2c();
    loadDetail(p.id);
  }
  function openItems(keep, messagesHtml) { // the target of "Back to items" and "Change item"
    if (catActive("search")) { sc2a(keep); if (messagesHtml) messagesHtml(); return Promise.resolve(); }
    if (catActive("lookup")) { sc2c(messagesHtml); return loadDetail(app.item); }
    return sc2(messagesHtml);
  }
  async function loadDetail(id) {
    const c = app.cat || (app.cat = freshCat());
    const seq = ++c.dseq;
    c.detailId = id;
    const back = catActive("search");
    $("detail-alert").innerHTML = "";
    $("detail-body").innerHTML = "";
    if (!catActive("lookup")) { // search only: no Get Product. Use the card (T-119, no call)
      const p = c.products.find((x) => x.id === id);
      return p ? renderDetail(p, []) : detailGone();
    }
    $("detail-status").textContent = S["detail.loading"];
    await waitStep("Get Product");
    if (seq !== c.dseq || !$("detail-body")) return;
    const row = pendingRow("Get Product", "M1b");
    const ans = await withTimeout(api("POST", "/api/catalog/product", { id }), catalogMs());
    catalogRow(row, "product", ans, { id });
    if (seq !== c.dseq || !$("detail-body")) return;
    const cls = classify(ans);
    $("detail-status").textContent = "";
    if (cls.kind === "ok") return renderDetail(cls.body.product || {}, notesOf(cls.body));
    if (cls.kind === "protocol" && cls.code === "not_found") return detailGone(); // AC-12.15: by code
    $("detail-alert").innerHTML = alertHtml(cls.kind, cls.http, "detail-retry", { prefix: "detail", back });
    const rb = $("detail-retry") || $("start-again");
    if (rb) rb.focus();
    if ($("detail-retry")) $("detail-retry").addEventListener("click", () => loadDetail(id));
    on("back-results", () => openItems(true));
  }
  function detailGone() { // ST16 text. 02-design F25 says unrecoverable. The spec says recoverable (AC-12.15).
    screen("This item is not available", panel("bad", "This item is not available", `<p>${esc(S["error.unrecoverable"])}</p>`) +
      `<div class="actions"><button type="button" class="primary" id="back-items">Back to items</button></div>`);
    on("back-items", () => openItems(true));
  }
  function renderDetail(p, notes) {
    const v = (p.variants || [])[0];
    const av = availText(v);
    const d = p.description || {};
    const text = d.plain || d.markdown || ""; // never `html`
    const unavailable = !v || (v.availability && v.availability.available === false);
    const price = v ? money(v.price) : priceText(p);
    $("detail-body").innerHTML = `
      <div class="panel" id="detail-card">${imgHtml(p)}<h3>${esc(p.title)}</h3><p class="price">${esc(price)}</p>
        ${av ? `<p class="avail">${esc(av)}</p>` : ""}${text ? `<p class="desc">${esc(text)}</p>` : ""}${notesHtml(notes)}
        <label for="field-line-items-0">Quantity</label>
        <input id="field-line-items-0" type="number" min="1" max="9" inputmode="numeric" value="${esc(app.quantity)}"></div>
      <p class="muted">${esc(S["agent.plan.create"])}</p>
      <div class="actions"><button type="button" class="primary" id="add"${unavailable ? ' disabled aria-describedby="add-unavailable"' : ""}>Add to checkout</button>
        ${unavailable ? `<span id="add-unavailable" class="field-msg">${esc(S["detail.unavailable"])}</span>` : ""}
        ${catActive("search") ? `<button type="button" id="back-results">${esc(S["detail.back"])}</button>` : ""}</div>`;
    if (!unavailable) on("add", () => addToCheckout(v.id)); // M2 gets the variant id
    on("back-results", () => openItems(true));
  }
  async function addToCheckout(itemId) {
    app.quantity = Math.max(1, parseInt($("field-line-items-0").value, 10) || 1);
    app.item = itemId;
    event("buyer_action", "Add to checkout", { phase: "Negotiation" });
    await waitStep("Create Checkout");
    const r = await api("POST", "/api/checkout", { line_items: [{ item: { id: app.item }, quantity: app.quantity }],
      fulfillment: { methods: [{ type: "shipping", destinations: [dest()], selected_destination_id: "d1" }] } });
    handle(r, "create");
  }

  // ---- replay: SC2a shows the saved query and the saved list. No call goes out.
  function replaySearch(m) {
    const rq = (m.request && m.request.body) || {};
    const b = (m.response && m.response.body) || {};
    const paged = !!(rq.pagination && rq.pagination.cursor) || !!rq.cursor;
    if (!$("search-form")) { app.cat = freshCat(); sc2a(true, true); }
    const c = app.cat;
    const pg = b.pagination || {};
    const got = Array.isArray(b.products) ? b.products : [];
    c.products = paged ? c.products.concat(got) : got;
    c.hasNext = false; // Show more does nothing in a replay
    c.total = typeof pg.total_count === "number" ? pg.total_count : null;
    c.query = typeof rq.query === "string" ? rq.query : c.query;
    c.notes = notesOf(b);
    c.sent = true;
    c.state = c.products.length ? "results" : "none";
    $("search-q").value = c.query;
    $("search-idle").hidden = true;
    c.statusHtml = summaryHtml(c);
    $("search-status").innerHTML = c.statusHtml;
    renderList();
  }

  function dest() {
    const b = app.buyer;
    return { id: "d1", street_address: b.street_address || "1 Test Street", address_locality: b.address_locality || "London",
      postal_code: b.postal_code || "SW1A 1AA", address_country: b.address_country || "GB" };
  }

  function sc3(messagesHtml) {
    const b = app.buyer;
    const field = (id, label, key, type, ac) => `<label for="${id}">${esc(label)}</label><input id="${id}" name="${key}" type="${type}" autocomplete="${ac}" value="${esc(b[key])}">`;
    screen("Your details", `
      <div id="top-messages"></div>
      <fieldset id="field-buyer"><legend>Contact</legend>
        ${field("field-buyer-email", "Email", "email", "email", "email")}
        ${field("field-buyer-first-name", "First name", "first_name", "text", "given-name")}
        ${field("field-buyer-last-name", "Last name", "last_name", "text", "family-name")}
      </fieldset>
      <fieldset id="field-fulfillment-methods-0-destinations-0"><legend>Delivery address</legend>
        ${field("addr-street", "Street", "street_address", "text", "address-line1")}
        ${field("addr-city", "Town or city", "address_locality", "text", "address-level2")}
        ${field("addr-postcode", "Postcode", "postal_code", "text", "postal-code")}
        <label for="addr-country">Country</label>
        <select id="addr-country" name="address_country" autocomplete="country"><option value="GB"${b.address_country === "GB" ? " selected" : ""}>United Kingdom</option><option value="FR"${b.address_country === "FR" ? " selected" : ""}>France</option></select>
      </fieldset>
      <p class="muted">${esc(S["agent.plan.update"])}</p>
      <div class="actions"><button type="button" class="primary" id="continue">Continue to review</button><button type="button" id="cancel-checkout">Cancel checkout</button></div>`);
    if (messagesHtml) messagesHtml();
    on("cancel-checkout", cancelCheckout);
    on("continue", async () => {
      document.querySelectorAll("#screen input[name], #screen select[name]").forEach((i) => { app.buyer[i.name] = i.value.trim(); });
      event("buyer_action", "Continue to review", { phase: "Negotiation" });
      const c = app.checkout;
      const m = c.fulfillment.methods[0];
      const buyer = {};
      ["email", "first_name", "last_name"].forEach((k) => { if (app.buyer[k]) buyer[k] = app.buyer[k]; }); // AC-15: never invent a value
      const body = { line_items: c.line_items.map((li) => ({ id: li.id, item: { id: li.item.id }, quantity: li.quantity })),
        fulfillment: { methods: [{ id: m.id, type: m.type, line_item_ids: m.line_item_ids, destinations: [dest()], selected_destination_id: "d1",
          groups: (m.groups || []).map((g) => ({ id: g.id, selected_option_id: (g.options && g.options[0] && g.options[0].id) || g.selected_option_id })) }] } };
      if (Object.keys(buyer).length) body.buyer = buyer;
      await waitStep("Update Checkout");
      handle(await api("PUT", "/api/checkout/" + encodeURIComponent(c.id), body), "update");
    });
  }

  // Message placement (AC-14): after the field that `path` names, with aria-describedby. Else at the top.
  function placeMessages(view) {
    const top = $("top-messages");
    (view.messages || []).forEach((m) => {
      const p = document.createElement("p");
      p.id = m.element_id;
      p.className = "field-msg";
      p.innerHTML = ICON.warn + " " + esc(m.content);
      const target = m.field_id ? document.getElementById(m.field_id) : null;
      if (target) {
        target.insertAdjacentElement("afterend", p);
        const ids = (target.getAttribute("aria-describedby") || "").split(" ").filter(Boolean);
        ids.push(p.id);
        target.setAttribute("aria-describedby", ids.join(" "));
      } else if (top) {
        top.appendChild(p);
      }
    });
  }

  function recordCalls(data) { (data && data.inspector || []).forEach((c) => addMessage(ucpMessage(c))); }

  function handle(r, op) {
    const data = r.data || {};
    recordCalls(data);
    const v = data.view;
    if (!v) return screen("The shop did not accept the request", panel("bad", "Setup problem", `<p>${esc(fmt("error.protocol", { code: r.status }))}</p>`) + startAgain());
    if (v.checkout) app.checkout = v.checkout;
    app.retryId = data.retry_id;
    const codes = (v.messages || []).map((m) => m.code);
    if (v.state === "setup_problem") return setupProblem(v.problem, data.retry_id);
    if (v.state === "requires_escalation") return escalation(v);
    if (v.state === "canceled") return canceled();
    const ac14 = codes.some((c) => c === "out_of_stock" || c === "address_undeliverable" || c === "item_unavailable");
    if (ac14) {
      const toItems = !codes.includes("address_undeliverable");
      if (toItems && catalogOn()) { // S7: "Change item" opens the item screen of the active catalog
        openItems(true, () => {
          placeMessages(v);
          if (v.checkout) {
            $("top-messages").insertAdjacentHTML("beforeend", '<div class="actions"><button type="button" id="cancel-checkout">Cancel checkout</button></div>');
            on("cancel-checkout", cancelCheckout);
          }
        });
        return;
      }
      const render = toItems ? sc2 : sc3;
      render(() => {
        placeMessages(v);
        const acts = $("screen").querySelector(".actions");
        acts.innerHTML = toItems
          ? `<button type="button" class="primary" id="add">Change item</button>${v.checkout ? '<button type="button" id="cancel-checkout">Cancel checkout</button>' : ""}`
          : `<button type="button" class="primary" id="continue">Change address</button>${v.checkout ? '<button type="button" id="cancel-checkout">Cancel checkout</button>' : ""}`;
      });
      // the buttons were replaced: wire them again
      if (toItems) rewireAdd(); else rewireContinue();
      on("cancel-checkout", cancelCheckout);
      return;
    }
    const sev = (v.messages || []).filter((m) => m.type === "error").map((m) => m.severity);
    if (sev.includes("unrecoverable")) { // AC-17
      screen("This item is not available", panel("bad", "This item is not available", `<p>${esc(S["error.unrecoverable"])}</p><div id="top-messages"></div>`) +
        `<div class="actions"><button type="button" class="primary" id="back-items">Back to items</button></div>`);
      placeMessages(v);
      on("back-items", () => openItems(true));
      return;
    }
    if (v.ask_buyer && v.ask_buyer.length) { // AC-15: ask the buyer, invent nothing
      sc3(() => {
        placeMessages(v);
        $("top-messages").insertAdjacentHTML("afterbegin", panel("warn", "The shop needs more details", "<p>Enter the details that the shop asks for. The agent does not make up a value.</p>"));
      });
      return;
    }
    if (op === "create") return sc3();
    if (v.state === "ready_for_complete") return reviewStep();
    sc3(() => placeMessages(v));
  }
  function rewireAdd() { const b = $("add"); if (!b) return; const nb = b.cloneNode(true); b.replaceWith(nb); nb.addEventListener("click", () => sc2()); }
  function rewireContinue() { const b = $("continue"); if (!b) return; const nb = b.cloneNode(true); b.replaceWith(nb); nb.addEventListener("click", () => sc3()); }

  function setupProblem(p, retryId) {
    if (p.kind === "transport") {
      screen("We cannot reach the shop", panel("bad", "No response", `<p>${esc(S["error.network"])}</p><p>Code: <code>${esc(p.code)}</code>. Tries: ${esc(p.tries)}.</p>`) +
        `<div class="actions">${retryId ? '<button type="button" class="primary" id="try-again">Try again</button>' : ""}<button type="button" id="start-again">Start again</button></div>`);
    } else {
      const retry = retryId && (p.http_status === 429 || p.http_status === 503);
      screen("The shop did not accept the request", panel("bad", "Setup problem, not a payment problem",
        `<p>${esc(fmt("error.protocol", { code: p.http_status }))}</p><p>Code: <code id="problem-code">${esc(p.code)}</code></p>${p.content ? `<p>${esc(Array.isArray(p.content) ? p.content.join("; ") : p.content)}</p>` : ""}`) +
        `<div class="actions">${retry ? '<button type="button" class="primary" id="try-again">Try again</button>' : ""}<button type="button" id="start-again">Start again</button></div>`);
    }
    on("try-again", async () => {
      event("buyer_action", "Try again", { phase: "Negotiation" });
      const r = await api("POST", "/api/retry/" + encodeURIComponent(retryId));
      handle(r, r.data && r.data.inspector && r.data.inspector[0] ? r.data.inspector[0].op : "update");
    });
  }
  function escalation(v) { // AC-16: a link to continue_url, no Complete
    const url = v.continue_url;
    screen("Finish on the shop website", panel("warn", "The shop needs more information", `<p>${esc(S["escalation"])}</p>`) +
      `<div class="actions">${url ? `<a class="button" id="continue-url" href="${esc(url)}" target="_blank" rel="noopener">Continue on the shop website</a>` : `<p id="no-link">${esc(S["escalation.noLink"])}</p>`}<button type="button" id="back-items">Back to items</button></div>`);
    on("back-items", () => openItems(true));
  }
  function canceled() {
    screen("Checkout stopped", panel("info", "You did not pay", `<p>${esc(S["canceled"])}</p>`) +
      `<div class="actions"><button type="button" class="primary" id="new-checkout">Start a new checkout</button></div>`);
    on("new-checkout", () => { app.checkout = null; openItems(true); });
  }
  async function cancelCheckout() { // AC-30
    event("buyer_action", "Cancel checkout", { phase: "Negotiation" });
    const r = await api("POST", "/api/checkout/" + encodeURIComponent(app.checkout.id) + "/cancel");
    handle(r, "cancel");
  }

  // ---------------------------------------------------------------- SC4 review and pay
  async function reviewStep(notice) {
    await waitStep("Get Checkout (review)");
    const r = await api("GET", "/api/checkout/" + encodeURIComponent(app.checkout.id) + "/review");
    recordCalls(r.data);
    renderReview(r.data, notice);
  }
  function linkText(t) { return { privacy_policy: "Privacy policy", terms_of_service: "Terms of service", refund_policy: "Refund policy", shipping_policy: "Shipping policy", faq: "FAQ" }[t] || t; }
  function renderReview(data, notice, opts) {
    const v = data.view;
    const rv = data.review || {};
    if (v.state === "setup_problem") return setupProblem(v.problem, data.retry_id);
    if (v.state === "requires_escalation") return escalation(v);
    if (v.state !== "ready_for_complete") return handle({ status: data.http_status, data: Object.assign({}, data, { inspector: [] }) }, "get");
    app.review = rv;
    const items = (rv.line_items || []).map((li) => `<tr><td>${esc(li.title)}</td><td class="num">${esc(li.quantity)}</td><td class="num">${esc(li.total)}</td></tr>`).join("");
    const totals = (rv.totals || []).map((t) => `<tr${t.type === "total" ? ' class="grand"' : ""}><th scope="row">${esc(t.label)}</th><td class="num">${esc(t.text)}</td></tr>`).join("");
    const links = (rv.links || []).map((l) => `<li><a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.title || linkText(l.type))}</a></li>`).join("");
    let gate = "";
    if ((rv.totals_problems || []).length) {
      gate = panel("bad", "Totals do not add up", `<p id="totals-mismatch">${esc(S["totals.mismatch"])}</p><ul>${rv.totals_problems.map((p) => `<li>Problem: <code>${esc(p)}</code></li>`).join("")}</ul>` +
        (rv.continue_url ? `<p><a id="continue-url" href="${esc(rv.continue_url)}" target="_blank" rel="noopener">Continue on the shop website</a></p>` : `<p id="no-link">${esc(S["escalation.noLink"])} Cancel the checkout or start again.</p>`), "gate-panel");
    } else if ((rv.gate || []).length) {
      gate = panel("bad", rv.gate[0].code === "not_test" ? "Demo stopped" : "The agent cannot pay", rv.gate.map((g) => `<p data-code="${esc(g.code)}">${esc(g.text)}</p>`).join(""), "gate-panel");
    } else if (!rv.ok) {
      gate = panel("bad", "The payment step stopped", `<p>The Google Pay handler config from the shop is not valid.</p><ul>${(rv.problems || []).map((p) => `<li>Problem: <code>${esc(p)}</code></li>`).join("")}</ul>`, "gate-panel");
    }
    screen("Review and pay", `
      ${notice ? panel("warn", "The order changed", `<p>${esc(notice)}</p>`) : ""}
      <p>${esc(S["agent.handover"])}</p>
      <h2>Items</h2>
      <table><thead><tr><th scope="col">Item</th><th scope="col" class="num">Quantity</th><th scope="col" class="num">Amount</th></tr></thead><tbody>${items}</tbody></table>
      <h2>Totals</h2>
      <table><tbody>${totals}</tbody></table>
      <p>Currency: <span id="currency">${esc(rv.currency)}</span></p>
      ${rv.total_text ? `<p><strong id="total-to-pay">${esc(fmt("review.total", { amount: rv.total_text }))}</strong></p>` : ""}
      <h2>Shop terms</h2><ul id="links">${links}</ul>
      ${gate}
      <div id="gpay-state"></div>
      <div id="gpay-area" ${rv.ok ? "" : "hidden"}><div id="gpay-container"></div></div>
      <div class="actions"><button type="button" id="cancel-checkout">Cancel checkout</button></div>`);
    on("cancel-checkout", cancelCheckout);
    if (rv.ok && opts && opts.declined && app.paymentsClient) {
      // ST13 to ST07: the same Google Pay button again. A new click gives a new token.
      $("gpay-container").appendChild(app.paymentsClient.createButton({ onClick: onGpayClick, buttonType: "buy", buttonColor: "black", buttonSizeMode: "fill" }));
    } else if (rv.ok) acquisition(rv);
  }

  function gpaySource() { return app.cfg.gpay === "stub" ? "SIMULATED" : "GOOGLE PAY TEST"; }
  function loadGpay() {
    if (!app.gpayLoaded) {
      app.gpayLoaded = new Promise((resolve, reject) => {
        const s = document.createElement("script");
        s.src = app.cfg.gpay_script;
        s.async = true;
        s.onload = () => resolve();
        s.onerror = () => reject(new Error("Google Pay script did not load"));
        document.head.appendChild(s);
      });
    }
    return app.gpayLoaded;
  }
  async function acquisition(rv) {
    const g = rv.gpay;
    addMessage({ kind: "gpay", name: "Mapping: PaymentDataRequest", phase: "Acquisition", source: "LOCAL STEP", not_ucp: true,
      request: { environment: g.environment, paymentDataRequest: g.payment_data_request }, result: "built" });
    try { await loadGpay(); } catch (e) { return gpayUnavailable("script"); }
    app.paymentsClient = new google.payments.api.PaymentsClient({ environment: g.environment });
    let ready = false;
    try {
      const res = await app.paymentsClient.isReadyToPay(g.is_ready_to_pay_request);
      ready = Boolean(res && res.result);
    } catch (e) { ready = false; }
    addMessage({ kind: "gpay", name: "isReadyToPay", phase: "Acquisition", source: gpaySource(), not_ucp: true, request: g.is_ready_to_pay_request, result: ready });
    event("gpay", "isReadyToPay", { phase: "Acquisition", source: gpaySource(), not_ucp: true, result: ready });
    if (!ready) return gpayUnavailable(false); // AC-28
    const button = app.paymentsClient.createButton({ onClick: onGpayClick, buttonType: "buy", buttonColor: "black", buttonSizeMode: "fill" });
    $("gpay-container").appendChild(button);
  }
  function gpayUnavailable(why) {
    $("gpay-area").hidden = true;
    $("gpay-state").innerHTML = panel("warn", "Google Pay is not available", `<p id="gpay-unavailable">${esc(S["gpay.unavailable"])}</p><p>${esc(S["gpay.checkResult"])} <code>${esc(why)}</code></p>` +
      `<div class="actions"><button type="button" id="use-replay">Use replay</button></div>`);
    on("use-replay", () => replay());
  }

  // AC-77: loadPaymentData is the first call in the click handler. No agent step comes before it.
  function onGpayClick() {
    const rv = app.review;
    const p = app.paymentsClient.loadPaymentData(rv.gpay.payment_data_request);
    $("gpay-state").innerHTML = `<p id="gpay-wait">${esc(S["review.wait"])}</p>`;
    announce(S["review.wait"]);
    p.then((pd) => {
      const shown = JSON.parse(JSON.stringify(pd));
      if (shown.paymentMethodData && shown.paymentMethodData.tokenizationData) shown.paymentMethodData.tokenizationData.token = MASK;
      addMessage({ kind: "gpay", name: "loadPaymentData", phase: "Acquisition", source: gpaySource(), not_ucp: true, request: rv.gpay.payment_data_request, response: { body: shown }, result: "approved" });
      event("gpay", "loadPaymentData", { phase: "Acquisition", source: gpaySource(), not_ucp: true, result: "approved" });
      pay(pd); // AC-98: Complete after the sheet approval, with no other buyer click
    }, (err) => {
      const code = (err && err.statusCode) || "ERROR";
      addMessage({ kind: "gpay", name: "loadPaymentData", phase: "Acquisition", source: gpaySource(), not_ucp: true, request: rv.gpay.payment_data_request, result: code });
      event("gpay", "loadPaymentData", { phase: "Acquisition", source: gpaySource(), not_ucp: true, result: code });
      if (code === "CANCELED") { // AC-29: no UCP request, the checkout stays open
        $("gpay-state").innerHTML = panel("info", "You did not pay", `<p id="buyer-canceled">${esc(S["cancel.buyer"])}</p>`);
        announce(S["cancel.buyer"]);
        const b = $("gpay-container").querySelector("button");
        if (b) b.focus();
      } else {
        $("gpay-state").innerHTML = panel("bad", "Google Pay setup problem", `<p>Google Pay returned this code: <code>${esc(code)}</code>. This is a problem in the demo setup, not a payment problem.</p>`);
      }
    });
  }
  async function pay(pd) {
    const rv = app.review;
    screen("Placing your order", `<p id="placing">${esc(S["placing"])}</p><p class="muted">Step: Complete Checkout.</p>`);
    announce(S["placing"]);
    const r = await api("POST", "/api/checkout/" + encodeURIComponent(app.checkout.id) + "/pay", { approval_hash: rv.approval_hash, payment_data: pd });
    pd = null;
    if (r.status === 409) return screen("Payment already sent", panel("info", "No second payment", `<p>${esc((r.data && r.data.content) || "")}</p>`));
    const data = r.data || {};
    if (data.outcome === "changed") { recordCalls(data); return renderReview(data, S["review.changed"]); }
    // M7 (AC-63): the instrument mapping row comes before the Complete row.
    if (data.m7) addMessage({ kind: "mapping", name: "Mapping: M7 card_payment_instrument", phase: "Acquisition", source: "LOCAL STEP", not_ucp: true, request: data.m7.input, response: { body: data.m7.output }, result: "built" });
    // M9 (ST13): the Platform does not see M9. The row shows what the M10 response tells.
    if (data.m9) addMessage({ kind: "psp", name: "M9: mock PSP charge (Business to PSP)", phase: "Completion", source: "SIMULATED", not_ucp: true, result: data.m9.result });
    const declined = data.m9 && data.m9.result === "declined";
    (data.inspector || []).forEach((c) => {
      const m = ucpMessage(c);
      m.notes = [];
      if (app.declines > 0) m.notes.push(S["inspector.retry.newKey"]);
      if (declined) m.notes.push(S["inspector.m10.declined"]);
      // UX-4.5.1: the Platform server sets same_key only in CI mode, when 3 records agree.
      if (c.op === "complete" && c.same_key === true) m.notes.push(S["inspector.retry.sameKey"]);
      if (c.op === "complete" && data.response_signature) m.notes.push(fmt("inspector.signature", { result: data.response_signature }));
      addMessage(m);
    });
    const v = data.view;
    if (v && v.checkout && v.checkout.status === "completed") return confirmed(v.checkout);
    if (declined) return declinedPanel(data.m9.declines || app.declines + 1);
    if (v) handle({ status: r.status, data: Object.assign({}, data, { inspector: [] }) }, "complete");
  }

  // AC-33, AC-79: the order confirmation. The order id comes from the shop.
  function confirmed(c) {
    const o = c.order || {};
    screen("Order confirmed", panel("info", "The shop placed your order", `<p id="simulated-payment">Simulated payment. No money moved.</p>` +
      `<p>Order ID: <code id="order-id">${esc(o.id)}</code></p>` +
      (o.permalink_url ? `<p><a id="order-link" href="${esc(o.permalink_url)}" target="_blank" rel="noopener">View the order on the shop website</a></p>` : "")) +
      `<section id="order-events" aria-labelledby="order-events-title"><h2 id="order-events-title">${esc(S["order.events.title"])}</h2>` +
      `<ol id="order-steps"></ol><p id="order-tracking"></p>` +
      `<div class="actions"><button type="button" id="reconcile">${esc(S["order.reconcile"])}</button></div><p id="reconcile-result" role="status"></p></section>` +
      startAgain());
    on("reconcile", () => reconcile(o.id));
    if (o.id) pollOrder(o.id, 0);
  }
  // AC-74 (T-69): the order events come from the Platform webhook receiver (a server feed).
  async function pollOrder(id, n) {
    if (app.replaying || !$("order-steps")) return;
    const r = await api("GET", "/api/orders/" + encodeURIComponent(id));
    if (r.status === 200 && r.data) renderOrder(r.data);
    const done = r.data && r.data.state === "delivered";
    if (!done && n < 60) setTimeout(() => pollOrder(id, n + 1), 500);
  }
  function renderOrder(v) {
    const ol = $("order-steps");
    if (!ol) return;
    ol.innerHTML = (v.steps || []).map((s) => `<li data-state="${esc(s.state)}">${esc(S["order." + s.state])} <span class="badge simulated">${esc(S["order.simulated"])}</span></li>`).join("");
    $("order-tracking").textContent = v.tracking && v.tracking.number ? fmt("order.tracking", { number: v.tracking.number }) : "";
    app.seenHooks = app.seenHooks || {};
    (v.webhooks || []).forEach((w, i) => {
      const key = (w.webhook_id || "") + ":" + i;
      if (app.seenHooks[key]) return;
      app.seenHooks[key] = true;
      addMessage({ kind: "webhook", name: "M11: Order webhook " + (w.event_type || ""), phase: "Post-purchase", source: "SIMULATED", not_ucp: false,
        notes: ["Signature: " + (w.signature || "none") + "."], request: { headers: { "Webhook-Id": w.webhook_id, "Webhook-Timestamp": w.webhook_timestamp } }, response: { status: w.status, body: { code: w.code } } });
    });
  }
  async function reconcile(id) { // AC-73 (T-43)
    const r = await api("POST", "/api/orders/" + encodeURIComponent(id) + "/reconcile");
    const d = r.data || {};
    recordCalls(d);
    $("reconcile-result").textContent = d.match ? fmt("order.reconcile.same", { state: d.get_state }) : fmt("order.reconcile.differ", { get: d.get_state || "none", hook: d.webhook_state || "none" });
  }
  // ST13 (T-105, UX-7.3): SC4 with a decline panel. The focus moves to the panel heading.
  function declinedPanel(count) {
    app.declines = count;
    const again = count > 1;
    const rv = app.review;
    renderReview({ view: { state: "ready_for_complete" }, review: rv }, null, { declined: true });
    const html = `<div class="panel declined" id="declined-panel">
      <h2 class="panel-title" id="declined-heading" tabindex="-1">${ICON.warn}<span>${esc(S[again ? "declined.again.heading" : "declined.heading"])}</span></h2>
      <p id="declined-body">${esc(S[again ? "declined.again.body" : "declined.body"])}</p>
      <p id="declined-simulated">${esc(S["declined.simulated"])}</p></div>`;
    $("gpay-state").insertAdjacentHTML("beforebegin", html);
    $("gpay-area").insertAdjacentHTML("afterbegin", `<p id="declined-retry-hint">${esc(S["declined.retry.hint"])}</p>`);
    $("declined-heading").focus();
    announce(S[again ? "declined.again.announce" : "declined.announce"]);
  }

  // ---------------------------------------------------------------- replay (AC-62): no calls
  async function replay() {
    if (!app.messages.length) {
      return screen("Replay", panel("info", "No recording", "<p>There is no recording in this session. Run the demo with live calls first.</p>") + startAgain());
    }
    app.replaying = true;
    setBanner(true);
    $("msg-list").innerHTML = "";
    $("msg-detail").hidden = true;
    screen("Replay", `<p>${esc(S["banner.replay"])}</p>`);
    for (let i = 0; i < app.messages.length; i++) {
      const m = app.messages[i];
      // UX-4.4: in replay the Google Pay button shows the recorded sheet result. It does not open
      // the Google Pay sheet: no loadPaymentData call and no call to Google (AC-62, UX-AC-19).
      if (m.kind === "gpay" && m.name === "loadPaymentData") await replaySheet(m);
      else await waitStep("recorded message " + (i + 1));
      if (m.op === "search") replaySearch(m); // S7: SC2a with the saved query and list. No call.
      addMessage(m, { replay: true, n: i + 1 });
    }
    $("screen").insertAdjacentHTML("beforeend", `<p id="replay-done">The replay is complete.</p>` + startAgain());
  }
  function replaySheet(m) {
    $("screen").insertAdjacentHTML("beforeend",
      `<div class="actions" id="replay-gpay-step"><button type="button" id="replay-gpay">${esc(S["replay.gpay.button"])}</button></div>` +
      '<p id="replay-sheet-result" role="status"></p>');
    return new Promise((resolve) => {
      on("replay-gpay", () => {
        $("replay-gpay").disabled = true;
        $("replay-sheet-result").textContent = fmt("replay.gpay.result", { result: m.result });
        resolve();
      });
    });
  }
  function setBanner(replay) {
    // UX-AC-20: the banner always starts with banner.test.label. It never shows a source label.
    $("mode-banner").classList.toggle("replay", replay);
    $("banner-label").textContent = S["banner.test.label"];
    $("banner-detail").textContent = replay ? S["banner.replay"] : S["banner.test"];
  }

  // ---------------------------------------------------------------- start
  async function boot() {
    const r = await fetch("/checkout/config.json");
    app.cfg = await r.json();
    const q = new URLSearchParams(location.search);
    if (q.get("auto_ms")) app.cfg.auto_ms = parseInt(q.get("auto_ms"), 10);
    if (q.get("catalog_ms")) app.cfg.catalog_ms = parseInt(q.get("catalog_ms"), 10);
    $("inspector-body").classList.add("closed");
    sc1();
  }
  boot();
})();
