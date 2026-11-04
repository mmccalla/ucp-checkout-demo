"""G7 helpers: keyboard driving, the tab sequence (AC-80) and the page audits (AC-82 to AC-85)."""

from __future__ import annotations

import json
import pathlib
from typing import Any

from playwright.sync_api import Page

FOCUSABLE_JS = r"""
() => {
  const sel = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';
  const visible = (e) => { const s = getComputedStyle(e); const r = e.getBoundingClientRect();
    return s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0 && !e.closest('[hidden]') && !e.closest('details:not([open]) > :not(summary)'); };
  const regionOf = (e) => e.closest('#mode-banner') ? 'mode-banner' : e.closest('#buyer-view') ? 'buyer-view' : e.closest('#inspector') ? 'inspector' : 'other';
  const out = []; const seenRadio = new Set();
  for (const e of document.querySelectorAll(sel)) {
    if (!visible(e)) continue;
    if (e.type === 'radio') {
      if (seenRadio.has(e.name)) continue;
      const group = [...document.querySelectorAll(`input[type=radio][name="${e.name}"]`)];
      const pick = group.find((x) => x.checked) || group[0];
      seenRadio.add(e.name);
      out.push({ key: key(pick), region: regionOf(pick) });
      continue;
    }
    out.push({ key: key(e), region: regionOf(e) });
  }
  function key(e) { return (e.id ? '#' + e.id : e.tagName.toLowerCase() + ':' + (e.textContent || e.value || '').trim().slice(0, 40)); }
  return out;
}
"""
ACTIVE_JS = r"""
() => { const e = document.activeElement; if (!e || e === document.body) return {key: 'body', region: 'none'};
  const regionOf = (e) => e.closest('#mode-banner') ? 'mode-banner' : e.closest('#buyer-view') ? 'buyer-view' : e.closest('#inspector') ? 'inspector' : 'other';
  return { key: e.id ? '#' + e.id : e.tagName.toLowerCase() + ':' + (e.textContent || e.value || '').trim().slice(0, 40), region: regionOf(e) }; }
"""


def tab_sequence(page: Page, screen: str, log: list[dict[str, Any]]) -> None:
    """AC-80: focus is on h1, then Tab visits banner, buyer view and inspector controls in DOM order."""
    active = page.evaluate(ACTIVE_JS)
    assert active["key"] == "#screen-title", (screen, active)
    expected = page.evaluate(FOCUSABLE_JS)
    seen: list[dict[str, Any]] = []
    # From the h1, Tab goes to the next control in DOM order. Start from the top of the page.
    page.evaluate("document.activeElement.blur(); window.getSelection().removeAllRanges();")
    page.evaluate(
        "() => { const a = document.createElement('span'); a.tabIndex = -1; a.id='__tabstart'; document.body.prepend(a); a.focus(); }"
    )
    for _ in range(len(expected) + 3):
        page.keyboard.press("Tab")
        a = page.evaluate(ACTIVE_JS)
        if a["key"] in ("body", "#__tabstart") or (seen and a["key"] == seen[0]["key"]):
            break
        seen.append(a)
    page.evaluate("document.getElementById('__tabstart').remove()")
    page.locator("#screen-title").focus()
    order = {"mode-banner": 0, "buyer-view": 1, "inspector": 2}
    regions = [order.get(s["region"], 9) for s in seen]
    entry = {
        "screen": screen,
        "expected": [e["key"] for e in expected],
        "seen": [s["key"] for s in seen],
        "regions": [s["region"] for s in seen],
        "pass": [s["key"] for s in seen] == [e["key"] for e in expected]
        and regions == sorted(regions),
    }
    log.append(entry)
    assert entry["pass"], json.dumps(entry, indent=1)


def kb_activate(page: Page, selector: str, key: str = "Enter", limit: int = 80) -> None:
    """Move the focus with Tab only, then press a key. No mouse."""
    for _ in range(limit):
        if page.evaluate(
            "(s) => document.activeElement && document.activeElement.matches(s)", selector
        ):
            page.keyboard.press(key)
            return
        page.keyboard.press("Tab")
    raise AssertionError(f"Tab did not reach {selector}")


def kb_type(page: Page, selector: str, text: str) -> None:
    for _ in range(80):
        if page.evaluate(
            "(s) => document.activeElement && document.activeElement.matches(s)", selector
        ):
            page.keyboard.press("Control+A")
            page.keyboard.type(text)
            return
        page.keyboard.press("Tab")
    raise AssertionError(f"Tab did not reach {selector}")


