"""
ui/components.py
────────────────
Reusable visual UI components: Hero header, metric cards, clip cards, empty states.
"""

import streamlit as st

from services.ai_caption_service import generate_social_promos
from utils.formatting import score_color, tag_badge_html


def render_hero_header(mode_label: str = "Ready"):
    """Render the cinematic hero banner."""
    st.markdown(f"""
        <div class="hero-container">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 1rem;">
                <div>
                    <div class="hero-title">🎬 Microdrama Promo Clip Studio</div>
                    <div class="hero-subtitle">
                        Discover viral 20–60s trailers from screenplay scripts with 3s hooks, 
                        emotional cliffhangers, and semantic deduplication.
                    </div>
                </div>
                <div>
                    <span style="background: rgba(99, 102, 241, 0.2); color: #A5B4FC; border: 1px solid rgba(99, 102, 241, 0.5); padding: 6px 14px; border-radius: 9999px; font-size: 0.85rem; font-weight: 600;">
                        Engine: {mode_label}
                    </span>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)


def render_metric_cards(ranked_clips: list[dict], mode_name: str):
    """Render top 4 key performance metrics."""
    if not ranked_clips:
        return

    n = len(ranked_clips)
    avg_score = sum(c.get("total_score", 0.0) for c in ranked_clips) / n
    avg_dur = sum(c.get("duration_sec", 0.0) for c in ranked_clips) / n
    fav_count = sum(1 for c in ranked_clips if c.get("is_favorite"))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
            <div class="metric-card-box">
                <div class="metric-label">Winning Promos</div>
                <div class="metric-val">{n} <span style="font-size: 0.9rem; color: #64748B;">selected</span></div>
            </div>
        """, unsafe_allow_html=True)

    with c2:
        st.markdown(f"""
            <div class="metric-card-box">
                <div class="metric-label">Average Score</div>
                <div class="metric-val" style="color: {score_color(avg_score)};">{avg_score:.2f} <span style="font-size: 0.9rem; color: #64748B;">/ 10</span></div>
            </div>
        """, unsafe_allow_html=True)

    with c3:
        st.markdown(f"""
            <div class="metric-card-box">
                <div class="metric-label">Average Duration</div>
                <div class="metric-val">{avg_dur:.1f}s</div>
            </div>
        """, unsafe_allow_html=True)

    with c4:
        st.markdown(f"""
            <div class="metric-card-box">
                <div class="metric-label">Engine Mode</div>
                <div class="metric-val" style="font-size: 1.3rem; margin-top: 0.3rem; color: #A5B4FC;">{mode_name}</div>
            </div>
        """, unsafe_allow_html=True)


def render_empty_state():
    """Render friendly empty state when no clips are loaded."""
    st.markdown("""
        <div style="text-align: center; padding: 4rem 2rem; background: #161922; border: 1px dashed rgba(255, 255, 255, 0.15); border-radius: 16px; margin: 2rem 0;">
            <div style="font-size: 3.5rem; margin-bottom: 1rem;">🎞️</div>
            <h3 style="color: #F8FAFC; margin-bottom: 0.5rem;">No Screenplays Processed Yet</h3>
            <p style="color: #94A3B8; max-width: 520px; margin: 0 auto 1.5rem auto;">
                Upload a microdrama screenplay script (<code style="color: #A5B4FC;">.txt</code>) above or click 
                <strong>"Load Sample Episode 1"</strong> in the sidebar to extract high-converting promo clips.
            </p>
        </div>
    """, unsafe_allow_html=True)


