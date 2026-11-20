"""UI package."""
from ui.styles import inject_custom_styles
from ui.components import (
    render_hero_header,
    render_metric_cards,
    render_clip_card,
    render_empty_state,
    render_social_and_blind_details,
)
from ui.charts import (
    render_drama_timeline,
    render_score_radar,
    render_score_distribution,
    render_character_share,
    render_tone_frequency,
    render_pacing_scatter,
)
from ui.editor import render_clip_editor, render_clip_comparison
from ui.history_sidebar import render_history_sidebar
from ui.chat import render_script_chat

__all__ = [
    "inject_custom_styles",
    "render_hero_header",
    "render_metric_cards",
    "render_clip_card",
    "render_empty_state",
    "render_social_and_blind_details",
    "render_drama_timeline",
    "render_score_radar",
    "render_score_distribution",
    "render_character_share",
    "render_tone_frequency",
    "render_pacing_scatter",
    "render_clip_editor",
    "render_clip_comparison",
    "render_history_sidebar",
    "render_script_chat",
]
