"""
src/rank.py
───────────
Rank promo clips:
  1. Calculate composite weighted score from config.yaml.
  2. Drop clips with temporal overlap > 50% (IoU > 0.50 or overlap_ratio > 0.50).
  3. Use sentence-transformers ('all-MiniLM-L6-v2') to drop semantic near-duplicates.
  4. Select at most 2 clips per episode (max 2 per episode).
"""

import logging
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_CFG = yaml.safe_load((Path(__file__).parent.parent / "config.yaml").read_text())
_W = _CFG.get("weights", {
    "hook": 0.30,
    "cliffhanger": 0.30,
    "standalone": 0.25,
    "emotion": 0.15,
})

MAX_PER_EPISODE = 2
SIMILARITY_THRESHOLD = 0.82  # Cosine similarity threshold for semantic near-duplicates

_EMBEDDER: Optional[object] = None


def _get_embedder():
    """Lazy load SentenceTransformer model."""
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
    """Float seconds → 'mm:ss.s' string."""
    m = int(secs) // 60
    s = secs % 60
    return f"{m:02d}:{s:05.2f}"


def _temporal_overlap(c1: dict, c2: dict) -> tuple[float, float]:
    """
    Compute temporal IoU and overlap ratio relative to shorter clip.
    Returns (iou, overlap_ratio).
    """
    s1 = c1.get("_start_s", c1.get("start_s", 0.0))
    e1 = c1.get("_end_s", c1.get("end_s", 0.0))
    s2 = c2.get("_start_s", c2.get("start_s", 0.0))
    e2 = c2.get("_end_s", c2.get("end_s", 0.0))

    inter_s = max(s1, s2)
    inter_e = min(e1, e2)
    inter = max(0.0, inter_e - inter_s)

    dur1 = e1 - s1
    dur2 = e2 - s2
    union = dur1 + dur2 - inter

    iou = inter / union if union > 0 else 0.0
    overlap_ratio = inter / min(dur1, dur2) if min(dur1, dur2) > 0 else 0.0
    return iou, overlap_ratio


def _extract_clip_text(clip: dict) -> str:
    """Extract clean dialogue text for semantic embedding."""
    events = clip.get("_events", [])
    dialogue_lines = [e["text"] for e in events if e.get("type") == "dialogue" and e.get("text")]
    return " ".join(dialogue_lines) if dialogue_lines else clip.get("why_it_works", "")


def compute_weighted_score(c: dict) -> float:
    """Compute weighted composite score from config.yaml weights."""
    hook = float(c.get("hook", 0.0))
    cliff = float(c.get("cliffhanger", 0.0))
    emo = float(c.get("emotion", 0.0))
    stand = float(c.get("standalone", c.get("understandability", 7.0)))

    w_hook = _W.get("hook", 0.30)
    w_cliff = _W.get("cliffhanger", 0.30)
    w_stand = _W.get("standalone", 0.25)
    w_emo = _W.get("emotion", 0.15)

    sum_w = w_hook + w_cliff + w_stand + w_emo
    w_h, w_c, w_s, w_e = w_hook / sum_w, w_cliff / sum_w, w_stand / sum_w, w_emo / sum_w

    score = w_h * hook + w_c * cliff + w_s * stand + w_e * emo
    return round(score, 3)


