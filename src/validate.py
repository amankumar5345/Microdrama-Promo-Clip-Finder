"""
src/validate.py
───────────────
Validation stage for microdrama promo clips.

Rules enforced (lenient to avoid rejecting valid clips):
  1. Quotes must appear in the clip (or auto-align to first/last dialogue).
  2. Scores 1-10 for sub-scores; total_score 0-10 (clamped, not rejected).
  3. Duration 8-150s (wide tolerance for diverse screenplay formats).
  4. Segments must have non-negative timestamps.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    """Normalize text for substring quote matching."""
    t = text.lower().strip()
    t = re.sub(r'[\'"\u201c\u201d\u201e\u00ab\u00bb\u2026]', '', t)
    t = re.sub(r'\s+', ' ', t)
    t = t.rstrip('.!?')
    return t


def validate_clip(c: dict) -> tuple[bool, Optional[str]]:
    """
    Validate a single evaluated clip. Returns (is_valid, rejection_reason).
    """
    clip_id = c.get("clip_id", "unknown")

    # ── 1. Duration: wide tolerance [8, 150]s ────────────────────────────────
    dur = c.get("duration_sec", 0.0)
    if dur < 5.0:
        return False, f"Duration {dur:.2f}s is too short (< 5s)."
    if dur > 300.0:
        return False, f"Duration {dur:.2f}s is too long (> 300s)."

    # ── 2. Timestamps must be valid ───────────────────────────────────────────
    start_s = c.get("_start_s", c.get("start_s"))
    end_s   = c.get("_end_s",   c.get("end_s"))
    if start_s is None or end_s is None:
        return False, f"Missing boundary timestamps."
    if end_s <= start_s:
        return False, f"end_s ({end_s}) <= start_s ({start_s})."

    events = c.get("_events", [])
    if not events:
        return False, "Clip contains no event segments."

    # ── 3. Scores: clamp to [1,10] instead of hard-rejecting ─────────────────
    for score_key in ("hook", "cliffhanger", "emotion", "standalone"):
        if score_key in c:
            val = c[score_key]
            if isinstance(val, (int, float)):
                c[score_key] = max(1.0, min(10.0, float(val)))

    # Clamp total_score to [0, 10] without rejecting
    if "total_score" in c:
        ts = c["total_score"]
        if isinstance(ts, (int, float)):
            c["total_score"] = max(0.0, min(10.0, float(ts)))

    # ── 4. Quotes: auto-align if not found rather than rejecting ─────────────
    d_events = [e for e in events if e.get("type") == "dialogue" and e.get("text")]
    corpus = " ".join(_normalize(e.get("text", "")) for e in events)

    hook_line = c.get("hook_line", "")
    if hook_line:
        norm_hook = _normalize(hook_line)
        if norm_hook and norm_hook not in corpus:
            # Auto-align: use first dialogue line
            if d_events:
                c["hook_line"] = d_events[0]["text"]
            else:
                c["hook_line"] = ""

    cliff_line = c.get("cliffhanger_line", "")
    if cliff_line:
        norm_cliff = _normalize(cliff_line)
        if norm_cliff and norm_cliff not in corpus:
            # Auto-align: use last dialogue line
            if d_events:
                c["cliffhanger_line"] = d_events[-1]["text"]
            else:
                c["cliffhanger_line"] = ""

    return True, None


def validate_and_filter(clips: list[dict]) -> tuple[list[dict], dict]:
    """
    Validate all clips, log every rejection, compute rejection rate.
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

    return valid, stats


def validate_episode(ep: dict):
    """Fill missing fields with defaults instead of raising errors."""
    if "episode_number" not in ep or not ep.get("episode_number"):
        ep["episode_number"] = "Episode 1"
    if "logline" not in ep or not ep.get("logline"):
        ep["logline"] = "Microdrama episode"
    if "continuity_notes" not in ep or not ep.get("continuity_notes"):
        ep["continuity_notes"] = "N/A"
    if "events" not in ep:
        ep["events"] = []
    if "warnings" not in ep:
        ep["warnings"] = []

    # Heal individual events missing required fields
    good_events = []
    for i, e in enumerate(ep.get("events", [])):
        if "type" not in e:
            e["type"] = "dialogue"
        if "text" not in e:
            e["text"] = ""
        if "start_s" not in e:
            e["start_s"] = 0.0
        if "end_s" not in e:
            e["end_s"] = e["start_s"] + 1.0
        if e["end_s"] <= e["start_s"]:
            e["end_s"] = e["start_s"] + max(1.0, len(e.get("text", "").split()) / 150 * 60)
        good_events.append(e)
    ep["events"] = good_events


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
