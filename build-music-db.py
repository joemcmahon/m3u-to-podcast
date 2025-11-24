#!/usr/bin/env python3
"""
Build a SQLite database of music library metadata.
Scans audio files and extracts artist/track info from file metadata.

Usage:
    python build-music-db.py /path/to/library [--db music.db]
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional, Tuple

from mutagen import File as MutagenFile
from mutagen.id3 import ID3, ID3NoHeaderError

# Try to import tqdm for progress bar, fall back to simple counter
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    print("Note: Install 'tqdm' for a better progress bar (pip install tqdm)")


def initialize_db(db_path: str) -> sqlite3.Connection:
    """Create and initialize the SQLite database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create tracks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL UNIQUE,
            artist TEXT,
            track_name TEXT,
            album TEXT,
            duration REAL,
            file_format TEXT,
            skip_reason TEXT DEFAULT ''
        )
    """)
    
    # Add the skip_reason column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE tracks ADD COLUMN skip_reason TEXT DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        # Column already exists
        pass

    # Create indexes for faster lookup
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_artist_track ON tracks(artist, track_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_artist ON tracks(artist)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_track ON tracks(track_name)")

    conn.commit()
    return conn


def extract_metadata(file_path: str) -> Optional[Tuple[str, str, str, float, str, str]]:
    """
    Extract metadata from audio file.
    Returns (artist, track_name, album, duration, file_format, skip_reason) or None if completely unreadable.
    """
    try:
        audio = MutagenFile(file_path, easy=True)
        if audio is None:
            return None

        # Get basic metadata
        artist = None
        track_name = None
        album = None
        duration = 0
        file_format = type(audio).__name__
        skip_reason = ""

        # Extract artist with multiple fallbacks
        if "artist" in audio and audio["artist"]:
            artist = audio["artist"][0]
        elif "albumartist" in audio and audio["albumartist"]:
            artist = audio["albumartist"][0]
        elif "performer" in audio and audio["performer"]:
            artist = audio["performer"][0]
        elif "composer" in audio and audio["composer"]:
            artist = audio["composer"][0]

        # Extract track name with fallbacks
        if "title" in audio and audio["title"]:
            track_name = audio["title"][0]
        else:
            # Use filename as fallback (remove extension and path)
            filename = os.path.basename(file_path)
            track_name = os.path.splitext(filename)[0]
            # Clean up common filename patterns
            if " - " in track_name and not artist:
                parts = track_name.split(" - ", 1)
                if len(parts) == 2:
                    artist = parts[0].strip()
                    track_name = parts[1].strip()

        # Extract album
        if "album" in audio and audio["album"]:
            album = audio["album"][0]

        # Extract duration
        if hasattr(audio, "info") and audio.info:
            duration = getattr(audio.info, "length", 0) or 0

        # Use "Unknown Artist" fallback if still no artist
        if not artist:
            artist = "Unknown Artist"
            skip_reason = "missing_artist_fallback"
            
        # Ensure we have a track name (this should always be true now)
        if not track_name:
            track_name = os.path.basename(file_path)
            skip_reason = "missing_title_fallback"

        return (artist, track_name, album or "", duration, file_format, skip_reason)

    except Exception as e:
        # Return detailed error info instead of just None
        filename = os.path.basename(file_path)
        return ("Unknown Artist", filename, "", 0, "Unknown", f"read_error: {str(e)}")


def scan_and_populate(library_path: Path, db_path: str, verbose: bool = False):
    """Scan library and populate database."""
    conn = initialize_db(db_path)
    cursor = conn.cursor()

    audio_extensions = (".mp3", ".m4a", ".flac", ".wav", ".aiff", ".ogg", ".opus")
    file_count = 0
    inserted_count = 0
    skipped_count = 0
    fallback_count = 0  # Files processed with fallback data

    if not library_path.exists():
        print(f"Error: Library path does not exist: {library_path}", file=sys.stderr)
        return

    print(f"Scanning {library_path}...")
    
    # First pass: count total audio files for progress tracking
    print("Counting audio files...")
    total_files = 0
    for root, dirs, files in os.walk(library_path):
        for file in files:
            if file.lower().endswith(audio_extensions):
                total_files += 1
    
    print(f"Found {total_files} audio files to process.")
    
    # Initialize progress bar or counter
    if HAS_TQDM:
        progress_bar = tqdm(total=total_files, desc="Processing tracks", unit="file")
    else:
        progress_update_interval = max(1, total_files // 20)  # Update every 5%
        
    print("\nProcessing audio files...")

    for root, dirs, files in os.walk(library_path):
        for file in files:
            if file.lower().endswith(audio_extensions):
                file_path = os.path.join(root, file)
                file_count += 1

                metadata = extract_metadata(file_path)
                if metadata:
                    artist, track_name, album, duration, file_format, skip_reason = metadata
                    try:
                        cursor.execute(
                            "INSERT INTO tracks (file_path, artist, track_name, album, duration, file_format, skip_reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (file_path, artist, track_name, album, duration, file_format, skip_reason),
                        )
                        inserted_count += 1
                        if skip_reason:
                            fallback_count += 1
                        
                        if verbose:
                            status = "(fallback)" if skip_reason else ""
                            progress_msg = f"Added {status}: {artist} - {track_name}"
                            if skip_reason and "read_error" in skip_reason:
                                progress_msg += f" [{skip_reason}]"
                            if HAS_TQDM:
                                progress_bar.set_postfix_str(progress_msg)
                            else:
                                print(f"  {progress_msg}")
                    except sqlite3.IntegrityError:
                        # File already in DB
                        skipped_count += 1
                        if verbose:
                            skip_msg = f"Skipped (duplicate): {os.path.basename(file_path)}"
                            if HAS_TQDM:
                                progress_bar.set_postfix_str(skip_msg)
                            else:
                                print(f"  {skip_msg}")
                else:
                    # This should rarely happen now since we have better fallbacks
                    skipped_count += 1
                    if verbose:
                        skip_msg = f"Skipped (unreadable): {os.path.basename(file_path)}"
                        if HAS_TQDM:
                            progress_bar.set_postfix_str(skip_msg)
                        else:
                            print(f"  {skip_msg}")
                
                # Update progress
                if HAS_TQDM:
                    progress_bar.update(1)
                    progress_bar.set_description(f"Processing tracks ({inserted_count} added, {fallback_count} fallback, {skipped_count} skipped)")
                else:
                    # Simple progress counter
                    if file_count % progress_update_interval == 0 or file_count == total_files:
                        percentage = (file_count / total_files) * 100
                        print(f"  Progress: {file_count}/{total_files} files ({percentage:.1f}%) - {inserted_count} added, {fallback_count} fallback, {skipped_count} skipped")
    
    # Close progress bar if using tqdm
    if HAS_TQDM:
        progress_bar.close()

    conn.commit()

    # Print summary
    print(f"\nScan complete:")
    print(f"  Files found: {file_count}")
    print(f"  Tracks indexed: {inserted_count}")
    print(f"    - Clean metadata: {inserted_count - fallback_count}")
    print(f"    - Using fallbacks: {fallback_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"  Database: {db_path}")

    # Show skip reason breakdown if there were fallbacks
    if fallback_count > 0:
        print(f"\n  Fallback breakdown:")
        cursor.execute("SELECT skip_reason, COUNT(*) FROM tracks WHERE skip_reason != '' GROUP BY skip_reason")
        for reason, count in cursor.fetchall():
            reason_desc = {
                'missing_artist_fallback': 'Missing artist (used "Unknown Artist")',
                'missing_title_fallback': 'Missing title (used filename)'
            }.get(reason, reason)
            print(f"    - {reason_desc}: {count}")
    
    # Show some stats
    cursor.execute("SELECT COUNT(DISTINCT artist) FROM tracks")
    artist_count = cursor.fetchone()[0]
    print(f"\n  Library stats:")
    print(f"    - Unique artists: {artist_count}")
    
    # Show files with read errors if any
    cursor.execute("SELECT COUNT(*) FROM tracks WHERE skip_reason LIKE 'read_error%'")
    error_count = cursor.fetchone()[0]
    if error_count > 0:
        print(f"    - Files with read errors: {error_count}")
        if verbose:
            print(f"\n  Files with read errors:")
            cursor.execute("SELECT file_path, skip_reason FROM tracks WHERE skip_reason LIKE 'read_error%' LIMIT 10")
            for file_path, reason in cursor.fetchall():
                print(f"    - {os.path.basename(file_path)}: {reason}")
            if error_count > 10:
                print(f"    ... and {error_count - 10} more")

    conn.close()


def analyze_database(db_path: str):
    """Analyze the database for problematic files and patterns."""
    if not os.path.exists(db_path):
        print(f"Error: Database does not exist: {db_path}", file=sys.stderr)
        return
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print(f"Analyzing database: {db_path}\n")
    
    # Total stats
    cursor.execute("SELECT COUNT(*) FROM tracks")
    total_tracks = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM tracks WHERE skip_reason != ''")
    fallback_tracks = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT artist) FROM tracks")
    unique_artists = cursor.fetchone()[0]
    
    print(f"Database Summary:")
    print(f"  Total tracks: {total_tracks:,}")
    print(f"  Clean tracks: {total_tracks - fallback_tracks:,}")
    print(f"  Fallback tracks: {fallback_tracks:,}")
    print(f"  Unique artists: {unique_artists:,}")
    
    # Fallback reason breakdown
    if fallback_tracks > 0:
        print(f"\nFallback Breakdown:")
        cursor.execute("""
            SELECT skip_reason, COUNT(*) as count 
            FROM tracks 
            WHERE skip_reason != '' 
            GROUP BY skip_reason 
            ORDER BY count DESC
        """)
        for reason, count in cursor.fetchall():
            percentage = (count / total_tracks) * 100
            reason_desc = {
                'missing_artist_fallback': 'Missing artist info',
                'missing_title_fallback': 'Missing title info'
            }.get(reason, reason)
            print(f"  {reason_desc}: {count:,} ({percentage:.1f}%)")
    
    # Top "Unknown Artist" tracks
    cursor.execute("""
        SELECT track_name, COUNT(*) as count 
        FROM tracks 
        WHERE artist = 'Unknown Artist' 
        GROUP BY track_name 
        ORDER BY count DESC 
        LIMIT 10
    """)
    unknown_results = cursor.fetchall()
    if unknown_results:
        print(f"\nMost Common 'Unknown Artist' Tracks:")
        for track, count in unknown_results:
            print(f"  {track}: {count} files")
    
    # Files with read errors
    cursor.execute("""
        SELECT file_path, skip_reason 
        FROM tracks 
        WHERE skip_reason LIKE 'read_error%' 
        ORDER BY file_path
    """)
    error_files = cursor.fetchall()
    if error_files:
        print(f"\nFiles with Read Errors ({len(error_files)}):")
        for file_path, reason in error_files[:20]:  # Show first 20
            print(f"  {os.path.basename(file_path)}: {reason}")
        if len(error_files) > 20:
            print(f"  ... and {len(error_files) - 20} more")
    
    # File format breakdown
    print(f"\nFile Format Breakdown:")
    cursor.execute("""
        SELECT file_format, COUNT(*) as count 
        FROM tracks 
        GROUP BY file_format 
        ORDER BY count DESC
    """)
    for format_type, count in cursor.fetchall():
        percentage = (count / total_tracks) * 100
        print(f"  {format_type}: {count:,} ({percentage:.1f}%)")
        
    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Build a SQLite database of music library metadata"
    )
    parser.add_argument("library", nargs="?", help="Path to music library folder (not required for --analyze)")
    parser.add_argument(
        "-d", "--db", default="music.db", help="Path to SQLite database (default: music.db)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose output"
    )
    parser.add_argument(
        "-a", "--analyze", action="store_true", help="Analyze existing database for problematic files"
    )

    args = parser.parse_args()
    
    if args.analyze:
        analyze_database(args.db)
    else:
        if not args.library:
            parser.error("library path is required when not using --analyze")
        library_path = Path(args.library)
        scan_and_populate(library_path, args.db, args.verbose)


if __name__ == "__main__":
    main()
