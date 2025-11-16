#!/bin/bash
# Start the M3U to Podcast web app

cd "$(dirname "$0")"

echo "🎵 M3U to Podcast Web App"
echo "========================"
echo ""
echo "Starting server on http://localhost:8080"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python3 app.py
