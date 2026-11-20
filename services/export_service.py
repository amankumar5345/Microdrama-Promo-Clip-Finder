"""
services/export_service.py
──────────────────────────
Multi-format export engine: CSV, JSON, Markdown, and full ZIP bundles.
"""

import csv
import io
import json
from typing import Union
import zipfile

from services.ai_caption_service import generate_social_promos


def export_promos_csv(ranked_clips: list[dict]) -> str:
    """Generate CSV string of ranked promo clips."""
    csv_buf = io.StringIO()
    fieldnames = [
        "rank", "episode", "clip_id", "start_time", "end_time", "duration_sec",
        "total_score", "hook_score", "cliffhanger_score", "emotion_score",
        "standalone_score", "hook_line", "hook_type", "cliffhanger_line", "why_it_works"
    ]
    writer = csv.DictWriter(csv_buf, fieldnames=fieldnames)
    writer.writeheader()
    for idx, c in enumerate(ranked_clips, 1):
        writer.writerow({
            "rank": idx,
            "episode": c.get("episode", "Episode 1"),
            "clip_id": c["clip_id"],
            "start_time": c.get("start_fmt", ""),
            "end_time": c.get("end_fmt", ""),
            "duration_sec": round(c.get("duration_sec", 0.0), 2),
            "total_score": round(c.get("total_score", 0.0), 2),
            "hook_score": round(c.get("hook", 0.0), 1),
            "cliffhanger_score": round(c.get("cliffhanger", 0.0), 1),
            "emotion_score": round(c.get("emotion", 0.0), 1),
            "standalone_score": round(c.get("standalone", 0.0), 1),
            "hook_line": c.get("hook_line", ""),
            "hook_type": c.get("hook_type", ""),
            "cliffhanger_line": c.get("cliffhanger_line", ""),
            "why_it_works": c.get("why_it_works", ""),
        })
    return csv_buf.getvalue()


def export_promos_json(ranked_clips: list[dict]) -> str:
    """Generate clean JSON string of ranked promo clips."""
    clean_list = []
    for c in ranked_clips:
        clean_list.append({
            "clip_id": c["clip_id"],
            "episode": c.get("episode", "Episode 1"),
            "duration_sec": round(c.get("duration_sec", 0.0), 2),
            "start_time": c.get("start_fmt", ""),
            "end_time": c.get("end_fmt", ""),
            "start_s": c.get("start_s", c.get("_start_s", 0.0)),
            "end_s": c.get("end_s", c.get("_end_s", 0.0)),
            "total_score": round(c.get("total_score", 0.0), 2),
            "scores": {
                "hook": c.get("hook", 0.0),
                "cliffhanger": c.get("cliffhanger", 0.0),
                "emotion": c.get("emotion", 0.0),
                "standalone": c.get("standalone", 0.0),
            },
            "hook_line": c.get("hook_line", ""),
            "hook_type": c.get("hook_type", ""),
            "cliffhanger_line": c.get("cliffhanger_line", ""),
            "why_it_works": c.get("why_it_works", ""),
            "problems": c.get("problems", []),
            "standalone_test": c.get("standalone_test", {}),
        })
    return json.dumps(clean_list, indent=2, ensure_ascii=False)


def create_zip_bundle(
    ranked_clips: list[dict],
    episode: dict,
    report_md: str,
) -> bytes:
    """
    Create a complete ZIP bundle containing:
      - promos.csv
      - promos.json
      - report.md
      - editor_cut_list.txt
      - captions/<clip_id>_social_captions.txt
    """
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. promos.csv
        zf.writestr("promos.csv", export_promos_csv(ranked_clips))

        # 2. promos.json
        zf.writestr("promos.json", export_promos_json(ranked_clips))

        # 3. report.md
        zf.writestr("report.md", report_md)

        # 4. Quick Cut List for Video Editors
        cut_lines = ["# Video Editor Cut List - Microdrama Promos\n"]
        for idx, c in enumerate(ranked_clips, 1):
            cut_lines.append(
                f"Clip #{idx} ({c['clip_id']}):\n"
                f"  Start:    {c.get('start_fmt')}  ({c.get('start_s', 0.0):.2f}s)\n"
                f"  End:      {c.get('end_fmt')}  ({c.get('end_s', 0.0):.2f}s)\n"
                f"  Duration: {c.get('duration_sec', 0.0):.2f}s\n"
                f"  Hook:     \"{c.get('hook_line', '')}\"\n"
                f"  Outro:    \"{c.get('cliffhanger_line', '')}\"\n"
                f"  Score:    {c.get('total_score', 0.0)}/10\n"
                "-----------------------------------------\n"
            )
        zf.writestr("editor_cut_list.txt", "\n".join(cut_lines))

        # 5. Captions per clip
        ep_title = episode.get("episode_number", "Episode")
        for c in ranked_clips:
            cid = c["clip_id"]
            social = generate_social_promos(c, episode_title=ep_title)
            cap_lines = [
                f"# Social Media Promo Package for {cid} ({ep_title})\n",
                "==================================================",
                "TIKTOK PRESET (9:16 Vertical)",
                "==================================================",
                f"Hook Title: {social['tiktok']['hook_title']}",
                f"First Line: {social['tiktok']['primary_hook']}\n",
                "Caption:",
                social['tiktok']['caption'],
                f"\nHashtags: {' '.join(social['tiktok']['hashtags'])}\n",
                "==================================================",
                "INSTAGRAM REELS PRESET (9:16 Vertical)",
                "==================================================",
                f"Title: {social['reels']['hook_title']}",
                f"Primary Hook: {social['reels']['primary_hook']}\n",
                "Caption:",
                social['reels']['caption'],
                f"\nHashtags: {' '.join(social['reels']['hashtags'])}\n",
                "==================================================",
                "YOUTUBE SHORTS PRESET (9:16 / 16:9)",
                "==================================================",
                f"Title: {social['shorts']['hook_title']}",
                f"Hook: {social['shorts']['primary_hook']}\n",
                "Description:",
                social['shorts']['caption'],
                f"\nTags: {' '.join(social['shorts']['hashtags'])}\n",
            ]
            zf.writestr(f"captions/{cid}_social_package.txt", "\n".join(cap_lines))

    return zip_buffer.getvalue()