def rank_and_select(
    scored_clips: list[dict],
    max_per_episode: int = MAX_PER_EPISODE,
    max_overlap_pct: float = 0.50,
) -> list[dict]:
    """
    Rank and filter scored candidate clips:
      1. Sort descending by config-weighted composite score.
      2. Drop clips overlapping > 50% with an already selected clip.
      3. Drop semantic near-duplicates using sentence-transformers (all-MiniLM-L6-v2).
      4. Select top `max_per_episode` (default 2) clips.
    """
    if not scored_clips:
        return []

    # 1. Update total_score with config weights
    for c in scored_clips:
        c["total_score"] = compute_weighted_score(c)

    # Sort descending by total score
    sorted_clips = sorted(scored_clips, key=lambda x: x["total_score"], reverse=True)

    # 2. Prepare text embeddings for semantic near-duplicate detection
    embedder = _get_embedder()
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

        # Check temporal overlap > 50%
        temporal_conflict = False
        for kept in selected:
            iou, overlap_ratio = _temporal_overlap(cand, kept)
            if iou > max_overlap_pct or overlap_ratio > max_overlap_pct:
                logger.info(
                    f"Dropping {cid}: temporal overlap > 50% with {kept['clip_id']} "
                    f"(iou={iou:.2f}, overlap_ratio={overlap_ratio:.2f})"
                )
                temporal_conflict = True
                break

        if temporal_conflict:
            continue

        # Check semantic near-duplicate using all-MiniLM-L6-v2
        semantic_conflict = False
        if embedder is not None and cid in embeddings:
            from sentence_transformers import util
            cand_emb = embeddings[cid]
            for kept in selected:
                kept_id = kept["clip_id"]
                if kept_id in embeddings:
                    sim = util.cos_sim(cand_emb, embeddings[kept_id]).item()
                    if sim > SIMILARITY_THRESHOLD:
                        logger.info(
                            f"Dropping {cid}: semantic near-duplicate with {kept_id} "
                            f"(cosine similarity={sim:.3f} > {SIMILARITY_THRESHOLD})"
                        )
                        semantic_conflict = True
                        break

        if semantic_conflict:
            continue

        # Format and append winning clip
        cand_dict = {
            "clip_id": cand["clip_id"],
            "episode": cand.get("episode", "Episode 1"),
            "duration_sec": cand["duration_sec"],
            "_start_s": cand["_start_s"],
            "_end_s": cand["_end_s"],
            "start_s": cand["_start_s"],
            "end_s": cand["_end_s"],
            "start_fmt": _fmt(cand["_start_s"]),
            "end_fmt": _fmt(cand["_end_s"]),
            "hook": cand.get("hook", 0.0),
            "cliffhanger": cand.get("cliffhanger", 0.0),
            "standalone": cand.get("standalone", cand.get("understandability", 7.0)),
            "emotion": cand.get("emotion", 0.0),
            "total_score": cand["total_score"],
            "hook_line": cand.get("hook_line", ""),
            "hook_type": cand.get("hook_type", ""),
            "cliffhanger_line": cand.get("cliffhanger_line", ""),
            "why_it_works": cand.get("why_it_works", ""),
            "problems": cand.get("problems", []),
            "standalone_test": cand.get("standalone_test", {}),
            "raw_evaluation": cand.get("raw_evaluation", {}),
        }
        selected.append(cand_dict)

        if len(selected) == max_per_episode:
            break

    return selected


