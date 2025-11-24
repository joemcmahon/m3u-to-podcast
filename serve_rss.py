#!/usr/bin/env python3
"""
Simple RSS feed server for testing podcast episodes locally.
Serves an RSS feed on http://localhost:8000/feed.xml
The episode points to the local Green.mp3 file.
"""

import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from mutagen.id3 import ID3
from urllib.parse import urljoin


class RSSHandler(BaseHTTPRequestHandler):
    # Path to the episode MP3
    EPISODE_FILE = Path("Green.mp3").resolve()
    EPISODE_URL = "http://localhost:8000/episode.mp3"

    def do_GET(self):
        if self.path == "/feed.xml":
            self.serve_rss()
        elif self.path == "/episode.mp3":
            self.serve_mp3()
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")

    def serve_rss(self):
        """Serve the RSS feed."""
        if not self.EPISODE_FILE.exists():
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Episode file not found")
            return

        # Get episode metadata from ID3 tags
        tags = ID3(self.EPISODE_FILE)
        title = tags.get("TIT2")
        title_str = str(title.text[0]) if title else "Episode"

        artist = tags.get("TPE1")
        artist_str = str(artist.text[0]) if artist else "Unknown"

        # File size for RSS
        file_size = self.EPISODE_FILE.stat().st_size

        # Get duration from audio info
        from mutagen import File as MutagenFile
        audio = MutagenFile(self.EPISODE_FILE)
        duration = int(audio.info.length) if audio and hasattr(audio.info, 'length') else 0

        # Simple RSS feed with iTunes namespace
        rss = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>{artist_str}</title>
    <link>http://localhost:8000</link>
    <description>Local podcast feed for testing</description>
    <language>en-us</language>
    <itunes:author>{artist_str}</itunes:author>
    <item>
      <title>{title_str}</title>
      <description>{title_str}</description>
      <enclosure url="{self.EPISODE_URL}" length="{file_size}" type="audio/mpeg"/>
      <pubDate>Wed, 01 Jan 2025 00:00:00 GMT</pubDate>
      <itunes:duration>{duration}</itunes:duration>
      <itunes:author>{artist_str}</itunes:author>
    </item>
  </channel>
</rss>'''

        self.send_response(200)
        self.send_header("Content-type", "application/rss+xml")
        self.send_header("Content-Length", len(rss.encode()))
        self.end_headers()
        self.wfile.write(rss.encode())

    def serve_mp3(self):
        """Serve the MP3 file."""
        if not self.EPISODE_FILE.exists():
            self.send_response(404)
            self.end_headers()
            return

        file_size = self.EPISODE_FILE.stat().st_size
        self.send_response(200)
        self.send_header("Content-type", "audio/mpeg")
        self.send_header("Content-Length", file_size)
        self.end_headers()

        with open(self.EPISODE_FILE, "rb") as f:
            self.wfile.write(f.read())

    def log_message(self, format, *args):
        """Suppress default logging."""
        return


def main():
    port = 8000
    server = HTTPServer(("localhost", port), RSSHandler)
    print(f"Serving RSS feed at http://localhost:{port}/feed.xml")
    print(f"Episode MP3 at http://localhost:{port}/episode.mp3")
    print(f"\nAdd http://localhost:{port}/feed.xml to your podcast app")
    print("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
