"""
src/prefilter.py
────────────────
Score candidate promo windows using:
  1. Tone tags (e.g. shocked, angry, gloating, betrayed, cold, commanding)
  2. '?' or '...' near the end (unresolved cliffhanger or suspenseful pause)
  3. Shock words (high-stakes drama keywords: marry, betray, husband, debt, ruin, etc.)
  4. Line pace (dialogue density: lines per minute)

Keeps the top 12 candidate windows per episode.
"""

import re
from pathlib import Path

# High-drama emotional tones common in microdramas
HIGH_DRAMA_TONES = {
    "shocked", "angry", "gloating", "accusing", "arrogant", "begging",
    "betrayed", "broken", "callous", "cold", "commanding", "confused",
    "cruel", "crushed", "crying out", "desperate", "devastated", "disgusted",
    "dismissive", "gasping", "heartbroken", "horrified", "incredulous",
    "mocking", "outraged", "painful", "piercing", "pleading", "raw",
    "scornful", "shaken", "smug", "stern", "trembling", "viciously calm",
    "furious", "venomous", "panic", "stunned", "menacing", "threatening"
}

# High-stakes shock keywords in microdrama scripts
SHOCK_WORDS = {
    "marry", "marrying", "marriage", "betray", "betrayed", "betrayal",
    "husband", "wife", "sister", "mistake", "never", "ruin", "secret",
    "love", "loved", "lie", "lied", "kill", "die", "dead", "debt",
    "money", "worth", "plainness", "embarrassed", "changed my mind",
    "lakhs", "sixty", "rupees", "disappeared", "police", "affair",
    "pregnant", "divorce", "disown", "jewel", "daughter", "father",
    "mother", "family", "no", "what", "who"
}

TOP_PREFILTER_COUNT = 12


def _score_tones(dialogue_events: list[dict]) -> tuple[float, list[str]]:
    """Score intensity of tone tags across dialogue lines."""
    matched = []
    for e in dialogue_events:
        tone_str = e.get("tone") or ""
        for t in tone_str.split(","):
            t_clean = t.strip().lower()
            if any(h in t_clean for h in HIGH_DRAMA_TONES):
                matched.append(t.strip())
    # Up to 10 points
    score = min(10.0, len(matched) * 1.4)
    return score, matched


def _score_ending_punctuation(dialogue_events: list[dict]) -> tuple[float, list[str]]:
    """
    Score presence of '?' or '...' near the end of the window
    (indicating unresolved cliffhangers or trailing tension).
    """
    if not dialogue_events:
        return 0.0, []

    reasons = []
    score = 0.0

    # Final dialogue line
    last_text = dialogue_events[-1]["text"].strip()
    if "?" in last_text:
        score += 8.0
        reasons.append("Final line ends in unresolved question '?'")
    elif "..." in last_text or "…" in last_text:
        score += 6.5
        reasons.append("Final line ends in trailing suspense '...'")

    # Penultimate dialogue line (support beat)
    if len(dialogue_events) >= 2:
        penult_text = dialogue_events[-2]["text"].strip()
        if "?" in penult_text:
            score += 2.0
            reasons.append("Penultimate question '?'")
        elif "..." in penult_text or "…" in penult_text:
            score += 1.5
            reasons.append("Penultimate suspense '...'")

    return min(10.0, score), reasons


def _score_shock_words(dialogue_events: list[dict]) -> tuple[float, list[str]]:
    """Score frequency of high-stakes dramatic keywords."""
    found = set()
    for e in dialogue_events:
        text_lower = e.get("text", "").lower()
        for sw in SHOCK_WORDS:
            # Word boundary check
            if re.search(r"\b" + re.escape(sw) + r"\b", text_lower):
                found.add(sw)

    score = min(10.0, len(found) * 1.5)
    return score, sorted(found)


def _score_line_pace(dialogue_events: list[dict], dur_sec: float) -> tuple[float, float]:
    """Score pace (lines per minute). Rapid back-and-forth tension scores highest."""
    if dur_sec <= 0:
        return 0.0, 0.0
    lpm = (len(dialogue_events) / dur_sec) * 60.0
    # Sweet spot is ~14-22 lines per minute
    score = min(10.0, (lpm / 16.0) * 8.5)
    return round(score, 2), round(lpm, 1)


def score_window(candidate: dict) -> dict:
    """
    Calculate the composite prefilter score and explanation for a candidate window.
    """
    events = candidate["_events"]
    d_events = [e for e in events if e["type"] == "dialogue"]
    dur = candidate["duration_sec"]

    tone_score, matched_tones = _score_tones(d_events)
    punc_score, punc_notes = _score_ending_punctuation(d_events)
    shock_score, matched_shocks = _score_shock_words(d_events)
    pace_score, lpm = _score_line_pace(d_events, dur)

    # Weights for the 4 requested factors
    # Tone tags (30%), '?' or '...' near end (30%), Shock words (25%), Line pace (15%)
    total_score = (
        0.30 * tone_score
        + 0.30 * punc_score
        + 0.25 * shock_score
        + 0.15 * pace_score
    )

    # Build concise human-readable reason
    reason_parts = []
    if punc_notes:
        reason_parts.append(punc_notes[0])
    if matched_tones:
        tones_sample = ", ".join(list(dict.fromkeys(matched_tones))[:3])
        reason_parts.append(f"{len(matched_tones)} dramatic tones ({tones_sample})")
    if matched_shocks:
        shocks_sample = ", ".join(matched_shocks[:4])
        reason_parts.append(f"shock words [{shocks_sample}]")
    reason_parts.append(f"pace {lpm} lines/min")

    reason_str = "; ".join(reason_parts)

    return {
        "prefilter_score": round(total_score, 2),
        "tone_score": round(tone_score, 2),
        "cliffhanger_punct_score": round(punc_score, 2),
        "shock_words_score": round(shock_score, 2),
        "pace_score": round(pace_score, 2),
        "lines_per_min": lpm,
        "prefilter_reason": reason_str,
    }


def _iou(c1: dict, c2: dict) -> float:
    """Temporal Intersection-over-Union."""
    s = max(c1["_start_s"], c2["_start_s"])
    e = min(c1["_end_s"], c2["_end_s"])
    inter = max(0.0, e - s)
    union = (c1["_end_s"] - c1["_start_s"]) + (c2["_end_s"] - c2["_start_s"]) - inter
    return inter / union if union > 0.0 else 0.0


def prefilter(candidates: list[dict], top_k: int = TOP_PREFILTER_COUNT, dedup_iou: float = 0.65) -> list[dict]:
    """
    Score all candidate windows and keep the top `top_k` (default 12) per episode.
    Applies Non-Maximum Suppression (IoU <= dedup_iou) so the top 12 represent
    distinct, diverse dramatic moments across the episode.

    Returns
    -------
    list[dict]
        Top scored candidate windows, sorted best-first.
    """
    scored = []
    for c in candidates:
        metrics = score_window(c)
        c_copy = dict(c)
        c_copy.update(metrics)
        scored.append(c_copy)

    # Sort descending by composite prefilter_score
    scored.sort(key=lambda x: x["prefilter_score"], reverse=True)

    # Non-maximum suppression over time overlap
    kept = []
    for c in scored:
        if not any(_iou(c, prior) > dedup_iou for prior in kept):
            kept.append(c)
            if len(kept) == top_k:
                break

    return kept


def passing(candidates: list[dict]) -> list[dict]:
    """Compatibility helper returning candidates that passed prefiltering."""
    return prefilter(candidates)
