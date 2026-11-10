#!/usr/bin/env python3
"""
Build a chapterized "skeleton" episode from an .m3u playlist.

Every playlist entry becomes one chapter. Entries whose filename contains
"equinox speaks" are voiceover slots: they become a block of silence with
their own chapter ("VO - Break N"), ready to be cut out and replaced with the
real voiceover in an editor such as Fission (which shifts the chapter markers
for you).

Why per-entry encoding: each entry is encoded on its own to constant-bitrate
MP3 and the frames are joined byte-for-byte. For CBR the duration of each piece
is exact, so chapter start times line up with the audio and do not drift the
way durations read from differently-encoded source files can.

Usage:
    uv run python build_skeleton_from_m3u.py "tonight.m3u"

    uv run python build_skeleton_from_m3u.py "tonight.m3u" \
        --episode-title "Etheric Currents - Tonight" \
        --episode-date 20261109 \
        --default-image cover.jpg \
        --output tonight.mp3

With --voiceovers FOLDER, recorded voiceovers fill the slots instead of silence.
Files are matched by number: voiceover01.* goes in the first "Equinox Speaks"
slot of the playlist, voiceover02.* in the second, and so on. The numbers must
match the slots exactly, or the script stops before encoding anything.

Source files are only read, never modified or converted in place.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from mutagen.mp3 import MP3

# Reuse the proven tag/chapter code from the library-based builder.
from build_episode_from_playlist_library import (
    Segment,
    build_chapters_and_tags,
    get_track_title,
    parse_m3u,
)

VO_MARKER = "equinox speaks"
SAMPLE_RATE = "44100"


AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".wav", ".aif", ".aiff", ".flac", ".ogg", ".opus"}
VO_FILE_RE = re.compile(r"^voiceover[\s_-]*(\d+)", re.IGNORECASE)


def is_vo_slot(path: Path) -> bool:
    return VO_MARKER in path.stem.lower()


def find_voiceovers(folder: Path, entries: List[Path]) -> dict:
    """
    Map slot number -> voiceover file for voiceoverNN.* files in `folder`.
    Exits with a clear report unless the numbers are exactly 1..(number of slots).
    """
    folder = folder.expanduser().resolve()
    if not folder.is_dir():
        sys.exit(f"Voiceover folder not found: {folder}")

    slots = [(i, p) for i, p in enumerate(entries) if is_vo_slot(p)]
    found: dict = {}
    dupes: List[str] = []
    ignored: List[str] = []
    for f in sorted(folder.iterdir()):
        if not f.is_file() or f.suffix.lower() not in AUDIO_EXTS:
            continue
        m = VO_FILE_RE.match(f.stem)
        if not m:
            ignored.append(f.name)
            continue
        n = int(m.group(1))
        if n in found:
            dupes.append(f"{found[n].name} and {f.name} are both number {n}")
        else:
            found[n] = f

    wanted = set(range(1, len(slots) + 1))
    missing = sorted(wanted - set(found))
    extra = sorted(set(found) - wanted)

    print(f"Playlist has {len(slots)} voiceover slot(s); "
          f"found {len(found)} voiceover file(s) in {folder}")
    for n, (i, p) in enumerate(slots, start=1):
        target = found[n].name if n in found else "** MISSING **"
        print(f"  Break {n}  (playlist entry {i + 1}, \"{p.stem}\")  <-  {target}")
    for n in extra:
        print(f"  ** no slot for {found[n].name} (number {n}) **")
    for name in ignored:
        print(f"  (ignored, not named voiceoverNN: {name})")

    problems = dupes + [f"slot {n} has no voiceover file" for n in missing] \
        + [f"{found[n].name} has no matching slot" for n in extra]
    if problems:
        print("\nVoiceovers do not match the playlist:")
        for line in problems:
            print(f"  - {line}")
        sys.exit(1)
    return found


PROGRESS_RE = re.compile(r"^[a-z_0-9]+=")


def encode_cbr(src: Path, dst: Path, bitrate: str) -> List[float]:
    """
    Encode any audio file to bare CBR MP3 (no ID3 tag, no Xing header).

    Returns the approximate positions (seconds into the source,
    roughly +/-1s) of any decoder messages ffmpeg printed, e.g. "Header missing"
    for a corrupt MP3 frame. ffmpeg skips the bad data and carries on.
    """
    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-progress", "pipe:2", "-nostats", "-stats_period", "0.001",
        "-i", str(src),
        "-vn", "-map_metadata", "-1",
        "-ac", "2", "-ar", SAMPLE_RATE,
        "-c:a", "libmp3lame", "-b:a", bitrate,
        "-write_xing", "0", "-write_id3v2", "0",
        str(dst),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        sys.exit(f"ffmpeg failed on: {src}")

    offsets: List[float] = []
    position = 0.0
    for line in r.stderr.splitlines():
        if line.startswith(("out_time_us=", "out_time_ms=")):
            try:
                position = int(line.split("=", 1)[1]) / 1e6
            except ValueError:
                pass
        elif line.strip() and not PROGRESS_RE.match(line):
            offsets.append(round(position))  # nearest second; ffmpeg's timing is approximate
    return sorted(set(offsets))


def make_silence(dst: Path, seconds: int, bitrate: str) -> None:
    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=stereo",
        "-t", str(seconds),
        "-c:a", "libmp3lame", "-b:a", bitrate,
        "-write_xing", "0", "-write_id3v2", "0",
        str(dst),
    ]
    subprocess.run(cmd, check=True)


def duration_ms(mp3: Path) -> int:
    return int(round(MP3(mp3).info.length * 1000))


def fmt_time(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def guess_episode_date(stem: str) -> str:
    m = re.match(r"(\d{8})", stem)
    return m.group(1) if m else ""


def build(args: argparse.Namespace) -> None:
    m3u = args.m3u.expanduser().resolve()
    if not m3u.is_file():
        sys.exit(f"Playlist not found: {m3u}")
    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg not found on PATH.")

    entries = parse_m3u(m3u)
    if not entries:
        sys.exit(f"No tracks found in {m3u}")

    missing = [p for p in entries if not is_vo_slot(p) and not p.is_file()]
    if missing:
        print("These playlist entries do not exist (is the drive mounted?):")
        for p in missing:
            print(f"  {p}")
        sys.exit(1)

    vo_files = find_voiceovers(args.voiceovers, entries) if args.voiceovers else {}

    output = (args.output or m3u.with_suffix(".mp3")).expanduser().resolve()
    title = args.episode_title or re.sub(r"^\d{8}\s*", "", m3u.stem) or m3u.stem
    date = args.episode_date or guess_episode_date(m3u.stem)

    segments: List[Segment] = []
    pieces: List[Path] = []
    vo_count = 0
    decode_issues: List[tuple] = []  # (entry index, source file, offsets)

    with tempfile.TemporaryDirectory(prefix="skeleton-") as tmp_name:
        tmp = Path(tmp_name)
        silence = tmp / "silence.mp3"
        make_silence(silence, args.silence_seconds, args.bitrate)
        silence_ms = duration_ms(silence)

        for i, src in enumerate(entries):
            if is_vo_slot(src):
                vo_count += 1
                label = f"VO - Break {vo_count}"
                if vo_count in vo_files:
                    vo_src = vo_files[vo_count]
                    print(f"[{i + 1}/{len(entries)}] {label}  <-  {vo_src.name}")
                    piece = tmp / f"{i:03d}.mp3"
                    offs = encode_cbr(vo_src, piece, args.bitrate)
                    if offs:
                        decode_issues.append((i, vo_src, offs))
                    segments.append(Segment(
                        index=i, kind="vo", role=f"break {vo_count}", date_code=None,
                        source_path=vo_src, title=label, duration_ms=duration_ms(piece),
                    ))
                    pieces.append(piece)
                    continue
                print(f"[{i + 1}/{len(entries)}] {label}  <-  silence ({src.stem})")
                segments.append(Segment(
                    index=i, kind="vo", role=f"break {vo_count}", date_code=None,
                    source_path=silence, title=label, duration_ms=silence_ms,
                ))
                pieces.append(silence)
                continue

            piece = tmp / f"{i:03d}.mp3"
            print(f"[{i + 1}/{len(entries)}] {src.name}")
            offs = encode_cbr(src, piece, args.bitrate)
            if offs:
                decode_issues.append((i, src, offs))
            segments.append(Segment(
                index=i, kind="track", role=None, date_code=None,
                source_path=src, title=get_track_title(src),
                duration_ms=duration_ms(piece),
            ))
            pieces.append(piece)

        # Join the CBR frames byte-for-byte. (Chapter tagging below must stay
        # inside this block: the silence chapter reads tags from the temp file.)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("wb") as out:
            for piece in pieces:
                with piece.open("rb") as f:
                    shutil.copyfileobj(f, out)

        build_chapters_and_tags(
            segments=segments,
            default_image=args.default_image,
            episode_title=title,
            episode_date=date,
            output_mp3=output,
            artist=args.artist or os.getenv("DEFAULT_ARTIST", "Etheric Currents"),
            album=args.album or os.getenv("DEFAULT_ALBUM", "Podcast Episode"),
        )

    total = sum(s.duration_ms for s in segments) / 1000
    print(f"\nDone: {output}")
    print(f"{len(segments)} chapters ({vo_count} voiceover slots), "
          f"expected length {total / 60:.1f} min")

    if decode_issues:
        starts = [0]
        for seg in segments:
            starts.append(starts[-1] + seg.duration_ms)
        print("\nHeads up: ffmpeg reported decoder errors in these source files "
              "(it skips the bad data and carries on; worth a listen):")
        for i, src, offs in decode_issues:
            where = ", ".join(fmt_time(o) for o in offs[:5]) + (" ..." if len(offs) > 5 else "")
            print(f"  - {src.name}  (chapter {i + 1})")
            print(f"      at ~{where} in the track  =  ~{fmt_time(starts[i] / 1000 + offs[0])} in the episode")


def main() -> None:
    load_dotenv()
    p = argparse.ArgumentParser(
        description="Build a chapterized skeleton episode from an m3u.")
    p.add_argument("m3u", type=Path, help="Playlist (.m3u / .m3u8)")
    p.add_argument("--output", type=Path, help="Output MP3 (default: next to the m3u)")
    p.add_argument("--episode-title", help="Default: m3u name without the date prefix")
    p.add_argument("--episode-date", help="YYYYMMDD. Default: leading digits of the m3u name")
    p.add_argument("--default-image", type=Path, help="Cover art for the episode")
    p.add_argument("--voiceovers", type=Path,
                   help="Folder of voiceover01.*, voiceover02.* ... files, matched to "
                        "the 'Equinox Speaks' slots in playlist order")
    p.add_argument("--artist", help="Default: DEFAULT_ARTIST from .env")
    p.add_argument("--album", help="Default: DEFAULT_ALBUM from .env")
    p.add_argument("--silence-seconds", type=int, default=600,
                   help="Length of each voiceover placeholder (default 600)")
    p.add_argument("--bitrate", default="128k", help="MP3 bitrate (default 128k)")
    build(p.parse_args())


if __name__ == "__main__":
    main()
