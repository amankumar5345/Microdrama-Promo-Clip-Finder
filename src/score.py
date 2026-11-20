"""
src/score.py
────────────
Score candidate promo clips using LLM:
  1. Main evaluation with Pydantic schema (hook, cliffhanger, emotion, hook_line, cliffhanger_line).
  2. Blind Standalone Test: the model sees ONLY the clip text (no series summary, no logline)
     and answers characters, conflict, what-happens-next, and 1-10 understandability score.

Rules:
  • Temperature: 0
  • JSON only
  • Quote ONLY lines that exist in the clip
  • NEVER give timestamps in the LLM response
  • Retry once on bad JSON, then log and skip
"""

import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, ValidationError
import yaml

from src.llm import llm

logger = logging.getLogger(__name__)

_CFG = yaml.safe_load((Path(__file__).parent.parent / "config.yaml").read_text())
_W = _CFG.get("weights", {
    "hook": 0.30,
    "cliffhanger": 0.30,
    "standalone": 0.25,
    "emotion": 0.15,
})


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class SubScores(BaseModel):
    hook: float = Field(..., ge=1, le=10, description="Hook intensity (1-10)")
    cliffhanger: float = Field(..., ge=1, le=10, description="Unresolved cliffhanger pull (1-10)")
    emotion: float = Field(..., ge=1, le=10, description="Emotional engagement (1-10)")


class ClipEvaluation(BaseModel):
    clip_id: str = Field(..., description="Unique clip identifier e.g. ep01_w083")
    hook_line: str = Field(
        ...,
        description="Exact quoted dialogue or action line that serves as the hook. Must exist in the clip lines."
    )
    hook_type: str = Field(
        ...,
        description="Category of hook e.g. question, shock reveal, confrontation, visual action"
    )
    cliffhanger_line: str = Field(
        ...,
        description="Exact quoted line at or near the end that leaves unresolved tension. Must exist in the clip lines."
    )
    why_it_works: str = Field(
        ...,
        description="Concise rationale explaining why this clip works as a standalone promo."
    )
    scores: SubScores
    problems: list[str] = Field(
        default_factory=list,
        description="Any narrative confusion, context gaps, or awkward cuts. Empty list if none."
    )


class BlindStandaloneEvaluation(BaseModel):
    characters: list[str] = Field(
        ...,
        description="List of characters appearing or interacting in this clip"
    )
    conflict: str = Field(
        ...,
        description="The primary conflict or tension depicted in this clip"
    )
    what_happens_next: str = Field(
        ...,
        description="What the audience anticipates or urgently needs to find out next"
    )
    understandability: float = Field(
        ...,
        ge=1,
        le=10,
        description="Cold understandability score (1-10) for a viewer with zero prior context"
    )


# ── Text Formatting Helpers ───────────────────────────────────────────────────

def _fmt_time(s: float) -> str:
    m = int(s) // 60
    sec = s % 60
    return f"{m:02d}:{sec:05.2f}"


def format_clip_lines(events: list[dict]) -> str:
    """Format clip lines as: time | speaker (tone): text"""
    lines = []
    for e in events:
        t_str = _fmt_time(e["start_s"])
        etype = e.get("type", "dialogue")
        if etype == "dialogue":
            spk = e.get("speaker") or "UNKNOWN"
            tone = e.get("tone")
            tone_str = f" ({tone})" if tone else ""
            lines.append(f'{t_str} | {spk}{tone_str}: {e.get("text", "")}')
        elif etype == "camera":
            lines.append(f'{t_str} | CAMERA: {e.get("text", "")}')
        elif etype == "action":
            lines.append(f'{t_str} | ACTION: {e.get("text", "")}')
        elif etype == "sound":
            lines.append(f'{t_str} | SOUND FX: {e.get("text", "")}')
    return "\n".join(lines)


def format_raw_clip_text_only(events: list[dict]) -> str:
    """
    Format clip for the Blind Standalone Test:
    ONLY dialogue and action text, NO timestamps, NO series context.
    """
    lines = []
    for e in events:
        etype = e.get("type", "dialogue")
        if etype == "dialogue":
            spk = e.get("speaker") or "UNKNOWN"
            tone = e.get("tone")
            tone_str = f" ({tone})" if tone else ""
            lines.append(f'{spk}{tone_str}: {e.get("text", "")}')
        elif etype == "action":
            lines.append(f'ACTION: {e.get("text", "")}')
    return "\n".join(lines)


# ── Prompt Builders ───────────────────────────────────────────────────────────

def build_scoring_prompt(clip_id: str, formatted_lines: str, episode: dict) -> str:
    series_summary = (
        f"SERIES SUMMARY:\n"
        f"Episode: {episode.get('episode_number', '')}\n"
        f"Logline: {episode.get('logline', '')}\n"
        f"Continuity Notes: {episode.get('continuity_notes', '')}"
    )

    rubric = """RUBRIC (Score each dimension strictly from 1 to 10):
1. hook (1-10): How gripping are the opening moments (first 3 seconds)? Does it immediately grab viewer attention?
2. cliffhanger (1-10): Does the clip end on high, unresolved tension where the viewer desperately wants to know what happens next?
3. emotion (1-10): How intense is the dramatic payoff (shock, betrayal, heartbreak, outrage)?

RULES:
- Return ONLY a valid JSON object matching the schema.
- temperature is 0.
- NEVER include timestamps or time values anywhere in your JSON response.
- quote ONLY lines that literally exist in the clip lines below for hook_line and cliffhanger_line.
- If there are narrative clarity or cut issues, list them under problems; otherwise return an empty array []."""

    return f"""You are a professional promo editor for a micro-drama streaming platform.
Evaluate this candidate promo clip ({clip_id}) for use as a 20-60s social video trailer.

{series_summary}

CLIP LINES FOR {clip_id}:
{formatted_lines}

{rubric}
"""


