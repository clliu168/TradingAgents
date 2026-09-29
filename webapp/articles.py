"""Per-article summaries: fetch the article text, ask the LLM for a Chinese summary
and key points, and cache the result on disk so each article is paid for once."""

from __future__ import annotations

import hashlib
import json
import re

from webapp.jobs import DATA_DIR

CACHE_DIR = DATA_DIR / "article_summaries"
MAX_CHARS = 8000
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def _key(link: str) -> str:
    return hashlib.sha1(link.encode()).hexdigest()[:16]


def cached(link: str) -> dict | None:
    p = CACHE_DIR / f"{_key(link)}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _store(link: str, result: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{_key(link)}.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


def extract_text(html: str) -> str:
    """Main article text: paragraphs inside <article> (or the whole page), boilerplate dropped."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]):
        tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    paras = [re.sub(r"\s+", " ", p.get_text(" ", strip=True)) for p in root.find_all(["p", "li", "h2"])]
    paras = [p for p in paras if len(p) > 40]
    return "\n".join(paras)[:MAX_CHARS]


def fetch_text(link: str) -> str:
    import requests

    resp = requests.get(link, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}, timeout=15)
    resp.raise_for_status()
    return extract_text(resp.text)


PROMPT = """你是財經編輯。請用繁體中文整理下面這篇新聞，輸出 JSON，欄位如下：
{{"summary": "3–4 句話的摘要", "points": ["重點 1", "重點 2", "重點 3"],
 "tickers": ["文中提到、與投資相關的股票或指數代碼"], "impact": "對相關股票或市場可能影響的一句話（中性描述，不要給買賣建議）",
 "sentiment": "偏多 / 偏空 / 中性"}}
只根據提供的內容，不要補充外部資訊，不要臆測數字。只輸出 JSON。

標題：{title}
來源：{publisher}
{body_label}：
{body}
"""


def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("model did not return JSON")
    data = json.loads(m.group(0))
    data["points"] = [str(p) for p in data.get("points", [])][:6]
    data["tickers"] = [str(t) for t in data.get("tickers", [])][:8]
    return data


def summarize(article: dict, llm=None) -> dict:
    """Summary dict for one article: summary, points, tickers, impact, sentiment, source."""
    link = article.get("link") or article["title"]
    from webapp.data import DEMO

    if DEMO:
        result = {"summary": f"（Demo）這是「{article['title'][:30]}」的示範摘要。", "points": ["示範重點一", "示範重點二"],
                  "tickers": ["2330.TW"], "impact": "示範影響描述。", "sentiment": "中性", "source": "demo"}
        _store(link, result)
        return result
    hit = cached(link)
    if hit:
        return hit
    body, source = "", "全文"
    if article.get("link"):
        try:
            body = fetch_text(article["link"])
        except Exception:  # noqa: BLE001 — paywall, block or timeout: fall back to the teaser
            body = ""
    if len(body) < 300:
        body, source = (article.get("summary") or "（無內文）"), "僅標題與導言"
    llm = llm or _llm()
    reply = llm.invoke(PROMPT.format(title=article["title"], publisher=article.get("publisher", ""),
                                     body_label="內文" if source == "全文" else "導言", body=body)).content
    if isinstance(reply, list):
        reply = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in reply)
    result = _parse_json(reply)
    result["source"] = source
    _store(link, result)
    return result


def _llm():
    from dotenv import load_dotenv

    from webapp.jobs import ROOT

    load_dotenv(ROOT / ".env")
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.llm_clients import build_llm_kwargs, create_llm_client
    from webapp.usage import UsageRecorder

    cfg = dict(DEFAULT_CONFIG)
    return create_llm_client(provider=cfg["llm_provider"], model=cfg["quick_think_llm"],
                             base_url=cfg.get("backend_url"),
                            **build_llm_kwargs(cfg), callbacks=[UsageRecorder("news-summary")]).get_llm()
