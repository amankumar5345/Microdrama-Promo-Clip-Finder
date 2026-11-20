"""
run_parse.py
────────────
Run parse.py on Episode 1 and print:
  1. Episode header
  2. Table of all DIALOGUE events
  3. Summary counts by type
  4. Any warnings
"""

import logging
import sys
from pathlib import Path

# Configure logging so warnings show on stdout with a clean format
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s %(message)s",
    stream=sys.stdout,
)

from src.parse import parse_screenplay

EP1 = (
    Path("I Married a Broken Soldier. He was a Duke-scripts (2) (1)")
    / "I Married a Broken Soldier. He was a Duke"
    / "episode-001-Episode 1671703.txt"
)


def fmt_time(s: float) -> str:
    m = int(s) // 60
    sec = s % 60
    return f"{m:02d}:{sec:05.2f}"


def print_table(events: list[dict]):
    """Print a fixed-width table of dialogue events."""
    dialogue = [e for e in events if e["type"] == "dialogue"]

    # Column widths
    W_START  = 8
    W_END    = 8
    W_DUR    = 6
    W_SCENE  = 8
    W_SPEAK  = 24
    W_TONE   = 18
    W_OS     = 3
    W_TEXT   = 55

    sep = (
        f"{'─'*W_START}─{'─'*W_END}─{'─'*W_DUR}─"
        f"{'─'*W_SCENE}─{'─'*W_SPEAK}─{'─'*W_TONE}─"
        f"{'─'*W_OS}─{'─'*W_TEXT}"
    )

    hdr = (
        f"{'START':^{W_START}} {'END':^{W_END}} {'DUR':^{W_DUR}} "
        f"{'SCENE':^{W_SCENE}} {'SPEAKER':<{W_SPEAK}} {'TONE':<{W_TONE}} "
        f"{'OS':^{W_OS}} {'TEXT':<{W_TEXT}}"
    )

    print(sep)
    print(hdr)
    print(sep)

    for e in dialogue:
        dur  = e["end_s"] - e["start_s"]
        text = e["text"][:W_TEXT-1] + "…" if len(e["text"]) > W_TEXT else e["text"]
        tone = (e["tone"] or "")[:W_TONE]
        spk  = (e["speaker"] or "")[:W_SPEAK]
        os_  = "OS" if e["offscreen"] else ""

        print(
            f"{fmt_time(e['start_s']):>{W_START}} {fmt_time(e['end_s']):>{W_END}} "
            f"{dur:>{W_DUR}.2f} "
            f"{e['scene']:<{W_SCENE}} {spk:<{W_SPEAK}} {tone:<{W_TONE}} "
            f"{os_:^{W_OS}} {text}"
        )

    print(sep)
    print(f"  {len(dialogue)} dialogue events\n")


def main():
    print(f"\nParsing: {EP1.name}\n{'='*70}")
    ep = parse_screenplay(EP1)

    # ── Header ────────────────────────────────────────────────────────────
    print(f"Episode : {ep['episode_number']}")
    print(f"Logline : {ep['logline'][:100]}{'…' if len(ep['logline'])>100 else ''}")
    print(f"File    : {ep['source_file']}")
    print()

    # ── Dialogue table ────────────────────────────────────────────────────
    print("DIALOGUE EVENTS")
    print_table(ep["events"])

    # ── Type summary ──────────────────────────────────────────────────────
    from collections import Counter
    counts = Counter(e["type"] for e in ep["events"])
    print("EVENT TYPE SUMMARY")
    print(f"  {'Type':<12} Count")
    print(f"  {'────':<12} ─────")
    for t, c in sorted(counts.items()):
        print(f"  {t:<12} {c}")
    print(f"  {'TOTAL':<12} {sum(counts.values())}")
    print()

    # ── Warnings ──────────────────────────────────────────────────────────
    if ep["warnings"]:
        print(f"WARNINGS ({len(ep['warnings'])})")
        for w in ep["warnings"]:
            print(f"  ⚠  {w}")
    else:
        print("WARNINGS  none ✓")
    print()


if __name__ == "__main__":
    main()
