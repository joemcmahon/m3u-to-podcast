# m3u to Podcast

A toolkit for building podcast episodes from Music.app playlists. Originally created to rescue live broadcasts when the recording fails by reconstructing episodes from the playlists used during the show.

## Overview

This project provides tools to:
- **Build chapterized podcast episodes** from Music.app playlists, embedding specially-named voiceover segments
- **Generate playlists** suitable for importing into Music.app from simple artist|track name lists
- **Analyze and validate** chapter metadata in MP3 files
- **Create visual reports** of podcast chapter structure
- **Test episodes** locally via RSS feeds before distribution

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Optional: Create a .env file for default values
cp .env.example .env
```

Create a `.env` file in the project root:
```env
DEFAULT_ARTIST=Your Show Name
DEFAULT_ALBUM=Your Podcast Name
```

## Quick Start

### Building a Podcast Episode (Recommended)

The main workflow for building a complete podcast episode with chapters:

```bash
python3 build_episode_from_playlist_library.py \
  --episode-date 20250317 \
  --episode-title "My Show Title" \
  --playlist path/to/playlist.m3u \
  --output episode.mp3 \
  --default-image cover.jpg \
  --bitrate 320k
```

**What this does:**
1. Reads your exported Music.app playlist (`.m3u` format)
2. Identifies voiceover segments by date prefix (e.g., `20250317 Intro`)
3. Extracts artist/album metadata from music tracks
4. Concatenates all audio with ffmpeg
5. Embeds chapter metadata with per-track artist/album info
6. Creates chapters with smart titles: `Artist: Track Title`

**Output:**
- `episode.mp3` - Complete podcast with embedded chapters and artwork

---

## All Scripts

### Core Workflow

#### `build_episode_from_playlist_library.py`
**Builds a fully chapterized podcast episode from a Music.app playlist.**

Handles voiceover segments, extracts metadata, and creates proper podcast-ready MP3s with chapters.

```bash
python3 build_episode_from_playlist_library.py \
  --episode-date YYYYMMDD \
  --episode-title "Episode Title" \
  --playlist path/to/playlist.m3u \
  --output episode.mp3 \
  --default-image cover.jpg \
  [--artist "Override Artist"] \
  [--album "Override Album"] \
  [--bitrate 320k]
```

**Features:**
- ✅ Extracts most common artist/album from playlist
- ✅ Falls back to DEFAULT_ARTIST/DEFAULT_ALBUM from `.env`
- ✅ Embeds per-chapter artist/album metadata
- ✅ Music track chapters show as "Artist: Title"
- ✅ Validates voiceover structure (intro/outro required)
- ✅ Supports chapter artwork from source files

**VO Naming Convention:**
Voiceover tracks must start with episode date and role:
- `20250317 Intro` (intro segment)
- `20250317 Outro` (outro segment)
- `20250317 Midbreak` (mid-episode break)
- `20250317 Break 1`, `20250317 Break 2`, etc.

---

#### `tracks-to-m3u.py`
**Create a playlist (`.m3u`) from a simple text list of tracks.**

Useful for building playlists programmatically or from a text file.

```bash
# From a text file (one per line: Artist | Track Title)
python3 tracks-to-m3u.py input.txt output.m3u

