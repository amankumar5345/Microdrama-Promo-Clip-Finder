"""
app.py
──────
Enterprise Microdrama Promo Clip Finder Studio.
Supports both:
  1. Interactive Streamlit Web Application:
       streamlit run app.py
  2. Headless Command-Line Interface (CLI):
       python app.py "path/to/episode.txt"
       python app.py "path/to/episode.txt" --stage score
       python app.py "path/to/episode.txt" --fallback
"""

import argparse
import io
import json
import logging
import os
from pathlib import Path
import sys
import tempfile

import yaml
from dotenv import load_dotenv
import streamlit as st

# Core pipeline modules (preserved 100%)
from src.parse import parse_screenplay
from src.candidates import build_candidates
from src.prefilter import prefilter
from src.score import score_clips
from src.rank import rank_and_select, rank_prefiltered
from src.report import write_report
from src.validate import validate_episode, validate_candidates, validate_and_filter
from src.llm import has_api_key

# Database, Services, and UI modules
from db.database import get_db
from services.pipeline_service import run_pipeline_for_script
from services.export_service import export_promos_csv, export_promos_json, create_zip_bundle
from ui.styles import inject_custom_styles
from ui.components import (
    render_hero_header,
    render_metric_cards,
    render_clip_card,
    render_empty_state,
)
from ui.charts import render_drama_timeline, render_score_radar, render_score_distribution
from ui.editor import render_clip_editor, render_clip_comparison
from ui.history_sidebar import render_history_sidebar
from ui.chat import render_script_chat

load_dotenv()
logger = logging.getLogger(__name__)

STAGES = ["parse", "candidates", "prefilter", "score", "rank", "report", "all"]


