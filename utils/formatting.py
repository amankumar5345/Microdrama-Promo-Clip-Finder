"""
utils/formatting.py
───────────────────
Formatting and HTML badge helper functions for promo clips.
"""

from typing import Union


def fmt_seconds(secs: Union[int, float]) -> str:
    """Format float seconds to 'mm:ss.s' string."""
    m = int(secs) // 60
    s = secs % 60
    return f"{m:02d}:{s:05.2f}"


def score_color(score: float) -> str:
    """Return hex color corresponding to score range."""
    if score >= 9.0:
        return "#10B981"  # Emerald green
    elif score >= 8.0:
        return "#3B82F6"  # Royal blue
    elif score >= 7.0:
        return "#F59E0B"  # Amber
    else:
        return "#EF4444"  # Red


def score_badge_html(score: float, label: str = "") -> str:
    """Generate inline HTML badge for a score."""
    color = score_color(score)
    prefix = f"{label}: " if label else ""
    return (
        f'<span style="background-color: {color}20; color: {color}; '
        f'border: 1px solid {color}50; padding: 2px 8px; border-radius: 9999px; '
        f'font-size: 0.82rem; font-weight: 600;">{prefix}{score:.1f}/10</span>'
    )


def tag_badge_html(tag: str, color_scheme: str = "indigo") -> str:
    """Generate inline tag badge."""
    schemes = {
        "indigo": ("#6366F120", "#818CF8", "#6366F150"),
        "cyan": ("#06B6D420", "#22D3EE", "#06B6D450"),
        "purple": ("#A855F720", "#C084FC", "#A855F750"),
        "rose": ("#F43F5E20", "#FB7185", "#F43F5E50"),
    }
    bg, fg, border = schemes.get(color_scheme, schemes["indigo"])
    return (
        f'<span style="background-color: {bg}; color: {fg}; '
        f'border: 1px solid {border}; padding: 2px 8px; border-radius: 6px; '
        f'font-size: 0.75rem; font-weight: 500; margin-right: 4px;">{tag}</span>'
    )
