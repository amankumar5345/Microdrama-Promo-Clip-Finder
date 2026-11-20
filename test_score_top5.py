"""
test_score_top5.py
──────────────────
Run scoring and the blind standalone test on Episode 1's top 5 candidate clips,
validate each clip using validate.py, and print the raw JSON.
"""

import json
from pathlib import Path

from src.parse import parse_screenplay
from src.candidates import build_candidates
from src.prefilter import prefilter
from src.score import score_clips
from src.validate import validate_and_filter

EP1_PATH = (
    Path("I Married a Broken Soldier. He was a Duke-scripts (2) (1)")
    / "I Married a Broken Soldier. He was a Duke"
    / "episode-001-Episode 1671703.txt"
)


def main():
    print(f"Loading and parsing: {EP1_PATH.name}...")
    episode = parse_screenplay(EP1_PATH)

    print("Generating candidate windows (dialogue-to-dialogue, 20-60s)...")
    candidates = build_candidates(episode)
    print(f"Total candidate windows: {len(candidates)}")

    print("Prefiltering to top 5 candidates...")
    top5 = prefilter(candidates, top_k=5)
    print(f"Top 5 candidate IDs: {[c['clip_id'] for c in top5]}")

    print("\nScoring top 5 clips with LLM (Temperature 0, JSON only, Blind Standalone Test)...")
    scored = score_clips(top5, episode)

    print("\n" + "=" * 80)
    print("RUNNING VALIDATE.PY CHECKS")
    print("=" * 80)
    valid_clips, stats = validate_and_filter(scored)

    print("\n" + "=" * 80)
    print("RAW JSON EVALUATIONS (TOP 5 CLIPS)")
    print("=" * 80)
    raw_evaluations = [c.get("raw_evaluation") for c in scored if "raw_evaluation" in c]
    print(json.dumps(raw_evaluations, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
