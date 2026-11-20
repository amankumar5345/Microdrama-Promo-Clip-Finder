"""
src/candidates.py
─────────────────
Generate candidate promo windows of 20-60s that:
  • Start at the start of a dialogue line.
  • End at the end of a dialogue line.
  • Have clip_id format like: ep01_w012.
  • Drop windows with no dialogue or action in the first 3 seconds.

Real timestamps are kept in internal fields (_start_s, _end_s) so code
does exact lookup while the LLM only ever references clip_id.
"""

import re
from pathlib import Path
import yaml

_CFG = yaml.safe_load((Path(__file__).parent.parent / "config.yaml").read_text())
MIN_SEC = _CFG["window"]["min_seconds"]  # 20
MAX_SEC = _CFG["window"]["max_seconds"]  # 60
HOOK_WIN = _CFG["window"]["hook_window_seconds"]  # 3


def _extract_ep_number(ep: dict) -> int:
    """Extract integer episode number from 'Episode 1', 'EPISODE 01', etc."""
    raw = str(ep.get("episode_number", "1"))
    m = re.search(r"\d+", raw)
    return int(m.group(0)) if m else 1


def build_candidates(
    episode: dict,
    min_seconds: float = None,
    max_seconds: float = None,
    hook_window_seconds: float = None,
) -> list[dict]:
    """
    Generate candidate windows of 20-60s bounded by dialogue lines.

    Parameters
    ----------
    episode : dict
        Parsed episode dictionary containing 'events' list.
    min_seconds : float, optional
        Minimum window duration in seconds (default from config: 20).
    max_seconds : float, optional
        Maximum window duration in seconds (default from config: 60).
    hook_window_seconds : float, optional
        Window limit to check early hook (default from config: 3).

    Returns
    -------
    list[dict]
        Candidate window dicts with clip_id like 'ep01_w001'.
    """
    min_s = min_seconds if min_seconds is not None else MIN_SEC
    max_s = max_seconds if max_seconds is not None else MAX_SEC
    hook_w = hook_window_seconds if hook_window_seconds is not None else HOOK_WIN

    events = episode.get("events", [])
    ep_num = _extract_ep_number(episode)

    # Indices of dialogue events
    d_indices = [i for i, e in enumerate(events) if e["type"] == "dialogue"]
    candidates = []
    seq = 0

    for idx_start, i in enumerate(d_indices):
        start_event = events[i]
        start_s = start_event["start_s"]

        for j in d_indices[idx_start:]:
            end_event = events[j]
            end_s = end_event["end_s"]
            dur = end_s - start_s

            if dur < min_s:
                continue
            if dur > max_s:
                break  # Further dialogue lines only increase duration

            # Window of all events between start dialogue and end dialogue
            win_events = events[i : j + 1]

            # Rule: Drop windows with no dialogue or action in the first 3 seconds
            has_early_hook = any(
                (e["type"] in ("dialogue", "action"))
                and (e["start_s"] - start_s <= hook_w)
                for e in win_events
            )
            if not has_early_hook:
                continue

            seq += 1
            clip_id = f"ep{ep_num:02d}_w{seq:03d}"

            candidates.append({
                "clip_id": clip_id,
                "duration_sec": round(dur, 2),
                "event_count": len(win_events),
                # Private fields for pipeline lookup (LLM never sees timestamps)
                "_start_s": round(start_s, 2),
                "_end_s": round(end_s, 2),
                "_events": win_events,
            })

    return candidates