def build_blind_standalone_prompt(clip_id: str, raw_text: str) -> str:
    """Prompt for blind evaluation: model sees ONLY the clip text."""
    return f"""You are evaluating a standalone video scene cold, with NO prior knowledge of the story, background, or series.
Read ONLY the following scene text:

SCENE TEXT ({clip_id}):
{raw_text}

Answer strictly as a JSON object matching the schema:
1. characters: list of distinct characters who speak or act in this scene.
2. conflict: what is the central confrontation, struggle, or tension?
3. what_happens_next: what unresolved question or next event does a viewer desperately want answered?
4. understandability: score from 1 to 10 on how easily a complete stranger can follow the scene cold without prior explanation (1 = totally baffling, 10 = completely clear, self-contained dramatic beat).

RULES:
- Return ONLY a valid JSON object matching the schema.
- temperature is 0.
- NEVER include timestamps in your response.
"""


# ── Evaluators with Retry Logic ───────────────────────────────────────────────

def score_single_clip(candidate: dict, episode: dict) -> Optional[dict]:
    """Score one candidate clip with retry-once-on-bad-JSON."""
    clip_id = candidate["clip_id"]
    formatted_lines = format_clip_lines(candidate["_events"])
    prompt = build_scoring_prompt(clip_id, formatted_lines, episode)
    schema = ClipEvaluation.model_json_schema()

    for attempt in (1, 2):
        try:
            raw_response = llm(prompt, schema, temperature=0.0)
            validated = ClipEvaluation.model_validate(raw_response)
            return validated.model_dump()
        except (ValidationError, json.JSONDecodeError, Exception) as err:
            if attempt == 1:
                logger.warning(
                    f"[{clip_id}] Bad JSON or validation error on attempt 1: {err}. Retrying once..."
                )
            else:
                logger.error(f"[{clip_id}] Second attempt failed: {err}. Skipping clip.")
                return None
    return None


def run_blind_standalone_test(candidate: dict) -> Optional[dict]:
    """
    Run the blind standalone test: model sees ONLY the clip text (no logline/context)
    with retry-once-on-bad-JSON.
    """
    clip_id = candidate["clip_id"]
    raw_text = format_raw_clip_text_only(candidate["_events"])
    prompt = build_blind_standalone_prompt(clip_id, raw_text)
    schema = BlindStandaloneEvaluation.model_json_schema()

    for attempt in (1, 2):
        try:
            raw_response = llm(prompt, schema, temperature=0.0)
            validated = BlindStandaloneEvaluation.model_validate(raw_response)
            return validated.model_dump()
        except (ValidationError, json.JSONDecodeError, Exception) as err:
            if attempt == 1:
                logger.warning(
                    f"[{clip_id}] Blind test bad JSON on attempt 1: {err}. Retrying once..."
                )
            else:
                logger.error(f"[{clip_id}] Blind test second attempt failed: {err}. Skipping.")
                return None
    return None


# ── Batch Scorer ──────────────────────────────────────────────────────────────

def score_clips(candidates: list[dict], episode: dict) -> list[dict]:
    """
    Score each candidate:
      1. Main promo evaluation (hook, cliffhanger, emotion)
      2. Blind standalone test (characters, conflict, what_happens_next, understandability)
    """
    scored = []
    w_hook = _W.get("hook", 0.30)
    w_cliff = _W.get("cliffhanger", 0.30)
    w_stand = _W.get("standalone", 0.25)
    w_emo = _W.get("emotion", 0.15)

    sum_w = w_hook + w_cliff + w_stand + w_emo
    w_hook, w_cliff, w_stand, w_emo = w_hook / sum_w, w_cliff / sum_w, w_stand / sum_w, w_emo / sum_w

    for cand in candidates:
        evaluation = score_single_clip(cand, episode)
        if evaluation is None:
            continue

        # Blind standalone test
        blind_test = run_blind_standalone_test(cand)
        understandability = blind_test["understandability"] if blind_test else 7.0

        scores = evaluation["scores"]
        total = (
            w_hook * scores["hook"]
            + w_cliff * scores["cliffhanger"]
            + w_stand * understandability
            + w_emo * scores["emotion"]
        )

        cand_copy = dict(cand)
        cand_copy.update({
            "hook": scores["hook"],
            "cliffhanger": scores["cliffhanger"],
            "emotion": scores["emotion"],
            "standalone": understandability,
            "understandability": understandability,
            "hook_line": evaluation["hook_line"],
            "hook_type": evaluation["hook_type"],
            "cliffhanger_line": evaluation["cliffhanger_line"],
            "why_it_works": evaluation["why_it_works"],
            "problems": evaluation["problems"],
            "standalone_test": blind_test,
            "reasoning": evaluation["why_it_works"],
            "total_score": round(total, 3),
            "raw_evaluation": {
                **evaluation,
                "standalone_test": blind_test,
            },
        })
        scored.append(cand_copy)

    return scored
