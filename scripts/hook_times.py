"""Summarize the hook timing log that the trueup plugin writes (purpose-and-state P5).

Each hook run adds one line to `$CLAUDE_PLUGIN_DATA/hook-times.jsonl`
(D13.4). This script prints, for each hook event, the run count and the
median, 95th percentile and largest time, for the field note that decides
the delivery form.

Usage: python3 scripts/hook_times.py [LOG]
The default LOG is the plugin data file under ~/.claude/plugins/data/.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

_DEFAULT_GLOB = "trueup*/hook-times.jsonl"
_DATA_DIR = Path.home() / ".claude" / "plugins" / "data"


def summarize(lines: list[str]) -> list[str]:
    """Give one summary line for each hook event in the log.

    Args:
        lines: The log lines, one JSON object each. A bad line is skipped.

    Returns:
        Lines of the form `event runs median p95 max first last`.
    """
    times: dict[str, list[float]] = defaultdict(list)
    dates: dict[str, list[str]] = defaultdict(list)
    for line in lines:
        try:
            entry = json.loads(line)
            times[entry["event"]].append(float(entry["seconds"]))
            dates[entry["event"]].append(entry["date"])
        except (ValueError, KeyError, TypeError):
            continue
    out = ["event      runs  median    p95    max  first .. last"]
    for event in sorted(times):
        values = sorted(times[event])
        p95 = values[min(len(values) - 1, int(len(values) * 0.95))]
        out.append(
            f"{event:<10} {len(values):>4}  {statistics.median(values):6.3f} "
            f"{p95:6.3f} {values[-1]:6.3f}  {min(dates[event])} .. {max(dates[event])}"
        )
    return out


def main(argv: list[str]) -> int:
    """Print the summary of one log.

    Args:
        argv: An optional log path.

    Returns:
        0 when a log was read, 1 when none was found.
    """
    if argv:
        logs = [Path(argv[0])]
    else:
        logs = sorted(_DATA_DIR.glob(_DEFAULT_GLOB))
    if not logs or not logs[0].is_file():
        print(f"no hook-times.jsonl found under {_DATA_DIR}")
        return 1
    print(logs[0])
    print("\n".join(summarize(logs[0].read_text(encoding="utf-8").splitlines())))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
