#!/usr/bin/env python3
"""
Build a chapterized MP3 episode from a CUE file and a recording.

This script:
1. Parses a CUE file to extract chapter titles, artists, and timecodes
2. Matches chapter tracks against your Music library
3. Creates chapters in the recording's MP3 file
4. Embeds metadata and artwork

Usage:
    python build_episode_from_cue.py \
        --cue /path/to/recording.cue \
        --recording /path/to/recording.mp3 \
        --episode-title "Etheric Currents – Horizons" \
        --episode-date 20251123 \
        --output /path/to/output.mp3 \
        --default-image /path/to/cover.jpg
"""

import argparse
import imghdr
import os
import re
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Dict
from difflib import SequenceMatcher

from dotenv import load_dotenv
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

load_dotenv()

# Fuzzy matching threshold (0.0 to 1.0)
FUZZY_THRESHOLD = 0.7

# Database of library tracks
MUSIC_DB_PATH = Path(os.getenv("MUSIC_DB", "music.db"))

# Logging helpers
def info(msg: str):
    print(f"[INFO] {msg}")

def warn(msg: str):
    print(f"[WARN] {msg}")

def debug(msg: str):
    print(f"[DEBUG] {msg}")

def error(msg: str):
    print(f"[ERROR] {msg}")


# -------- CUE file parsing -------- #

@dataclass
class CueChapter:
    """Represents a single chapter from a CUE file."""
    track_num: int
    title: str
    artist: str
    # Time in format MM:SS:FF (minutes:seconds:frames, frames are 1/75th of a second)
    index_str: str
    # Calculated timestamp in seconds (float)
    timestamp_seconds: float


def parse_cue_file(cue_path: Path) -> List[CueChapter]:
    """
    Parse a CUE file and return list of chapters.

    CUE format:
        PERFORMER "Global Artist"
        FILE "filename" WAVE
        TRACK 01 AUDIO
            TITLE "Chapter Title"
            PERFORMER "Chapter Artist"
            INDEX 01 MM:SS:FF
    """
    chapters = []
    current_track = None
    current_title = ""
    current_artist = ""
    current_index = ""

    with cue_path.open("r") as f:
        for line in f:
            line = line.strip()

            if line.startswith("TRACK"):
                # New track starting
                if current_track is not None and current_title and current_index:
                    ts = cue_timestamp_to_seconds(current_index)
                    chapters.append(CueChapter(
                        track_num=current_track,
                        title=current_title,
                        artist=current_artist,
                        index_str=current_index,
                        timestamp_seconds=ts
                    ))
                # Reset for new track
                parts = line.split()
                current_track = int(parts[1])
                current_title = ""
                current_artist = ""
                current_index = ""

            elif "TITLE" in line:
                # Extract title: TITLE "Some Title"
                match = re.search(r'TITLE\s+"([^"]*)"', line)
                if match:
                    current_title = match.group(1).strip()

            elif "PERFORMER" in line:
                # Extract performer: PERFORMER "Artist Name"
                match = re.search(r'PERFORMER\s+"([^"]*)"', line)
                if match:
                    current_artist = match.group(1).strip()

            elif "INDEX" in line:
                # Extract index: INDEX 01 MM:SS:FF
                match = re.search(r'INDEX\s+\d+\s+([\d:]+)', line)
                if match:
                    current_index = match.group(1).strip()

        # Don't forget the last track
        if current_track is not None and current_title and current_index:
            ts = cue_timestamp_to_seconds(current_index)
            chapters.append(CueChapter(
                track_num=current_track,
                title=current_title,
                artist=current_artist,
                index_str=current_index,
                timestamp_seconds=ts
            ))

    return chapters


