#!/usr/bin/env python3
"""
Build a chapterized MP3 episode using ONLY tracks from your Music library.

Assumptions / conventions:

- All segments (music + voiceovers) are normal tracks in your library.
- An exported .m3u playlist describes the episode order.
- Voiceover tracks are named with an episode date prefix, e.g.:

    20251105 Intro
    20251105 Break 1
    20251105 Break 2
    20251105 Outro

  (Title as seen in Music, and/or file stem if tags are missing.)

- Music tracks have ordinary titles.

The script:

1. Parses the playlist (.m3u) in order.
2. For each entry:
   - Resolves the file path.
   - Reads the track title via mutagen (ID3 TIT2 or MP4 ©nam), or falls back
     to the filename stem.
   - Classifies a segment as VO if its title matches:

        ^YYYYMMDD (something)

     AND that YYYYMMDD matches the --episode-date parameter.
     It infers role from the trailing words ("intro", "outro", "break 1", etc.).
   - Otherwise, the segment is a "track".

3. VALIDATION before building:
   - Ensures there is at least one VO segment for --episode-date.
   - Ensures there is at least one 'intro' and one 'outro' VO for that date.
   - Warns if there are VO-like titles for OTHER dates in the playlist.

4. Concatenates all segments via ffmpeg into a single MP3 (re-encoded at a
   specified bitrate).

5. Computes chapter start/end times from the durations.

6. Writes ID3v2.3 tags:
   - TIT2 = episode title.
   - TALB/TPE1 set to generic values unless already present.
   - Global APIC from --default-image (episode art).
   - CTOC with all chapters in order.
   - CHAP per segment:
       - Chapter title = segment title.
       - Per-chapter APIC:
           - For music segments: from the track’s own cover art if present,
             otherwise default episode art if provided.
           - For VO segments: default episode art (if provided).

Usage:

    python build_episode_from_playlist_library.py \
        --episode-date 20251105 \
        --episode-title "Etheric Currents – Green" \
        --playlist /path/to/20251105-green.m3u \
        --output /path/to/Etheric_Currents_20251105_Green.mp3 \
        --default-image /path/to/20251105-green-cover.jpg \
        --bitrate 128k
"""

import argparse
import imghdr
import os
import re
import subprocess
import tempfile
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from mutagen import File as MutagenFile
from mutagen.id3 import (
    ID3,
    ID3NoHeaderError,
    APIC,
    CHAP,
    CTOC,
    CTOCFlags,
    TIT2,
    TALB,
    TPE1,
    TDRC,
)
from mutagen import MutagenError

# ---------------- helpers ---------------- #

def debug(msg: str):
    print(f"[DEBUG] {msg}")


def parse_m3u(m3u_path: Path) -> List[Path]:
    """Parse an .m3u/.m3u8 and return a list of audio file paths (in order)."""
    tracks: List[Path] = []
    base = m3u_path.parent

    with m3u_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            p = Path(line)
            if not p.is_absolute():
                p = base / p
            tracks.append(p)

    return tracks


def run_ffmpeg_concat(files: List[Path], output: Path, bitrate: str) -> None:
    """
    Use ffmpeg concat demuxer to join files into a single MP3, re-encoding to a
    consistent bitrate (e.g., 128k).
    """
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
        list_path = Path(f.name)
        for p in files:
            quoted = shlex.quote(str(p))
            # ffmpeg concat lists do NOT want the outer quotes produced by shlex.quote,
            # so we strip them:
            if quoted.startswith("'") and quoted.endswith("'"):
                quoted = quoted[1:-1]
            f.write(f"file '{quoted}'\n")

    cmd = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_path),
        "-c:a", "libmp3lame",
        "-b:a", bitrate,
        "-y",
        str(output),
    ]
    print("[INFO] Running ffmpeg concat...")
    subprocess.run(cmd, check=True)
    os.unlink(list_path)
    print(f"[INFO] Created concatenated MP3: {output}")


def norm_title(s: str) -> str:
    """Normalize title: strip and collapse whitespace."""
    s = re.sub(r"\s+", " ", s.strip())
    return s