AUDIT_JS = r"""
() => {
  const parse = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return [0,0,0,0]; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return [p[0],p[1],p[2], p.length > 3 ? p[3] : 1]; };
  const lum = ([r,g,b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126*f(r) + 0.7152*f(g) + 0.0722*f(b); };
  const bgOf = (e) => { let x = e; while (x) { const c = parse(getComputedStyle(x).backgroundColor); if (c[3] > 0.99) return c; x = x.parentElement; } return [255,255,255,1]; };
  const visible = (e) => { const s = getComputedStyle(e); const r = e.getBoundingClientRect(); return s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0 && !e.closest('.visually-hidden'); };
  const contrast = [];
  for (const e of document.querySelectorAll('body *')) {
    if (!visible(e)) continue;
    const own = [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!own) continue;
    const s = getComputedStyle(e);
    const fg = parse(s.color), bg = bgOf(e);
    const L1 = lum(fg), L2 = lum(bg);
    const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const size = parseFloat(s.fontSize), bold = parseInt(s.fontWeight, 10) >= 700;
    const large = size >= 24 || (bold && size >= 18.66);
    const need = large ? 3 : 4.5;
    contrast.push({ el: e.id || e.tagName.toLowerCase() + '.' + e.className, text: e.textContent.trim().slice(0, 40), ratio: Math.round(ratio * 100) / 100, need, pass: ratio >= need });
  }
  const controls = [];
  for (const e of document.querySelectorAll('a[href], button, input, select, summary')) {
    if (!visible(e)) continue;
    const r = e.getBoundingClientRect();
    const inline = e.tagName === 'A' && getComputedStyle(e).display === 'inline' && e.parentElement && e.parentElement.tagName === 'P';
    let name = (e.getAttribute('aria-label') || '').trim();
    let label = '';
    if (e.labels && e.labels.length) { label = [...e.labels].map((l) => l.textContent.trim()).join(' '); name = name || label; }
    if (!name) name = (e.textContent || '').trim();
    const visibleLabel = e.type === 'radio' || e.type === 'checkbox' || e.tagName === 'INPUT' || e.tagName === 'SELECT' ? label.length > 0 : name.length > 0;
    controls.push({ el: e.id || e.tagName.toLowerCase() + ':' + name.slice(0, 30), w: Math.round(r.width), h: Math.round(r.height),
      target_pass: inline || (r.width >= 24 && r.height >= 24), name, role: e.getAttribute('role') || e.tagName.toLowerCase(), name_pass: name.length > 0 && visibleLabel });
  }
  return { contrast, controls, scrollW: document.documentElement.scrollWidth, clientW: document.documentElement.clientWidth };
}
"""


AXE = pathlib.Path(__file__).parent / "vendor" / "axe-4.14.0.min.js"
AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]


def run_axe(page: Page) -> dict[str, Any]:
    """axe-core 4.14.0 with the WCAG 2.0, 2.1 and 2.2 A and AA tags (vendor/README.md)."""
    if not page.evaluate("typeof window.axe !== 'undefined'"):
        page.add_script_tag(content=AXE.read_text())
    res: dict[str, Any] = page.evaluate(
        """async (tags) => {
          const r = await axe.run(document, {runOnly: {type: 'tag', values: tags}});
          const slim = (xs) => xs.map(v => ({id: v.id, impact: v.impact, help: v.help,
            nodes: v.nodes.map(n => n.target.join(' '))}));
          return {version: axe.version, tags, violations: slim(r.violations),
                  incomplete: slim(r.incomplete), passes: r.passes.map(p => p.id)};
        }""",
        AXE_TAGS,
    )
    return res


def audit(
    page: Page, screen: str, log: list[dict[str, Any]], width: int | None = None
) -> dict[str, Any]:
    a: dict[str, Any] = page.evaluate(AUDIT_JS)
    a["axe"] = run_axe(page)
    a["screen"] = screen
    a["width"] = width
    log.append(a)
    bad_c = [c for c in a["contrast"] if not c["pass"]]
    bad_t = [c for c in a["controls"] if not c["target_pass"]]
    bad_n = [c for c in a["controls"] if not c["name_pass"]]
    assert not bad_c, (screen, bad_c)
    assert not bad_t, (screen, bad_t)
    assert not bad_n, (screen, bad_n)
    assert a["scrollW"] <= a["clientW"], (screen, a["scrollW"], a["clientW"])
    assert not a["axe"]["violations"], (screen, a["axe"]["violations"])
    return a


def write(name: str, data: Any, folder: pathlib.Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False))
