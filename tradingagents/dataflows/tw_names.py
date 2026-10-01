"""Chinese company names for Taiwan tickers (2330.TW -> 台積電).

The full code->name list is fetched once and cached for a week in
~/.tradingagents/tw_names.json. Sources, in order:

1. FinMind TaiwanStockInfo (listed + OTC + ETFs; FINMIND_TOKEN optional),
2. TWSE and TPEx open data (no key),
3. a small built-in table, so common names still show when offline.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE = Path.home() / ".tradingagents" / "tw_names.json"
MAX_AGE = 7 * 86400
RETRY_AFTER = 3600  # after a failed refresh, don't hit the network again for an hour

BUILTIN = {
    "0050": "元大台灣50", "0056": "元大高股息", "006208": "富邦台50", "00878": "國泰永續高股息",
    "00919": "群益台灣精選高息", "00929": "復華台灣科技優息", "006201": "元大富櫃50",
    "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2308": "台達電", "2382": "廣達",
    "2303": "聯電", "2412": "中華電", "2881": "富邦金", "2882": "國泰金", "2891": "中信金",
    "2886": "兆豐金", "2884": "玉山金", "2885": "元大金", "2892": "第一金", "2880": "華南金",
    "2357": "華碩", "2379": "瑞昱", "3711": "日月光投控", "2395": "研華", "3034": "聯詠",
    "3008": "大立光", "2345": "智邦", "3231": "緯創", "2356": "英業達", "6669": "緯穎",
    "3037": "欣興", "2327": "國巨", "4938": "和碩", "2603": "長榮", "2609": "陽明",
    "2615": "萬海", "1301": "台塑", "1303": "南亞", "1216": "統一", "2002": "中鋼",
    "2207": "和泰車", "3017": "奇鋐", "3661": "世芯-KY", "3443": "創意", "2376": "技嘉",
    "2301": "光寶科", "2408": "南亞科", "2344": "華邦電", "1519": "華城", "1504": "東元",
    "5274": "信驊", "6488": "環球晶", "5347": "世界", "3105": "穩懋", "8299": "群聯",
    "6274": "台燿", "2360": "致茂", "3324": "雙鴻", "2059": "川湖", "3533": "嘉澤", "8046": "南電", "2368": "金像電", "3044": "健鼎", "6415": "矽力*-KY", "3529": "力旺", "5483": "中美晶", "6547": "高端疫苗", "4966": "譜瑞-KY",
}

_lock = threading.Lock()
_names: dict[str, str] | None = None
_last_try = 0.0


def stock_id(ticker: str) -> str | None:
    t = str(ticker).strip().upper()
    for suf in (".TWO", ".TW"):
        if t.endswith(suf):
            return t[: -len(suf)]
    return None


def _get_json(url: str, **kw):
    import requests

    r = requests.get(url, timeout=20, **kw)
    r.raise_for_status()
    return r.json()


def _from_finmind() -> dict[str, str]:
    tok = os.environ.get("FINMIND_TOKEN", "")
    body = _get_json("https://api.finmindtrade.com/api/v4/data", params={"dataset": "TaiwanStockInfo"},
                     headers={"Authorization": f"Bearer {tok}"} if tok else {})
    return {str(r["stock_id"]).strip(): str(r["stock_name"]).strip()
            for r in body.get("data", []) if r.get("stock_id") and r.get("stock_name")}


def _from_exchanges() -> dict[str, str]:
    out: dict[str, str] = {}
    for r in _get_json("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"):
        if r.get("Code") and r.get("Name"):
            out[str(r["Code"]).strip()] = str(r["Name"]).strip()
    try:
        for r in _get_json("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"):
            code, name = r.get("SecuritiesCompanyCode"), r.get("CompanyName")
            if code and name:
                out.setdefault(str(code).strip(), str(name).strip())
    except Exception as exc:  # noqa: BLE001 — TWSE alone is still useful
        logger.info("TPEx name list unavailable: %s", exc)
    return out


def _refresh() -> dict[str, str]:
    for source in (_from_finmind, _from_exchanges):
        try:
            names = source()
            if len(names) > 500:
                CACHE.parent.mkdir(parents=True, exist_ok=True)
                CACHE.write_text(json.dumps(names, ensure_ascii=False), encoding="utf-8")
                return names
        except Exception as exc:  # noqa: BLE001
            logger.info("Taiwan name list from %s failed: %s", source.__name__, exc)
    return {}


def _load() -> dict[str, str]:
    global _names, _last_try
    with _lock:
        fresh = CACHE.exists() and time.time() - CACHE.stat().st_mtime < MAX_AGE
        if _names is None or (not fresh and time.time() - _last_try > RETRY_AFTER):
            cached: dict[str, str] = {}
            with contextlib.suppress(OSError, ValueError):
                cached = json.loads(CACHE.read_text(encoding="utf-8"))
            if not fresh and time.time() - _last_try > RETRY_AFTER:
                _last_try = time.time()
                cached = _refresh() or cached
            _names = {**BUILTIN, **cached}
        return _names


def zh_name(ticker: str) -> str | None:
    """Chinese short name for a .TW/.TWO ticker, or None (US tickers, unknown codes)."""
    sid = stock_id(ticker)
    if not sid:
        return None
    return _load().get(sid)


def label(ticker: str) -> str:
    """'2330.TW 台積電' for Taiwan tickers with a known name, else the ticker itself."""
    name = zh_name(ticker)
    return f"{ticker} {name}" if name else str(ticker)