def get_track_title(path: Path) -> str:
    """
    Get a human-readable title for a track:
    - For MP3: ID3 TIT2
    - For MP4/M4A: ©nam
    - Fallback: file stem
    """
    audio = MutagenFile(path)
    if audio is None or not hasattr(audio, "tags") or audio.tags is None:
        return norm_title(path.stem)

    tags = audio.tags

    # MP3 / ID3
    if isinstance(tags, ID3):
        tit2 = tags.get("TIT2")
        if tit2 and tit2.text:
            return norm_title(str(tit2.text[0]))

    # MP4/M4A
    if audio.__class__.__name__ in ("MP4", "MP4File"):
        for key in ("\xa9nam", "©nam"):
            if key in tags and tags[key]:
                return norm_title(str(tags[key][0]))

    return norm_title(path.stem)


def get_cover_from_audio(path: Path) -> Optional[Tuple[bytes, str]]:
    """
    Extract cover art bytes + mime type from a source audio file.
    Supports:
      - MP3 (APIC)
      - MP4/M4A (covr atoms)
    Returns (data, mime) or None if not found.
    """
    audio = MutagenFile(path)
    if audio is None or audio.tags is None:
        debug(f"No tags / could not open for art: {path}")
        return None

    tags = audio.tags

    # MP3 / ID3
    if isinstance(tags, ID3):
        apics = tags.getall("APIC")
        if apics:
            apic = apics[0]
            mime = apic.mime or "image/jpeg"
            return apic.data, mime

    # MP4/M4A
    if audio.__class__.__name__ in ("MP4", "MP4File"):
        covr = tags.get("covr")
        if covr:
            data = covr[0]
            kind = imghdr.what(None, h=data)
            if kind == "png":
                mime = "image/png"
            else:
                mime = "image/jpeg"
            return data, mime

    debug(f"No cover art found in: {path}")
    return None


def get_duration_ms(path: Path) -> int:
    """Get duration in milliseconds using mutagen."""
    audio = MutagenFile(path)
    if audio is None or not hasattr(audio, "info") or audio.info is None:
        debug(f"No duration info for {path}, assuming 0.")
        return 0
    seconds = getattr(audio.info, "length", 0.0)
    return int(round(seconds * 1000))


def load_id3_or_create(path: Path) -> ID3:
    """Load ID3 tags from an MP3, or create a new tag object if none present."""
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    except MutagenError as e:
        raise SystemExit(f"Error loading ID3 tags from {path}: {e}")
    return tags


# ---------------- segment model ---------------- #

@dataclass
class Segment:
    index: int
    kind: str          # 'vo' or 'track'
    role: Optional[str]  # 'intro', 'outro', 'break 1', etc. for vo; None for track
    date_code: Optional[str]  # YYYYMMDD for VO, else None
    source_path: Path
    title: str
    duration_ms: int


# ---------------- classification ---------------- #

VO_TITLE_RE = re.compile(r"^(?P<date>\d{8})\s+(?P<label>.+)$", re.IGNORECASE)


