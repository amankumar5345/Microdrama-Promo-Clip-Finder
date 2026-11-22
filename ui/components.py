"""
ui/components.py
────────────────
Reusable visual UI components: Hero header, metric cards, clip cards, empty states,
human approval controls, full promo conversation transcripts, and video editor cut guides.
"""

import re
import streamlit as st

from db.database import get_db
from services.ai_caption_service import generate_social_promos
from utils.formatting import score_color, fmt_seconds, tag_badge_html


def render_hero_header(mode_label: str = "Ready"):
    """Render the cinematic hero banner."""
    st.markdown(f"""
        <div class="hero-container">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 1rem;">
                <div>
                    <div class="hero-title">🎬 Microdrama Promo Clip Studio</div>
                    <div class="hero-subtitle">
                        Discover viral 20–60s trailers from screenplay scripts with 3s hooks, 
                        emotional cliffhangers, human approval sign-off, and exact video editor cut ranges.
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
    """Render top key performance metrics including human approval progress."""
    if not ranked_clips:
        return

    n = len(ranked_clips)
    avg_score = sum(c.get("total_score", 0.0) for c in ranked_clips) / n
    avg_dur = sum(c.get("duration_sec", 0.0) for c in ranked_clips) / n

    # Calculate human approval count from session state or clip attributes
    approved_count = 0
    rejected_count = 0
    pending_count = 0
    for c in ranked_clips:
        cid = c.get("clip_id", "")
        status = st.session_state.get(f"approval_{cid}") or c.get("approval_status") or "pending"
        if status == "approved":
            approved_count += 1
        elif status == "rejected":
            rejected_count += 1
        else:
            pending_count += 1

    c1, c2, c3, c4, c5 = st.columns(5)
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
                <div class="metric-label">Human Sign-Off</div>
                <div class="metric-val" style="color: {'#10B981' if approved_count > 0 else '#F59E0B'};">
                    {approved_count} <span style="font-size: 0.9rem; color: #94A3B8;">/ {n} Approved</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

    with c5:
        st.markdown(f"""
            <div class="metric-card-box">
                <div class="metric-label">Engine Mode</div>
                <div class="metric-val" style="font-size: 1.25rem; margin-top: 0.35rem; color: #A5B4FC;">{mode_name}</div>
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


def extract_clip_events(clip: dict, episode: dict = None) -> list[dict]:
    """
    Extract the sequence of scene/dialogue events that fall inside this promo window.
    Supports both freshly parsed candidate objects and stored history objects.
    """
    # 1. Check direct _events
    events = clip.get("_events")
    if events and isinstance(events, list) and len(events) > 0:
        return events

    # 2. Extract from episode object if available
    if episode and isinstance(episode, dict) and "events" in episode:
        start_s = float(clip.get("start_s", clip.get("_start_s", 0.0)))
        end_s = float(clip.get("end_s", clip.get("_end_s", 999999.0)))
        ep_events = episode.get("events", [])
        matched = [
            e for e in ep_events
            if (start_s - 0.25 <= float(e.get("start_s", 0.0)) <= end_s + 0.25)
            or (start_s - 0.25 <= float(e.get("end_s", 0.0)) <= end_s + 0.25)
        ]
        if matched:
            return matched

    return []


def _normalize_match(text: str) -> str:
    """Normalize string for fuzzy hook/cliffhanger line matching."""
    t = text.lower().strip()
    t = re.sub(r'[\'""“”„«»…]', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t.rstrip('.!?')


def render_clip_card(
    clip: dict,
    rank_idx: int,
    session_id: str,
    episode: dict = None,
    aspect_ratio: str = "9:16 (Vertical)",
):
    """
    Render full interactive promo clip card featuring:
      1. Overall Score & Viral Performance Attributes
      2. ⏱️ Exact Video Editor Cutting Timestamps ([start_fmt] to [end_fmt])
      3. 💬 Full Promo Conversation & Script Transcript (What viewers will see and hear)
      4. 👤 Human Approval & Editorial Decision Controls
    """
    cid = clip["clip_id"]
    score = clip.get("total_score", 0.0)
    dur = clip.get("duration_sec", 0.0)
    start_s = float(clip.get("start_s", clip.get("_start_s", 0.0)))
    end_s = float(clip.get("end_s", clip.get("_end_s", start_s + dur)))
    start_fmt = clip.get("start_fmt") or fmt_seconds(start_s)
    end_fmt = clip.get("end_fmt") or fmt_seconds(end_s)
    ep = clip.get("episode", episode.get("episode_number", "Episode 1") if episode else "Episode 1")
    hook_line = clip.get("hook_line", "")
    hook_type = clip.get("hook_type", "hook")
    cliff_line = clip.get("cliffhanger_line", "")
    why = clip.get("why_it_works", "")
    problems = clip.get("problems", [])

    # Human Approval State (retrieved from session state, clip dict, or DB)
    db = get_db()
    current_status = st.session_state.get(f"approval_{cid}")
    if not current_status:
        current_status = clip.get("approval_status") or "pending"
        st.session_state[f"approval_{cid}"] = current_status

    current_notes = st.session_state.get(f"approval_notes_{cid}")
    if current_notes is None:
        current_notes = clip.get("approval_notes") or ""
        st.session_state[f"approval_notes_{cid}"] = current_notes

    # Visual badge for approval in header
    approval_pill_html = ""
    if current_status == "approved":
        approval_pill_html = """
            <span style="background: rgba(16, 185, 129, 0.2); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.6); padding: 3px 10px; border-radius: 9999px; font-size: 0.82rem; font-weight: 700;">
                ✅ Approved for Promo
            </span>
        """
    elif current_status == "rejected":
        approval_pill_html = """
            <span style="background: rgba(239, 68, 68, 0.2); color: #F87171; border: 1px solid rgba(239, 68, 68, 0.6); padding: 3px 10px; border-radius: 9999px; font-size: 0.82rem; font-weight: 700;">
                ❌ Rejected Cut
            </span>
        """
    elif current_status == "recut":
        approval_pill_html = """
            <span style="background: rgba(245, 158, 11, 0.2); color: #FBBF24; border: 1px solid rgba(245, 158, 11, 0.6); padding: 3px 10px; border-radius: 9999px; font-size: 0.82rem; font-weight: 700;">
                ⚠️ Needs Re-cut
            </span>
        """
    else:
        approval_pill_html = """
            <span style="background: rgba(148, 163, 184, 0.15); color: #94A3B8; border: 1px solid rgba(148, 163, 184, 0.35); padding: 3px 10px; border-radius: 9999px; font-size: 0.82rem; font-weight: 600;">
                ⏳ Pending Review
            </span>
        """

    # ── Card Container ────────────────────────────────────────────────────────
    st.markdown(f"""
        <div class="clip-card">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.8rem; margin-bottom: 0.8rem;">
                <div style="display: flex; align-items: center; flex-wrap: wrap; gap: 0.6rem;">
                    <span style="background: #312E81; color: #C7D2FE; padding: 3px 10px; border-radius: 6px; font-weight: 700; font-size: 0.9rem;">
                        #{rank_idx}
                    </span>
                    <span style="font-size: 1.2rem; font-weight: 700; color: #F8FAFC;">{cid}</span>
                    <span style="background: rgba(255,255,255,0.08); color: #CBD5E1; padding: 2px 8px; border-radius: 4px; font-size: 0.78rem;">
                        {ep}
                    </span>
                    <span style="background: rgba(99, 102, 241, 0.15); color: #818CF8; padding: 2px 8px; border-radius: 4px; font-size: 0.78rem; font-family: monospace;">
                        ⏱️ {start_fmt} → {end_fmt} ({dur:.1f}s)
                    </span>
                </div>
                <div style="display: flex; align-items: center; gap: 0.8rem;">
                    {approval_pill_html}
                    <span class="score-pill" style="background: {score_color(score)}20; color: {score_color(score)}; border: 1px solid {score_color(score)}50; font-size: 1rem;">
                        ★ {score:.2f} / 10
                    </span>
                </div>
            </div>
    """, unsafe_allow_html=True)

    # ── Top Row: Quotes & Sub-Scores ──────────────────────────────────────────
    col_left, col_right = st.columns([1.6, 1.0])

    with col_left:
        st.markdown(f"""
            <div style="margin-bottom: 0.4rem;">
                <strong style="color: #818CF8;">🪝 3-Second Viral Opening Hook ({hook_type}):</strong>
                <div class="quote-box">"{hook_line}"</div>
            </div>
            <div style="margin-bottom: 0.4rem;">
                <strong style="color: #F472B6;">⚡ High-Tension Cliffhanger Ending:</strong>
                <div class="quote-box quote-cliff">"{cliff_line}"</div>
            </div>
            <div style="margin-top: 0.6rem;">
                <strong style="color: #E2E8F0;">💡 Editorial Rationale (Why It Works):</strong>
                <p style="color: #94A3B8; font-size: 0.92rem; margin-top: 0.2rem; line-height: 1.45;">{why}</p>
            </div>
        """, unsafe_allow_html=True)

        if problems:
            st.warning(f"⚠️ **Identified Narrative Risks:** {'; '.join(problems)}")

    with col_right:
        h_score = clip.get("hook", 0.0)
        c_score = clip.get("cliffhanger", 0.0)
        e_score = clip.get("emotion", 0.0)
        s_score = clip.get("standalone", 0.0)

        st.caption("Sub-Score Performance Breakdown:")
        st.progress(h_score / 10.0, text=f"Opening Hook: {h_score:.1f}/10")
        st.progress(c_score / 10.0, text=f"Cliffhanger Pull: {c_score:.1f}/10")
        st.progress(e_score / 10.0, text=f"Emotional Payoff: {e_score:.1f}/10")
        st.progress(s_score / 10.0, text=f"Standalone Clarity: {s_score:.1f}/10")

    # ── 1. TIMESTAMPS: Exact Video Editor Promotion Cutting Window ────────────
    st.markdown(f"""
        <div class="editor-cut-banner">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.6rem; margin-bottom: 0.6rem;">
                <div style="display: flex; align-items: center; gap: 0.6rem;">
                    <span style="font-size: 1.25rem;">✂️</span>
                    <strong style="color: #F8FAFC; font-size: 1.05rem;">Video Editor Cut Guide: Promotion Time Range</strong>
                    <span style="background: #312E81; color: #C7D2FE; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 700;">
                        {ep}
                    </span>
                </div>
                <div style="color: #A5B4FC; font-size: 0.85rem; font-weight: 600;">
                    Target Social Duration: <span style="color: #38BDF8;">{dur:.1f}s</span> (20s–60s Microdrama Spec)
                </div>
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.75rem; margin: 0.6rem 0;">
                <div style="background: rgba(0, 0, 0, 0.35); border-left: 3px solid #10B981; border-radius: 6px; padding: 0.6rem 0.9rem;">
                    <div style="color: #94A3B8; font-size: 0.72rem; text-transform: uppercase; font-weight: 600; letter-spacing: 0.05em;">Cut Start Timecode</div>
                    <div style="color: #34D399; font-size: 1.25rem; font-weight: 700; font-family: monospace;">[{start_fmt}]</div>
                    <div style="color: #64748B; font-size: 0.75rem;">Timeline offset: {start_s:.2f} seconds</div>
                </div>
                <div style="background: rgba(0, 0, 0, 0.35); border-left: 3px solid #EC4899; border-radius: 6px; padding: 0.6rem 0.9rem;">
                    <div style="color: #94A3B8; font-size: 0.72rem; text-transform: uppercase; font-weight: 600; letter-spacing: 0.05em;">Cut End Timecode</div>
                    <div style="color: #F472B6; font-size: 1.25rem; font-weight: 700; font-family: monospace;">[{end_fmt}]</div>
                    <div style="color: #64748B; font-size: 0.75rem;">Timeline offset: {end_s:.2f} seconds</div>
                </div>
                <div style="background: rgba(0, 0, 0, 0.35); border-left: 3px solid #6366F1; border-radius: 6px; padding: 0.6rem 0.9rem;">
                    <div style="color: #94A3B8; font-size: 0.72rem; text-transform: uppercase; font-weight: 600; letter-spacing: 0.05em;">Total Promo Length</div>
                    <div style="color: #818CF8; font-size: 1.25rem; font-weight: 700; font-family: monospace;">{dur:.1f}s</div>
                    <div style="color: #64748B; font-size: 0.75rem;">Standard 9:16 Vertical Video</div>
                </div>
            </div>
            <div style="color: #CBD5E1; font-size: 0.88rem; line-height: 1.45; margin-top: 0.5rem; background: rgba(0,0,0,0.25); padding: 0.5rem 0.8rem; border-radius: 6px;">
                📌 <strong>Action for Video Editor / Promo Producer:</strong> Cut the master video for <strong>{ep}</strong> starting exactly at <strong>{start_fmt}</strong> and concluding at <strong>{end_fmt}</strong> to create this promotional asset.
            </div>
        </div>
    """, unsafe_allow_html=True)

    with st.expander(f"📋 Quick Copy Timecodes & FFmpeg Export Command — {cid}", expanded=False):
        c_tc1, c_tc2 = st.columns([1, 2])
        with c_tc1:
            st.text_input("Raw Timecode Window:", value=f"{start_fmt} - {end_fmt}", key=f"raw_tc_{cid}")
        with c_tc2:
            safe_ep = re.sub(r"[^\w\-_.]", "_", ep)
            ffmpeg_cmd = f'ffmpeg -ss {start_fmt} -to {end_fmt} -i "{safe_ep}.mp4" -c copy "promo_{cid}.mp4"'
            st.text_input("FFmpeg Video Cut Command:", value=ffmpeg_cmd, key=f"ffmpeg_cmd_{cid}")

    # ── 2. CONVERSATION: Full Promo Script & Dialogue Breakdown ───────────────
    events = extract_clip_events(clip, episode=episode)
    d_events = [e for e in events if e.get("type") == "dialogue" and e.get("text")]
    characters_in_promo = sorted(list(set(e.get("speaker") for e in events if e.get("speaker"))))
    word_count = sum(len(e.get("text", "").split()) for e in events if e.get("text"))

    norm_hook = _normalize_match(hook_line)
    norm_cliff = _normalize_match(cliff_line)

    with st.expander(
        f"💬 Full Promo Conversation & Script Transcript (What Viewers Will See & Hear) — {len(d_events)} Dialogue Lines",
        expanded=True,
    ):
        st.markdown(f"""
            <div style="color: #94A3B8; font-size: 0.9rem; margin-bottom: 0.8rem; line-height: 1.45;">
                🎬 <strong>If you choose this promo, this is the exact conversation and scene dialogue that will be shown to viewers in the trailer video:</strong>
            </div>
            <div style="display: flex; gap: 0.6rem; flex-wrap: wrap; margin-bottom: 0.8rem;">
                <span style="background: rgba(99,102,241,0.2); color: #C7D2FE; padding: 2px 8px; border-radius: 4px; font-size: 0.78rem;">
                    🗣️ Dialogue Lines: <strong>{len(d_events)}</strong>
                </span>
                <span style="background: rgba(56,189,248,0.2); color: #BAE6FD; padding: 2px 8px; border-radius: 4px; font-size: 0.78rem;">
                    👥 Featured Characters: <strong>{', '.join(characters_in_promo) if characters_in_promo else 'Narrative / Voice'}</strong>
                </span>
                <span style="background: rgba(244,114,182,0.2); color: #FBCFE8; padding: 2px 8px; border-radius: 4px; font-size: 0.78rem;">
                    📝 Dialogue Words: <strong>{word_count}</strong>
                </span>
                <span style="background: rgba(16,185,129,0.2); color: #A7F3D0; padding: 2px 8px; border-radius: 4px; font-size: 0.78rem;">
                    ⚡ Window: <strong>{start_fmt} → {end_fmt}</strong>
                </span>
            </div>
        """, unsafe_allow_html=True)

        if not events:
            # Fallback if events list was not present
            st.markdown(f"""
                <div class="transcript-line transcript-line-hook">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 0.2rem;">
                        <span style="color: #34D399; font-weight: 700; font-size: 0.82rem;">🪝 OPENING HOOK (00:00–00:03s)</span>
                        <span style="color: #64748B; font-family: monospace; font-size: 0.75rem;">[{start_fmt}]</span>
                    </div>
                    <div style="color: #F8FAFC; font-size: 0.95rem;">"{hook_line}"</div>
                </div>
                <div style="padding: 0.8rem; background: rgba(0,0,0,0.2); border-radius: 6px; margin: 0.4rem 0; color: #94A3B8; font-size: 0.88rem;">
                    <em>Scene dramatic exchange: {why}</em>
                </div>
                <div class="transcript-line transcript-line-cliff">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 0.2rem;">
                        <span style="color: #F472B6; font-weight: 700; font-size: 0.82rem;">⚡ CLIFFHANGER CLIMAX</span>
                        <span style="color: #64748B; font-family: monospace; font-size: 0.75rem;">[{end_fmt}]</span>
                    </div>
                    <div style="color: #F8FAFC; font-size: 0.95rem;">"{cliff_line}"</div>
                </div>
            """, unsafe_allow_html=True)
        else:
            for ev_idx, ev in enumerate(events, 1):
                ev_type = ev.get("type", "dialogue")
                ev_text = ev.get("text", "")
                ev_start = float(ev.get("start_s", 0.0))
                ev_end = float(ev.get("end_s", 0.0))
                ev_s_fmt = fmt_seconds(ev_start)
                ev_e_fmt = fmt_seconds(ev_end)
                norm_text = _normalize_match(ev_text)

                is_hook = bool(norm_hook and (norm_hook in norm_text or norm_text in norm_hook))
                is_cliff = bool(norm_cliff and (norm_cliff in norm_text or norm_text in norm_cliff))

                if ev_type == "dialogue":
                    spk = ev.get("speaker") or "SPEAKER"
                    tone = ev.get("tone")
                    tone_html = f'<span style="color: #A5B4FC; font-style: italic; font-size: 0.78rem; margin-left: 0.35rem;">({tone})</span>' if tone else ""

                    badge_html = ""
                    card_extra_class = ""
                    if is_hook:
                        badge_html = '<span style="background: rgba(16,185,129,0.25); color: #34D399; border: 1px solid rgba(16,185,129,0.5); padding: 1px 7px; border-radius: 4px; font-size: 0.72rem; font-weight: 700;">🪝 3s VIRAL HOOK</span>'
                        card_extra_class = "transcript-line-hook"
                    elif is_cliff:
                        badge_html = '<span style="background: rgba(236,72,153,0.25); color: #F472B6; border: 1px solid rgba(236,72,153,0.5); padding: 1px 7px; border-radius: 4px; font-size: 0.72rem; font-weight: 700;">⚡ CLIFFHANGER</span>'
                        card_extra_class = "transcript-line-cliff"

                    st.markdown(f"""
                        <div class="transcript-line {card_extra_class}">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
                                <div>
                                    <span style="background: #312E81; color: #E0E7FF; padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 0.8rem;">
                                        {spk}
                                    </span>
                                    {tone_html}
                                </div>
                                <div style="display: flex; align-items: center; gap: 0.5rem;">
                                    {badge_html}
                                    <span style="color: #64748B; font-family: monospace; font-size: 0.75rem;">[{ev_s_fmt}]</span>
                                </div>
                            </div>
                            <div style="color: #F8FAFC; font-size: 0.94rem; line-height: 1.45; margin-top: 0.15rem;">
                                "{ev_text}"
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                else:
                    icon = "🎬" if ev_type == "action" else ("🎥" if ev_type == "camera" else "🔊")
                    st.markdown(f"""
                        <div style="background: rgba(30, 41, 59, 0.4); border-left: 2px solid #64748B; border-radius: 4px; padding: 0.4rem 0.8rem; margin-bottom: 0.4rem; font-size: 0.82rem; color: #94A3B8;">
                            <div style="display: flex; justify-content: space-between;">
                                <span style="color: #CBD5E1; font-weight: 600;">{icon} [{ev_type.upper()}]</span>
                                <span style="color: #64748B; font-family: monospace; font-size: 0.72rem;">[{ev_s_fmt}]</span>
                            </div>
                            <div style="margin-top: 0.15rem; color: #CBD5E1;">{ev_text}</div>
                        </div>
                    """, unsafe_allow_html=True)

    # ── 3. HUMAN APPROVAL: Interactive Editorial Sign-Off & Notes ─────────────
    st.markdown("---")
    st.markdown("#### 👤 Human Editorial Approval & Campaign Sign-Off")

    # Current status banner
    if current_status == "approved":
        st.success(f"✅ **PROMO APPROVED:** This clip ({cid}) has been approved by human reviewer for social promotion and trailer editing.")
    elif current_status == "rejected":
        st.error(f"❌ **PROMO REJECTED:** This clip ({cid}) was rejected from the final promotional campaign.")
    elif current_status == "recut":
        st.warning(f"⚠️ **FLAGGED FOR RE-CUT:** This clip ({cid}) requires re-trimming or timeline boundary adjustment.")
    else:
        st.info(f"⏳ **PENDING REVIEW:** Awaiting human editorial decision for {cid}.")

    # Interactive Action Buttons
    b_col1, b_col2, b_col3, b_col4 = st.columns(4)

    with b_col1:
        if st.button("✅ Approve Promo", key=f"btn_approve_{cid}", use_container_width=True, type="primary" if current_status != "approved" else "secondary"):
            st.session_state[f"approval_{cid}"] = "approved"
            clip["approval_status"] = "approved"
            if session_id and session_id != "temp":
                db.set_approval_status(cid, session_id, "approved", current_notes)
            st.toast(f"✅ Promo {cid} approved for campaign!", icon="🎉")
            st.rerun()

    with b_col2:
        if st.button("❌ Reject Promo", key=f"btn_reject_{cid}", use_container_width=True):
            st.session_state[f"approval_{cid}"] = "rejected"
            clip["approval_status"] = "rejected"
            if session_id and session_id != "temp":
                db.set_approval_status(cid, session_id, "rejected", current_notes)
            st.toast(f"❌ Promo {cid} rejected", icon="🚫")
            st.rerun()

    with b_col3:
        if st.button("⚠️ Needs Re-cut", key=f"btn_recut_{cid}", use_container_width=True):
            st.session_state[f"approval_{cid}"] = "recut"
            clip["approval_status"] = "recut"
            if session_id and session_id != "temp":
                db.set_approval_status(cid, session_id, "recut", current_notes)
            st.toast(f"⚠️ Promo {cid} flagged for re-cut", icon="✂️")
            st.rerun()

    with b_col4:
        if st.button("🔄 Reset to Pending", key=f"btn_reset_{cid}", use_container_width=True):
            st.session_state[f"approval_{cid}"] = "pending"
            clip["approval_status"] = "pending"
            if session_id and session_id != "temp":
                db.set_approval_status(cid, session_id, "pending", current_notes)
            st.toast(f"🔄 Promo {cid} reset to pending", icon="⏳")
            st.rerun()

    # Reviewer notes / feedback
    c_notes1, c_notes2 = st.columns([4, 1])
    with c_notes1:
        new_note = st.text_input(
            "Reviewer Creative Notes / Feedback (Optional):",
            value=current_notes,
            placeholder="e.g. Approved for TikTok & Instagram Reels; add dramatic audio swell at 00:20...",
            key=f"input_note_{cid}",
        )
    with c_notes2:
        st.write("") # vertical spacing
        if st.button("💾 Save Note", key=f"btn_save_note_{cid}", use_container_width=True):
            st.session_state[f"approval_notes_{cid}"] = new_note
            clip["approval_notes"] = new_note
            if session_id and session_id != "temp":
                db.set_approval_status(cid, session_id, current_status, new_note)
            st.toast("Feedback note saved successfully!", icon="💾")
            st.rerun()

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

    clip_labels = [
        f"#{idx} — {c['clip_id']} ({c.get('start_fmt')} → {c.get('end_fmt')}) — Score: {c.get('total_score', 0):.2f}"
        for idx, c in enumerate(ranked_clips, 1)
    ]
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
