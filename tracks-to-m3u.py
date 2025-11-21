#!/usr/bin/env python3
"""
Create an M3U playlist from a list of artist | track names.
Uses SQLite database of library metadata for more accurate matching.
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import List, Tuple, Optional
import re
from difflib import SequenceMatcher


def normalize_string(s: str) -> str:
    """Normalize string for matching: lowercase, remove extra spaces."""
    s = s.lower().strip()
    s = re.sub(r'\s+', ' ', s)
    return s


def get_or_create_db(library_path: Path, db_path: str) -> str:
    """
    Check if database exists. If not, build it.
    Returns the path to the database.
    """
    if os.path.exists(db_path):
        return db_path

    print(f"Database not found at {db_path}")
    print(f"Building database from library: {library_path}")
    print("This may take a moment...\n")

    # Import and run the database builder
    try:
        from build_music_db import scan_and_populate
        scan_and_populate(library_path, db_path, verbose=False)
        print()  # Blank line after scan output
        return db_path
    except ImportError:
        print(
            "Error: build_music_db.py not found. Please run it first:\n"
            f"  python build-music-db.py {library_path} -d {db_path}",
            file=sys.stderr,
        )
        sys.exit(1)


def similarity_ratio(a: str, b: str) -> float:
    """Calculate similarity ratio between two strings (0.0 to 1.0)."""
    return SequenceMatcher(None, a, b).ratio()


def find_best_match(
    artist: str, track: str, conn: sqlite3.Connection
) -> Optional[Tuple[str, float]]:
    """
    Find best matching file path for artist/track combination.
    Returns (file_path, confidence_score) or None.
    Uses normalized matching with fuzzy fallback.
    """
    cursor = conn.cursor()
    artist_norm = normalize_string(artist)
    track_norm = normalize_string(track)

    # Try exact match first (normalized)
    cursor.execute(
        "SELECT file_path FROM tracks WHERE LOWER(artist) = ? AND LOWER(track_name) = ?",
        (artist_norm, track_norm),
    )
    result = cursor.fetchone()
    if result:
        return (result[0], 1.0)

    # Try fuzzy matching: get candidates and score them
    cursor.execute(
        """
        SELECT file_path, artist, track_name FROM tracks
        WHERE LOWER(artist) LIKE ? OR LOWER(track_name) LIKE ?
        LIMIT 50
        """,
        (f"%{artist_norm}%", f"%{track_norm}%"),
    )

    best_match = None
    best_score = 0.7  # Minimum threshold - require 70% similarity

    for file_path, lib_artist, lib_track in cursor.fetchall():
        lib_artist_norm = normalize_string(lib_artist)
        lib_track_norm = normalize_string(lib_track)

        # Score based on both artist and track similarity
        artist_score = similarity_ratio(artist_norm, lib_artist_norm)
        track_score = similarity_ratio(track_norm, lib_track_norm)

        # Combined score: weight track name higher since it's more specific
        combined_score = (artist_score * 0.3) + (track_score * 0.7)

        if combined_score > best_score:
            best_score = combined_score
            best_match = (file_path, combined_score)

    return best_match


def load_track_list(input_file: str) -> List[Tuple[str, str]]:
    """Load track list from file. Format: Artist | Track"""
    tracks = []
    with open(input_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            if '|' not in line:
                print(f"Warning: Skipping line without pipe separator: {line}", file=sys.stderr)
                continue

            parts = line.split('|', 1)
            artist = parts[0].strip()
            track = parts[1].strip()

            if artist and track:
                tracks.append((artist, track))

    return tracks


def create_m3u(
    tracks: List[Tuple[str, str]], conn: sqlite3.Connection, output_file: str
):
    """Create M3U file from tracks using database lookup."""
    found = 0
    not_found = []
    matches = []

    for idx, (artist, track) in enumerate(tracks, 1):
        result = find_best_match(artist, track, conn)

        if result:
            path, confidence = result
            matches.append((idx, path, confidence))
            found += 1
        else:
            not_found.append((idx, artist, track))

    # Write M3U file with both found and not-found entries
    with open(output_file, 'w') as m3u:
        m3u.write("#EXTM3U\n")

        track_idx = 1
        not_found_idx = 0

        for idx in range(1, len(tracks) + 1):
            # Check if this track was found
            match_for_idx = next((m for m in matches if m[0] == idx), None)

            if match_for_idx:
                idx_num, path, confidence = match_for_idx
                m3u.write(f"{path}\n")
            else:
                # Track not found - write as comment
                not_found_track = not_found[not_found_idx]
                not_found_idx += 1
                idx_num, artist, track = not_found_track
                m3u.write(f"# NOT FOUND: {artist} | {track}\n")

    # Print summary
    print(f"\nCreated: {output_file}")
    print(f"Found: {found}/{len(tracks)} tracks")

    if not_found:
        print(f"\nCould not find ({len(not_found)}):")
        for idx, artist, track in not_found:
            print(f"  {idx:2d}. {artist} | {track}")


def main():
    parser = argparse.ArgumentParser(
        description="Create an M3U playlist from a list of artist/track names"
    )
    parser.add_argument("input_file", help='Text file with "Artist | Track" entries')
    parser.add_argument("-o", "--output", help="Output M3U file (default: input_file.m3u)")
    parser.add_argument(
        "-l", "--library", help="Path to Music library folder (default: ~/Music/Music Media.localized)"
    )
    parser.add_argument(
        "-d", "--db", help="Path to SQLite database (default: music.db in current dir)"
    )
    parser.add_argument(
        "--rebuild-db", action="store_true", help="Force rebuild of database"
    )

    args = parser.parse_args()

    # Determine library path
    library_path = (
        Path(args.library)
        if args.library
        else Path.home() / "Music" / "Music Media.localized"
    )

    # Determine database path
    db_path = args.db or "music.db"

    # Determine output file
    output_file = args.output or f"{Path(args.input_file).stem}.m3u"

    # Check input file exists
    if not os.path.exists(args.input_file):
        print(f"Error: Input file not found: {args.input_file}", file=sys.stderr)
        sys.exit(1)

    # Handle database rebuild
    if args.rebuild_db and os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing database: {db_path}\n")

    # Get or create database
    db_path = get_or_create_db(library_path, db_path)

    # Open database connection
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM tracks")
    track_count = cursor.fetchone()[0]
    print(f"Database ready: {track_count} tracks indexed")

    # Load and match tracks
    print(f"\nLoading track list: {args.input_file}")
    tracks = load_track_list(args.input_file)
    print(f"Loaded {len(tracks)} tracks to find")

    print(f"\nMatching tracks...")
    create_m3u(tracks, conn, output_file)

    conn.close()


if __name__ == "__main__":
    main()
