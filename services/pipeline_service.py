"""
services/pipeline_service.py
────────────────────────────
Orchestrates the 6-stage microdrama promo discovery pipeline for Streamlit.
Integrates with SQLite database for history persistence.
"""

import io
import logging
from pathlib import Path
import tempfile
from typing import Callable, Optional

import yaml

from src.parse import parse_screenplay
from src.candidates import build_candidates
from src.prefilter import prefilter
from src.score import score_clips
from src.rank import rank_and_select, rank_prefiltered
from src.report import write_report_md
from src.validate import validate_episode, validate_candidates, validate_and_filter
from db.database import get_db

logger = logging.getLogger(__name__)


def run_pipeline_for_script(
    script_text: str,
    filename: str,
    use_fallback: bool = False,
    max_per_episode: int = 2,
    min_seconds: int = 20,
    max_seconds: int = 60,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    save_to_db: bool = True,
    session_title: Optional[str] = None,
) -> tuple[dict, list[dict], str, Optional[str]]:
    """
    Execute the promo clip discovery pipeline for an uploaded screenplay.

    Parameters
    ----------
    script_text : str
        Raw text of the screenplay.
    filename : str
        Source filename.
    use_fallback : bool
        If True, skips LLM scoring and uses the heuristic prefilter ranker.
    max_per_episode : int
        Maximum winning clips to select.
    min_seconds : int
        Minimum promo clip duration.
    max_seconds : int
        Maximum promo clip duration.
    progress_callback : Callable[[int, str], None], optional
        Callback taking (percentage_int, status_message).
    save_to_db : bool
        Whether to store run results in SQLite.

    Returns
    -------
    tuple[dict, list[dict], str, Optional[str]]
        (episode_dict, ranked_clips, report_md, session_id)
    """
    def _notify(pct: int, msg: str):
        if progress_callback:
            progress_callback(pct, msg)

    # Write temporary file for parser
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
        tmp.write(script_text)
        tmp_path = Path(tmp.name)

    try:
        # ── Stage 1: Parse ────────────────────────────────────────────────
        _notify(15, f"[{filename}] Stage 1/5: Parsing dialogue lines, tones & timestamps...")
        episode = parse_screenplay(tmp_path)
        validate_episode(episode)

        # ── Stage 2: Candidates ───────────────────────────────────────────
        _notify(35, f"[{filename}] Stage 2/5: Enumerating dialogue-bounded windows ({min_seconds}s–{max_seconds}s)...")
        candidates = build_candidates(episode, min_seconds=min_seconds, max_seconds=max_seconds)
        validate_candidates(candidates)

        # ── Stage 3: Prefilter ────────────────────────────────────────────
        _notify(55, f"[{filename}] Stage 3/5: Prefiltering top 12 windows (tone tags, punctuation, shock words, pace)...")
        good = prefilter(candidates, top_k=12)

        # ── Stage 4 & 5: Score & Rank ─────────────────────────────────────
        if use_fallback:
            _notify(80, f"[{filename}] Stage 4/5: Fallback Heuristic Ranking + sentence-transformers deduplication...")
            ranked = rank_prefiltered(good, episode=episode, max_per_episode=max_per_episode)
            mode_name = "Fallback (Heuristic)"
        else:
            _notify(75, f"[{filename}] Stage 4/5: LLM Pydantic Scoring & Blind Standalone comprehension testing...")
            scored = score_clips(good, episode)
            ep_num = episode.get("episode_number", "Episode 1")
            for c in scored:
                c.setdefault("episode", ep_num)
            valid_scored, _ = validate_and_filter(scored)

            _notify(90, f"[{filename}] Stage 5/5: Ranking with weights & sentence-transformers (all-MiniLM-L6-v2) dedup...")
            ranked = rank_and_select(valid_scored, max_per_episode=max_per_episode)
            mode_name = "LLM (Nemotron/Gemini)"

        # ── Generate Report Markdown ──────────────────────────────────────
        out_tmp_md = Path(tempfile.gettempdir()) / f"{Path(filename).stem}_report.md"
        write_report_md(episode, ranked, out_tmp_md)
        report_md = out_tmp_md.read_text(encoding="utf-8") if out_tmp_md.exists() else ""

        session_id = None
        if save_to_db:
            db = get_db()
            title = session_title or f"{episode.get('episode_number', Path(filename).stem)} Run"
            settings = {
                "min_seconds": min_seconds,
                "max_seconds": max_seconds,
                "max_per_episode": max_per_episode,
                "mode": mode_name,
            }
            session_id = db.create_session(
                title=title,
                filename=filename,
                script_text=script_text,
                mode=mode_name,
                settings=settings,
                report_md=report_md,
            )
            db.save_clips(session_id, ranked)

        _notify(100, f"[{filename}] Complete! Extracted {len(ranked)} winning promo clips.")
        return episode, ranked, report_md, session_id

    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