def render_clip_card(
    clip: dict,
    rank_idx: int,
    session_id: str,
    aspect_ratio: str = "9:16 (Vertical)",
):
    """Render full interactive promo clip card."""
    cid = clip["clip_id"]
    score = clip.get("total_score", 0.0)
    dur = clip.get("duration_sec", 0.0)
    start_fmt = clip.get("start_fmt", "00:00.00")
    end_fmt = clip.get("end_fmt", "00:00.00")
    ep = clip.get("episode", "Episode 1")
    hook_line = clip.get("hook_line", "")
    hook_type = clip.get("hook_type", "hook")
    cliff_line = clip.get("cliffhanger_line", "")
    why = clip.get("why_it_works", "")
    problems = clip.get("problems", [])
    is_fav = clip.get("is_favorite", False)

    st.markdown(f"""
        <div class="clip-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.8rem;">
                <div style="display: flex; align-items: center; gap: 0.6rem;">
                    <span style="background: #312E81; color: #C7D2FE; padding: 3px 10px; border-radius: 6px; font-weight: 700; font-size: 0.9rem;">
                        #{rank_idx}
                    </span>
                    <span style="font-size: 1.15rem; font-weight: 700; color: #F8FAFC;">{cid}</span>
                    <span style="background: rgba(255,255,255,0.08); color: #CBD5E1; padding: 2px 8px; border-radius: 4px; font-size: 0.78rem;">
                        {dur:.1f}s
                    </span>
                    <span style="background: rgba(99, 102, 241, 0.15); color: #818CF8; padding: 2px 8px; border-radius: 4px; font-size: 0.78rem;">
                        {start_fmt} → {end_fmt}
                    </span>
                </div>
                <div style="display: flex; align-items: center; gap: 0.8rem;">
                    <span class="score-pill" style="background: {score_color(score)}20; color: {score_color(score)}; border: 1px solid {score_color(score)}50; font-size: 1rem;">
                        ★ {score:.2f} / 10
                    </span>
                </div>
            </div>
    """, unsafe_allow_html=True)

    # Main content columns: Left (Script quotes & why), Right (Visual aspect ratio & scores)
    col_left, col_right = st.columns([1.6, 1.0])

    with col_left:
        st.markdown(f"""
            <div style="margin-bottom: 0.4rem;">
                <strong style="color: #818CF8;">🪝 Hook ({hook_type}):</strong>
                <div class="quote-box">"{hook_line}"</div>
            </div>
            <div style="margin-bottom: 0.4rem;">
                <strong style="color: #F472B6;">⚡ Cliffhanger:</strong>
                <div class="quote-box quote-cliff">"{cliff_line}"</div>
            </div>
            <div style="margin-top: 0.6rem;">
                <strong style="color: #E2E8F0;">💡 Why It Works:</strong>
                <p style="color: #94A3B8; font-size: 0.92rem; margin-top: 0.2rem; line-height: 1.45;">{why}</p>
            </div>
        """, unsafe_allow_html=True)

        if problems:
            st.warning(f"⚠️ **Identified Narrative Risks:** {'; '.join(problems)}")

    with col_right:
        # Score progress breakdown
        h_score = clip.get("hook", 0.0)
        c_score = clip.get("cliffhanger", 0.0)
        e_score = clip.get("emotion", 0.0)
        s_score = clip.get("standalone", 0.0)

        st.caption("Sub-Score Analysis:")
        st.progress(h_score / 10.0, text=f"Hook: {h_score:.1f}/10")
        st.progress(c_score / 10.0, text=f"Cliffhanger: {c_score:.1f}/10")
        st.progress(e_score / 10.0, text=f"Emotion: {e_score:.1f}/10")
        st.progress(s_score / 10.0, text=f"Standalone: {s_score:.1f}/10")

    st.markdown("</div>", unsafe_allow_html=True)


def render_social_and_blind_details(ranked_clips: list[dict], episode: dict = None):
    """
    Render social media captions and blind test analysis ONCE in the UI
    with an interactive clip selector to prevent duplicate expanders.
    """
    if not ranked_clips:
        return

    st.markdown("---")
    st.markdown("### 📱 Social Copywriting & Blind Comprehension Studio")
    st.caption("Select a promo cut to inspect viral social media presets and narrative comprehension testing.")

    clip_labels = [f"#{idx} — {c['clip_id']} ({c.get('start_fmt')} → {c.get('end_fmt')}) — Score: {c.get('total_score', 0):.2f}" for idx, c in enumerate(ranked_clips, 1)]
    selected_idx = st.selectbox(
        "Select Clip to Inspect:",
        range(len(ranked_clips)),
        format_func=lambda i: clip_labels[i],
        key="global_social_blind_selector",
    )
    clip = ranked_clips[selected_idx]
    cid = clip["clip_id"]
    ep = clip.get("episode", episode.get("episode_number", "Episode") if episode else "Episode")

    # 1. Social Media Presets (Appears ONCE)
    with st.expander(f"📱 AI Social Media Captions & Hashtags (Reels / TikTok / Shorts) — {cid}", expanded=True):
        social = generate_social_promos(clip, episode_title=ep)
        tab_tt, tab_ig, tab_yt = st.tabs(["🎵 TikTok", "📸 Instagram Reels", "▶️ YouTube Shorts"])

        with tab_tt:
            st.text_area("TikTok Hook & Caption:", value=social["tiktok"]["caption"], height=120, key=f"tt_single_{cid}")
            st.code(" ".join(social["tiktok"]["hashtags"]), language="markdown")

        with tab_ig:
            st.text_area("Instagram Reels Caption:", value=social["reels"]["caption"], height=120, key=f"ig_single_{cid}")
            st.code(" ".join(social["reels"]["hashtags"]), language="markdown")

        with tab_yt:
            st.text_area("YouTube Shorts Title & Description:", value=f"{social['shorts']['hook_title']}\n\n{social['shorts']['caption']}", height=120, key=f"yt_single_{cid}")
            st.code(" ".join(social["shorts"]["hashtags"]), language="markdown")

    # 2. Blind Comprehension Test (Appears ONCE)
    st_test = clip.get("standalone_test")
    if st_test:
        with st.expander(f"🧪 Blind Standalone Comprehension Test Details — {cid}"):
            c1, c2 = st.columns([1, 1])
            with c1:
                st.markdown(f"**Detected Characters:**\n- {', '.join(st_test.get('characters', []))}")
                st.markdown(f"**Identified Core Conflict:**\n> {st_test.get('conflict', '')}")
            with c2:
                st.markdown(f"**Audience Anticipation & Hook:**\n> {st_test.get('what_happens_next', '')}")
                und = st_test.get("understandability", clip.get("standalone", 7.0))
                st.metric("Understandability Score", f"{und:.1f} / 10")

