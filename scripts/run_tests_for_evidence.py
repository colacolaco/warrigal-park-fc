"""Produce a clean, presentation-ready transcript of the test suite run.

Running the suite through a shell adds noise (the shell's own error records) to
the output, which makes a poor screenshot. This runs the suite in-process and
writes a plain transcript, so the evidence is the program's own words.

    python scripts/run_tests_for_evidence.py
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT = ROOT / "docs" / "test-evidence.txt"


def main() -> int:
    buffer = io.StringIO()
    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    runner = unittest.TextTestRunner(stream=buffer, verbosity=2)

    started = datetime.now(timezone.utc)
    with redirect_stdout(buffer), redirect_stderr(buffer):
        result = runner.run(suite)
    finished = datetime.now(timezone.utc)

    header = [
        "=" * 74,
        "  Warrigal Park FC - Member Registration & Team Roster System",
        "  Automated test suite transcript",
        "=" * 74,
        f"  python  : {sys.version.split()[0]}",
        f"  started : {started.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"  finished: {finished.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"  tests   : {result.testsRun} run, "
        f"{len(result.failures)} failed, {len(result.errors)} errored, "
        f"{len(result.skipped)} skipped",
        f"  result  : {'PASS' if result.wasSuccessful() else 'FAIL'}",
        "=" * 74,
        "",
    ]
    # The runner already wrote a one-line-per-test transcript and a summary into
    # the buffer; only the two "====" banner lines it adds are dropped.
    body = [
        line for line in buffer.getvalue().splitlines()
        if not line.startswith("====") and "-----" not in line[:10] or line.startswith("Ran ")
    ]

    OUTPUT.write_text("\n".join(header) + "\n".join(buffer.getvalue().splitlines()) + "\n",
                      encoding="utf-8")
    print(f"transcript written to {OUTPUT}")
    print(f"  {result.testsRun} tests, "
          f"{'PASS' if result.wasSuccessful() else 'FAIL'}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
