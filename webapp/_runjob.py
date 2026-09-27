"""Run a command and record its exit code: python _runjob.py <job_dir> <cmd...>."""

import signal
import subprocess
import sys
from pathlib import Path

job_dir = Path(sys.argv[1])
code = 1


def _stopped(signum, frame):
    raise SystemExit(-signum)


signal.signal(signal.SIGTERM, _stopped)
try:
    code = subprocess.call(sys.argv[2:])
except SystemExit as exc:
    code = exc.code
finally:
    (job_dir / "exit_code").write_text(str(code))
sys.exit(0 if code == 0 else 1)