def cue_timestamp_to_seconds(cue_time: str) -> float:
    """
    Convert CUE timestamp MM:SS:FF (minutes:seconds:frames) to seconds.
    Frames are 1/75th of a second (CD standard).
    """
    parts = cue_time.split(":")
    if len(parts) != 3:
        warn(f"Invalid CUE timestamp format: {cue_time}")
        return 0.0

    try:
        minutes = int(parts[0])
        seconds = int(parts[1])
        frames = int(parts[2])
        total_seconds = minutes * 60 + seconds + (frames / 75.0)
        return total_seconds
    except (ValueError, IndexError) as e:
        warn(f"Error parsing CUE timestamp {cue_time}: {e}")
        return 0.0


# -------- Music library matching -------- #

def load_music_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Load the music library database."""
    path = db_path or MUSIC_DB_PATH
    if not path.exists():
        raise FileNotFoundError(f"Music database not found: {path}")
    return sqlite3.connect(path)


def fuzzy_match(query: str, target: str) -> float:
    """
    Return a fuzzy match score between 0 and 1.
    1.0 = exact match, 0.0 = no match.
    """
    query_lower = query.lower().strip()
    target_lower = target.lower().strip()
    return SequenceMatcher(None, query_lower, target_lower).ratio()


def find_track_in_library(db: sqlite3.Connection, artist: str, title: str) -> Optional[Path]:
    """
    Search the music library for a track matching the given artist and title.
    Returns the file path if found, None otherwise.
    """
    cursor = db.cursor()

    # First, try exact match
    cursor.execute(
        "SELECT file_path FROM tracks WHERE artist = ? AND track_name = ?",
        (artist, title)
    )
    row = cursor.fetchone()
    if row:
        return Path(row[0])

    # Then, try fuzzy matching
    cursor.execute("SELECT file_path, artist, track_name FROM tracks WHERE artist LIKE ?",
                   (f"%{artist}%",))
    candidates = cursor.fetchall()

    best_match = None
    best_score = FUZZY_THRESHOLD

    for file_path, db_artist, db_title in candidates:
        artist_score = fuzzy_match(artist, db_artist)
        title_score = fuzzy_match(title, db_title)
        combined_score = (artist_score + title_score) / 2.0

        if combined_score > best_score:
            best_score = combined_score
            best_match = file_path

    if best_match:
        debug(f"Fuzzy matched '{artist} - {title}' to {best_match} (score: {best_score:.2f})")
        return Path(best_match)

    return None


def resolve_cue_chapters(db: sqlite3.Connection, chapters: List[CueChapter]) -> Dict[int, Optional[Path]]:
    """
    Try to resolve each chapter to a file in the library.
    Returns {track_num: Path or None}.
    """
    resolved = {}

    for chapter in chapters:
        info(f"[Track {chapter.track_num:02d}] Searching for: {chapter.artist} - {chapter.title}")

        track_path = find_track_in_library(db, chapter.artist, chapter.title)
        if track_path and track_path.exists():
            info(f"  ✓ Found: {track_path}")
            resolved[chapter.track_num] = track_path
        else:
            warn(f"  ✗ Not found in library")
            resolved[chapter.track_num] = None

    return resolved


# -------- ID3 tag writing -------- #

def get_cover_from_audio(path: Path) -> Optional[Tuple[bytes, str]]:
    """
    Extract cover art bytes + mime type from an audio file.
    """
    try:
        audio = MutagenFile(path)
        if audio is None or audio.tags is None:
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

    except Exception as e:
        debug(f"Could not extract cover from {path}: {e}")

    return None


def load_image_file(image_path: Optional[Path]) -> Optional[Tuple[bytes, str]]:
    """Load image file and return (data, mime_type)."""
    if not image_path or not image_path.exists():
        return None

    mime_type = "image/jpeg"  # default
    if image_path.suffix.lower() == ".png":
        mime_type = "image/png"

    try:
        with image_path.open("rb") as f:
            return f.read(), mime_type
    except Exception as e:
        warn(f"Could not load image {image_path}: {e}")
        return None


def load_id3_or_create(path: Path) -> ID3:
    """Load or create ID3 tags for an MP3."""
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    except MutagenError as e:
        raise SystemExit(f"Error loading ID3 tags from {path}: {e}")
    return tags


def write_chapters_to_mp3(
    mp3_path: Path,
    chapters: List[CueChapter],
    resolved_paths: Dict[int, Optional[Path]],
    episode_title: str,
    episode_artist: Optional[str] = None,
    episode_album: Optional[str] = None,
    default_image: Optional[Tuple[bytes, str]] = None,
    recording_duration_seconds: float = 0.0,
) -> None:
    """
    Write ID3 tags with chapter information to the MP3 file.
    """
    tags = load_id3_or_create(mp3_path)

    # Set global tags
    tags["TIT2"] = TIT2(encoding=3, text=[episode_title])
    if episode_artist:
        tags["TPE1"] = TPE1(encoding=3, text=[episode_artist])
    if episode_album:
        tags["TALB"] = TALB(encoding=3, text=[episode_album])

    # Add global artwork if provided
    if default_image:
        image_data, mime = default_image
        tags["APIC"] = APIC(encoding=3, mime=mime, type=3, desc="", data=image_data)

    # Build chapter list for CTOC
    chapter_ids = []
    for i, chapter in enumerate(chapters):
        chapter_id = f"ch{i:02d}"
        chapter_ids.append(chapter_id)

        # Calculate chapter end time
        if i + 1 < len(chapters):
            end_time_ms = int(chapters[i + 1].timestamp_seconds * 1000)
        else:
            end_time_ms = int(recording_duration_seconds * 1000)

        start_time_ms = int(chapter.timestamp_seconds * 1000)

        # Determine chapter title
        chapter_title = f"{chapter.artist}: {chapter.title}"

        # Create CHAP frame with title
        chap = CHAP(
            encoding=3,
            frame_id=chapter_id,
            start_time=start_time_ms,
            end_time=end_time_ms,
            start_offset=0,
            end_offset=0,
        )

        # Add title as a sub-frame
        chap.sub_frames.add(TIT2(encoding=3, text=[chapter_title]))

        # Add artwork to chapter:
        # - For matched tracks: try to use track's own artwork
        # - For unmatched tracks (voiceovers, etc): use default image if provided
        is_matched = resolved_paths.get(chapter.track_num) is not None
        if is_matched:
            # Try to extract artwork from the matched track
            track_image = get_cover_from_audio(resolved_paths[chapter.track_num])
            if track_image:
                image_data, mime = track_image
                chap.sub_frames.add(
                    APIC(encoding=3, mime=mime, type=3, desc="", data=image_data)
                )
        else:
            # No match - use default image if provided (for unmatched/VO chapters)
            if default_image:
                image_data, mime = default_image
                chap.sub_frames.add(
                    APIC(encoding=3, mime=mime, type=3, desc="", data=image_data)
                )

        tags[chapter_id] = chap

    # Create CTOC (table of contents)
    # Note: frame_id in CTOC refers to the element_id, not the tag key
    ctoc = CTOC(
        encoding=3,
        frame_id="toc",
        flags=CTOCFlags.TOP_LEVEL | CTOCFlags.ORDERED,
        child_element_ids=chapter_ids,
        sub_frames=[TIT2(encoding=3, text=[episode_title])]
    )
    tags["CTOC:toc"] = ctoc

    # Write tags
    tags.save(mp3_path, v2_version=3)
    info(f"Wrote ID3 tags with {len(chapters)} chapters to {mp3_path}")


# -------- Main workflow -------- #

def get_mp3_duration(mp3_path: Path) -> float:
    """Get MP3 duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1:noprint_wrappers=1",
        str(mp3_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        warn(f"Could not determine MP3 duration: {e}")
        return 0.0


def main():
    parser = argparse.ArgumentParser(
        description="Build a chapterized MP3 from a CUE file and recording"
    )
    parser.add_argument("--cue", required=True, type=Path, help="Path to CUE file")
    parser.add_argument("--recording", required=True, type=Path, help="Path to recording MP3")
    parser.add_argument("--episode-title", required=True, help="Episode title for metadata")
    parser.add_argument("--episode-date", required=True, help="Episode date (YYYYMMDD format)")
    parser.add_argument("--output", required=True, type=Path, help="Output MP3 path")
    parser.add_argument("--default-image", type=Path, help="Episode artwork image")
    parser.add_argument("--episode-artist", help="Episode artist (defaults to global CUE artist)")
    parser.add_argument("--episode-album", help="Episode album")
    parser.add_argument("-l", "--library", type=Path, help="Path to Music library folder (for fuzzy matching)")
    parser.add_argument("--rebuild-db", action="store_true", help="Rebuild the music database from the library")
    parser.add_argument("-d", "--db", type=Path, help="Path to music database (default: music.db)")

    args = parser.parse_args()

    # Validate inputs
    if not args.cue.exists():
        raise FileNotFoundError(f"CUE file not found: {args.cue}")
    if not args.recording.exists():
        raise FileNotFoundError(f"Recording not found: {args.recording}")

    # Ensure output directory exists
    args.output.parent.mkdir(parents=True, exist_ok=True)

    # Handle database rebuild if requested
    if args.rebuild_db:
        if not args.library:
            raise ValueError("--library is required when using --rebuild-db")
        info(f"Rebuilding music database from: {args.library}")
        # Import here to avoid hard dependency
        import subprocess
        result = subprocess.run(
            ["python", "build-music-db.py", str(args.library), "-d", str(args.db or MUSIC_DB_PATH)],
            check=True
        )
        info("Database rebuild complete")

    info(f"Parsing CUE file: {args.cue}")
    chapters = parse_cue_file(args.cue)
    info(f"Found {len(chapters)} chapters")

    # Load music database
    db_path = args.db or MUSIC_DB_PATH
    info(f"Loading music library database: {db_path}")
    db = load_music_db(Path(db_path) if args.db else None)

    # Resolve chapters to library tracks
    info("Resolving chapters to library tracks...")
    resolved = resolve_cue_chapters(db, chapters)

    # Count successful resolutions
    found_count = sum(1 for v in resolved.values() if v is not None)
    info(f"Resolved {found_count}/{len(chapters)} chapters to library tracks")

    if found_count < len(chapters):
        warn(f"Warning: {len(chapters) - found_count} chapters could not be matched to library")

    # Get recording duration
    info("Determining recording duration...")
    duration = get_mp3_duration(args.recording)
    info(f"Recording duration: {duration:.2f} seconds ({int(duration // 60)}m {int(duration % 60)}s)")

    # Load default image if provided
    default_image = None
    if args.default_image:
        info(f"Loading artwork: {args.default_image}")
        default_image = load_image_file(args.default_image)

    # Copy recording to output
    info(f"Copying recording to output: {args.output}")
    import shutil
    shutil.copy2(args.recording, args.output)

    # Write chapters to output MP3
    info("Writing chapters to output MP3...")
    write_chapters_to_mp3(
        args.output,
        chapters=chapters,
        resolved_paths=resolved,
        episode_title=args.episode_title,
        episode_artist=args.episode_artist,
        episode_album=args.episode_album,
        default_image=default_image,
        recording_duration_seconds=duration,
    )

    info(f"✓ Complete! Chapterized MP3: {args.output}")

    # Print summary
    print("\n" + "=" * 70)
    print("CHAPTER SUMMARY")
    print("=" * 70)
    for chapter in chapters:
        status = "✓" if resolved.get(chapter.track_num) else "✗"
        ts = f"{int(chapter.timestamp_seconds // 60):02d}:{int(chapter.timestamp_seconds % 60):02d}"
        print(f"{status} [{ts}] Track {chapter.track_num:02d}: {chapter.artist} - {chapter.title}")
    print("=" * 70)


if __name__ == "__main__":
    main()
