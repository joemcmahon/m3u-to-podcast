# Accessing Files on External Drive

The M3U to Podcast app needs to read audio files from your external iTunes drive. Here's how to make sure it works:

## The Issue

When running the app from an IDE or restricted environment, it may get permission errors when trying to access files on external drives:

```
Permission denied accessing file: /Volumes/Aux brain/...
Operation not permitted
```

This is a macOS sandboxing restriction, not a bug.

## Solution: Run from Terminal

**The simplest fix is to run the app from Terminal:**

```bash
cd ~/Code/m3u-to-podcast
python3 app.py
```

Or use the convenience script:

```bash
~/Code/m3u-to-podcast/start.sh
```

Then open http://localhost:8080 in your browser.

### Why This Works

Terminal.app has full disk access permissions on macOS, so it can read from external drives. When you run the app from Terminal, Flask inherits those permissions.

## Alternative: Grant Full Disk Access

If you want to run the app from an IDE, you can grant it full disk access:

1. **System Settings** → **Privacy & Security** → **Full Disk Access**
2. Click the **+** button
3. Add the IDE application (or Terminal.app)
4. Restart the app

## What Gets Accessed

The app reads:
- **M3U playlist files** you upload
- **Audio files** referenced in the playlists (MP3, M4A, AIFF, etc.)
- Creates **converted output files** in the upload directory

All input files must be readable from the paths specified in your m3u file.

## File Paths in M3U Files

Make sure your m3u files use full paths:

✓ **Good:**
```
#EXTM3U
#EXTINF:300,Song Title
/Volumes/Aux brain/iTunes Libraries/...Music/Song.mp3
```

✗ **Bad (relative paths may not work):**
```
Music/Song.mp3
./Song.mp3
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Permission denied on external drive | Run from Terminal instead of IDE |
| File not found | Check external drive is mounted: `ls /Volumes/` |
| M4A conversion fails | Make sure M4A files exist and are readable |
| Conversion hangs | Check the browser console for progress; large files take time |

## Pre-converting M4A Files

If you continue to have issues with M4A files, you can pre-convert them to MP3:

```bash
ffmpeg -i "input.m4a" -c:a libmp3lame -q:a 2 "input.mp3"
```

Then update your m3u file to reference the MP3 instead of the M4A.
