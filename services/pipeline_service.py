"""
services/pipeline_service.py
────────────────────────────
Orchestrates the 6-stage microdrama promo discovery pipeline for Streamlit.
Integrates with SQLite database for history persistence.

Auto-fallback: if LLM returns a quota/credit/auth error, automatically
switches to heuristic prefilter ranking so the UI always shows results.
"""

import logging
import tempfile
from pathlib import Path
from typing import Callable, Optional

import yaml

from src.parse import parse_screenplay
from src.candidates import build_candidates
from src.prefilter import prefilter
from src.score import score_clips
from src.rank import rank_and_select, rank_prefiltered
from src.report import write_report_md
from src.validate import validate_episode, validate_candidates, validate_and_filter
from src.llm import QuotaOrCreditExceededError
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

    Returns
    -------
    tuple[dict, list[dict], str, Optional[str]]
        (episode_dict, ranked_clips, report_md, session_id)
    """
    def _notify(pct: int, msg: str):
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception:
                pass

    # Write temporary file for parser
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
        tmp.write(script_text)
        tmp_path = Path(tmp.name)

    try:
        # ── Stage 1: Parse ────────────────────────────────────────────────
        _notify(10, f"[{filename}] Stage 1/5: Parsing dialogue lines, tones & timestamps...")
        episode = parse_screenplay(tmp_path)
        validate_episode(episode)

        if not episode.get("events"):
            raise ValueError(
                f"No events could be parsed from '{filename}'. "
                "Please verify the file is a valid screenplay in .txt format."
            )

        # ── Stage 2: Candidates ───────────────────────────────────────────
        _notify(30, f"[{filename}] Stage 2/5: Building dialogue windows ({min_seconds}s–{max_seconds}s)...")
        try:
            candidates = build_candidates(
                episode, min_seconds=min_seconds, max_seconds=max_seconds
            )
        except TypeError:
            candidates = build_candidates(episode)

        validate_candidates(candidates)

        if not candidates:
            raise ValueError(
                f"No candidate windows found in '{filename}'. "
                "The screenplay may be too short or have no valid dialogue segments."
            )

        # ── Stage 3: Prefilter ────────────────────────────────────────────
        _notify(50, f"[{filename}] Stage 3/5: Scoring & prefiltering top 12 windows...")
        good = prefilter(candidates, top_k=12)
        if not good:
            good = candidates[:12]  # Safety: use raw candidates if prefilter returns nothing

        # ── Stage 4 & 5: Score & Rank ─────────────────────────────────────
        ranked = []
        mode_name = "Fallback (Heuristic)"

        if use_fallback:
            _notify(75, f"[{filename}] Stage 4/5: Fallback Heuristic Ranking...")
            ranked = rank_prefiltered(good, episode=episode, max_per_episode=max_per_episode)
        else:
            _notify(70, f"[{filename}] Stage 4/5: LLM Scoring & Blind Standalone Test...")
            try:
                scored = score_clips(good, episode)
                ep_num = episode.get("episode_number", "Episode 1")
                for c in scored:
                    c.setdefault("episode", ep_num)
                valid_scored, _ = validate_and_filter(scored)

                _notify(88, f"[{filename}] Stage 5/5: Ranking with weights & deduplication...")

                if valid_scored:
                    ranked = rank_and_select(valid_scored, max_per_episode=max_per_episode)
                    mode_name = "LLM (Nemotron/Gemini)"
                else:
                    logger.warning(f"[{filename}] All LLM-scored clips failed validation — using fallback")
                    ranked = rank_prefiltered(good, episode=episode, max_per_episode=max_per_episode)

            except QuotaOrCreditExceededError as qe:
                logger.warning(
                    f"[{filename}] LLM quota/credit error — auto-engaging fallback: {qe}"
                )
                _notify(80, f"[{filename}] ⚠️ LLM quota exceeded — switching to heuristic fallback...")
                ranked = rank_prefiltered(good, episode=episode, max_per_episode=max_per_episode)

        if not ranked:
            # Absolute last resort: pick top-1 prefiltered candidate
            if good:
                ranked = rank_prefiltered(good[:1], episode=episode, max_per_episode=1)
            if not ranked:
                raise ValueError(
                    f"⚠️ No promo candidates could be extracted from '{filename}'. "
                    "Please verify the screenplay has dialogue lines with timestamps."
                )

        # ── Generate Report ───────────────────────────────────────────────
        out_md = Path(tempfile.gettempdir()) / f"{Path(filename).stem}_report.md"
        write_report_md(episode, ranked, out_md)
        report_md = out_md.read_text(encoding="utf-8") if out_md.exists() else ""

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

        _notify(100, f"[{filename}] ✅ Complete! Extracted {len(ranked)} winning promo clips.")
        return episode, ranked, report_md, session_id

    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
