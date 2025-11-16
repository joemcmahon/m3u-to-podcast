#!/usr/bin/env python3
"""
Flask web application for m3u-to-podcast conversion.
"""
import os
import json
import shlex
import subprocess
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from threading import Thread

app = Flask(__name__, template_folder='web', static_folder='web/static')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
app.config['UPLOAD_FOLDER'] = 'uploads'

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Global state for progress tracking
conversion_state = {}

def create_silence_file():
    """Generates 10 minutes of silence."""
    silence_file = os.path.abspath("silence.mp3")
    if not os.path.exists(silence_file):
        app.logger.info("Creating silence file...")
        subprocess.run(["ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "600", "-q:a", "2", silence_file], check=True)
    return silence_file

def convert_to_mp3(track):
    """Converts M4A to MP3 if needed."""
    if track.lower().endswith(".m4a"):
        mp3_track = track.rsplit(".", 1)[0] + ".mp3"
        if not os.path.exists(mp3_track):
            app.logger.info(f"Converting: {track} → {mp3_track}")
            try:
                subprocess.run(["ffmpeg", "-i", track, "-c:a", "libmp3lame", "-q:a", "2", mp3_track], check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr.decode() if e.stderr else str(e)
                if "Operation not permitted" in error_msg or "Permission denied" in error_msg:
                    raise Exception(
                        f"Permission denied accessing file: {track}\n"
                        f"This is a macOS sandboxing issue. Run the app from Terminal, or grant ffmpeg Full Disk Access:\n"
                        f"System Settings > Privacy & Security > Full Disk Access, then add Terminal (or your shell)"
                    )
                raise
        return mp3_track
    return track

def parse_m3u(m3u_path):
    """Extracts track paths, converting M4A and replacing 'Equinox Speaks' with silence."""
    tracks = []
    silence_file = create_silence_file()
    with open(m3u_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                track_path = line.strip()
                # Resolve to absolute path if it's relative
                if not os.path.isabs(track_path):
                    track_path = os.path.abspath(track_path)
                track_name = os.path.basename(track_path).rsplit(".", 1)[0]
                if "equinox speaks" in track_name.lower():
                    app.logger.info(f"Replacing: {track_name} → Silence")
                    tracks.append((silence_file, "Silence Placeholder"))
                else:
                    tracks.append((convert_to_mp3(track_path), track_name))
    return tracks

def generate_ffmpeg_concat(tracks, concat_file):
    """Creates FFmpeg concat file with properly escaped filenames."""
    with open(concat_file, "w") as f:
        for track, _ in tracks:
            safe_track = track.replace("'", "'\\''")
            f.write(f"file '{safe_track}'\n")

def get_track_duration(track):
    """Gets track duration, handling missing durations."""
    cmd = f"ffprobe -i {shlex.quote(track)} -show_entries format=duration -v quiet -of csv=p=0"
    duration = os.popen(cmd).read().strip()
    return int(float(duration)) if duration else 0

def generate_chapter_file(tracks, chapter_file):
    """Creates a chapter file in MM::SS format."""
    with open(chapter_file, "w") as f:
        elapsed_time = 0
        for track, name in tracks:
            f.write(f"{elapsed_time//60:02}:{elapsed_time%60:02} {name}\n")
            elapsed_time += get_track_duration(track)

def merge_audio(concat_file, output_mp3, job_id):
    """Runs FFmpeg to concatenate tracks with re-encoding."""
    os.system(f"ffmpeg -f concat -safe 0 -i {shlex.quote(concat_file)} -c:a libmp3lame -q:a 2 {shlex.quote(output_mp3)}")
    conversion_state[job_id]['status'] = 'complete'

def process_conversion(m3u_file, output_dir, job_id):
    """Background task for conversion."""
    try:
        conversion_state[job_id] = {'status': 'processing', 'progress': 0, 'message': 'Starting conversion...'}

        base_name = os.path.splitext(os.path.basename(m3u_file))[0]
        concat_file = os.path.join(output_dir, f"{base_name}_concat.txt")
        output_mp3 = os.path.join(output_dir, f"{base_name}.mp3")
        chapter_file = os.path.join(output_dir, f"{base_name}.txt")

        conversion_state[job_id]['message'] = 'Parsing playlist...'
        tracks = parse_m3u(m3u_file)

        conversion_state[job_id]['message'] = 'Generating concat file...'
        generate_ffmpeg_concat(tracks, concat_file)

        conversion_state[job_id]['message'] = 'Computing chapter durations...'
        generate_chapter_file(tracks, chapter_file)

        conversion_state[job_id]['message'] = 'Merging audio files...'
        conversion_state[job_id]['progress'] = 50
        merge_audio(concat_file, output_mp3, job_id)

        conversion_state[job_id]['progress'] = 100
        conversion_state[job_id]['message'] = 'Complete!'
        conversion_state[job_id]['status'] = 'complete'
        conversion_state[job_id]['output_files'] = {
            'mp3': output_mp3,
            'chapters': chapter_file,
            'concat': concat_file
        }
    except Exception as e:
        conversion_state[job_id]['status'] = 'error'
        conversion_state[job_id]['message'] = str(e)
        app.logger.error(f"Conversion error: {e}")

@app.route('/')
def index():
    """Serve the main page."""
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Handle m3u file upload."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not file.filename.lower().endswith('.m3u'):
        return jsonify({'error': 'File must be .m3u format'}), 400

    filename = secure_filename(file.filename)
    output_dir = os.path.join(app.config['UPLOAD_FOLDER'], Path(filename).stem)
    os.makedirs(output_dir, exist_ok=True)

    m3u_path = os.path.join(output_dir, filename)
    file.save(m3u_path)

    # Start conversion in background
    job_id = f"{Path(filename).stem}_{datetime.now().timestamp()}"
    thread = Thread(target=process_conversion, args=(m3u_path, output_dir, job_id))
    thread.daemon = True
    thread.start()

    return jsonify({'job_id': job_id, 'filename': filename})

@app.route('/api/status/<job_id>')
def get_status(job_id):
    """Get conversion status."""
    if job_id not in conversion_state:
        return jsonify({'error': 'Job not found'}), 404

    return jsonify(conversion_state[job_id])

@app.route('/api/download/<job_id>/<file_type>')
def download_file(job_id, file_type):
    """Download converted files."""
    if job_id not in conversion_state or conversion_state[job_id]['status'] != 'complete':
        return jsonify({'error': 'Conversion not complete'}), 400

    files = conversion_state[job_id].get('output_files', {})
    if file_type == 'mp3':
        file_path = files.get('mp3')
    elif file_type == 'chapters':
        file_path = files.get('chapters')
    else:
        return jsonify({'error': 'Invalid file type'}), 400

    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404

    return send_file(file_path, as_attachment=True)

@app.route('/api/health')
def health():
    """Health check."""
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(debug=True, port=8080)
