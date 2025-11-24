#!/usr/bin/env python3
"""
Generate an HTML chapter report for a chapterized MP3.

Usage:
    python chapter_report.py input.mp3 [output.html]

If output.html is omitted, it will be derived from the input filename.
"""

import sys
import base64
import imghdr
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from mutagen import File as MutagenFile
from mutagen.id3 import (
    ID3,
    ID3NoHeaderError,
    APIC,
    CHAP,
    CTOC,
    CTOCFlags,
    TIT2,
)


# ---------------- helpers ---------------- #

def format_ms(ms: int) -> str:
    """Format milliseconds as H:MM:SS or M:SS."""
    total_seconds = int(round(ms / 1000.0))
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    else:
        return f"{m:d}:{s:02d}"


def get_audio_info(path: Path) -> Dict[str, Optional[str]]:
    audio = MutagenFile(path)
    if audio is None or not hasattr(audio, "info") or audio.info is None:
        return {
            "class": audio.__class__.__name__ if audio else "Unknown",
            "length": None,
            "bitrate": None,
            "sample_rate": None,
            "channels": None,
        }

    info = audio.info
    length = getattr(info, "length", None)
    bitrate = getattr(info, "bitrate", None)
    sample_rate = getattr(info, "sample_rate", None)
    channels = getattr(info, "channels", None)

    return {
        "class": audio.__class__.__name__,
        "length": length,
        "bitrate": bitrate,
        "sample_rate": sample_rate,
        "channels": channels,
    }


def load_id3(path: Path) -> Optional[ID3]:
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        return None
    return tags


def pick_top_level_ctoc(ctocs: List[CTOC]) -> Optional[CTOC]:
    """Pick a top-level CTOC frame, if any."""
    if not ctocs:
        return None
    # Prefer element_id == 'TOC' with TOP_LEVEL
    best = None
    for ctoc in ctocs:
        flags = getattr(ctoc, "flags", 0)
        is_top = bool(flags & CTOCFlags.TOP_LEVEL)
        if ctoc.element_id == "TOC" and is_top:
            return ctoc
        if is_top and best is None:
            best = ctoc
    if best is not None:
        return best
    # Fallback: first CTOC
    return ctocs[0]


def get_chapter_order(tags: ID3) -> List[CHAP]:
    """Return CHAP frames in CTOC order if possible, else tag order."""
    chaps = tags.getall("CHAP")
    if not chaps:
        return []

    ctocs = tags.getall("CTOC")
    ctoc = pick_top_level_ctoc(ctocs)
    if not ctoc:
        # No CTOC or no usable one; fall back to tag order.
        return chaps

    chap_by_id = {chap.element_id: chap for chap in chaps}
    ordered: List[CHAP] = []
    for cid in ctoc.child_element_ids:
        chap = chap_by_id.get(cid)
        if chap:
            ordered.append(chap)

    # If something went wrong, fall back to all CHAPs.
    if not ordered:
        return chaps

    return ordered


def get_chap_title(chap: CHAP) -> str:
    """Get chapter title from TIT2 subframe, or fall back to element_id."""
    sub_frames = chap.sub_frames
    if "TIT2" in sub_frames:
        sf = sub_frames["TIT2"]
        frames = sf if isinstance(sf, list) else [sf]
        for f in frames:
            if isinstance(f, TIT2) and f.text:
                return str(f.text[0])
    return chap.element_id

def get_chap_apic(chap: CHAP) -> Optional[Tuple[bytes, str]]:
    """
    Get per-chapter APIC data+mime from CHAP subframes, if any.

    Note: sub_frames keys are often like 'APIC:' (ID + description),
    so we can't just look up "APIC" by key. We need to inspect the
    frame objects themselves.
    """
    sub_frames = chap.sub_frames

    for key, value in sub_frames.items():
        # Each value can be a single frame or a list of frames
        frames = value if isinstance(value, list) else [value]
        for f in frames:
            if isinstance(f, APIC):
                data = f.data
                mime = f.mime or "image/jpeg"
                return data, mime

    return None


def get_file_apic(tags: ID3) -> Optional[Tuple[bytes, str]]:
    """
    Get file-level (album art) APIC from ID3 tags, not from chapters.
    Returns the first APIC found that's not inside a CHAP frame.
    """
    apics = tags.getall("APIC")
    for apic in apics:
        if isinstance(apic, APIC):
            data = apic.data
            mime = apic.mime or "image/jpeg"
            return data, mime
    return None

