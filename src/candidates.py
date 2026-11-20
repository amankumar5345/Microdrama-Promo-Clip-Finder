"""
src/candidates.py
─────────────────
Generate candidate promo windows of 20-60s that:
  • Start at the start of a dialogue line.
  • End at the end of a dialogue line.
  • Have clip_id format like: ep01_w012.
  • Drop windows with no dialogue or action in the first 3 seconds.

Auto-fallback: if no candidates found in normal mode, widens window and
guarantees at least 1 candidate using all events.
"""

import re
from pathlib import Path
import yaml

_CFG = yaml.safe_load((Path(__file__).parent.parent / "config.yaml").read_text())
MIN_SEC  = _CFG["window"]["min_seconds"]    # 20
MAX_SEC  = _CFG["window"]["max_seconds"]    # 60
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
    Generate candidate windows bounded by dialogue lines.
    If no candidates found, widens constraints and guarantees ≥ 1 result.
    """
    min_s  = min_seconds if min_seconds is not None else MIN_SEC
    max_s  = max_seconds if max_seconds is not None else MAX_SEC
    hook_w = hook_window_seconds if hook_window_seconds is not None else HOOK_WIN

    events = episode.get("events", [])
    ep_num = _extract_ep_number(episode)

    candidates = _build(events, ep_num, min_s, max_s, hook_w)

    # ── Widen window if no candidates found ───────────────────────────────────
    if not candidates:
        wider_min = max(5.0, min_s - 10.0)
        wider_max = min(300.0, max_s + 30.0)
        candidates = _build(events, ep_num, wider_min, wider_max, hook_w, seq_offset=0)

    # ── Relax hook constraint if still nothing ────────────────────────────────
    if not candidates:
        candidates = _build(events, ep_num, 5.0, 300.0, hook_w=9999.0, seq_offset=0)

    # ── Last resort: wrap all events as one single candidate ──────────────────
    if not candidates and events:
        all_start = events[0]["start_s"]
        all_end   = events[-1]["end_s"]
        dur = max(1.0, all_end - all_start)
        candidates = [{
            "clip_id":      f"ep{ep_num:02d}_w001",
            "duration_sec": round(dur, 2),
            "event_count":  len(events),
            "_start_s":     round(all_start, 2),
            "_end_s":       round(all_end, 2),
            "_events":      events,
        }]

    return candidates


def _build(events, ep_num, min_s, max_s, hook_w, seq_offset=0):
    """Core sliding-window candidate builder."""
    # Try dialogue-bounded windows first
    d_indices = [i for i, e in enumerate(events) if e["type"] == "dialogue"]

    # If no dialogue events, use all events
    if not d_indices:
        d_indices = list(range(len(events)))

    candidates = []
    seq = seq_offset

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
                break

            win_events = events[i: j + 1]

            # Early hook check
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
                "clip_id":      clip_id,
                "duration_sec": round(dur, 2),
                "event_count":  len(win_events),
                "_start_s":     round(start_s, 2),
                "_end_s":       round(end_s, 2),
                "_events":      win_events,
            })

    return candidates