def classify_segment(title: str, episode_date: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Classify a segment based on its title.

    Returns (kind, role, date_code):
      - kind: 'vo' or 'track'
      - role: 'intro', 'outro', 'break 1', 'break 2', etc. for vo; None for track
      - date_code: YYYYMMDD for vo; None for track
    """
    m = VO_TITLE_RE.match(title)
    if not m:
        return "track", None, None

    date_code = m.group("date")
    label = m.group("label").strip().lower()

    # Only treat as VO if date_code matches this episode
    if date_code != episode_date:
        # VO-like naming but not this episode
        return "track", None, date_code

    role = None
    if "intro" in label:
        role = "intro"
    elif "outro" in label:
        role = "outro"
    elif "midbreak" in label:
        role = "midbreak"
    elif "break" in label:
        # capture e.g. "break 1", "break #2", etc.
        num_match = re.search(r"break\s*(\d+)", label)
        if num_match:
            role = f"break {num_match.group(1)}"
        else:
            role = "break"
    else:
        # generic VO for this episode
        role = label

    return "vo", role, date_code


def build_segments_from_playlist(playlist: Path, episode_date: str) -> List[Segment]:
    """Parse playlist and build classified segments."""
    entries = parse_m3u(playlist)
    segments: List[Segment] = []

    for idx, entry in enumerate(entries):
        if not entry.is_file():
            raise SystemExit(f"Playlist entry not found on disk: {entry}")

        title = get_track_title(entry)
        kind, role, date_code = classify_segment(title, episode_date)
        duration_ms = get_duration_ms(entry)

        segments.append(
            Segment(
                index=idx,
                kind=kind,
                role=role,
                date_code=date_code if kind == "vo" else None,
                source_path=entry,
                title=title,
                duration_ms=duration_ms,
            )
        )

    print("[INFO] Segment plan from playlist:")
    for seg in segments:
        k = seg.kind.upper()
        role = f" ({seg.role})" if seg.role else ""
        dc = f" [{seg.date_code}]" if seg.date_code else ""
        print(
            f"  #{seg.index:02d}: {k}{role}{dc} - {seg.title!r} "
            f"({seg.duration_ms/1000.0:.1f}s) from {seg.source_path.name}"
        )

    return segments


# ---------------- validation ---------------- #

def validate_segments(segments: List[Segment], episode_date: str) -> None:
    """
    Validate that:
    - At least one VO for this episode date exists.
    - At least one 'intro' and one 'outro' VO for this episode date exist.
    - Warn if VO-looking titles exist for other dates.
    """
    vo_this_ep = [s for s in segments if s.kind == "vo" and s.date_code == episode_date]
    vo_other_dates = [
        s for s in segments
        if s.date_code and s.date_code != episode_date and s.kind == "vo"
    ]

    # Only warn if those VO-like items appear *in this playlist*.
    # If the user keeps all VO files in one album, do not warn about global leftovers.
    # Only warn about mismatches that appear inside the playlist itself.
    # So if the playlist only contains correct-date VOs, no warning is triggered.
    if vo_other_dates:
        print("\n[WARN] Playlist contains VO-like titles for OTHER dates:")
        for s in vo_other_dates:
            print(f"  #{s.index:02d}: {s.title!r} (date {s.date_code}) from {s.source_path}")
            print("       ↑ This means you dragged the wrong VO into THIS playlist.")
            print("       (This is *not* a warning about your library organization!)\n")

    if not vo_this_ep:
        raise SystemExit(
            f"[ERROR] No VO segments found for episode date {episode_date}. "
            f"Make sure VO tracks are named like 'YYYYMMDD Intro' and in this playlist."
        )

    has_intro = any(s.role == "intro" for s in vo_this_ep)
    has_outro = any(s.role == "outro" for s in vo_this_ep)

    if not has_intro or not has_outro:
        missing = []
        if not has_intro:
            missing.append("Intro")
        if not has_outro:
            missing.append("Outro")
        raise SystemExit(
            f"[ERROR] Missing required VO roles for episode {episode_date}: "
            f"{', '.join(missing)}. Did you import & name them correctly?"
        )

    print(
        f"\n[INFO] VO validation for {episode_date}: "
        f"{len(vo_this_ep)} VO segments, intro present = {has_intro}, "
        f"outro present = {has_outro}.\n"
    )


# ---------------- chapterization / tagging ---------------- #

def build_chapters_and_tags(
    segments: List[Segment],
    default_image: Optional[Path],
    episode_title: str,
    episode_date: str,
    output_mp3: Path,
):
    """
    Build ID3v2.3 tags on output_mp3 with:
    - TIT2 = episode_title
    - TALB/TPE1/TDRC as generic or derived
    - global APIC from default_image
    - CTOC
    - CHAP frames with TIT2 + per-chapter APIC
    """
    tags = load_id3_or_create(output_mp3)

    # Set high-level fields if not present
    if "TIT2" not in tags:
        tags.add(TIT2(encoding=3, text=episode_title))
    if "TALB" not in tags:
        tags.add(TALB(encoding=3, text="Podcast Episode"))
    if "TPE1" not in tags:
        tags.add(TPE1(encoding=3, text="Etheric Currents"))  # tweak as desired
    if "TDRC" not in tags and re.fullmatch(r"\d{8}", episode_date):
        # YYYYMMDD -> YYYY-MM-DD
        date_str = f"{episode_date[0:4]}-{episode_date[4:6]}-{episode_date[6:8]}"
        tags.add(TDRC(encoding=3, text=date_str))

    # Default/episode art
    default_bytes: Optional[bytes] = None
    default_mime: Optional[str] = None
    if default_image is not None:
        default_bytes = default_image.read_bytes()
        kind = imghdr.what(None, h=default_bytes)
        if kind == "png":
            default_mime = "image/png"
        else:
            default_mime = "image/jpeg"

        # Global APIC
        tags.add(
            APIC(
                encoding=3,
                mime=default_mime,
                type=0,
                desc="",
                data=default_bytes,
            )
        )

    # Compute chapter times and CHAP frames
    current_start = 0
    chap_frames: List[CHAP] = []
    child_ids: List[str] = []

    for i, seg in enumerate(segments):
        start_time = current_start
        end_time = current_start + seg.duration_ms
        current_start = end_time

        element_id = f"ch{i}"
        child_ids.append(element_id)

        chap = CHAP(
            element_id=element_id,
            start_time=start_time,
            end_time=end_time,
            start_offset=0,
            end_offset=0,
        )

        # Title: keep the full title, but you could strip the date prefix if you want
        title = seg.title
        # For VO, optionally strip "YYYYMMDD " from display title:
        if seg.kind == "vo" and seg.date_code and title.startswith(seg.date_code):
            title = title[len(seg.date_code):].lstrip()

        chap.sub_frames["TIT2"] = TIT2(encoding=3, text=title)

        # Per-chapter art
        if seg.kind == "track":
            art = get_cover_from_audio(seg.source_path)
            if art is not None:
                img_data, mime = art
                chap.sub_frames["APIC"] = APIC(
                    encoding=3,
                    mime=mime,
                    type=0,
                    desc="",
                    data=img_data,
                )
            elif default_bytes is not None:
                chap.sub_frames["APIC"] = APIC(
                    encoding=3,
                    mime=default_mime,
                    type=0,
                    desc="",
                    data=default_bytes,
                )
        else:  # VO segment
            if default_bytes is not None:
                chap.sub_frames["APIC"] = APIC(
                    encoding=3,
                    mime=default_mime,
                    type=0,
                    desc="",
                    data=default_bytes,
                )

        chap_frames.append(chap)

    # Attach CHAP frames
    for chap in chap_frames:
        tags.add(chap)

    # CTOC
    ctoc = CTOC(
        element_id="TOC",
        flags=CTOCFlags.TOP_LEVEL | CTOCFlags.ORDERED,
        child_element_ids=child_ids,
    )
    tags.add(ctoc)

    # Save
    tags.save(output_mp3, v2_version=3)
    print(f"[INFO] Wrote chapters and tags to {output_mp3}")


# ---------------- CLI ---------------- #

def main():
    parser = argparse.ArgumentParser(
        description="Build a chapterized MP3 episode from a Music.app playlist, "
                    "using only library tracks (including VO tracks with "
                    "YYYYMMDD-prefixed titles)."
    )
    parser.add_argument(
        "--episode-date",
        required=True,
        help="Episode date code used as title prefix for VO tracks, e.g. 20251105",
    )
    parser.add_argument(
        "--episode-title",
        required=True,
        help="Title for the episode (TIT2 for the final MP3).",
    )
    parser.add_argument(
        "--playlist",
        type=Path,
        required=True,
        help="Exported .m3u playlist describing the show order.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path for the final MP3 (will be created/overwritten).",
    )
    parser.add_argument(
        "--default-image",
        type=Path,
        default=None,
        help="Optional episode/default cover art image.",
    )
    parser.add_argument(
        "--bitrate",
        default="128k",
        help="Final MP3 audio bitrate, e.g. 128k, 160k, 192k. Default: 128k",
    )

    args = parser.parse_args()

    if not args.playlist.is_file():
        raise SystemExit(f"Playlist not found: {args.playlist}")
    if args.default_image is not None and not args.default_image.is_file():
        raise SystemExit(f"Default image not found: {args.default_image}")

    episode_date = args.episode_date

    # 1. Build segment list and classify
    segments = build_segments_from_playlist(
        playlist=args.playlist,
        episode_date=episode_date,
    )

    # 2. Validate that you did your part (VOs present, intro/outro exist)
    validate_segments(segments, episode_date=episode_date)

    # 3. Concatenate audio into final MP3
    files = [s.source_path for s in segments]
    run_ffmpeg_concat(files, args.output, args.bitrate)

    # 4. Add chapters + tags
    build_chapters_and_tags(
        segments=segments,
        default_image=args.default_image,
        episode_title=args.episode_title,
        episode_date=episode_date,
        output_mp3=args.output,
    )


if __name__ == "__main__":
    main()

