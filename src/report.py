"""
src/report.py
─────────────
Generate final promo outputs:
  1. outputs/promos.json   – Structured JSON of winning promo clips
  2. outputs/promos.csv    – Tabular CSV representation
  3. outputs/report.md     – Human-readable markdown report (rank, episode,
                             start/end, hook, cliffhanger, why it works, scores)
  4. outputs/raw/*.json    – All raw LLM responses saved unedited
"""

import csv
import json
from pathlib import Path
from typing import Union

_OUT = Path(__file__).parent.parent / "outputs"
_RAW_DIR = _OUT / "raw"


def save_raw_llm_responses(scored_clips: list[dict]):
    """Save all raw LLM responses unedited in outputs/raw/."""
    _RAW_DIR.mkdir(parents=True, exist_ok=True)
    for c in scored_clips:
        clip_id = c.get("clip_id", "clip_unknown")
        raw_eval = c.get("raw_evaluation") or {}
        raw_path = _RAW_DIR / f"{clip_id}.json"
        raw_path.write_text(
            json.dumps(raw_eval, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )


def write_promos_json(ranked_clips: list[dict], out_path: Path):
    """Write outputs/promos.json."""
    clean_promos = []
    for c in ranked_clips:
        item = {
            "clip_id": c["clip_id"],
            "episode": c.get("episode", "Episode 1"),
            "duration_sec": c["duration_sec"],
            "start_time": c["start_fmt"],
            "end_time": c["end_fmt"],
            "start_s": c["start_s"],
            "end_s": c["end_s"],
            "total_score": c["total_score"],
            "scores": {
                "hook": c["hook"],
                "cliffhanger": c["cliffhanger"],
                "emotion": c["emotion"],
                "standalone": c.get("standalone", c.get("understandability", 0.0)),
            },
            "hook_line": c.get("hook_line", ""),
            "hook_type": c.get("hook_type", ""),
            "cliffhanger_line": c.get("cliffhanger_line", ""),
            "why_it_works": c.get("why_it_works", ""),
            "problems": c.get("problems", []),
            "standalone_test": c.get("standalone_test", {}),
        }
        clean_promos.append(item)

    out_path.write_text(
        json.dumps(clean_promos, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def write_promos_csv(ranked_clips: list[dict], out_path: Path):
    """Write outputs/promos.csv."""
    fieldnames = [
        "rank",
        "episode",
        "clip_id",
        "start_time",
        "end_time",
        "duration_sec",
        "total_score",
        "hook_score",
        "cliffhanger_score",
        "emotion_score",
        "standalone_score",
        "hook_line",
        "hook_type",
        "cliffhanger_line",
        "why_it_works",
    ]

    with open(out_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for idx, c in enumerate(ranked_clips, 1):
            writer.writerow({
                "rank": idx,
                "episode": c.get("episode", "Episode 1"),
                "clip_id": c["clip_id"],
                "start_time": c["start_fmt"],
                "end_time": c["end_fmt"],
                "duration_sec": c["duration_sec"],
                "total_score": c["total_score"],
                "hook_score": c["hook"],
                "cliffhanger_score": c["cliffhanger"],
                "emotion_score": c["emotion"],
                "standalone_score": c.get("standalone", c.get("understandability", 0.0)),
                "hook_line": c.get("hook_line", ""),
                "hook_type": c.get("hook_type", ""),
                "cliffhanger_line": c.get("cliffhanger_line", ""),
                "why_it_works": c.get("why_it_works", ""),
            })


def write_report_md(episode: dict, ranked_clips: list[dict], out_path: Path):
    """Write outputs/report.md."""
    ep_num = episode.get("episode_number", "Episode 1")
    logline = episode.get("logline", "")

    lines = [
        f"# Microdrama Promo Selection Report — {ep_num}",
        f"\n**Logline:** {logline}\n",
        "## Selected Winning Promos (Max 2 per episode)\n",
    ]

    for idx, c in enumerate(ranked_clips, 1):
        lines.extend([
            f"### #{idx}. `{c['clip_id']}` — {c['start_fmt']} → {c['end_fmt']} ({c['duration_sec']}s)",
            f"- **Episode:** {c.get('episode', ep_num)}",
            f"- **Segment Time Range:** `{c['start_fmt']}` to `{c['end_fmt']}` ({c['duration_sec']:.2f} seconds)",
            f"- **Total Weighted Score:** **{c['total_score']:.2f} / 10**",
            f"- **Sub-Scores:** Hook: `{c['hook']}/10` | Cliffhanger: `{c['cliffhanger']}/10` | Emotion: `{c['emotion']}/10` | Standalone Understandability: `{c.get('standalone', c.get('understandability', 0.0))}/10`",
            f"- **Hook ({c.get('hook_type', 'line')}):** > *\"{c.get('hook_line', '')}\"*",
            f"- **Cliffhanger:** > *\"{c.get('cliffhanger_line', '')}\"*",
            f"- **Why It Works:** {c.get('why_it_works', '')}",
        ])

        if c.get("problems"):
            lines.append(f"- **Identified Problems / Risks:** {'; '.join(c['problems'])}")

        st = c.get("standalone_test")
        if st:
            chars = ", ".join(st.get("characters", []))
            lines.extend([
                f"- **Blind Standalone Test Analysis:**",
                f"  - **Detected Characters:** {chars}",
                f"  - **Core Conflict:** {st.get('conflict', '')}",
                f"  - **Audience Anticipation:** {st.get('what_happens_next', '')}",
            ])
        lines.append("\n---\n")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def write_report(episode: dict, ranked: list[dict], episode_path: Union[str, Path]):
    """
    Main export entry point:
      - outputs/promos.json
      - outputs/promos.csv
      - outputs/report.md
      - outputs/raw/*.json
    """
    _OUT.mkdir(parents=True, exist_ok=True)
    json_path = _OUT / "promos.json"
    csv_path = _OUT / "promos.csv"
    md_path = _OUT / "report.md"

    # 1. Save unedited raw LLM responses
    save_raw_llm_responses(ranked)

    # 2. promos.json
    write_promos_json(ranked, json_path)

    # 3. promos.csv
    write_promos_csv(ranked, csv_path)

    # 4. report.md
    write_report_md(episode, ranked, md_path)

    print(f"  → {json_path}")
    print(f"  → {csv_path}")
    print(f"  → {md_path}")
    print(f"  → {_RAW_DIR}/ (all raw LLM responses unedited)")
    return json_path, csv_path, md_path
