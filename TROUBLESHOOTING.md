# Troubleshooting

## Permission Error: "Operation not permitted" on External Drive

If you see an error like:
```
Permission denied accessing file: /Volumes/Aux brain/...
This is a macOS sandboxing issue.
```

This happens when trying to access files on an external drive. macOS restricts access to external drives for security.

### Solution 1: Run from Terminal (Quickest)

Run the Flask app directly from Terminal instead:

```bash
cd ~/Code/m3u-to-podcast
python3 app.py
```

Then open http://localhost:8080 in your browser. Terminal has full disk access by default.

### Solution 2: Grant Full Disk Access (Permanent)

If you're running the app from somewhere else (like an IDE), you need to grant it full disk access:

1. **Open System Settings**
2. Go to **Privacy & Security** → **Full Disk Access**
3. Click the **+** button
4. Navigate to `/Applications/Utilities/Terminal.app` (or your shell/IDE)
5. Click **Open**
6. You may need to restart the app

### Solution 3: Pre-convert M4A to MP3

If the permission issue persists, pre-convert your M4A files to MP3 before creating the m3u playlist. This avoids the permission check entirely.

## File Not Found Errors

If you get "file not found" errors:
- Make sure the external drive is mounted (check `/Volumes/`)
- Verify the paths in your m3u file point to actual files
- Use absolute paths in m3u files (like `/Volumes/Aux brain/...`)

## Conversion Hangs

If the conversion seems to hang:
- Wait longer (large files take time)
- Check the browser console for status updates
- Try a smaller playlist first

## Port Already in Use

If port 8080 is in use, edit `app.py` and change:
```python
app.run(debug=True, port=8080)  # Change 8080 to something else
```

Then restart the app.