# Or from stdin
cat tracks.txt | python3 tracks-to-m3u.py - output.m3u
```

**Input Format:**
```
Artist Name | Track Title
Another Artist | Another Track
```

**Features:**
- ✅ Fuzzy matching against library database
- ✅ Automatically builds music library database if missing
- ✅ Handles multiple artists with same track title
- ✅ Works with both MP3 and M4A files

---

### Testing & Validation

#### `serve_rss.py`
**Local RSS feed server for testing podcast episodes.**

Test how your episode displays in locally-running podcast apps before uploading to distribution platforms.

```bash
python3 serve_rss.py
# Navigate to: http://localhost:8000/feed.xml
# Add this URL to your podcast app
```

**Serves:**
- RSS feed at `/feed.xml` with episode metadata from MP3 tags
- Episode MP3 at `/episode.mp3`

---

#### `chapter-analyzer.py`
**Inspect and validate chapter metadata in MP3 files.**

Detailed analysis of all ID3 tags, chapters, artwork, and file structure.

```bash
python3 chapter-analyzer.py episode.mp3
```

**Output:**
- File metadata (bitrate, sample rate, duration)
- ID3 tag summary
- Global artwork
- Chapter structure with titles, times, and per-chapter metadata
- Detailed frame information

---

#### `chapter-report.py`
**Generate an HTML visual report of chapter structure.**

Creates a browsable HTML file showing all chapters with timestamps and artwork.

```bash
python3 chapter-report.py episode.mp3 [report.html]
```

**Output:**
- Interactive HTML report with chapter timeline
- Chapter titles with timestamps
- Per-chapter artwork display (including "hidden" artwork)
- Episode metadata summary

---

### Utilities

#### `build-music-db.py`
**Build a SQLite database of your Music.app library.**

Creates an indexed database for fast track lookups (used by `tracks-to-m3u.py`).

```bash
python3 build-music-db.py "/path/to/Music Library" -d music.db
```

---

#### `rescue_busted_offsets.py`
**Fix chapter offset errors in MP3 files.**

Repairs chapterized MP3s where byte offsets were written incorrectly, while preserving chapter times, titles, and artwork.

```bash
python3 rescue_busted_offsets.py broken.mp3
# Creates: broken.rescued.mp3

# Or specify output:
python3 rescue_busted_offsets.py broken.mp3 fixed.mp3
```

---

#### `compare-libraries.py`
**Compare two Music.app libraries for differences.**

Useful for finding files that need to be added or removed to sync up libraries.

```bash
python3 compare-libraries.py library1.musiclibrary library2.musiclibrary
```

---

### Legacy / Experimental

#### `podcast-from-m3u.py`
Older command-line interface for building podcast episodes. Replaced by `build_episode_from_playlist_library.py`.

---

## Configuration

### Environment Variables (`.env`)

```env
# Default artist name (used when not extracted from tracks)
DEFAULT_ARTIST=Your Show Name

# Default album name (used when not extracted from tracks)
DEFAULT_ALBUM=Your Podcast Series Name
```

If `.env` is not found, hardcoded defaults are used:
- DEFAULT_ARTIST: "Etheric Currents"
- DEFAULT_ALBUM: "Podcast Episode"

---

## Workflow Example

### 1. Prepare Your Playlist

In Music.app:
1. Create or open your playlist
2. Add music tracks and voiceover segments
3. Export: File > Library > Export Playlist
4. Choose `.m3u` format

### 2. Build the Episode

```bash
python3 build_episode_from_playlist_library.py \
  --episode-date 20250317 \
  --episode-title "Green - A Musical Journey" \
  --playlist "Green.m3u" \
  --output "Green.mp3" \
  --default-image "green-cover.jpg" \
  --bitrate 320k
```

### 3. Verify Metadata

```bash
python3 chapter-analyzer.py Green.mp3
```

### 4. Test in Podcast App

```bash
python3 serve_rss.py
# Add http://localhost:8000/feed.xml to your podcast app
```

### 5. Generate Documentation

```bash
python3 chapter-report.py Green.mp3 Green-report.html
# Open Green-report.html in your browser
```

---

## Requirements

- Python 3.7+
- ffmpeg (for audio concatenation)
- mutagen (ID3 tag handling)
- dotenv (environment configuration)

See `requirements.txt` for complete dependency list.

---

## Common Issues

### "No VO segments found"
Make sure your voiceover tracks are named with the correct date and role:
- Format: `YYYYMMDD Role` (e.g., `20250317 Intro`)
- Date must match `--episode-date` parameter
- Roles: `intro`, `outro`, `break`, `midbreak`

### Chapters show wrong artist/album
Run `chapter-analyzer.py` to inspect the actual metadata embedded in the file. The most common issue is that source tracks don't have ID3 tags set in Music.app.

### "Track not found in library"
Check that the tracks are actually imported into your Music.app library and that their paths are accessible (especially for external drives).

---

## License

These tools are provided as-is for personal podcast production use.
