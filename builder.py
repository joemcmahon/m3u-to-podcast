import os
import sys
import shlex
import subprocess

def convert_to_mp3(track):
    """Converts M4A to MP3 if needed."""
    if track.lower().endswith(".m4a"):
        mp3_track = track.rsplit(".", 1)[0] + ".mp3"
        if not os.path.exists(mp3_track):  # Avoid unnecessary conversion
            print(f"Converting: {track} → {mp3_track}")
            subprocess.run(["ffmpeg", "-i", track, "-c:a", "libmp3lame", "-q:a", "2", mp3_track], check=True)
        return mp3_track
    return track  # Return unchanged if already MP3

def parse_m3u(m3u_path):
    """Extracts track paths, filtering 'Equinox Speaks' & converting M4A."""
    tracks = []
    with open(m3u_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                track_path = line.strip()
                track_name = os.path.basename(track_path).rsplit(".", 1)[0]
                if "equinox speaks" in track_name.lower():
                    print(f"Skipping: {track_name}")
                    continue  # Exclude these
                tracks.append((convert_to_mp3(track_path), track_name))
    return tracks

def generate_ffmpeg_concat(tracks, concat_file):
    """Creates FFmpeg concat file with properly quoted filenames."""
    with open(concat_file, "w") as f:
        for track, _ in tracks:
            f.write(f"file {shlex.quote(track)}\n")

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

def merge_audio(concat_file, output_mp3):
    """Runs FFmpeg to concatenate tracks with re-encoding."""
    os.system(f"ffmpeg -f concat -safe 0 -i {shlex.quote(concat_file)} -c:a libmp3lame -q:a 2 {shlex.quote(output_mp3)}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python builder.py <playlist.m3u>")
        sys.exit(1)

    m3u_file = sys.argv[1]
    base_name = os.path.splitext(m3u_file)[0]
    concat_file = f"{base_name}_concat.txt"
    output_mp3 = f"{base_name}.mp3"
    chapter_file = f"{base_name}.txt"

    tracks = parse_m3u(m3u_file)
    generate_ffmpeg_concat(tracks, concat_file)
    generate_chapter_file(tracks, chapter_file)
    merge_audio(concat_file, output_mp3)

    print(f"✅ Chapter file '{chapter_file}' generated.")
    print(f"✅ Merged audio '{output_mp3}' created.")
