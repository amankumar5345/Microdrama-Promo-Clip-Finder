"""
src/validate.py
───────────────
Validation stage for microdrama promo clips.

Rules enforced:
  1. Quotes must appear in the clip:
     Both hook_line and cliffhanger_line must literally exist in the clip text.
  2. Scores 1-10:
     All sub-scores (hook, cliffhanger, emotion, understandability) must be within [1, 10].
  3. Duration 20-60s:
     Total duration must be strictly between 20.0s and 60.0s.
  4. Segments in order:
     Timestamps must be strictly positive and events must be in non-decreasing chronological order.

Every rejection is logged with its exact reason, and the rejection rate is printed.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    """Normalize text for substring quote matching (remove quotes, extra whitespace)."""
    t = text.lower().strip()
    t = re.sub(r'[\'""“”„«»…]', '', t)
    t = re.sub(r'\s+', ' ', t)
    t = t.rstrip('.!?')
    return t


def validate_clip(c: dict) -> tuple[bool, Optional[str]]:
    """
    Validate a single evaluated clip against the 4 core rules.

    Returns
    -------
    (is_valid, rejection_reason)
    """
    clip_id = c.get("clip_id", "unknown")

    # ── 1. Duration 20-60s ────────────────────────────────────────────────────
    dur = c.get("duration_sec", 0.0)
    if not (20.0 <= dur <= 60.0):
        return False, f"Duration {dur:.2f}s is outside allowed [20.0, 60.0]s bounds."

    # ── 2. Segments in order ──────────────────────────────────────────────────
    start_s = c.get("_start_s")
    end_s = c.get("_end_s")
    if start_s is None or end_s is None or end_s <= start_s:
        return False, f"Invalid boundary timestamps: start={start_s}, end={end_s}."

    events = c.get("_events", [])
    if not events:
        return False, "Clip contains no event segments."

    for idx in range(len(events) - 1):
        if events[idx]["start_s"] > events[idx + 1]["start_s"]:
            return False, (
                f"Segments out of chronological order at event {idx} "
                f"({events[idx]['start_s']}s > {events[idx+1]['start_s']}s)."
            )

    # ── 3. Scores 1-10 ────────────────────────────────────────────────────────
    for score_key in ("hook", "cliffhanger", "emotion", "understandability", "total_score"):
        if score_key in c:
            val = c[score_key]
            if not isinstance(val, (int, float)) or not (1.0 <= float(val) <= 10.0):
                return False, f"Score '{score_key}' = {val} is outside [1, 10] range."

    # ── 4. Quotes must appear in the clip ─────────────────────────────────────
    # Concatenate all event texts into a single search corpus
    corpus = " ".join(_normalize(e.get("text", "")) for e in events)

    hook_line = c.get("hook_line")
    if hook_line:
        norm_hook = _normalize(hook_line)
        if norm_hook and norm_hook not in corpus:
            return False, f"hook_line quote '{hook_line}' not found in clip events."

    cliff_line = c.get("cliffhanger_line")
    if cliff_line:
        norm_cliff = _normalize(cliff_line)
        if norm_cliff and norm_cliff not in corpus:
            return False, f"cliffhanger_line quote '{cliff_line}' not found in clip events."

    return True, None


def validate_and_filter(clips: list[dict]) -> tuple[list[dict], dict]:
    """
    Validate all clips, log every rejection with its exact reason,
    and compute the rejection rate.

    Returns
    -------
    (valid_clips, stats_dict)
    """
    valid = []
    rejections = []

    for c in clips:
        clip_id = c.get("clip_id", "unknown")
        ok, reason = validate_clip(c)
        if ok:
            valid.append(c)
        else:
            logger.warning(f"[REJECTED] {clip_id}: {reason}")
            print(f"  ⚠  [REJECTED] {clip_id}: {reason}")
            rejections.append({"clip_id": clip_id, "reason": reason})

    total = len(clips)
    rejected_count = len(rejections)
    rejection_rate = (rejected_count / total * 100.0) if total > 0 else 0.0

    stats = {
        "total": total,
        "passed": len(valid),
        "rejected": rejected_count,
        "rejection_rate_pct": round(rejection_rate, 2),
        "rejections": rejections,
    }

    print(
        f"\n[Validation Stats] Evaluated: {total} | Passed: {len(valid)} | "
        f"Rejected: {rejected_count} | Rejection Rate: {rejection_rate:.1f}%\n"
    )

    return valid, stats


# ── Existing schema checks for pipeline boundaries ────────────────────────────

def validate_episode(ep: dict):
    required = ("episode_number", "logline", "continuity_notes", "events")
    for key in required:
        if key not in ep:
            raise ValueError(f"Episode dict missing key: {key!r}")
    for i, e in enumerate(ep["events"]):
        for k in ("type", "start_s", "end_s", "text"):
            if k not in e:
                raise ValueError(f"Event {i} missing {k!r}")
        if e["end_s"] < e["start_s"]:
            raise ValueError(f"Event {i}: end_s ({e['end_s']}) < start_s ({e['start_s']})")


def validate_candidates(candidates: list[dict]):
    seen_ids = set()
    for c in candidates:
        for key in ("clip_id", "duration_sec", "_start_s", "_end_s", "_events"):
            if key not in c:
                raise ValueError(f"Candidate missing key {key!r}: {c}")
        if c["clip_id"] in seen_ids:
            raise ValueError(f"Duplicate clip_id: {c['clip_id']}")
        seen_ids.add(c["clip_id"])


def validate_scored(scored: list[dict]):
    valid, stats = validate_and_filter(scored)
    if not valid and scored:
        raise ValueError(f"All {len(scored)} scored clips failed validation checks!")
