# Quick Start Guide

## Web App Setup

### First Time Only
```bash
cd ~/Code/m3u-to-podcast
pip install -r requirements.txt
```

### Start the App
Run from **Terminal** (important for external drive access!):

```bash
~/Code/m3u-to-podcast/start.sh
```

Or directly:
```bash
cd ~/Code/m3u-to-podcast && python3 app.py
```

Then open your browser to **http://localhost:8080**

⚠️ **Important:** Always run from Terminal, not from an IDE. Terminal has full disk access to external drives.

## Using the Web Interface

1. **Upload** - Drag and drop a `.m3u` file onto the upload area (or click to browse)
2. **Wait** - Watch real-time progress as it processes your playlist
3. **Download** - Click buttons to download your `.mp3` and chapter file

## What Gets Generated

- **Filename.mp3** - Your concatenated podcast-ready audio file
- **Filename.txt** - Chapter markers with track names and timestamps (MM:SS format)
- **Filename_concat.txt** - Internal FFmpeg concat file (you won't need this)

## Features

✅ Automatic M4A to MP3 conversion
✅ Replaces "Equinox Speaks" tracks with silence
✅ Generates chapter markers automatically
✅ Real-time progress tracking
✅ Drag-and-drop interface
✅ Direct file downloads

## System Requirements

- Python 3.7+
- ffmpeg (for audio conversion)
- ffprobe (for duration detection)

## Troubleshooting

**Port 8080 already in use?** Edit `app.py` and change the port number in the last line.

**Conversion failing?** Check that ffmpeg is installed: `which ffmpeg`

**Files not downloading?** Try a different browser or check your download settings.
