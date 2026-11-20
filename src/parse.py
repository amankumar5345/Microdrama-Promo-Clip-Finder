"""
src/parse.py
────────────
Parse a microdrama screenplay .txt into a structured episode dict.

Supports ALL common timestamp/block formats found in real datasets:
  1. Standard: Start: (mm:ss.ss) | End: (mm:ss.ss)
  2. Square bracket: Start: [mm:ss.ss] | End: [mm:ss.ss]
  3. Arrow SRT:  00:01:13.500 --> 00:01:14.300
  4. Range:      [mm:ss.ss - mm:ss.ss]  or  [mm:ss.ss -> mm:ss.ss]
  5. Inline:     [mm:ss.ss] SPEAKER: dialogue text
  6. No timestamps: auto-heals by synthesising timestamps from word count

Public API
──────────
    from src.parse import parse_screenplay

    ep = parse_screenplay("data/episode1.txt")
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

# Format 1 & 2: Start: (00:13.50) | End: (00:14.30)  or  Start: [00:13.50] | End: [00:14.30]
_RE_TS = re.compile(
    r"Start\s*:\s*[\(\[](?P<s>[\d:.,]+)[\)\]]"
    r"\s*\|\s*"
    r"End\s*:\s*[\(\[](?P<e>[\d:.,]+)[\)\]]",
    re.I,
)

# Format 3: SRT arrow  00:01:13.500 --> 00:01:14.300
_RE_TS_ARROW = re.compile(
    r"(?P<s>\d{1,2}:\d{2}:\d{2}[.,]\d+)\s*-->\s*(?P<e>\d{1,2}:\d{2}:\d{2}[.,]\d+)"
)

# Format 4: [mm:ss.ss - mm:ss.ss] or [mm:ss.ss -> mm:ss.ss]
_RE_TS_RANGE = re.compile(
    r"\[(?P<s>[\d:.,]+)\s*(?:->|-)\s*(?P<e>[\d:.,]+)\]"
)

# Format 5: Inline timestamp at start  [mm:ss.ss] SPEAKER: text
_RE_INLINE_TS = re.compile(
    r"^\[(?P<ts>[\d:.,]+)\]\s*(?P<rest>.+)$"
)

# Block header: **ANYTHING:**  or  **ANYTHING**:  or plain SPEAKER:
_RE_BLOCK_HDR_BOLD = re.compile(r"^\*\*(.+?)(?::\s*\*\*|\*\*\s*:)\s*$")
_RE_BLOCK_HDR_PLAIN = re.compile(r"^([A-Z][A-Z\s\(\)\.]+?):\s*$")

# Speaker header parser
_RE_SPEAKER = re.compile(
    r"^(?P<name>.+?)"
    r"(?:\s+\(O\.S\.\))?"
    r"(?:\s+\((?P<tone>[^)]+)\))?"
    r"\s*$",
    re.I,
)

_FIXED_TYPES = {"CAMERA", "ACTION", "SOUND FX", "SOUND"}


# ── Time helpers ──────────────────────────────────────────────────────────────

def _to_seconds(ts: str) -> float:
    """
    Convert timestamp string to float seconds.
    Handles: hh:mm:ss.sss  mm:ss.ss  ss.ss  with comma or period
    """
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    try:
        if len(parts) == 3:
            # hh:mm:ss.sss
            return round(float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2]), 3)
        elif len(parts) == 2:
            # mm:ss.ss
            return round(float(parts[0]) * 60 + float(parts[1]), 3)
        else:
            return round(float(parts[0]), 3)
    except (ValueError, IndexError):
        return 0.0


def _words_to_seconds(text: str, wpm: float = 150.0) -> float:
    """Estimate reading duration from word count."""
    return max(1.0, len(text.split()) / wpm * 60.0)


# ── Block header parser ───────────────────────────────────────────────────────

def _parse_block_header(inner: str) -> dict:
    """
    Given the content of a block header line, return block type and speaker info.
    """
    upper = inner.strip().upper()

    if upper == "CAMERA":
        return {"block_type": "camera", "speaker": None, "tone": None, "offscreen": False}
    if upper == "ACTION":
        return {"block_type": "action", "speaker": None, "tone": None, "offscreen": False}
    if upper in ("SOUND FX", "SOUND"):
        return {"block_type": "sound", "speaker": None, "tone": None, "offscreen": False}

    # Speaker line
    offscreen = bool(re.search(r"\(O\.S\.\)", inner, re.I))
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
    Robust to all common timestamp formats and auto-heals missing timestamps.
    """
    path = Path(path)
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

    # Auto-fill missing metadata
    if not ep["episode_number"]:
        # Try to extract from filename
        fn_match = re.search(r"episode[-_\s]*(\d+)", path.stem, re.I)
        ep["episode_number"] = f"Episode {fn_match.group(1)}" if fn_match else "Episode 1"
    if not ep["logline"]:
        ep["logline"] = f"Microdrama episode: {path.stem}"
    if not ep["continuity_notes"]:
        ep["continuity_notes"] = "N/A"

    # ── Pass 2: body — build events ───────────────────────────────────────
    current_scene  = "SCENE 00"
    cur_hdr: dict | None = None
    cur_ts_start: float | None = None
    cur_ts_end:   float | None = None
    cur_text_lines: list[str]  = []
    cur_lineno = 0
    last_end_s = 0.0   # for auto-healing timestamp synthesis

    def flush(lineno: int):
        """Commit the buffered block as an event."""
        nonlocal cur_hdr, cur_ts_start, cur_ts_end, cur_text_lines, cur_lineno, last_end_s
        if cur_hdr is None:
            return

        raw_text = " ".join(cur_text_lines).strip()

        if not raw_text:
            cur_hdr = None; cur_ts_start = None; cur_ts_end = None
            cur_text_lines = []
            return

        # Auto-heal missing timestamps
        if cur_ts_start is None or cur_ts_end is None:
            estimated_dur = _words_to_seconds(raw_text)
            cur_ts_start = last_end_s
            cur_ts_end = last_end_s + estimated_dur
            warn(cur_lineno, f"Missing timestamp in {cur_hdr['block_type']} block — auto-synthesised [{cur_ts_start:.2f}s → {cur_ts_end:.2f}s]")

        if cur_ts_end <= cur_ts_start:
            cur_ts_end = cur_ts_start + max(1.0, _words_to_seconds(raw_text))

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
        last_end_s = cur_ts_end

        cur_hdr = None; cur_ts_start = None; cur_ts_end = None
        cur_text_lines = []

    for i, ln in enumerate(lines[body_start:], start=body_start + 1):
        s = ln.strip()

        # Script-end marker
        if _RE_SCREND.match(s):
            break

        if not s:
            continue
        if _RE_SCENE_HDG.match(s) or _RE_SCENE_S.match(s) or _RE_SCENE_E.match(s):
            continue
        if _RE_NOISE.match(s):
            continue

        # Scene ID line
        if m := _RE_SCENE_ID.match(s):
            flush(i)
            current_scene = m.group(1).upper()
            continue

        # Try SRT arrow timestamp
        if m := _RE_TS_ARROW.search(s):
            cur_ts_start = _to_seconds(m.group("s"))
            cur_ts_end   = _to_seconds(m.group("e"))
            continue

        # Try range timestamp [mm:ss - mm:ss]
        if m := _RE_TS_RANGE.search(s):
            cur_ts_start = _to_seconds(m.group("s"))
            cur_ts_end   = _to_seconds(m.group("e"))
            continue

        # Try standard timestamp format
        if m := _RE_TS.search(s):
            cur_ts_start = _to_seconds(m.group("s"))
            cur_ts_end   = _to_seconds(m.group("e"))
            continue

        # Try inline timestamp: [mm:ss.ss] SPEAKER: text
        if m := _RE_INLINE_TS.match(s):
            ts_val = _to_seconds(m.group("ts"))
            rest = m.group("rest").strip()
            # Try to parse as "SPEAKER: dialogue"
            colon_idx = rest.find(":")
            if colon_idx > 0:
                flush(i)
                speaker_raw = rest[:colon_idx].strip()
                text_raw = rest[colon_idx + 1:].strip()
                cur_hdr = _parse_block_header(speaker_raw)
                cur_ts_start = ts_val
                cur_ts_end   = ts_val + _words_to_seconds(text_raw)
                cur_lineno = i
                if text_raw:
                    cur_text_lines.append(text_raw)
                flush(i)
            else:
                # It's a standalone timestamp marker
                cur_ts_start = ts_val
                cur_ts_end   = ts_val + 2.0
            continue

        # Bold block header: **ANYTHING:**  or  **ANYTHING**:
        if m := _RE_BLOCK_HDR_BOLD.match(s):
            flush(i)
            inner   = m.group(1)
            cur_hdr = _parse_block_header(inner)
            cur_lineno = i
            continue

        # Plain uppercase block header: SPEAKER NAME (Tone):
        if m := _RE_BLOCK_HDR_PLAIN.match(s):
            candidate_inner = m.group(1).strip()
            # Only treat as header if it looks like a speaker name (not prose)
            upper_c = candidate_inner.upper()
            if (upper_c in _FIXED_TYPES or
                    (len(candidate_inner.split()) <= 5 and candidate_inner.isupper())):
                flush(i)
                cur_hdr = _parse_block_header(candidate_inner)
                cur_lineno = i
                continue

        # Quoted line with no block header = treat as dialogue
        if cur_hdr is None and (s.startswith('"') or s.startswith('\u201c')):
            text_clean = s.strip('""\u201c\u201d').strip()
            if text_clean:
                # Create anonymous dialogue event
                flush(i)
                cur_hdr = {"block_type": "dialogue", "speaker": "NARRATOR", "tone": None, "offscreen": False}
                cur_lineno = i
                cur_text_lines.append(text_clean)
            continue

        # Text content of current block
        if cur_hdr is not None:
            cur_text_lines.append(s)

    # Flush last block
    flush(len(lines))

    # ── Auto-heal: if zero events found, try to parse as plain dialogue ───
    if not ep["events"]:
        warn(0, "No structured events found — attempting plain-text dialogue parse")
        t = last_end_s
        for ln in lines[body_start:]:
            s = ln.strip()
            if not s or _RE_SCREND.match(s):
                continue
            # Try "SPEAKER: text" pattern
            m = re.match(r"^([A-Z][A-Z\s]{1,30}):\s*(.+)$", s)
            if m:
                spk = m.group(1).strip()
                txt = m.group(2).strip()
                dur = _words_to_seconds(txt)
                ep["events"].append({
                    "type": "dialogue", "speaker": spk, "tone": None,
                    "offscreen": False, "text": txt,
                    "start_s": round(t, 3), "end_s": round(t + dur, 3),
                    "scene": "SCENE 01",
                })
                t += dur
            elif len(s) > 10:
                dur = _words_to_seconds(s)
                ep["events"].append({
                    "type": "action", "speaker": None, "tone": None,
                    "offscreen": False, "text": s,
                    "start_s": round(t, 3), "end_s": round(t + dur, 3),
                    "scene": "SCENE 01",
                })
                t += dur

    # ── Auto-heal: if all timestamps are 0, synthesise progressive ones ───
    if ep["events"] and all(e["start_s"] == 0.0 and e["end_s"] == 0.0 for e in ep["events"]):
        warn(0, "All timestamps are zero — synthesising progressive timestamps")
        t = 0.0
        for ev in ep["events"]:
            dur = _words_to_seconds(ev.get("text", ""))
            ev["start_s"] = round(t, 3)
            ev["end_s"] = round(t + dur, 3)
            t += dur

    n_events = len(ep["events"])
    n_warn   = len(ep["warnings"])
    logger.info(
        "[%s] %s — %d events parsed, %d warnings",
        path.name, ep["episode_number"], n_events, n_warn,
    )
    return ep
