from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any

from aqt import gui_hooks, mediasrv, mw
from aqt.webview import AnkiWebView, AnkiWebViewKind
from flask import Response, request

from .entry_db import EntryDB

_REGISTERED: bool = False


def _local_tz() -> timezone:
    """Return Anki's timezone; fall back to the system tz."""

    if mw is not None and getattr(mw, "col", None) is not None:
        tzinfo = getattr(mw.col, "timezone", None)
        if tzinfo is not None:
            return tzinfo
    return datetime.now().astimezone().tzinfo or timezone.utc


def _card_id_date(card_id: int, tzinfo: timezone) -> date:
    """Convert a card ID (ms epoch) into a local calendar date."""

    return datetime.fromtimestamp(card_id / 1000, tz=tzinfo).date()


def _first_entry_counts(search: str, days: int | None) -> dict[str, Any]:
    if mw is None or mw.col is None:
        return {"bars": [], "total": 0}

    try:
        card_ids = set(mw.col.find_cards(search, order=False))
    except Exception:
        card_ids = set()

    if not card_ids:
        return {"bars": [], "total": 0}

    with EntryDB() as entry_db:
        grouped = entry_db.get_card_ids_grouped_by_entry()

    first_card_ids = {min(ids) for ids in grouped.values() if ids}
    target_ids = card_ids & first_card_ids
    if not target_ids:
        return {"bars": [], "total": 0}

    tzinfo = _local_tz()
    today = datetime.now(tzinfo).date()
    start_date: date | None = None
    if days and days > 0:
        start_date = today - timedelta(days=days - 1)

    counts: Counter[date] = Counter()
    for cid in target_ids:
        card_day = _card_id_date(cid, tzinfo)
        if start_date and card_day < start_date:
            continue
        counts[card_day] += 1

    bars = [{"date": day.isoformat(), "count": counts[day]} for day in sorted(counts)]
    return {
        "bars": bars,
        "total": sum(counts.values()),
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": today.isoformat(),
    }


def _handle_http_first_entry_graph() -> Response:
    payload: dict[str, Any]
    try:
        raw = request.data.decode("utf-8") if request.data else "{}"
        payload = json.loads(raw or "{}")
    except Exception:
        payload = {}

    search = str(payload.get("search") or "deck:current").strip()
    days_raw = payload.get("days", 365)
    try:
        days = int(days_raw)
    except Exception:
        days = 365

    data = _first_entry_counts(search, days)
    return Response(json.dumps(data), mimetype="application/json")


