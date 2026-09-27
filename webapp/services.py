"""Report files on disk and the optional AI news digest."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from webapp.jobs import ROOT

RESULTS_DIR = Path(os.getenv("TRADINGAGENTS_RESULTS_DIR") or Path.home() / ".tradingagents" / "logs")


@dataclass
class ReportFile:
    kind: str       # 選股建議 / 個股彙整 / 完整報告
    title: str
    path: Path
    modified: datetime


def list_reports() -> list[ReportFile]:
    found: list[ReportFile] = []
    for kind, folder, pattern in (
        ("選股建議", ROOT / "recommendations", "recommendations_*.md"),
        ("個股彙整", ROOT / "watchlist_results", "summary_*.md"),
    ):
        for p in folder.glob(pattern) if folder.exists() else []:
            found.append(ReportFile(kind, p.stem, p, datetime.fromtimestamp(p.stat().st_mtime)))
    reports_dir = RESULTS_DIR / "reports"
    if reports_dir.exists():
        for p in reports_dir.glob("*/complete_report.md"):
            found.append(ReportFile("完整報告", p.parent.name, p, datetime.fromtimestamp(p.stat().st_mtime)))
    return sorted(found, key=lambda r: r.modified, reverse=True)


_ROW = re.compile(r"^\|\s*(台股|美股)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|$")


def parse_recommendations(text: str) -> list[dict]:
    """Suggested stocks from a recommendations_*.md file, with their horizon section."""
    rows, horizon = [], ""
    for line in text.splitlines():
        if line.startswith("## "):
            horizon = line[3:].strip()
        m = _ROW.match(line.strip())
        if m:
            market, ticker, name, rating, target, period = m.groups()
            rows.append({"期間": horizon, "市場": market, "代碼": ticker, "名稱": name,
                         "評等": rating, "目標價": target, "持有期間": period})
    return rows


def split_report_sections(text: str) -> dict[str, str]:
    """Stock sections of a recommendations file keyed by ticker (### <ticker> <name>)."""
    out, current, buf = {}, None, []
    for line in text.splitlines():
        if line.startswith("### ") or line.startswith("## "):
            if current:
                out[current] = "\n".join(buf).strip()
            current = line[4:].split()[0] if line.startswith("### ") else None
            buf = []
        elif current:
            buf.append(line)
    if current:
        out[current] = "\n".join(buf).strip()
    return out


def ai_digest(articles: list[dict], topic: str) -> str:
    """Summarize headlines in Traditional Chinese with the configured quick-thinking model."""
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.llm_clients import build_llm_kwargs, create_llm_client

    cfg = dict(DEFAULT_CONFIG)
    llm = create_llm_client(provider=cfg["llm_provider"], model=cfg["quick_think_llm"],
                            base_url=cfg.get("backend_url"), **build_llm_kwargs(cfg)).get_llm()
    lines = []
    for i, a in enumerate(articles[:20], 1):
        when = a["pub_date"].strftime("%m/%d") if a.get("pub_date") else ""
        lines.append(f"[{i}] {when} {a['title']} ({a.get('publisher', '')}) — {a.get('summary', '')[:300]}")
    prompt = (
        f"以下是關於「{topic}」的最新新聞標題與摘要。請用繁體中文寫一份給投資人看的重點整理：\n"
        "1. 先用 2–3 句話說明整體情勢；\n2. 再列出 3–6 個重點，每點一句，並在句末用 [編號] 標註來源；\n"
        "3. 最後一句說明對股市可能的影響，並提醒這不是投資建議。\n"
        "只根據提供的內容，不要補充外部資訊或臆測數字。\n\n" + "\n".join(lines)
    )
    return llm.invoke(prompt).content
