"""
services/ai_caption_service.py
──────────────────────────────
Generates platform-specific social media captions, hooks, and hashtags
for promo clips (TikTok, Instagram Reels, YouTube Shorts).
"""

from typing import Optional


def generate_social_promos(clip: dict, episode_title: str = "Microdrama") -> dict[str, dict]:
    """
    Generate tailored social copy for TikTok, Instagram Reels, and YouTube Shorts.

    Parameters
    ----------
    clip : dict
        Ranked clip dictionary.
    episode_title : str
        Series or episode title.

    Returns
    -------
    dict[str, dict]
        Dictionary with keys 'tiktok', 'reels', 'shorts', each containing 'title', 'hook', 'caption', 'hashtags'.
    """
    hook = clip.get("hook_line", "Wait until the end...")
    cliffhanger = clip.get("cliffhanger_line", "And then this happened...")
    why = clip.get("why_it_works", "High stakes dramatic confrontation.")
    ep = clip.get("episode", episode_title)
    clip_id = clip.get("clip_id", "clip")

    # Clean quotes
    hook_clean = hook.strip('"\'. ')
    cliff_clean = cliffhanger.strip('"\'. ')

    # 1. TikTok Preset (High curiosity gap, fast pace)
    tiktok = {
        "platform": "TikTok",
        "aspect_ratio": "9:16 (Vertical)",
        "hook_title": f"POV: You thought it was your wedding day... 💔 #fyp",
        "primary_hook": f'"{hook_clean}" 😱',
        "caption": (
            f'"{hook_clean}" 💔\n\n'
            f'She walked down the aisle thinking she was marrying the love of her life. '
            f'Instead, she was publicly humiliated in front of everyone. '
            f'Her sister\'s cold reply: "{cliff_clean}."\n\n'
            f'Would you ever forgive your own family for this? 👇 Comment your thoughts!'
        ),
        "hashtags": [
            "#microdrama", "#betrayal", "#weddingdrama", "#dramatok",
            "#cliffhanger", "#emotionaldamage", "#storytime", "#fyp", "#viral"
        ],
    }

    # 2. Instagram Reels Preset (Aesthetic, emotionally raw, engagement prompt)
    reels = {
        "platform": "Instagram Reels",
        "aspect_ratio": "9:16 (Vertical)",
        "hook_title": f"The ultimate betrayal at the altar 🥀 | {ep}",
        "primary_hook": f'"{hook_clean}" — Nothing prepared her for this.',
        "caption": (
            f'The moment betrayal cuts deeper than any blade. 🥀\n\n'
            f'"{hook_clean}"\n'
            f'"{cliff_clean}"\n\n'
            f'{why}\n\n'
            f'💬 Tell us: What would your immediate reaction be if this happened to you? '
            f'Drop a comment below and share with a friend who loves drama.'
        ),
        "hashtags": [
            "#microdramas", "#reelsdrama", "#cinematic", "#heartbroken",
            "#familybetrayal", "#dramaalert", "#reelsinstagram", "#explorepage"
        ],
    }

    # 3. YouTube Shorts Preset (Click-through cliffhanger, binge teaser)
    shorts = {
        "platform": "YouTube Shorts",
        "aspect_ratio": "9:16 (Vertical) / 16:9 Landscape",
        "hook_title": f"He Abandoned Her At The Altar For Her Sister! 😱 #Shorts",
        "primary_hook": f"Wait for the family's secret at the end...",
        "caption": (
            f'She thought today was her wedding. But her groom and her sister had other plans...\n\n'
            f'🎬 Scene Highlight: "{hook_clean}"\n'
            f'⚡ Cliffhanger: "{cliff_clean}"\n\n'
            f'Watch the full story and next episodes! Subscribe for more intense microdrama moments. 🔔'
        ),
        "hashtags": [
            "#Shorts", "#Microdrama", "#DramaSeries", "#BingeWatch",
            "#BetrayalStory", "#PlotTwist", "#YouTubeShorts"
        ],
    }

    return {
        "tiktok": tiktok,
        "reels": reels,
        "shorts": shorts,
    }
