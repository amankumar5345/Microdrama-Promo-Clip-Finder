"""
ui/charts.py
────────────
Plotly visualization charts: Drama timeline, multi-attribute score radar, and pacing distribution.
"""

import plotly.graph_objects as go
import streamlit as st


def render_drama_timeline(episode: dict, ranked_clips: list[dict]):
    """
    Render an interactive Plotly timeline showing script dialogue events
    and highlighted winning promo clip windows.
    """
    events = episode.get("events", [])
    if not events:
        return

    # Extract time points and text length / tone intensity proxy
    dialogue_events = [e for e in events if e.get("type") == "dialogue"]
    if not dialogue_events:
        return

    times = [e.get("start_s", 0.0) for e in dialogue_events]
    texts = [e.get("text", "")[:60] + "..." for e in dialogue_events]
    speakers = [e.get("speaker", "Character") for e in dialogue_events]
    tones = [e.get("tone") or "dialogue" for e in dialogue_events]

    # Create proxy tension score: 5 base + tone tag presence
    intensities = []
    for e in dialogue_events:
        t = (e.get("tone") or "").lower()
        val = 5.0
        if any(w in t for w in ["shock", "angry", "betray", "heartbroken", "crushed", "cold", "raw", "crying"]):
            val += 4.0
        elif t:
            val += 2.0
        if "?" in e.get("text", ""):
            val += 1.0
        intensities.append(val)

    fig = go.Figure()

    # Base dialogue tension scatter line
    fig.add_trace(go.Scatter(
        x=times,
        y=intensities,
        mode="lines+markers",
        name="Dialogue Drama Flow",
        line=dict(color="#6366F1", width=2.5),
        marker=dict(size=7, color="#A5B4FC"),
        hovertext=[f"<b>{sp}</b>: {tx}<br><i>Tone: {tn}</i>" for sp, tx, tn in zip(speakers, texts, tones)],
        hoverinfo="text",
    ))

    # Highlight winning promo windows
    colors = ["#10B981", "#F59E0B", "#EC4899", "#8B5CF6", "#06B6D4"]
    for idx, c in enumerate(ranked_clips):
        col = colors[idx % len(colors)]
        s = c.get("start_s", c.get("_start_s", 0.0))
        e = c.get("end_s", c.get("_end_s", 0.0))
        cid = c.get("clip_id", f"clip_{idx+1}")
        total = c.get("total_score", 0.0)

        fig.add_vrect(
            x0=s,
            x1=e,
            fillcolor=col,
            opacity=0.22,
            layer="below",
            line_width=1.5,
            line_color=col,
            annotation_text=f"#{idx+1} {cid} ({total:.1f})",
            annotation_position="top left",
            annotation_font=dict(color=col, size=11),
        )

    fig.update_layout(
        title="<b>Episode Drama Flow & Promo Clip Windows</b>",
        title_font=dict(size=16, color="#F8FAFC"),
        paper_bgcolor="#161922",
        plot_bgcolor="#0F172A",
        xaxis=dict(
            title="Timestamp (Seconds)",
            title_font=dict(color="#94A3B8"),
            tickfont=dict(color="#CBD5E1"),
            gridcolor="rgba(255, 255, 255, 0.06)",
        ),
        yaxis=dict(
            title="Dramatic Tension Index",
            title_font=dict(color="#94A3B8"),
            tickfont=dict(color="#CBD5E1"),
            gridcolor="rgba(255, 255, 255, 0.06)",
        ),
        height=320,
        margin=dict(l=40, r=40, t=50, b=40),
        legend=dict(font=dict(color="#E2E8F0")),
    )

    st.plotly_chart(fig, use_container_width=True)


def render_score_radar(ranked_clips: list[dict]):
    """
    Render comparative multi-attribute bar / radar chart for winning clips.
    """
    if not ranked_clips:
        return

    categories = ["Hook", "Cliffhanger", "Emotion", "Standalone"]
    fig = go.Figure()

    colors = ["#10B981", "#6366F1", "#F59E0B", "#EC4899", "#06B6D4"]
    for idx, c in enumerate(ranked_clips):
        cid = c.get("clip_id", f"Clip #{idx+1}")
        vals = [
            c.get("hook", 0.0),
            c.get("cliffhanger", 0.0),
            c.get("emotion", 0.0),
            c.get("standalone", 0.0),
        ]
        # Close radar loop
        vals.append(vals[0])
        cats = categories + [categories[0]]

        fig.add_trace(go.Scatterpolar(
            r=vals,
            theta=cats,
            fill="toself",
            name=f"#{idx+1} {cid} ({c.get('total_score', 0):.2f})",
            line=dict(color=colors[idx % len(colors)], width=2),
            opacity=0.6,
        ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 10], color="#94A3B8"),
            angularaxis=dict(color="#CBD5E1"),
            bgcolor="#0F172A",
        ),
        paper_bgcolor="#161922",
        title="<b>Multi-Attribute Scoring Radar</b>",
        title_font=dict(size=16, color="#F8FAFC"),
        height=340,
        margin=dict(l=40, r=40, t=50, b=40),
        legend=dict(font=dict(color="#CBD5E1")),
    )

    st.plotly_chart(fig, use_container_width=True)


def render_score_distribution(ranked_clips: list[dict]):
    """Render grouped bar chart showing score breakdown."""
    if not ranked_clips:
        return

    clip_ids = [c["clip_id"] for c in ranked_clips]
    hooks = [c.get("hook", 0) for c in ranked_clips]
    cliffs = [c.get("cliffhanger", 0) for c in ranked_clips]
    emotions = [c.get("emotion", 0) for c in ranked_clips]
    standalones = [c.get("standalone", 0) for c in ranked_clips]

    fig = go.Figure(data=[
        go.Bar(name="Hook", x=clip_ids, y=hooks, marker_color="#38BDF8"),
        go.Bar(name="Cliffhanger", x=clip_ids, y=cliffs, marker_color="#F472B6"),
        go.Bar(name="Emotion", x=clip_ids, y=emotions, marker_color="#A78BFA"),
        go.Bar(name="Standalone", x=clip_ids, y=standalones, marker_color="#34D399"),
    ])

    fig.update_layout(
        barmode="group",
        title="<b>Sub-Score Distribution Across Clips</b>",
        title_font=dict(size=16, color="#F8FAFC"),
        paper_bgcolor="#161922",
        plot_bgcolor="#0F172A",
        xaxis=dict(tickfont=dict(color="#CBD5E1")),
        yaxis=dict(range=[0, 10.5], tickfont=dict(color="#CBD5E1")),
        height=300,
        margin=dict(l=40, r=40, t=50, b=40),
        legend=dict(font=dict(color="#CBD5E1")),
    )

    st.plotly_chart(fig, use_container_width=True)
