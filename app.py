"""
app.py
──────
Dual-mode application for the Microdrama Promo Clip Finder:
  1. Streamlit Web UI:
       streamlit run app.py
  2. Command-Line Interface (CLI):
       python app.py "path/to/episode.txt"
       python app.py "path/to/episode.txt" --stage score
       python app.py "path/to/episode.txt" --fallback
"""

import argparse
import csv
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

from src.parse import parse_screenplay
from src.candidates import build_candidates
from src.prefilter import prefilter
from src.score import score_clips
from src.rank import rank_and_select, rank_prefiltered
from src.report import write_report, write_promos_json, write_promos_csv, write_report_md, save_raw_llm_responses
from src.validate import validate_episode, validate_candidates, validate_and_filter
from src.llm import has_api_key

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
# CLI Helper Functions & Stages
# ─────────────────────────────────────────────────────────────────────────────

def _print_clips(clips: list[dict]):
    print(f"\n{'CLIP_ID':<12} {'DUR':<8} {'START':<8} {'END':<8} {'EVENTS':<8} {'STATUS'}")
    print("─" * 60)
    for c in clips[:15]:
        s = c.get('_start_s', 0)
        e = c.get('_end_s', 0)
        m_s, sec_s = int(s) // 60, s % 60
        m_e, sec_e = int(e) // 60, e % 60
        st_fmt = f"{m_s:02d}:{sec_s:05.2f}"
        et_fmt = f"{m_e:02d}:{sec_e:05.2f}"
        rej = c.get('prefilter_reject', 'PASS')
        print(f"{c['clip_id']:<12} {c['duration_sec']:<8.2f} {st_fmt:<8} {et_fmt:<8} {c.get('event_count', len(c.get('_events', []))):<8} {rej}")
    if len(clips) > 15:
        print(f"… and {len(clips) - 15} more candidates")


def _print_prefiltered(clips: list[dict]):
    print(f"\n{'RANK':<5} {'CLIP_ID':<12} {'START':<9} {'END':<9} {'DUR':<7} {'SCORE':<7} REASON")
    print("─" * 105)
    for i, c in enumerate(clips, 1):
        s = c["_start_s"]
        e = c["_end_s"]
        m_s, sec_s = int(s) // 60, s % 60
        m_e, sec_e = int(e) // 60, e % 60
        st_fmt = f"{m_s:02d}:{sec_s:05.2f}"
        et_fmt = f"{m_e:02d}:{sec_e:05.2f}"
        score = c.get("prefilter_score", 0.0)
        reason = c.get("prefilter_reason", "")
        print(f"#{i:<4} {c['clip_id']:<12} {st_fmt:<9} {et_fmt:<9} {c['duration_sec']:<7.2f} {score:<7.2f} {reason}")


def _print_scored(scored: list[dict]):
    print(f"\n{'CLIP_ID':<12} {'DUR':<8} {'HOOK':<6} {'CLIFF':<7} {'STAND':<7} {'EMO':<6} {'TOTAL':<7} REASONING")
    print("─" * 90)
    preview = sorted(scored, key=lambda x: x.get('total_score', 0), reverse=True)
    for c in preview[:15]:
        reason = c.get('why_it_works', c.get('reasoning', ''))
        reason = reason[:55] + ("…" if len(reason) > 55 else "")
        stand = c.get('standalone', c.get('understandability', 0.0))
        total = c.get('total_score', 0.0)
        print(f"{c['clip_id']:<12} {c['duration_sec']:<8.2f} {c['hook']:<6.1f} {c['cliffhanger']:<7.1f} {stand:<7.1f} {c['emotion']:<6.1f} {total:<7.2f} {reason}")
    if len(preview) > 15:
        print(f"… and {len(preview) - 15} more scored clips")


def _print_ranked(ranked: list[dict]):
    for i, r in enumerate(ranked, 1):
        print(f"\n  #{i}  {r['clip_id']}  ({r['duration_sec']:.1f}s)  [{r['start_fmt']} → {r['end_fmt']}]  Total: {r['total_score']:.2f}")
        print(f"       Hook: {r['hook']} | Cliffhanger: {r['cliffhanger']} | Standalone: {r.get('standalone', 0)} | Emotion: {r['emotion']}")
        print(f"       Reasoning: {r.get('why_it_works', r.get('reasoning', ''))}")