def _CFG() -> dict:
    cfg_path = Path(__file__).parent / "config.yaml"
    if cfg_path.exists():
        return yaml.safe_load(cfg_path.read_text())
    return {
        "window": {"min_seconds": 20, "max_seconds": 60, "hook_window_seconds": 3},
        "top_n": 5,
        "max_per_episode": 2,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI Runner (Preserved for full backward compatibility)
# ─────────────────────────────────────────────────────────────────────────────

def _print_ranked(ranked: list[dict]):
    for i, r in enumerate(ranked, 1):
        print(f"\n  #{i}  {r['clip_id']}  ({r['duration_sec']:.1f}s)  [{r['start_fmt']} → {r['end_fmt']}]  Total: {r['total_score']:.2f}")
        print(f"       Hook: {r['hook']} | Cliffhanger: {r['cliffhanger']} | Standalone: {r.get('standalone', 0)} | Emotion: {r['emotion']}")
        print(f"       Reasoning: {r.get('why_it_works', r.get('reasoning', ''))}")


def run_cli(episode_path: str, stage: str = "all", fallback: bool = False):
    """Headless CLI execution of the promo discovery pipeline."""
    path = Path(episode_path)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    cfg = _CFG()
    stop_after = stage

    print(f"\n[1/6] Parsing: {path.name} …")
    episode = parse_screenplay(path)
    validate_episode(episode)
    print(f"      Episode: {episode['episode_number']} | Events: {len(episode['events'])}")
    if stop_after == "parse":
        return

    print(f"\n[2/6] Building candidates [{cfg['window']['min_seconds']}s – {cfg['window']['max_seconds']}s] …")
    candidates = build_candidates(episode)
    validate_candidates(candidates)
    print(f"      Found {len(candidates)} candidate windows.")
    if stop_after == "candidates":
        return

    print(f"\n[3/6] Prefiltering (scoring tones, '?'/'...', shock words, pace; keeping top 12) …")
    good = prefilter(candidates, top_k=12)
    print(f"      Kept top {len(good)} windows from {len(candidates)} candidates.")
    if stop_after == "prefilter":
        return

    is_fallback = fallback or not has_api_key()
    if is_fallback:
        print(f"\n[Mode: Fallback] (No API key set or --fallback specified)")
        ranked = rank_prefiltered(good, episode=episode, max_per_episode=cfg.get("max_per_episode", 2))
        print(f"      Top {len(ranked)} clips selected via fallback ranking.")
        if stop_after in ("score", "rank"):
            _print_ranked(ranked)
            return

        print(f"\n[6/6] Writing report …")
        write_report(episode, ranked, path)
        print("\n── Final Top Clips ──────────────────────────────────────────")
        _print_ranked(ranked)
        return

    print(f"\n[4/6] Scoring {len(good)} clips with LLM …")
    scored = score_clips(good, episode)
    ep_num = episode.get("episode_number", "Episode 1")
    for c in scored:
        c.setdefault("episode", ep_num)
    valid_scored, v_stats = validate_and_filter(scored)
    print(f"      {len(valid_scored)} clips scored and validated ({v_stats['rejection_rate_pct']}% rejected)")
    if stop_after == "score":
        return

    print(f"\n[5/6] Ranking …")
    ranked = rank_and_select(valid_scored)
    print(f"      Top {len(ranked)} clips selected")
    if stop_after == "rank":
        _print_ranked(ranked)
        return

    print(f"\n[6/6] Writing report …")
    write_report(episode, ranked, path)
    print("\n── Final Top Clips ──────────────────────────────────────────")
    _print_ranked(ranked)


# ─────────────────────────────────────────────────────────────────────────────
# Streamlit Web Application Interface
# ─────────────────────────────────────────────────────────────────────────────

def run_streamlit_app():
    """Interactive Streamlit Web Dashboard."""
    st.set_page_config(
        page_title="Microdrama Promo Clip Studio",
        page_icon="🎬",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Injected modern CSS
    inject_custom_styles()

    cfg = _CFG()
    db = get_db()

    # ── Initialize Session State ──────────────────────────────────────────────
    if "current_session_id" not in st.session_state:
        st.session_state["current_session_id"] = None
    if "ranked_results" not in st.session_state:
        st.session_state["ranked_results"] = None
    if "current_episode" not in st.session_state:
        st.session_state["current_episode"] = None
    if "reports_md" not in st.session_state:
        st.session_state["reports_md"] = ""
    if "mode_used" not in st.session_state:
        st.session_state["mode_used"] = "Ready"

    # ── Sidebar Controls ─────────────────────────────────────────────────────
    st.sidebar.header("⚙️ Studio Settings")

    api_key_available = has_api_key()
    if api_key_available:
        st.sidebar.success("✅ LLM API Key Active")
    else:
        st.sidebar.warning("⚠️ No API Key (Fallback Active)")

    custom_key = st.sidebar.text_input(
        "API Key (Optional Override):",
        type="password",
        help="Optional: enter an OpenRouter, NVIDIA, or Gemini API key here.",
    )
    if custom_key:
        if custom_key.startswith("nvapi-"):
            os.environ["NVIDIA_API_KEY"] = custom_key
        elif custom_key.startswith("sk-or-"):
            os.environ["OPENROUTER_API_KEY"] = custom_key
        else:
            os.environ["OPENROUTER_API_KEY"] = custom_key
            os.environ["NVIDIA_API_KEY"] = custom_key
            os.environ["OPENAI_API_KEY"] = custom_key
        api_key_available = True
        st.sidebar.info("🔑 Custom API Key Active")

    st.sidebar.markdown("---")
    st.sidebar.subheader("🎯 Pipeline Mode")
    mode_options = [
        "Automatic (LLM with Fallback)",
        "Fallback Mode Only (Heuristic Pre-filter - Fast & Free)",
    ]
    default_idx = 0 if api_key_available else 1
    selected_mode = st.sidebar.radio("Execution Mode:", mode_options, index=default_idx)

    st.sidebar.markdown("---")
    st.sidebar.subheader("📐 Clip Constraints")
    min_dur = st.sidebar.slider("Min Duration (s):", 15, 30, 20)
    max_dur = st.sidebar.slider("Max Duration (s):", 35, 90, 60)
    max_promos = st.sidebar.slider("Max Promos per Episode:", 1, 5, 2)

    st.sidebar.markdown("---")
    st.sidebar.subheader("📱 Aspect Ratio Preset")
    aspect_ratio = st.sidebar.selectbox(
        "Social Video Preset:",
        ["9:16 (Vertical - TikTok / Reels / Shorts)", "1:1 (Square - Feed)", "16:9 (Landscape - YouTube / Web)"],
        index=0,
    )

    # Sample script button
    sample_file = Path("I Married a Broken Soldier. He was a Duke-scripts (2) (1)/I Married a Broken Soldier. He was a Duke/episode-001-Episode 1671703.txt")
    load_sample = False
    if sample_file.exists():
        st.sidebar.markdown("---")
        st.sidebar.subheader("🧪 Quick Test")
        if st.sidebar.button("📂 Load Sample Episode 1", use_container_width=True):
            load_sample = True

    # History Drawer in Sidebar
    switched_sid = render_history_sidebar()
    if switched_sid and switched_sid != st.session_state["current_session_id"]:
        session_data = db.get_session(switched_sid)
        if session_data:
            st.session_state["current_session_id"] = switched_sid
            st.session_state["ranked_results"] = db.get_clips(switched_sid)
            st.session_state["reports_md"] = session_data.get("report_md", "")
            st.session_state["mode_used"] = session_data.get("mode", "Loaded")
            st.rerun()

    # ── Main Content Area ────────────────────────────────────────────────────
    render_hero_header(mode_label=st.session_state.get("mode_used", "Ready"))

    # File Uploader
    uploaded_files = st.file_uploader(
        "Upload Screenplay Scripts (`.txt`):",
        type=["txt"],
        accept_multiple_files=True,
        help="Upload one or multiple microdrama screenplay files formatted with scene headers and [mm:ss.s] timestamps.",
    )

    scripts_to_process = []
    if load_sample and sample_file.exists():
        scripts_to_process.append((sample_file.name, sample_file.read_text(encoding="utf-8")))
        st.info(f"Loaded sample file: **{sample_file.name}**")

    if uploaded_files:
        for uf in uploaded_files:
            text = uf.getvalue().decode("utf-8", errors="replace")
            scripts_to_process.append((uf.name, text))

    run_btn = st.button("🚀 Run Promo Finder", type="primary", use_container_width=True)

    # ── Execute Pipeline ─────────────────────────────────────────────────────
    if run_btn:
        if not scripts_to_process:
            st.error("Please upload at least one `.txt` screenplay file (or click 'Load Sample Episode 1').")
            return

        effective_fallback = (selected_mode == mode_options[1]) or (not api_key_available)
        all_ranked_clips = []
        all_reports_md = []
        last_sid = None
        last_episode = None

        total_files = len(scripts_to_process)
        for idx, (filename, text) in enumerate(scripts_to_process, 1):
            st.markdown(f"### Processing: `{filename}` ({idx}/{total_files})")
            if effective_fallback:
                st.caption("⚡ **Fallback Engine:** Heuristic scoring (tones, '?'/'...', shock words, pace) + sentence-transformers. Zero token cost.")
            else:
                st.caption("🤖 **LLM Engine:** Multi-attribute evaluation & Blind Standalone comprehension testing.")

            prog_bar = st.progress(0)
            status_box = st.empty()

            def _update_progress(pct: int, msg: str):
                prog_bar.progress(pct)
                status_box.text(msg)

            try:
                ep_dict, ranked, report_md, sid = run_pipeline_for_script(
                    script_text=text,
                    filename=filename,
                    use_fallback=effective_fallback,
                    max_per_episode=max_promos,
                    min_seconds=min_dur,
                    max_seconds=max_dur,
                    progress_callback=_update_progress,
                    save_to_db=True,
                )
                all_ranked_clips.extend(ranked)
                all_reports_md.append(report_md)
                last_sid = sid
                last_episode = ep_dict
            except Exception as ex:
                st.error(f"Error processing {filename}: {ex}")
                logger.exception(ex)

        if all_ranked_clips:
            st.session_state["current_session_id"] = last_sid
            st.session_state["ranked_results"] = all_ranked_clips
            st.session_state["current_episode"] = last_episode
            st.session_state["reports_md"] = "\n\n---\n\n".join(all_reports_md)
            st.session_state["mode_used"] = "Fallback" if effective_fallback else "LLM"
            st.toast(f"Extracted {len(all_ranked_clips)} winning promos!", icon="🎉")
            st.rerun()

    # ── Results Presentation ─────────────────────────────────────────────────
    ranked_clips = st.session_state.get("ranked_results")
    if ranked_clips:
        render_metric_cards(ranked_clips, st.session_state.get("mode_used", "Standard"))

        st.markdown("---")

        # Top Filter & Search Bar
        f_col1, f_col2, f_col3 = st.columns([1.5, 1.2, 1.3])
        with f_col1:
            search_query = st.text_input("🔍 Search within dialogue/quotes:", placeholder="e.g. altar, marry, gown...").lower()
        with f_col2:
            min_score_filter = st.slider("Filter by Min Total Score:", 0.0, 10.0, 7.0, step=0.1)
        with f_col3:
            sort_by = st.selectbox("Sort Results By:", ["Total Score (High → Low)", "Duration (Short → Long)", "Start Time (Earliest First)"])

        # Apply filtering & sorting
        filtered_clips = list(ranked_clips)
        if search_query:
            filtered_clips = [
                c for c in filtered_clips
                if search_query in c.get("hook_line", "").lower()
                or search_query in c.get("cliffhanger_line", "").lower()
                or search_query in c.get("why_it_works", "").lower()
            ]

        filtered_clips = [c for c in filtered_clips if c.get("total_score", 0.0) >= min_score_filter]

        if sort_by == "Total Score (High → Low)":
            filtered_clips.sort(key=lambda x: x.get("total_score", 0), reverse=True)
        elif sort_by == "Duration (Short → Long)":
            filtered_clips.sort(key=lambda x: x.get("duration_sec", 0))
        elif sort_by == "Start Time (Earliest First)":
            filtered_clips.sort(key=lambda x: x.get("start_s", x.get("_start_s", 0)))

        # Multi-Tab Studio Interface
        tab_cards, tab_charts, tab_editor, tab_chat, tab_data = st.tabs([
            "🏆 Promo Clip Cards",
            "📊 Visual Analytics",
            "🎛️ Clip Trimmer & Compare",
            "💬 AI Screenplay Assistant",
            "📋 Raw Data & Exports",
        ])

        # ── Tab 1: Clip Cards ────────────────────────────────────────────────
        with tab_cards:
            if not filtered_clips:
                st.info("No clips match your current search/score filters.")
            else:
                for idx, clip in enumerate(filtered_clips, 1):
                    render_clip_card(
                        clip=clip,
                        rank_idx=idx,
                        session_id=st.session_state.get("current_session_id", "temp"),
                        aspect_ratio=aspect_ratio,
                    )

        # ── Tab 2: Visual Charts ─────────────────────────────────────────────
        with tab_charts:
            episode_obj = st.session_state.get("current_episode") or {}
            render_drama_timeline(episode=episode_obj, ranked_clips=filtered_clips)
            c_c1, c_c2 = st.columns(2)
            with c_c1:
                render_score_radar(ranked_clips=filtered_clips)
            with c_c2:
                render_score_distribution(ranked_clips=filtered_clips)

        # ── Tab 3: Trimmer & Compare ─────────────────────────────────────────
        with tab_editor:
            sid = st.session_state.get("current_session_id", "temp")
            render_clip_editor(ranked_clips=filtered_clips, session_id=sid)
            st.markdown("---")
            render_clip_comparison(ranked_clips=filtered_clips)

        # ── Tab 4: Screenplay Q&A Assistant ──────────────────────────────────
        with tab_chat:
            sid = st.session_state.get("current_session_id")
            if sid:
                render_script_chat(
                    session_id=sid,
                    episode_dict=st.session_state.get("current_episode"),
                    ranked_clips=filtered_clips,
                )
            else:
                st.info("Run a screenplay analysis or load a previous session to chat with the AI assistant.")

        # ── Tab 5: Raw Data & Download Bundle ────────────────────────────────
        with tab_data:
            st.markdown("### 📥 Export Promo Assets")
            d1, d2, d3, d4 = st.columns(4)

            # 1. Full ZIP Bundle
            zip_bytes = create_zip_bundle(
                ranked_clips=filtered_clips,
                episode=st.session_state.get("current_episode") or {},
                report_md=st.session_state.get("reports_md", ""),
            )
            d1.download_button(
                label="📦 Download Full ZIP Bundle",
                data=zip_bytes,
                file_name="promo_studio_package.zip",
                mime="application/zip",
                use_container_width=True,
            )

            # 2. CSV
            csv_str = export_promos_csv(filtered_clips)
            d2.download_button(
                label="📄 Download Promos CSV",
                data=csv_str,
                file_name="promos.csv",
                mime="text/csv",
                use_container_width=True,
            )

            # 3. JSON
            json_str = export_promos_json(filtered_clips)
            d3.download_button(
                label="📦 Download Promos JSON",
                data=json_str,
                file_name="promos.json",
                mime="application/json",
                use_container_width=True,
            )

            # 4. Markdown Report
            md_text = st.session_state.get("reports_md", "")
            d4.download_button(
                label="📝 Download Report (MD)",
                data=md_text,
                file_name="report.md",
                mime="text/markdown",
                use_container_width=True,
            )

            st.markdown("---")
            st.markdown("#### Structured Data Table")
            table_data = []
            for i, c in enumerate(filtered_clips, 1):
                table_data.append({
                    "Rank": i,
                    "Clip ID": c["clip_id"],
                    "Time Window": f"{c.get('start_fmt')} → {c.get('end_fmt')}",
                    "Duration": f"{c.get('duration_sec', 0):.1f}s",
                    "Total Score": c.get("total_score", 0.0),
                    "Hook": c.get("hook", 0.0),
                    "Cliffhanger": c.get("cliffhanger", 0.0),
                    "Emotion": c.get("emotion", 0.0),
                    "Standalone": c.get("standalone", 0.0),
                    "Hook Line": c.get("hook_line", "")[:40] + "…",
                    "Cliffhanger Line": c.get("cliffhanger_line", "")[:40] + "…",
                })
            st.dataframe(
                table_data,
                use_container_width=True,
                column_config={
                    "Total Score": st.column_config.ProgressColumn(min_value=0, max_value=10, format="%.2f"),
                },
            )
    else:
        render_empty_state()


# ─────────────────────────────────────────────────────────────────────────────
# Dual-Mode Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """Main application entry point."""
    if st.runtime.exists():
        run_streamlit_app()
        return

    # CLI Parser
    parser = argparse.ArgumentParser(description="Microdrama Promo Clip Finder Studio")
    parser.add_argument("episode", nargs="?", help="Path to screenplay .txt file")
    parser.add_argument("--stage", default="all", choices=STAGES, help="Stop after this stage")
    parser.add_argument("--fallback", action="store_true", help="Force fallback mode using prefilter only")
    args = parser.parse_args()

    if not args.episode:
        print("\n" + "=" * 65)
        print("🎬 Microdrama Promo Clip Studio")
        print("=" * 65)
        print("To launch the interactive Web Studio:")
        print("    streamlit run app.py\n")
        print("To run from the command line:")
        print("    python app.py \"path/to/episode.txt\"")
        print("    python app.py \"path/to/episode.txt\" --fallback")
        print("=" * 65 + "\n")
        return

    run_cli(args.episode, args.stage, fallback=args.fallback)


if __name__ == "__main__":
    main()
