"""
ui/editor.py
────────────
Interactive timeline trimming and side-by-side clip comparison.
"""

import streamlit as st

from db.database import get_db
from utils.formatting import fmt_seconds, score_badge_html


def render_clip_editor(ranked_clips: list[dict], session_id: str):
    """
    Render interactive timeline trimming tool to fine-tune start and end seconds.
    """
    if not ranked_clips:
        return

    st.markdown("### 🎛️ Fine-Tune Clip Timestamps")
    st.caption("Adjust the start and end boundary points to perfect the trailer cut.")

    clip_options = {c["clip_id"]: c for c in ranked_clips}
    selected_id = st.selectbox("Select Clip to Adjust:", list(clip_options.keys()))
    clip = clip_options[selected_id]

    cur_start = float(clip.get("start_s", clip.get("_start_s", 0.0)))
    cur_end = float(clip.get("end_s", clip.get("_end_s", 0.0)))

    # Boundaries allowed: +/- 15 seconds padding
    min_bound = max(0.0, cur_start - 15.0)
    max_bound = cur_end + 15.0

    c1, c2 = st.columns(2)
    with c1:
        new_start = st.number_input(
            "Start Time (seconds):",
            min_value=min_bound,
            max_value=cur_end - 5.0,
            value=cur_start,
            step=0.5,
            format="%.2f",
        )
    with c2:
        new_end = st.number_input(
            "End Time (seconds):",
            min_value=new_start + 5.0,
            max_value=max_bound,
            value=cur_end,
            step=0.5,
            format="%.2f",
        )

    new_dur = new_end - new_start
    st.info(
        f"**Updated Cut:** `{fmt_seconds(new_start)}` → `{fmt_seconds(new_end)}` "
        f"(Duration: **{new_dur:.2f}s**)"
    )

    if st.button("💾 Apply & Save Adjusted Cut", type="primary"):
        db = get_db()
        st_fmt = fmt_seconds(new_start)
        et_fmt = fmt_seconds(new_end)
        db.update_clip_times(
            clip_id=selected_id,
            session_id=session_id,
            new_start_s=new_start,
            new_end_s=new_end,
            start_fmt=st_fmt,
            end_fmt=et_fmt,
        )
        # Update session state object
        clip["start_s"] = new_start
        clip["end_s"] = new_end
        clip["_start_s"] = new_start
        clip["_end_s"] = new_end
        clip["duration_sec"] = new_dur
        clip["start_fmt"] = st_fmt
        clip["end_fmt"] = et_fmt
        st.toast(f"Updated timestamps for {selected_id}!", icon="✂️")
        st.rerun()


def render_clip_comparison(ranked_clips: list[dict]):
    """Render side-by-side comparison between 2 selected clips."""
    if len(ranked_clips) < 2:
        st.info("At least 2 promo clips are required for side-by-side comparison.")
        return

    st.markdown("### ⚖️ Side-by-Side Clip Comparison")

    col_sel1, col_sel2 = st.columns(2)
    with col_sel1:
        id1 = st.selectbox("Select First Clip:", [c["clip_id"] for c in ranked_clips], index=0)
    with col_sel2:
        id2 = st.selectbox("Select Second Clip:", [c["clip_id"] for c in ranked_clips], index=1)

    c1 = next(c for c in ranked_clips if c["clip_id"] == id1)
    c2 = next(c for c in ranked_clips if c["clip_id"] == id2)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"#### #{ranked_clips.index(c1)+1}: `{c1['clip_id']}`")
        st.metric("Total Score", f"{c1.get('total_score', 0):.2f} / 10")
        st.write(f"**Duration:** `{c1.get('duration_sec', 0):.1f}s` | **Range:** `{c1.get('start_fmt')} → {c1.get('end_fmt')}`")
        st.markdown(f"**Hook ({c1.get('hook_type', 'line')}):** > *\"{c1.get('hook_line')}\"*")
        st.markdown(f"**Cliffhanger:** > *\"{c1.get('cliffhanger_line')}\"*")
        st.caption(f"**Why It Works:** {c1.get('why_it_works')}")

    with col2:
        st.markdown(f"#### #{ranked_clips.index(c2)+1}: `{c2['clip_id']}`")
        st.metric("Total Score", f"{c2.get('total_score', 0):.2f} / 10")
        st.write(f"**Duration:** `{c2.get('duration_sec', 0):.1f}s` | **Range:** `{c2.get('start_fmt')} → {c2.get('end_fmt')}`")
        st.markdown(f"**Hook ({c2.get('hook_type', 'line')}):** > *\"{c2.get('hook_line')}\"*")
        st.markdown(f"**Cliffhanger:** > *\"{c2.get('cliffhanger_line')}\"*")
        st.caption(f"**Why It Works:** {c2.get('why_it_works')}")
