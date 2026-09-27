"""Background jobs: run recommend.py / run_watchlist.py outside the Streamlit process.

A job survives page reloads and switching pages: it is a detached subprocess
whose output goes to ``webapp_data/jobs/<id>/log.txt`` and whose exit code is
written to ``exit_code`` by the small wrapper in ``_runjob.py``.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "webapp_data"
JOBS_DIR = DATA_DIR / "jobs"


def start(kind: str, args: list[str], label: str) -> str:
    """Launch ``python <script> <args>`` in the background; return the job id."""
    script = {"recommend": "recommend.py", "watchlist": "run_watchlist.py"}[kind]
    job_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    jdir = JOBS_DIR / job_id
    jdir.mkdir(parents=True)
    cmd = [sys.executable, "-u", str(ROOT / script), *args]
    meta = {"id": job_id, "kind": kind, "label": label, "cmd": cmd, "started": datetime.now().isoformat()}
    log = open(jdir / "log.txt", "w", encoding="utf-8")  # noqa: SIM115 — handed to the child
    proc = subprocess.Popen(
        [sys.executable, "-u", str(Path(__file__).with_name("_runjob.py")), str(jdir), *cmd],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    meta["pid"] = proc.pid
    (jdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return job_id


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def status(jdir: Path) -> str:
    code_file = jdir / "exit_code"
    if code_file.exists():
        code = code_file.read_text().strip()
        return "完成" if code == "0" else ("已停止" if code in ("-15", "143") else f"失敗（{code}）")
    meta = json.loads((jdir / "meta.json").read_text(encoding="utf-8"))
    return "執行中" if _alive(meta.get("pid", -1)) else "中斷"


def list_jobs() -> list[dict]:
    if not JOBS_DIR.exists():
        return []
    jobs = []
    for jdir in sorted(JOBS_DIR.iterdir(), reverse=True):
        meta_file = jdir / "meta.json"
        if not meta_file.exists():
            continue
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        meta["status"] = status(jdir)
        meta["dir"] = jdir
        jobs.append(meta)
    return jobs


def tail(jdir: Path, lines: int = 60) -> str:
    log = jdir / "log.txt"
    if not log.exists():
        return ""
    text = log.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(text[-lines:])


def output_file(jdir: Path) -> Path | None:
    """The report file the job wrote, read from its 'written to' log line."""
    for line in reversed((jdir / "log.txt").read_text(encoding="utf-8", errors="replace").splitlines()):
        for marker in ("Written to ", "Summary written to "):
            if line.startswith(marker):
                p = Path(line[len(marker):].strip())
                return p if p.is_absolute() else ROOT / p
    return None


def stop(jdir: Path) -> None:
    meta = json.loads((jdir / "meta.json").read_text(encoding="utf-8"))
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(os.getpgid(meta["pid"]), signal.SIGTERM)
