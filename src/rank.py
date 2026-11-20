"""
src/rank.py
───────────
Rank promo clips:
  1. Compute composite weighted score from config.yaml.
  2. Drop clips with temporal overlap > 50% (IoU > 0.50 or overlap_ratio > 0.50).
  3. Use sentence-transformers (all-MiniLM-L6-v2) to drop semantic near-duplicates.
  4. Select at most max_per_episode clips.
  5. GUARANTEE: always return at least 1 clip (top-scoring) even if deduplication
     would remove everything.
"""

import logging
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_CFG = yaml.safe_load((Path(__file__).parent.parent / "config.yaml").read_text())
_W   = _CFG.get("weights", {
    "hook":        0.30,
    "cliffhanger": 0.30,
    "standalone":  0.25,
    "emotion":     0.15,
})

MAX_PER_EPISODE      = 2
SIMILARITY_THRESHOLD = 0.82

_EMBEDDER: Optional[object] = None


def _get_embedder():
    """Lazy load SentenceTransformer model (safe – returns None on failure)."""
    global _EMBEDDER
    if _EMBEDDER is None:
        try:
            from sentence_transformers import SentenceTransformer
            _EMBEDDER = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception as e:
            logger.warning(f"Could not load sentence-transformers: {e}")
            _EMBEDDER = None
    return _EMBEDDER


def _fmt(secs: float) -> str:
    """Float seconds → 'mm:ss.ss' string."""
    m = int(secs) // 60
    s = secs % 60
    return f"{m:02d}:{s:05.2f}"


def _temporal_overlap(c1: dict, c2: dict) -> tuple[float, float]:
    s1 = c1.get("_start_s", c1.get("start_s", 0.0))
    e1 = c1.get("_end_s",   c1.get("end_s",   0.0))
    s2 = c2.get("_start_s", c2.get("start_s", 0.0))
    e2 = c2.get("_end_s",   c2.get("end_s",   0.0))

    inter_s = max(s1, s2)
    inter_e = min(e1, e2)
    inter   = max(0.0, inter_e - inter_s)

    dur1  = e1 - s1
    dur2  = e2 - s2
    union = dur1 + dur2 - inter

    iou          = inter / union if union > 0 else 0.0
    overlap_ratio = inter / min(dur1, dur2) if min(dur1, dur2) > 0 else 0.0
    return iou, overlap_ratio


def _extract_clip_text(clip: dict) -> str:
    events = clip.get("_events", [])
    dialogue_lines = [e["text"] for e in events if e.get("type") == "dialogue" and e.get("text")]
    return " ".join(dialogue_lines) if dialogue_lines else clip.get("why_it_works", "")


def compute_weighted_score(c: dict) -> float:
    """Compute weighted composite score from config.yaml weights."""
    hook  = float(c.get("hook", 0.0))
    cliff = float(c.get("cliffhanger", 0.0))
    emo   = float(c.get("emotion", 0.0))
    stand = float(c.get("standalone", c.get("understandability", 7.0)))

    w_hook  = _W.get("hook",        0.30)
    w_cliff = _W.get("cliffhanger", 0.30)
    w_stand = _W.get("standalone",  0.25)
    w_emo   = _W.get("emotion",     0.15)

    total = w_hook + w_cliff + w_stand + w_emo
    w_h, w_c, w_s, w_e = w_hook/total, w_cliff/total, w_stand/total, w_emo/total

    return round(w_h * hook + w_c * cliff + w_s * stand + w_e * emo, 3)


def _format_clip(cand: dict, ep_num: str = "Episode 1") -> dict:
    """Normalize a candidate into the final output format."""
    return {
        "clip_id":          cand["clip_id"],
        "episode":          cand.get("episode", ep_num),
        "duration_sec":     cand["duration_sec"],
        "_start_s":         cand.get("_start_s", cand.get("start_s", 0.0)),
        "_end_s":           cand.get("_end_s",   cand.get("end_s",   0.0)),
        "start_s":          cand.get("_start_s", cand.get("start_s", 0.0)),
        "end_s":            cand.get("_end_s",   cand.get("end_s",   0.0)),
        "start_fmt":        _fmt(cand.get("_start_s", cand.get("start_s", 0.0))),
        "end_fmt":          _fmt(cand.get("_end_s",   cand.get("end_s",   0.0))),
        "hook":             cand.get("hook",        0.0),
        "cliffhanger":      cand.get("cliffhanger", 0.0),
        "standalone":       cand.get("standalone",  cand.get("understandability", 7.0)),
        "emotion":          cand.get("emotion",     0.0),
        "total_score":      cand.get("total_score", 0.0),
        "hook_line":        cand.get("hook_line",        ""),
        "hook_type":        cand.get("hook_type",        ""),
        "cliffhanger_line": cand.get("cliffhanger_line", ""),
        "why_it_works":     cand.get("why_it_works",     ""),
        "problems":         cand.get("problems",         []),
        "standalone_test":  cand.get("standalone_test",  {}),
        "raw_evaluation":   cand.get("raw_evaluation",   {}),
    }


