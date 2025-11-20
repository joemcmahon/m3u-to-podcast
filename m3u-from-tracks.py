#!/usr/bin/env python3
"""
Create an M3U playlist from a list of artist | track names.
Scans Music.app library to find matching files.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Tuple, Dict
import re


def normalize_string(s: str) -> str:
    """Normalize string for matching: lowercase, remove extra spaces, basic punctuation handling."""
    s = s.lower().strip()
    # Remove extra whitespace
    s = re.sub(r'\s+', ' ', s)
    return s


def scan_music_library(library_path: Path) -> Dict[str, str]:
    """
    Scan Music library folder and build a map of (artist, track) -> file_path.
    Returns dict with key like "artist name | track name" -> absolute path
    """
    matches = {}

    if not library_path.exists():
        print(f"Error: Library path does not exist: {library_path}", file=sys.stderr)
        return matches

    # Walk through the library
    for root, dirs, files in os.walk(library_path):
        for file in files:
            # Only look at audio files
            if file.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.aiff')):
                file_path = os.path.join(root, file)

                # Try to extract artist and track from path structure
                # Typical structure: Artist/Album/Track.ext
                parts = file_path.split(os.sep)

                # Look for patterns: if we have at least Artist/Album/Track structure
                if len(parts) >= 3:
                    # Usually: ... / Artist / Album / Track.ext
                    track_name = Path(file).stem  # filename without extension

                    # Try to find artist - could be 2 or 3 levels up depending on structure
                    artist = None

                    # Check if we have a clear Artist/Album/Track structure
                    # by looking at relative position in Music Media folder
                    rel_parts = Path(file_path).relative_to(library_path).parts

                    if len(rel_parts) >= 2:
                        # Assume first level is artist, second is album (or artist/track)
                        artist = rel_parts[0]

                    if artist:
                        # Normalize and create key
                        artist_norm = normalize_string(artist)
                        track_norm = normalize_string(track_name)
                        key = f"{artist_norm} | {track_norm}"
                        matches[key] = file_path

    return matches


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


def find_best_match(artist: str, track: str, library_index: Dict[str, str]) -> str | None:
    """
    Find best matching file path for artist/track combination.
    Uses normalized string matching.
    """
    artist_norm = normalize_string(artist)
    track_norm = normalize_string(track)
    search_key = f"{artist_norm} | {track_norm}"

    # Exact match first
    if search_key in library_index:
        return library_index[search_key]

    # Fuzzy match: look for entries that contain both artist and track
    for lib_key, path in library_index.items():
        lib_artist, lib_track = lib_key.split(' | ', 1)

        # Check if both artist and track are contained (forgiving match)
        if artist_norm in lib_artist and track_norm in lib_track:
            return path

    return None


def create_m3u(tracks: List[Tuple[str, str]], library_index: Dict[str, str], output_file: str):
    """Create M3U file from tracks using library index."""
    found = 0
    not_found = []

    with open(output_file, 'w') as m3u:
        m3u.write("#EXTM3U\n")

        for artist, track in tracks:
            path = find_best_match(artist, track, library_index)

            if path:
                m3u.write(f"{path}\n")
                found += 1
            else:
                not_found.append((artist, track))

    print(f"\nCreated: {output_file}")
    print(f"Found: {found}/{len(tracks)} tracks")

    if not_found:
        print(f"\nCould not find ({len(not_found)}):")
        for artist, track in not_found:
            print(f"  - {artist} | {track}")


def main():
    parser = argparse.ArgumentParser(
        description='Create an M3U playlist from a list of artist/track names'
    )
    parser.add_argument('input_file', help='Text file with "Artist | Track" entries')
    parser.add_argument('-o', '--output', help='Output M3U file (default: input_file.m3u)')
    parser.add_argument('-l', '--library', help='Path to Music library folder (default: ~/Music/Music Media.localized)')

    args = parser.parse_args()

    # Determine library path
    library_path = Path(args.library) if args.library else Path.home() / 'Music' / 'Music Media.localized'

    # Determine output file
    output_file = args.output or f"{Path(args.input_file).stem}.m3u"

    # Check input file exists
    if not os.path.exists(args.input_file):
        print(f"Error: Input file not found: {args.input_file}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning library: {library_path}")
    library_index = scan_music_library(library_path)
    print(f"Found {len(library_index)} audio files in library")

    print(f"\nLoading track list: {args.input_file}")
    tracks = load_track_list(args.input_file)
    print(f"Loaded {len(tracks)} tracks to find")

    print(f"\nMatching tracks...")
    create_m3u(tracks, library_index, output_file)


if __name__ == '__main__':
    main()