def rank_prefiltered(
    prefiltered_clips: list[dict],
    episode: Optional[dict] = None,
    max_per_episode: int = MAX_PER_EPISODE,
    max_overlap_pct: float = 0.50,
) -> list[dict]:
    """
    Fallback ranking mode when no LLM API key is configured.
    Ranks candidates using prefilter heuristic scores (tone, shock words, cliffhanger punctuation, pace),
    drops temporal overlap > 50%, and drops semantic near-duplicates using sentence-transformers (all-MiniLM-L6-v2).
    """
    if not prefiltered_clips:
        return []

    ep_num = episode.get("episode_number", "Episode 1") if episode else "Episode 1"

    # Adapt prefilter candidate format into the standard scored candidate schema
    prepared = []
    for c in prefiltered_clips:
        cand = dict(c)
        events = cand.get("_events", [])
        d_events = [e for e in events if e.get("type") == "dialogue" and e.get("text")]

        hook_line = d_events[0]["text"] if d_events else (events[0]["text"] if events else "")
        cliff_line = d_events[-1]["text"] if d_events else (events[-1]["text"] if events else "")

        cand.setdefault("episode", ep_num)
        cand.setdefault("hook_line", hook_line)
        cand.setdefault("hook_type", "question" if "?" in hook_line else "dialogue hook")
        cand.setdefault("cliffhanger_line", cliff_line)
        cand.setdefault("why_it_works", f"Fallback heuristic rank: {cand.get('prefilter_reason', 'high emotional pace and unresolved ending')}")
        cand.setdefault("hook", round(min(10.0, max(1.0, cand.get("shock_words_score", 7.0))), 1))
        cand.setdefault("cliffhanger", round(min(10.0, max(1.0, cand.get("cliffhanger_punct_score", 7.0))), 1))
        cand.setdefault("emotion", round(min(10.0, max(1.0, cand.get("tone_score", 7.0))), 1))
        cand.setdefault("standalone", 7.5)
        cand.setdefault("problems", [])
        cand["total_score"] = cand.get("prefilter_score", compute_weighted_score(cand))
        prepared.append(cand)

    # Sort descending by total_score
    prepared.sort(key=lambda x: x["total_score"], reverse=True)

    # Deduplication using sentence-transformers
    embedder = _get_embedder()
    embeddings = {}
    if embedder is not None:
        texts = [_extract_clip_text(c) for c in prepared]
        try:
            emb_list = embedder.encode(texts, convert_to_tensor=True)
            for idx, c in enumerate(prepared):
                embeddings[c["clip_id"]] = emb_list[idx]
        except Exception as e:
            logger.warning(f"Error computing embeddings in fallback mode: {e}")
            embedder = None

    selected = []
    for cand in prepared:
        cid = cand["clip_id"]

        # Temporal overlap check > 50%
        temporal_conflict = False
        for kept in selected:
            iou, overlap_ratio = _temporal_overlap(cand, kept)
            if iou > max_overlap_pct or overlap_ratio > max_overlap_pct:
                temporal_conflict = True
                break
        if temporal_conflict:
            continue

        # Semantic duplicate check
        semantic_conflict = False
        if embedder is not None and cid in embeddings:
            from sentence_transformers import util
            cand_emb = embeddings[cid]
            for kept in selected:
                kept_id = kept["clip_id"]
                if kept_id in embeddings:
                    sim = util.cos_sim(cand_emb, embeddings[kept_id]).item()
                    if sim > SIMILARITY_THRESHOLD:
                        semantic_conflict = True
                        break
        if semantic_conflict:
            continue

        cand_dict = {
            "clip_id": cand["clip_id"],
            "episode": cand.get("episode", ep_num),
            "duration_sec": cand["duration_sec"],
            "_start_s": cand["_start_s"],
            "_end_s": cand["_end_s"],
            "start_s": cand["_start_s"],
            "end_s": cand["_end_s"],
            "start_fmt": _fmt(cand["_start_s"]),
            "end_fmt": _fmt(cand["_end_s"]),
            "hook": cand.get("hook", 7.0),
            "cliffhanger": cand.get("cliffhanger", 7.0),
            "standalone": cand.get("standalone", 7.5),
            "emotion": cand.get("emotion", 7.0),
            "total_score": cand["total_score"],
            "hook_line": cand.get("hook_line", ""),
            "hook_type": cand.get("hook_type", ""),
            "cliffhanger_line": cand.get("cliffhanger_line", ""),
            "why_it_works": cand.get("why_it_works", ""),
            "problems": cand.get("problems", []),
            "standalone_test": {
                "characters": list(dict.fromkeys([e.get("speaker") for e in cand.get("_events", []) if e.get("speaker")])),
                "conflict": "Determined via heuristic conflict pre-filtering",
                "what_happens_next": "Cliffhanger leaves high anticipation",
                "understandability": 7.5,
            },
            "raw_evaluation": {"mode": "fallback_prefilter", "prefilter_reason": cand.get("prefilter_reason")},
        }
        selected.append(cand_dict)
        if len(selected) == max_per_episode:
            break

    return selected