def image_data_uri(data: bytes, mime_hint: Optional[str]) -> str:
    """Build a data: URI from raw image bytes."""
    mime = mime_hint or "image/jpeg"
    # If mime is generic or missing, try sniffing
    if mime in ("application/octet-stream", None, ""):
        kind = imghdr.what(None, h=data)
        if kind == "png":
            mime = "image/png"
        else:
            mime = "image/jpeg"
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def is_nil_offset(value: Optional[int]) -> bool:
    """
    Detect if an offset value looks like a bogus sentinel value.
    E.g., 0xFFFFFFFF or values very close to that (0xFFFFFF00+).
    Returns True if the offset is corrupted/invalid.
    """
    if value is None:
        return False
    NIL_OFFSET_THRESHOLD = 0xFFFFFF00  # 4294967040
    return value >= NIL_OFFSET_THRESHOLD


# ---------------- HTML report generation ---------------- #

def generate_html_report(
    input_path: Path,
    audio_info: Dict[str, Optional[str]],
    tags: Optional[ID3],
) -> str:
    title = f"Chapter Report – {input_path.name}"

    # Basic audio summary
    length_str = None
    if audio_info["length"] is not None:
        length_str = format_ms(int(round(audio_info["length"] * 1000)))

    bitrate_str = None
    if audio_info["bitrate"] is not None:
        kbps = int(round(audio_info["bitrate"] / 1000))
        bitrate_str = f"{kbps} kbps"

    # ID3 summary
    id3_version = None
    frame_counts: Dict[str, int] = {}
    ctoc_summary = ""
    chapters_html = ""
    warnings_html = ""

    if tags is None:
        warnings_html += "<p class='warn'>No ID3 tag found in this file.</p>\n"
    else:
        id3_version = tags.version

        # Frame counts
        for key in tags.keys():
            fid = key[:4]
            frame_counts[fid] = frame_counts.get(fid, 0) + 1

        # CTOC summary
        ctocs = tags.getall("CTOC")
        if not ctocs:
            ctoc_summary = "<p>No CTOC frames present.</p>"
        else:
            ct = pick_top_level_ctoc(ctocs)
            if ct is None:
                ctoc_summary = f"<p>{len(ctocs)} CTOC frame(s), but none marked top-level.</p>"
            else:
                flags = getattr(ct, "flags", 0)
                is_top = bool(flags & CTOCFlags.TOP_LEVEL)
                is_ord = bool(flags & CTOCFlags.ORDERED)
                ctoc_summary = (
                    "<p>"
                    f"Using CTOC element_id <code>{ct.element_id}</code>; "
                    f"flags: {'TOP_LEVEL ' if is_top else ''}"
                    f"{'ORDERED' if is_ord else ''}. "
                    f"{len(ct.child_element_ids)} child chapter IDs."
                    "</p>"
                )

        # Chapters
        ordered_chaps = get_chapter_order(tags)
        if not ordered_chaps:
            warnings_html += "<p class='warn'>No CHAP (chapter) frames found.</p>\n"
        else:
            # Get file-level image for fallback
            file_apic = get_file_apic(tags)

            # Build chapter list
            rows = []
            for idx, chap in enumerate(ordered_chaps):
                chap_title = get_chap_title(chap)
                start_ms = chap.start_time
                end_ms = chap.end_time
                dur_ms = max(0, end_ms - start_ms)

                start_str = format_ms(start_ms)
                end_str = format_ms(end_ms)
                dur_str = format_ms(dur_ms)

                # Check for bad offsets
                has_bad_offset = is_nil_offset(chap.start_offset) or is_nil_offset(chap.end_offset)

                apic = get_chap_apic(chap)

                # Image display logic:
                # 1. Good pointers + chapter art: show chapter art normally
                # 2. Bad pointers + chapter art: show chapter art but marked as corrupted
                # 3. Bad pointers + no chapter art: show default file art (if available) with note
                # 4. Otherwise: show "No art"
                if apic is not None:
                    data_uri = image_data_uri(apic[0], apic[1])
                    if has_bad_offset:
                        # Bad offsets + has image: show image but mark as hidden
                        img_html = f"<div class='corrupted-art'><img src='{data_uri}' alt='Chapter art (corrupted)' class='thumb' /><p class='art-note'>Image data present but offsets corrupted</p></div>"
                    else:
                        # Good offsets: show normally
                        img_html = f"<img src='{data_uri}' alt='Chapter art' class='thumb' />"
                elif has_bad_offset and file_apic is not None:
                    # Bad offsets + no chapter art + file art available: show file art with note
                    data_uri = image_data_uri(file_apic[0], file_apic[1])
                    img_html = f"<div class='fallback-art'><img src='{data_uri}' alt='File cover art (fallback)' class='thumb' /><p class='art-note'>Using file cover art (no chapter image)</p></div>"
                else:
                    img_html = "<span class='no-art'>No art</span>"

                rows.append(
                    f"<tr>"
                    f"<td>{idx + 1}</td>"
                    f"<td><code>{chap.element_id}</code></td>"
                    f"<td>{chap_title}</td>"
                    f"<td>{start_str}</td>"
                    f"<td>{end_str}</td>"
                    f"<td>{dur_str}</td>"
                    f"<td>{img_html}</td>"
                    f"</tr>"
                )

            chapters_html = (
                "<table class='chapters'>"
                "<thead><tr>"
                "<th>#</th>"
                "<th>ID</th>"
                "<th>Title</th>"
                "<th>Start</th>"
                "<th>End</th>"
                "<th>Duration</th>"
                "<th>Art</th>"
                "</tr></thead>"
                "<tbody>"
                + "\n".join(rows) +
                "</tbody></table>"
            )

    # Frame counts HTML
    frame_counts_html = ""
    if frame_counts:
        items = []
        for fid in sorted(frame_counts.keys()):
            items.append(f"<li><code>{fid}</code>: {frame_counts[fid]}</li>")
        frame_counts_html = "<ul>" + "\n".join(items) + "</ul>"

    # Build full HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{title}</title>