def run_cli(episode_path: str, stage: str = "all", fallback: bool = False):
    path = Path(episode_path)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    cfg = _CFG()
    stop_after = stage

    # ── Stage 1: Parse ────────────────────────────────────────────────────
    print(f"\n[1/6] Parsing: {path.name} …")
    episode = parse_screenplay(path)
    validate_episode(episode)
    print(f"      Episode: {episode['episode_number']} | Events: {len(episode['events'])}")
    if stop_after == "parse":
        return

    # ── Stage 2: Candidates ───────────────────────────────────────────────
    print(f"\n[2/6] Building candidates [{cfg['window']['min_seconds']}s – {cfg['window']['max_seconds']}s] …")
    candidates = build_candidates(episode)
    validate_candidates(candidates)
    print(f"      Found {len(candidates)} candidate windows.")
    if stop_after == "candidates":
        _print_clips(candidates)
        return

    # ── Stage 3: Prefilter ────────────────────────────────────────────────
    print(f"\n[3/6] Prefiltering (scoring tones, '?'/'...', shock words, pace; keeping top 12) …")
    good = prefilter(candidates, top_k=12)
    print(f"      Kept top {len(good)} windows from {len(candidates)} candidates.")
    if stop_after == "prefilter":
        _print_prefiltered(good)
        return

    # ── Check Fallback Mode ───────────────────────────────────────────────
    is_fallback = fallback or not has_api_key()

    if is_fallback:
        print(f"\n[Mode: Fallback] (No API key set or --fallback specified)")
        print(f"      Ranking {len(good)} candidates using prefilter metrics + sentence-transformers deduplication …")
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

    # ── Stage 4: LLM Score ────────────────────────────────────────────────
    print(f"\n[4/6] Scoring {len(good)} clips with LLM …")
    scored = score_clips(good, episode)
    ep_num = episode.get("episode_number", "Episode 1")
    for c in scored:
        c.setdefault("episode", ep_num)
    valid_scored, v_stats = validate_and_filter(scored)
    print(f"      {len(valid_scored)} clips scored and validated ({v_stats['rejection_rate_pct']}% rejected)")
    if stop_after == "score":
        _print_scored(valid_scored)
        return

    # ── Stage 5: Rank ─────────────────────────────────────────────────────
    print(f"\n[5/6] Ranking …")
    ranked = rank_and_select(valid_scored)
    print(f"      Top {len(ranked)} clips selected")
    if stop_after == "rank":
        _print_ranked(ranked)
        return

    # ── Stage 6: Report ───────────────────────────────────────────────────
    print(f"\n[6/6] Writing report …")
    write_report(episode, ranked, path)
    print("\n── Final Top Clips ──────────────────────────────────────────")
    _print_ranked(ranked)


# ─────────────────────────────────────────────────────────────────────────────
# Streamlit Web App Interface
# ─────────────────────────────────────────────────────────────────────────────

def process_single_script(
    script_text: str,
    filename: str,
    use_fallback: bool,
    max_per_episode: int = 2,
    progress_bar=None,
    status_text=None,
) -> tuple[dict, list[dict], str]:
    """Process a single uploaded screenplay script."""
    cfg = _CFG()

    # Save to temporary file for parser
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
        tmp.write(script_text)
        tmp_path = Path(tmp.name)

    try:
        # Stage 1: Parse
        if status_text:
            status_text.text(f"[{filename}] Step 1/5: Parsing screenplay...")
        if progress_bar:
            progress_bar.progress(15)
        episode = parse_screenplay(tmp_path)
        validate_episode(episode)

        # Stage 2: Candidates
        if status_text:
            status_text.text(f"[{filename}] Step 2/5: Enumerating dialogue-to-dialogue windows (20–60s)...")
        if progress_bar:
            progress_bar.progress(35)
        candidates = build_candidates(episode)
        validate_candidates(candidates)

        # Stage 3: Prefilter
        if status_text:
            status_text.text(f"[{filename}] Step 3/5: Prefiltering top 12 windows (tones, punctuation, shock words, pace)...")
        if progress_bar:
            progress_bar.progress(55)
        good = prefilter(candidates, top_k=12)

        # Stage 4 & 5: Score & Rank
        if use_fallback:
            if status_text:
                status_text.text(f"[{filename}] Step 4/5: Running Fallback Ranker (prefilter scores + all-MiniLM-L6-v2 deduplication)...")
            if progress_bar:
                progress_bar.progress(80)
            ranked = rank_prefiltered(good, episode=episode, max_per_episode=max_per_episode)
        else:
            if status_text:
                status_text.text(f"[{filename}] Step 4/5: LLM multi-attribute scoring & blind standalone evaluation...")
            if progress_bar:
                progress_bar.progress(75)
            scored = score_clips(good, episode)
            ep_num = episode.get("episode_number", "Episode 1")
            for c in scored:
                c.setdefault("episode", ep_num)
            valid_scored, _ = validate_and_filter(scored)

            if status_text:
                status_text.text(f"[{filename}] Step 5/5: Ranking with config weights & all-MiniLM-L6-v2 deduplication...")
            if progress_bar:
                progress_bar.progress(90)
            ranked = rank_and_select(valid_scored, max_per_episode=max_per_episode)

        # Generate markdown report
        md_buf = io.StringIO()
        out_tmp_md = Path(tempfile.gettempdir()) / f"{Path(filename).stem}_report.md"
        write_report_md(episode, ranked, out_tmp_md)
        md_content = out_tmp_md.read_text(encoding="utf-8") if out_tmp_md.exists() else ""

        if progress_bar:
            progress_bar.progress(100)
        if status_text:
            status_text.text(f"[{filename}] Completed! Selected {len(ranked)} winning promos.")

        return episode, ranked, md_content

    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass


def run_streamlit_app():
    st.set_page_config(
        page_title="Microdrama Promo Clip Finder",
        page_icon="🎬",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    st.markdown("""
        <style>
        .main-header {
            font-size: 2.2rem;
            font-weight: 700;
            color: #1E3A8A;
            margin-bottom: 0.2rem;
        }
        .sub-header {
            font-size: 1.05rem;
            color: #4B5563;
            margin-bottom: 1.5rem;
        }
        .metric-card {
            background: #F3F4F6;
            padding: 1rem;
            border-radius: 8px;
            border-left: 4px solid #2563EB;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="main-header">🎬 Microdrama Promo Clip Finder</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Find the best 20–60s promo clips with high hooks, emotional cliffhangers, and semantic deduplication.</div>',
        unsafe_allow_html=True
    )

    # ── Sidebar Configuration ────────────────────────────────────────────────
    st.sidebar.header("⚙️ Configuration")

    cfg = _CFG()
    api_key_available = has_api_key()

    if api_key_available:
        st.sidebar.success("✅ LLM API Key Detected (.env)")
    else:
        st.sidebar.warning("⚠️ No API Key Detected (Fallback Mode active)")

    custom_key = st.sidebar.text_input(
        "Override / Enter API Key (optional):",
        type="password",
        help="Optional: enter an OpenRouter or Gemini API key here if not configured in .env"
    )
    if custom_key:
        os.environ["OPENROUTER_API_KEY"] = custom_key
        os.environ["OPENAI_API_KEY"] = custom_key
        api_key_available = True
        st.sidebar.info("🔑 Custom API key active for this session")

    st.sidebar.markdown("---")
    st.sidebar.subheader("🎯 Mode Selection")
    mode_options = ["Automatic (LLM with Fallback)", "Fallback Mode Only (Heuristic Pre-filter - Fast & Free)"]
    if not api_key_available:
        default_idx = 1
    else:
        default_idx = 0

    selected_mode = st.sidebar.radio(
        "Execution Mode:",
        mode_options,
        index=default_idx,
        help="Fallback mode ranks candidate clips directly using tone tags, shock words, ending suspense punctuation, pace, and local sentence-transformers (all-MiniLM-L6-v2) embeddings without requiring any external LLM API key."
    )

    st.sidebar.markdown("---")
    max_per_ep = st.sidebar.slider("Max Promos Per Episode:", min_value=1, max_value=5, value=2)

    # Sample script loader
    sample_file = Path("I Married a Broken Soldier. He was a Duke-scripts (2) (1)/I Married a Broken Soldier. He was a Duke/episode-001-Episode 1671703.txt")
    load_sample = False
    if sample_file.exists():
        st.sidebar.markdown("---")
        st.sidebar.subheader("🧪 Quick Test")
        if st.sidebar.button("📂 Load Sample Episode 1"):
            load_sample = True

    # ── Main File Uploader ────────────────────────────────────────────────────
    uploaded_files = st.file_uploader(
        "Upload Microdrama Screenplay Files (`.txt`):",
        type=["txt"],
        accept_multiple_files=True,
        help="Upload one or multiple episode script files formatted with SCENE headers, character dialogue lines, and [mm:ss.s] timestamps."
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

    # ── Execution ─────────────────────────────────────────────────────────────
    if run_btn:
        if not scripts_to_process:
            st.error("Please upload at least one `.txt` screenplay file (or click 'Load Sample Episode 1' in the sidebar).")
            return

        effective_fallback = (selected_mode == mode_options[1]) or (not api_key_available)

        all_ranked_clips = []
        all_reports_md = []

        total_files = len(scripts_to_process)
        for idx, (filename, text) in enumerate(scripts_to_process, 1):
            st.write(f"### Processing: `{filename}` ({idx}/{total_files})")
            if effective_fallback:
                st.caption("⚡ Running in **Fallback Mode** (Heuristic Pre-filter + sentence-transformers). Zero API tokens used.")
            else:
                st.caption("🤖 Running in **LLM Mode** (Nemotron-3 / Gemini scoring + Blind standalone test).")

            p_bar = st.progress(0)
            status_txt = st.empty()

            try:
                ep_dict, ranked, report_md = process_single_script(
                    script_text=text,
                    filename=filename,
                    use_fallback=effective_fallback,
                    max_per_episode=max_per_ep,
                    progress_bar=p_bar,
                    status_text=status_txt,
                )
                all_ranked_clips.extend(ranked)
                all_reports_md.append(report_md)
            except Exception as ex:
                st.error(f"Error processing {filename}: {ex}")
                logger.exception(ex)

        if all_ranked_clips:
            st.session_state["ranked_results"] = all_ranked_clips
            st.session_state["reports_md"] = "\n\n---\n\n".join(all_reports_md)
            st.session_state["mode_used"] = "Fallback" if effective_fallback else "LLM"
            st.success(f"🎉 Successfully extracted {len(all_ranked_clips)} winning promo clips across {len(scripts_to_process)} script(s)!")

    # ── Results Display ───────────────────────────────────────────────────────
    if "ranked_results" in st.session_state and st.session_state["ranked_results"]:
        ranked_clips = st.session_state["ranked_results"]
        mode_used = st.session_state.get("mode_used", "Standard")

        st.markdown("---")
        st.subheader("🏆 Ranked Promo Clips")

        # Metric banners
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Selected Promos", len(ranked_clips))
        avg_score = sum(c.get("total_score", 0) for c in ranked_clips) / len(ranked_clips)
        col2.metric("Average Score", f"{avg_score:.2f} / 10")
        avg_dur = sum(c.get("duration_sec", 0) for c in ranked_clips) / len(ranked_clips)
        col3.metric("Average Duration", f"{avg_dur:.1f}s")
        col4.metric("Engine Mode", mode_used)

        # Tabular Summary Dataframe
        table_rows = []
        for i, c in enumerate(ranked_clips, 1):
            table_rows.append({
                "Rank": i,
                "Episode": c.get("episode", "Episode 1"),
                "Clip ID": c["clip_id"],
                "Time Window": f"{c.get('start_fmt', '')} → {c.get('end_fmt', '')}",
                "Duration (s)": round(c.get("duration_sec", 0.0), 1),
                "Total Score": c.get("total_score", 0.0),
                "Hook": c.get("hook", 0.0),
                "Cliffhanger": c.get("cliffhanger", 0.0),
                "Emotion": c.get("emotion", 0.0),
                "Standalone": c.get("standalone", 0.0),
                "Hook Line": c.get("hook_line", "")[:45] + ("…" if len(c.get("hook_line", "")) > 45 else ""),
                "Cliffhanger Line": c.get("cliffhanger_line", "")[:45] + ("…" if len(c.get("cliffhanger_line", "")) > 45 else ""),
                "Why It Works": c.get("why_it_works", ""),
            })

        st.dataframe(
            table_rows,
            use_container_width=True,
            column_config={
                "Rank": st.column_config.NumberColumn(width="small"),
                "Clip ID": st.column_config.TextColumn(width="small"),
                "Total Score": st.column_config.ProgressColumn(min_value=0, max_value=10, format="%.2f"),
                "Hook": st.column_config.NumberColumn(format="%.1f"),
                "Cliffhanger": st.column_config.NumberColumn(format="%.1f"),
                "Emotion": st.column_config.NumberColumn(format="%.1f"),
                "Standalone": st.column_config.NumberColumn(format="%.1f"),
            }
        )

        # ── Export & Download Buttons ─────────────────────────────────────────
        st.subheader("📥 Download Promo Assets")
        d_col1, d_col2, d_col3 = st.columns(3)

        # 1. CSV Download
        csv_buffer = io.StringIO()
        fieldnames = [
            "rank", "episode", "clip_id", "start_time", "end_time", "duration_sec",
            "total_score", "hook_score", "cliffhanger_score", "emotion_score",
            "standalone_score", "hook_line", "hook_type", "cliffhanger_line", "why_it_works"
        ]
        writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
        writer.writeheader()
        for idx, c in enumerate(ranked_clips, 1):
            writer.writerow({
                "rank": idx,
                "episode": c.get("episode", "Episode 1"),
                "clip_id": c["clip_id"],
                "start_time": c.get("start_fmt", ""),
                "end_time": c.get("end_fmt", ""),
                "duration_sec": c.get("duration_sec", 0.0),
                "total_score": c.get("total_score", 0.0),
                "hook_score": c.get("hook", 0.0),
                "cliffhanger_score": c.get("cliffhanger", 0.0),
                "emotion_score": c.get("emotion", 0.0),
                "standalone_score": c.get("standalone", 0.0),
                "hook_line": c.get("hook_line", ""),
                "hook_type": c.get("hook_type", ""),
                "cliffhanger_line": c.get("cliffhanger_line", ""),
                "why_it_works": c.get("why_it_works", ""),
            })

        d_col1.download_button(
            label="📄 Download Promos CSV",
            data=csv_buffer.getvalue(),
            file_name="promos.csv",
            mime="text/csv",
            use_container_width=True
        )

        # 2. JSON Download
        json_str = json.dumps(ranked_clips, indent=2, ensure_ascii=False)
        d_col2.download_button(
            label="📦 Download Promos JSON",
            data=json_str,
            file_name="promos.json",
            mime="application/json",
            use_container_width=True
        )

        # 3. Markdown Report Download
        md_text = st.session_state.get("reports_md", "")
        d_col3.download_button(
            label="📝 Download Markdown Report",
            data=md_text,
            file_name="report.md",
            mime="text/markdown",
            use_container_width=True
        )

        # Detailed expandable cards for each clip
        st.markdown("---")
        st.subheader("🔍 Detailed Clip Breakdown")
        for i, c in enumerate(ranked_clips, 1):
            with st.expander(f"#{i} — {c['clip_id']} [{c.get('start_fmt')} → {c.get('end_fmt')}] — Score: {c.get('total_score')}/10"):
                c_col1, c_col2 = st.columns([2, 1])
                with c_col1:
                    st.markdown(f"**Episode:** `{c.get('episode')}` | **Duration:** `{c.get('duration_sec'):.1f}s`")
                    st.markdown(f"**🪝 Hook ({c.get('hook_type', 'line')}):** > *\"{c.get('hook_line')}\"*")
                    st.markdown(f"**⚡ Cliffhanger:** > *\"{c.get('cliffhanger_line')}\"*")
                    st.markdown(f"**💡 Why It Works:** {c.get('why_it_works')}")
                    if c.get("problems"):
                        st.warning(f"**Identified Risks / Flags:** {'; '.join(c.get('problems'))}")

                with c_col2:
                    st.write("**Score Breakdown:**")
                    st.progress(c.get("hook", 0.0) / 10.0, text=f"Hook: {c.get('hook', 0.0)}/10")
                    st.progress(c.get("cliffhanger", 0.0) / 10.0, text=f"Cliffhanger: {c.get('cliffhanger', 0.0)}/10")
                    st.progress(c.get("emotion", 0.0) / 10.0, text=f"Emotion: {c.get('emotion', 0.0)}/10")
                    st.progress(c.get("standalone", 0.0) / 10.0, text=f"Standalone: {c.get('standalone', 0.0)}/10")

                st_test = c.get("standalone_test")
                if st_test:
                    st.markdown("**Blind Standalone Comprehension Test:**")
                    st.markdown(f"- **Characters:** {', '.join(st_test.get('characters', []))}")
                    st.markdown(f"- **Core Conflict:** {st_test.get('conflict', '')}")
                    st.markdown(f"- **What Happens Next:** {st_test.get('what_happens_next', '')}")


# ─────────────────────────────────────────────────────────────────────────────
# Dual-Mode Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    # If run through `streamlit run app.py`, execute the Streamlit UI
    if st.runtime.exists():
        run_streamlit_app()
        return

    # Otherwise execute CLI runner
    parser = argparse.ArgumentParser(description="Microdrama promo clip finder")
    parser.add_argument("episode", nargs="?", help="Path to screenplay .txt file")
    parser.add_argument("--stage", default="all", choices=STAGES, help="Stop after this stage")
    parser.add_argument("--fallback", action="store_true", help="Force fallback mode using prefilter only")
    args = parser.parse_args()

    if not args.episode:
        print("\n" + "=" * 65)
        print("🎬 Microdrama Promo Clip Finder")
        print("=" * 65)
        print("To launch the interactive Web UI:")
        print("    streamlit run app.py\n")
        print("To run from the command line:")
        print("    python app.py \"path/to/episode.txt\"")
        print("    python app.py \"path/to/episode.txt\" --fallback")
        print("=" * 65 + "\n")
        return

    run_cli(args.episode, args.stage, fallback=args.fallback)


if __name__ == "__main__":
    main()