def rank_and_select(
    scored_clips:    list[dict],
    max_per_episode: int   = MAX_PER_EPISODE,
    max_overlap_pct: float = 0.50,
) -> list[dict]:
    """
    Rank and deduplicate LLM-scored clips. Always returns ≥ 1 clip.
    """
    if not scored_clips:
        return []

    for c in scored_clips:
        c["total_score"] = compute_weighted_score(c)

    sorted_clips = sorted(scored_clips, key=lambda x: x["total_score"], reverse=True)

    # Semantic embeddings
    embedder   = _get_embedder()
    embeddings = {}
    if embedder is not None:
        texts = [_extract_clip_text(c) for c in sorted_clips]
        try:
            emb_list = embedder.encode(texts, convert_to_tensor=True)
            for idx, c in enumerate(sorted_clips):
                embeddings[c["clip_id"]] = emb_list[idx]
        except Exception as e:
            logger.warning(f"Error computing embeddings: {e}")
            embedder = None

    selected = []
    for cand in sorted_clips:
        cid = cand["clip_id"]

        temporal_conflict = any(
            _temporal_overlap(cand, kept)[0] > max_overlap_pct
            or _temporal_overlap(cand, kept)[1] > max_overlap_pct
            for kept in selected
        )
        if temporal_conflict:
            continue

        semantic_conflict = False
        if embedder is not None and cid in embeddings:
            from sentence_transformers import util
            cand_emb = embeddings[cid]
            for kept in selected:
                if kept["clip_id"] in embeddings:
                    sim = util.cos_sim(cand_emb, embeddings[kept["clip_id"]]).item()
                    if sim > SIMILARITY_THRESHOLD:
                        semantic_conflict = True
                        break
        if semantic_conflict:
            continue

        selected.append(_format_clip(cand))
        if len(selected) == max_per_episode:
            break

    # GUARANTEE: always return at least 1 clip
    if not selected and sorted_clips:
        selected = [_format_clip(sorted_clips[0])]

    return selected


def rank_prefiltered(
    prefiltered_clips: list[dict],
    episode:           Optional[dict] = None,
    max_per_episode:   int            = MAX_PER_EPISODE,
    max_overlap_pct:   float          = 0.50,
) -> list[dict]:
    """
    Fallback ranking: uses heuristic prefilter scores.
    Always returns ≥ 1 clip.
    """
    if not prefiltered_clips:
        return []

    ep_num = episode.get("episode_number", "Episode 1") if episode else "Episode 1"

    prepared = []
    for c in prefiltered_clips:
        cand = dict(c)
        events   = cand.get("_events", [])
        d_events = [e for e in events if e.get("type") == "dialogue" and e.get("text")]

        hook_line  = d_events[0]["text"]  if d_events else (events[0]["text"]  if events else "")
        cliff_line = d_events[-1]["text"] if d_events else (events[-1]["text"] if events else "")

        cand.setdefault("episode",          ep_num)
        cand.setdefault("hook_line",        hook_line)
        cand.setdefault("hook_type",        "question" if "?" in hook_line else "dialogue hook")
        cand.setdefault("cliffhanger_line", cliff_line)
        cand.setdefault("why_it_works",     f"Heuristic rank: {cand.get('prefilter_reason', 'high emotional pace')}")
        cand.setdefault("hook",        round(min(10.0, max(1.0, cand.get("shock_words_score",      7.0))), 1))
        cand.setdefault("cliffhanger", round(min(10.0, max(1.0, cand.get("cliffhanger_punct_score", 7.0))), 1))
        cand.setdefault("emotion",     round(min(10.0, max(1.0, cand.get("tone_score",              7.0))), 1))
        cand.setdefault("standalone",  7.5)
        cand.setdefault("problems",    [])
        cand["total_score"] = cand.get("prefilter_score", compute_weighted_score(cand))
        prepared.append(cand)

    prepared.sort(key=lambda x: x["total_score"], reverse=True)

    # Semantic deduplication
    embedder   = _get_embedder()
    embeddings = {}
    if embedder is not None:
        texts = [_extract_clip_text(c) for c in prepared]
        try:
            emb_list = embedder.encode(texts, convert_to_tensor=True)
            for idx, c in enumerate(prepared):
                embeddings[c["clip_id"]] = emb_list[idx]
        except Exception as e:
            logger.warning(f"Error computing embeddings (fallback): {e}")
            embedder = None

    selected = []
    for cand in prepared:
        cid = cand["clip_id"]

        temporal_conflict = any(
            _temporal_overlap(cand, kept)[0] > max_overlap_pct
            or _temporal_overlap(cand, kept)[1] > max_overlap_pct
            for kept in selected
        )
        if temporal_conflict:
            continue

        semantic_conflict = False
        if embedder is not None and cid in embeddings:
            from sentence_transformers import util
            cand_emb = embeddings[cid]
            for kept in selected:
                if kept["clip_id"] in embeddings:
                    sim = util.cos_sim(cand_emb, embeddings[kept["clip_id"]]).item()
                    if sim > SIMILARITY_THRESHOLD:
                        semantic_conflict = True
                        break
        if semantic_conflict:
            continue

        standalone_test = {
            "characters":        list(dict.fromkeys(
                e.get("speaker") for e in cand.get("_events", []) if e.get("speaker")
            )),
            "conflict":          "Determined via heuristic conflict pre-filtering",
            "what_happens_next": "Cliffhanger leaves high anticipation",
            "understandability": 7.5,
        }

        out = _format_clip(cand, ep_num)
        out["standalone_test"] = standalone_test
        out["raw_evaluation"]  = {
            "mode": "fallback_prefilter",
            "prefilter_reason": cand.get("prefilter_reason"),
        }
        selected.append(out)
        if len(selected) == max_per_episode:
            break

    # GUARANTEE: always return at least 1 clip
    if not selected and prepared:
        out = _format_clip(prepared[0], ep_num)
        out["standalone_test"] = {
            "characters": [], "conflict": "N/A",
            "what_happens_next": "N/A", "understandability": 7.5,
        }
        out["raw_evaluation"] = {"mode": "fallback_prefilter"}
        selected = [out]

    return selected
