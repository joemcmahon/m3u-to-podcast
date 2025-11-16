# m3u to Podcast

More than once, I've hit the problem of not getting a good recording of my live broadcast
when I'm doing my radio show, which means no podcast for that week. 

I _do_ however, have the Music.app playlists that I use to play the music and
voiceover breaks, and I decided to assemble a handy little script to recreate
the _music_ portion of the podcast, allowing me to pull it into whatever editor
and record replacement voiceovers, giving me a slightly ersatz version of the
original.

Since a slightly fake live show is better than no show at all, I'm using this
to cover for me on those days when I screw the pooch and lose the recording.

## Usage

### Web Interface (Recommended)

The easiest way to use this tool is through the web interface:

1. Install dependencies (first time only):
   ```bash
   pip install -r requirements.txt
   ```

2. Start the server from Terminal:
   ```bash
   ~/Code/m3u-to-podcast/start.sh
   ```

   Or run directly:
   ```bash
   cd ~/Code/m3u-to-podcast && python3 app.py
   ```

   **Important:** Run from Terminal, not from an IDE. Terminal has full disk access to external drives.

3. Open your browser to `http://localhost:8080`

4. Drag and drop your `.m3u` file onto the upload area and watch the conversion happen in real-time

5. Download your converted MP3 and chapter file when complete

### Command-Line Usage

If you prefer the original command-line interface:

1. Open Music.app and click on a playlist in the left sidebar.
2. File > Library > Export Playlist...
3. Select the target folder, and choose `m3u` as the output format
4. `python3 podcast-from-m3u.py "Path to the.m3u"`

This will create:
- An `.mp3` file of all the tracks concatenated
- A `.txt` file with chapter markers and timestamps for each track

## Features

- **Drag & drop upload** - Simply drag your .m3u file onto the interface
- **Real-time progress** - Watch the conversion happen step-by-step
- **Automatic silence insertion** - Replaces "Equinox Speaks" tracks with silence
- **M4A conversion** - Automatically converts M4A files to MP3
- **Chapter support** - Generates chapter markers with track names and timestamps
- **Direct download** - Download your files immediately after conversion

## Output Files

- **{playlist_name}.mp3** - The concatenated audio file ready for editing
- **{playlist_name}.txt** - Chapter markers in MM:SS format with track names
- **{playlist_name}_concat.txt** - FFmpeg concat file (for reference)
