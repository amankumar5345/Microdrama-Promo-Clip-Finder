"""
src/parse.py
────────────
Parse a microdrama screenplay .txt into a structured episode dict.

Public API
──────────
    from src.parse import parse_screenplay

    ep = parse_screenplay("data/episode1.txt")
    # ep = {
    #   "episode_number": "Episode 1",
    #   "logline": "...",
    #   "continuity_notes": "...",
    #   "source_file": "episode1.txt",
    #   "events": [
    #     {
    #       "type":    "dialogue" | "action" | "camera" | "sound",
    #       "speaker": "LADY JULIANA" | None,
    #       "tone":    "Heartbroken" | None,
    #       "offscreen": True | False,
    #       "text":    "...",
    #       "start_s": 13.5,   # seconds (float)
    #       "end_s":   15.0,
    #       "scene":   "SCENE 01",
    #     },
    #     ...
    #   ],
    #   "warnings": ["line 42: end_s <= start_s …", …],
    # }

Real format (from dataset):
  Header lines before "--- SCRIPT START ---":
    EPISODE NUMBER: Episode 1
    EPISODE LOGLINE: …
    CONTINUITY NOTES: …

  Scene blocks:
    SCENE 01
    Scene heading: INT. CATHEDRAL – DAY
    Scene start: 00:00.00
    Scene end:   02:18.00
    Actions and dialogue:        ← noise line, skip

  Block pattern (bold-starred header, then timestamp, then text):
    **CAMERA:**
    **ACTION:**
    **SOUND FX:**
    **SPEAKER NAME (Tone):**
    **SPEAKER NAME (O.S.) (Tone):**

    Start: (00:13.50) | End: (00:14.30)
    "dialogue text" or plain description text

  Timestamps are ABSOLUTE (episode-wide; they do NOT reset per scene).
  Format: mm:ss.ss  (minutes : seconds.centiseconds)
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Regex patterns ────────────────────────────────────────────────────────────

_RE_EP_NUM    = re.compile(r"EPISODE\s+NUMBER\s*:\s*(.+)", re.I)
_RE_LOGLINE   = re.compile(r"EPISODE\s+LOGLINE\s*:\s*(.+)", re.I)
_RE_CONT      = re.compile(r"CONTINUITY\s+NOTES\s*:\s*(.+)", re.I)
_RE_SCRSTART  = re.compile(r"---\s*SCRIPT\s+START\s*---", re.I)
_RE_SCREND    = re.compile(r"---\s*SCRIPT\s+END\s*---", re.I)

_RE_SCENE_ID  = re.compile(r"^(SCENE\s+\d+)\s*$", re.I)
_RE_SCENE_HDG = re.compile(r"Scene\s+heading\s*:", re.I)
_RE_SCENE_S   = re.compile(r"Scene\s+start\s*:", re.I)
_RE_SCENE_E   = re.compile(r"Scene\s+end\s*:", re.I)
_RE_NOISE     = re.compile(r"Actions\s+and\s+dialogue\s*:", re.I)

# Timestamp line:  Start: (00:13.50) | End: (00:14.30)
_RE_TS = re.compile(
    r"Start\s*:\s*\((?P<s>\d+:\d+(?:\.\d+)?)\)"
    r"\s*\|\s*"
    r"End\s*:\s*\((?P<e>\d+:\d+(?:\.\d+)?)\)",
    re.I,
)

# Block header:  **ANYTHING:**
# After stripping the outer **, the content can be:
#   CAMERA
#   ACTION
#   SOUND FX
#   SPEAKER NAME (O.S.) (Tone)
#   SPEAKER NAME (Tone)
#   SPEAKER NAME            ← tone sometimes absent
_RE_BLOCK_HDR = re.compile(r"^\*\*(.+?):\s*\*\*\s*$")

# Speaker header parser  (applied to the inner text after stripping **)
# Captures optional (O.S.) and optional (Tone)
_RE_SPEAKER = re.compile(
    r"^(?P<name>.+?)"
    r"(?:\s+\(O\.S\.\))?"
    r"(?:\s+\((?P<tone>[^)]+)\))?"
    r"\s*$",
    re.I,
)

_FIXED_TYPES = {"CAMERA", "ACTION", "SOUND FX"}


# ── Time helpers ──────────────────────────────────────────────────────────────

def _to_seconds(ts: str) -> float:
    """
    Convert timestamp string to float seconds.
    Handles: mm:ss.ss  mm:ss.s  mm:ss
    """
    parts = ts.split(":")
    minutes = float(parts[0])
    seconds = float(parts[1])
    return round(minutes * 60 + seconds, 3)


# ── Block header parser ───────────────────────────────────────────────────────

def _parse_block_header(inner: str) -> dict:
    """
    Given the text between the outer ** markers (minus trailing colon),
    return {"block_type", "speaker", "tone", "offscreen"}.

    block_type ∈ {"camera", "action", "sound", "dialogue"}
    """
    upper = inner.strip().upper()

    if upper == "CAMERA":
        return {"block_type": "camera", "speaker": None, "tone": None, "offscreen": False}
    if upper == "ACTION":
        return {"block_type": "action", "speaker": None, "tone": None, "offscreen": False}
    if upper in ("SOUND FX", "SOUND"):
        return {"block_type": "sound",  "speaker": None, "tone": None, "offscreen": False}

    # Speaker line
    offscreen = bool(re.search(r"\(O\.S\.\)", inner, re.I))
    # Remove (O.S.) before parsing tone
    inner_clean = re.sub(r"\s*\(O\.S\.\)", "", inner, flags=re.I).strip()

    m = _RE_SPEAKER.match(inner_clean)
    if m:
        name = m.group("name").strip().upper()
        tone = m.group("tone").strip() if m.group("tone") else None
    else:
        name = inner_clean.upper()
        tone = None

    return {"block_type": "dialogue", "speaker": name, "tone": tone, "offscreen": offscreen}


# ── Main parser ───────────────────────────────────────────────────────────────

def parse_screenplay(path: str | Path) -> dict:
    """
    Parse a screenplay .txt file and return a structured episode dict.

    Parameters
    ----------
    path : str | Path  Path to the .txt file.

    Returns
    -------
    dict  with keys: episode_number, logline, continuity_notes,
                     source_file, events, warnings
    """
    path  = Path(path)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    ep = {
        "episode_number":   "",
        "logline":          "",
        "continuity_notes": "",
        "source_file":      path.name,
        "events":           [],
        "warnings":         [],
    }

    def warn(lineno: int, msg: str):
        w = f"line {lineno}: {msg}"
        logger.warning("[%s] %s", path.name, w)
        ep["warnings"].append(w)

    # ── Pass 1: header ────────────────────────────────────────────────────
    body_start = 0
    for i, ln in enumerate(lines):
        s = ln.strip()
        if m := _RE_EP_NUM.match(s):
            ep["episode_number"] = m.group(1).strip()
        elif m := _RE_LOGLINE.match(s):
            ep["logline"] = m.group(1).strip()
        elif m := _RE_CONT.match(s):
            ep["continuity_notes"] = m.group(1).strip()
        elif _RE_SCRSTART.match(s):
            body_start = i + 1
            break

    # ── Pass 2: body — build events ───────────────────────────────────────
    current_scene  = "SCENE 00"   # fallback if no SCENE header found first
    cur_hdr: dict | None = None   # parsed block header info
    cur_ts_start: float | None = None
    cur_ts_end:   float | None = None
    cur_text_lines: list[str]  = []
    cur_lineno = 0

    def flush(lineno: int):
        """Commit the buffered block as an event."""
        nonlocal cur_hdr, cur_ts_start, cur_ts_end, cur_text_lines, cur_lineno
        if cur_hdr is None:
            return

        raw_text = " ".join(cur_text_lines).strip()

        # ── Sanity checks ──────────────────────────────────────────────
        if not raw_text:
            warn(cur_lineno, f"empty text in {cur_hdr['block_type']} block "
                             f"({current_scene})")

        if cur_ts_start is None or cur_ts_end is None:
            warn(cur_lineno, f"missing timestamp in {cur_hdr['block_type']} block "
                             f"({current_scene}) — skipping event")
            cur_hdr = None; cur_ts_start = None; cur_ts_end = None
            cur_text_lines = []
            return

        if cur_ts_end <= cur_ts_start:
            warn(cur_lineno,
                 f"end_s ({cur_ts_end}) <= start_s ({cur_ts_start}) "
                 f"in {cur_hdr['block_type']} block ({current_scene})")

        event = {
            "type":      cur_hdr["block_type"],
            "speaker":   cur_hdr["speaker"],
            "tone":      cur_hdr["tone"],
            "offscreen": cur_hdr["offscreen"],
            "text":      raw_text,
            "start_s":   cur_ts_start,
            "end_s":     cur_ts_end,
            "scene":     current_scene,
        }
        ep["events"].append(event)

        cur_hdr = None; cur_ts_start = None; cur_ts_end = None
        cur_text_lines = []

    for i, ln in enumerate(lines[body_start:], start=body_start + 1):
        s = ln.strip()

        # Script-end marker
        if _RE_SCREND.match(s):
            break

        # Skip blank lines, scene metadata noise
        if not s:
            continue
        if _RE_SCENE_HDG.match(s) or _RE_SCENE_S.match(s) or _RE_SCENE_E.match(s):
            continue
        if _RE_NOISE.match(s):
            continue

        # Scene ID line  →  flush current block, update scene
        if m := _RE_SCENE_ID.match(s):
            flush(i)
            current_scene = m.group(1).upper()
            continue

        # Block header line  **…:**
        if m := _RE_BLOCK_HDR.match(s):
            flush(i)
            inner    = m.group(1)   # text between ** and :**
            cur_hdr  = _parse_block_header(inner)
            cur_lineno = i
            continue

        # Timestamp line
        if m := _RE_TS.search(s):
            cur_ts_start = _to_seconds(m.group("s"))
            cur_ts_end   = _to_seconds(m.group("e"))
            continue

        # Anything else inside a block = text content
        if cur_hdr is not None:
            cur_text_lines.append(s)

    # Flush last block
    flush(len(lines))

    # ── Summary log ───────────────────────────────────────────────────────
    n_events = len(ep["events"])
    n_warn   = len(ep["warnings"])
    logger.info(
        "[%s] %s — %d events parsed, %d warnings",
        path.name, ep["episode_number"], n_events, n_warn,
    )
    return ep