_JS_SNIPPET = r"""
(function () {
  const WRAP_ID = "ps-first-entry-chart";
  if (document.getElementById(WRAP_ID)) {
    return;
  }

  const graphs = document.querySelector(".graphs-container");
  const host = graphs || document.body;

  const wrapper = document.createElement("section");
  wrapper.id = WRAP_ID;
  wrapper.innerHTML = `
    <h3 style="margin:0 0 8px;">First Entry Adds</h3>
    <div class="ps-entry-chart">
      <div class="ps-entry-bars"></div>
      <div class="ps-entry-footer">
        <span class="ps-entry-total"></span>
        <button class="ps-entry-refresh" aria-label="Refresh first-entry chart">Refresh</button>
      </div>
    </div>`;
  (host.firstChild ? host.insertBefore(wrapper, host.firstChild) : host.appendChild(wrapper));

  const style = document.createElement("style");
  style.textContent = `
    #${WRAP_ID} { border: 1px solid var(--border, #ccc); padding: 12px; margin-bottom: 12px; border-radius: 8px; background: var(--canvas, #fff); }
    #${WRAP_ID}.ps-loading { opacity: 0.6; }
    #${WRAP_ID} .ps-entry-bars { display: flex; align-items: flex-end; gap: 2px; min-height: 120px; }
    #${WRAP_ID} .ps-entry-bar { flex: 1; background: linear-gradient(180deg, #66c2ff, #1a73e8); border-radius: 2px 2px 0 0; position: relative; min-height: 4px; }
    #${WRAP_ID} .ps-entry-bar::after { display: none; }
    #${WRAP_ID} .ps-entry-bar:hover::after { display: block; content: attr(data-title); position: absolute; left: 50%; transform: translate(-50%, -6px); background: rgba(0,0,0,0.8); color: #fff; padding: 4px 6px; border-radius: 4px; white-space: nowrap; font-size: 11px; z-index: 10; }
    #${WRAP_ID} .ps-entry-footer { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; font-size: 12px; }
    #${WRAP_ID} button.ps-entry-refresh { padding: 4px 8px; border: 1px solid var(--border, #ccc); background: var(--canvas, #fff); border-radius: 4px; cursor: pointer; }
  `;
  document.head.appendChild(style);

  const barsEl = wrapper.querySelector(".ps-entry-bars");
  const totalEl = wrapper.querySelector(".ps-entry-total");
  const refreshBtn = wrapper.querySelector(".ps-entry-refresh");

  function currentSearch() {
    const input = document.getElementById("statisticsSearchText");
    const radios = input ? input.parentElement.querySelectorAll('input[type="radio"]') : null;
    if (radios && radios.length >= 2) {
      if (radios[0].checked) return "deck:current";
      if (radios[1].checked) return "";
    }
    return (input && input.value.trim()) || "deck:current";
  }

  function currentDays() {
    const radios = document.querySelectorAll('.range-box input[type="radio"]');
    if (radios.length >= 2) {
      if (radios[0].checked) return 365;
      if (radios[1].checked) return 0;
    }
    return 365;
  }

  async function loadData() {
    wrapper.classList.add("ps-loading");
    try {
      const resp = await fetch("_anki/ps-first-entry-graph", {
        method: "POST",
        headers: { "Content-Type": "application/binary" },
        body: JSON.stringify({ search: currentSearch(), days: currentDays() }),
      });
      const data = await resp.json();
      render(data);
    } catch (err) {
      render({ bars: [], error: String(err) });
    } finally {
      wrapper.classList.remove("ps-loading");
    }
  }

  function render(data) {
    barsEl.innerHTML = "";
    const bars = (data && data.bars) || [];
    if (!bars.length) {
      barsEl.innerHTML = '<div style="padding:8px; color: var(--fg-muted, #666);">No first-entry additions in range.</div>';
      totalEl.textContent = "";
      return;
    }
    const max = Math.max(...bars.map((b) => b.count));
    for (const bar of bars) {
      const el = document.createElement("div");
      el.className = "ps-entry-bar";
      el.style.height = max ? `${(bar.count / max) * 100}%` : "4px";
      el.dataset.title = `${bar.date}: ${bar.count}`;
      barsEl.appendChild(el);
    }
    const total = data.total != null ? data.total : bars.reduce((sum, b) => sum + b.count, 0);
    totalEl.textContent = `Total: ${total} entries`;
  }

  refreshBtn.addEventListener("click", loadData);

  const searchInput = document.getElementById("statisticsSearchText");
  if (searchInput) {
    ["change", "blur"].forEach((evt) => searchInput.addEventListener(evt, loadData));
    searchInput.addEventListener("keyup", (ev) => {
      if (ev.key === "Enter") loadData();
    });
  }
  document.querySelectorAll('.range-box input[type="radio"]').forEach((el) => el.addEventListener("change", loadData));

  loadData();
})();
"""


def _inject_chart(webview: AnkiWebView) -> None:
    if webview.kind != AnkiWebViewKind.DECK_STATS:
        return
    webview.eval(_JS_SNIPPET)


def init_first_entry_added_chart() -> None:
    global _REGISTERED
    if _REGISTERED:
        return

    mediasrv.post_handlers["ps-first-entry-graph"] = _handle_http_first_entry_graph
    gui_hooks.webview_did_inject_style_into_page.append(_inject_chart)
    _REGISTERED = True
