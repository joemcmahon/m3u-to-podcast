# Getting Started with M3U to Podcast Web App

## Quick Setup (2 minutes)

### 1. Install Dependencies (first time only)
```bash
cd ~/Code/m3u-to-podcast
pip install -r requirements.txt
```

### 2. Start the App from Terminal
```bash
~/Code/m3u-to-podcast/start.sh
```

You'll see:
```
🎵 M3U to Podcast Web App
========================

Starting server on http://localhost:8080

Press Ctrl+C to stop
```

### 3. Open Your Browser
Go to **http://localhost:8080**

You should see a beautiful purple interface with an upload area.

## Using the App

1. **Drag and Drop** your `.m3u` file onto the upload area (or click "Browse Files")
2. **Wait** while the conversion happens - you'll see:
   - Progress bar showing overall completion
   - Step-by-step status (parsing playlist, preparing audio, computing chapters, merging)
   - Real-time percentage
3. **Download** your files when done:
   - Click "Download Audio (MP3)" for the concatenated podcast file
   - Click "Download Chapters" for timing markers
4. **Convert Another** to process more playlists

## Important Note: Run from Terminal

**Always run the app from Terminal, not from an IDE.**

Terminal has full disk access to your external drive, so it can read all your iTunes library files. IDEs and other apps may have sandboxing restrictions.

If you see "Operation not permitted" errors, it means the app needs to run from Terminal.

## What Gets Generated

Your downloads include:

- **{playlist}.mp3** - The combined podcast file ready to edit
  - All tracks concatenated together
  - M4A files automatically converted to MP3
  - "Equinox Speaks" tracks replaced with 10 minutes of silence

- **{playlist}.txt** - Chapter markers
  - Format: `MM:SS Track Name`
  - Import into your editor for track positioning
  - Perfect for DaVinci Resolve or other editors

## Tips & Tricks

✓ **Works with iTunes library paths** - Just export your playlist as .m3u from Music.app
✓ **Automatic M4A conversion** - No need to pre-convert
✓ **Silent replacements** - Any track with "Equinox Speaks" becomes silence automatically
✓ **Large files OK** - Can handle gigabytes
✓ **Browser-based** - No installation needed after initial setup

## Common Issues

| Problem | Solution |
|---------|----------|
| "Permission denied" error | Make sure you're running from Terminal |
| Port 8080 in use | Edit `app.py`, change port 8080 to something else |
| Conversion is slow | Large files take time. Be patient or try a smaller playlist |
| Can't find external drive | Make sure `/Volumes/Aux brain` is mounted |

## Keyboard Shortcuts

While on the app's page:
- **Cmd+V** - Paste to upload (after drag area is focused)
- **Ctrl+C** in Terminal - Stop the server

## Next Steps

- Read **QUICKSTART.md** for a quick reference
- Check **TROUBLESHOOTING.md** if you hit issues
- See **EXTERNAL_DRIVE_ACCESS.md** for detailed drive access info
- Review **README.md** for full feature list

## Questions?

The app is running locally on your machine. All processing happens on your computer - nothing is uploaded anywhere.

For issues, check the documentation files or try running the original `podcast-from-m3u.py` script directly:

```bash
python3 podcast-from-m3u.py "path/to/your.m3u"
```

Enjoy creating podcasts from your playlists! 🎵