<style>
body {{
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #111;
    color: #eee;
    margin: 2rem;
}}
h1, h2, h3 {{
    color: #fff;
}}
code {{
    font-family: SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    background: #222;
    padding: 0.1em 0.2em;
    border-radius: 3px;
}}
.summary, .section {{
    background: #181818;
    border-radius: 8px;
    padding: 1rem 1.25rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 0 0 1px #222;
}}
.warn {{
    color: #ffb347;
}}
.chapters {{
    width: 100%;
    border-collapse: collapse;
    margin-top: 0.5rem;
}}
.chapters th, .chapters td {{
    border: 1px solid #333;
    padding: 0.4rem 0.5rem;
    font-size: 0.9rem;
    vertical-align: middle;
}}
.chapters th {{
    background: #202020;
}}
.thumb {{
    max-width: 160px;
    max-height: 160px;
    display: block;
}}
.no-art {{
    font-size: 0.8rem;
    color: #888;
}}
.corrupted-art {{
    position: relative;
    display: inline-block;
}}
.corrupted-art .thumb {{
    opacity: 0.6;
    border: 2px dashed #ff6b6b;
}}
.corrupted-art .art-note {{
    margin: 0.3rem 0 0 0;
    font-size: 0.7rem;
    color: #ff6b6b;
    font-weight: bold;
}}
.fallback-art {{
    position: relative;
    display: inline-block;
}}
.fallback-art .thumb {{
    opacity: 0.7;
    border: 2px dashed #ffb347;
}}
.fallback-art .art-note {{
    margin: 0.3rem 0 0 0;
    font-size: 0.7rem;
    color: #ffb347;
    font-weight: bold;
}}
.art-note {{
    margin: 0.3rem 0 0 0;
    font-size: 0.7rem;
    font-weight: 600;
}}
</style>
</head>
<body>
<h1>Chapter Report</h1>

<div class="summary">
  <h2>File</h2>
  <p><strong>Name:</strong> {input_path.name}</p>
  <p><strong>Path:</strong> <code>{input_path}</code></p>
  <p><strong>Audio class:</strong> {audio_info.get("class", "Unknown")}</p>
  <p><strong>Length:</strong> {length_str or "Unknown"} &nbsp;&nbsp;
     <strong>Bitrate:</strong> {bitrate_str or "Unknown"} &nbsp;&nbsp;
     <strong>Sample rate:</strong> {audio_info.get("sample_rate") or "Unknown"} Hz &nbsp;&nbsp;
     <strong>Channels:</strong> {audio_info.get("channels") or "Unknown"}
  </p>
  <p><strong>ID3 version:</strong> {id3_version or "None / not present"}</p>
</div>

<div class="section">
  <h2>ID3 Frame Counts</h2>
  {frame_counts_html or "<p>No ID3 frames to report.</p>"}
</div>

<div class="section">
  <h2>CTOC (Table of Contents)</h2>
  {ctoc_summary or "<p>No CTOC info.</p>"}
</div>

<div class="section">
  <h2>Chapters</h2>
  {warnings_html or ""}
  {chapters_html or "<p>No chapters found.</p>"}
</div>

</body>
</html>
"""
    return html


# ---------------- main ---------------- #

def main():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print(f"Usage: {sys.argv[0]} input.mp3 [output.html]")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    if not input_path.is_file():
        print(f"Input file not found: {input_path}")
        sys.exit(1)

    if len(sys.argv) == 3:
        output_path = Path(sys.argv[2])
    else:
        output_path = input_path.with_suffix(".chapter-report.html")

    audio_info = get_audio_info(input_path)
    tags = load_id3(input_path)

    html = generate_html_report(input_path, audio_info, tags)
    output_path.write_text(html, encoding="utf-8")
    print(f"Wrote chapter report to: {output_path}")


if __name__ == "__main__":
    main()
