"""Write the configuration-management evidence to a text file.

The evidence script prints to the terminal and also writes JSON. JSON is good
for a machine; a marker reading a report wants the transcript. This runs the
same checks and writes a plain text transcript as well, so the evidence can be
reproduced and read without a screenshot.

    python scripts/write_configuration_evidence.py
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EVIDENCE_SCRIPT = ROOT / "scripts" / "show_configuration_evidence.py"
OUTPUT = ROOT / "docs" / "configuration-evidence.txt"


def main() -> int:
    started = datetime.now(timezone.utc)

    # The evidence script prints a transcript; capture it by running it in a
    # child process so that its output is exactly what a user would see.  The
    # child is told to write UTF-8 on its streams, because Python otherwise uses
    # the Windows console code page for a pipe, which cannot represent the em
    # dash in the transcript and silently replaces it.
    environment = dict(os.environ)
    environment["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [sys.executable, str(EVIDENCE_SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )
    body = completed.stdout or ""
    if completed.returncode != 0 and not body:
        body = completed.stderr or ""

    header = [
        "=" * 76,
        "  Warrigal Park FC - Member Registration & Team Roster System",
        "  Configuration management evidence",
        "=" * 76,
        f"  python  : {sys.version.split()[0]}",
        f"  run at  : {started.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"  command : python scripts/write_configuration_evidence.py",
        f"  result  : {'completed' if completed.returncode == 0 else 'reported errors'}",
        "=" * 76,
        "",
    ]
    OUTPUT.write_text("\n".join(header) + body, encoding="utf-8")
    print(f"transcript written to {OUTPUT}")
    print(f"  {len(body.splitlines())} lines of evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
