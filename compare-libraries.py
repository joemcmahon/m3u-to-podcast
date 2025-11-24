#!/usr/bin/env python3
import argparse
import plistlib
import sys
from urllib.parse import urlparse, unquote


def normalize_text(s: str) -> str:
    if s is None:
        return ""
    # lower-case, strip, collapse internal whitespace
    return " ".join(s.strip().lower().split())


def ms_to_secs(ms):
    if ms is None:
        return None
    try:
        return round(int(ms) / 1000)
    except (ValueError, TypeError):
        return None


def format_duration(secs):
    if secs is None:
        return "?:??"
    m, s = divmod(secs, 60)
    return f"{m:d}:{s:02d}"


def location_to_path(loc):
    if not loc:
        return ""
    # iTunes/Music exports as file:// URL
    try:
        parsed = urlparse(loc)
        if parsed.scheme in ("file", ""):
            return unquote(parsed.path)
        # fallback: raw string
        return unquote(loc)
    except Exception:
        return loc


def build_key(track, mode="metadata"):
    if mode == "location":
        path = location_to_path(track.get("Location", ""))
        return path.lower()

    # default: metadata-based key
    name = normalize_text(track.get("Name"))
    artist = normalize_text(track.get("Artist"))
    album = normalize_text(track.get("Album"))
    secs = ms_to_secs(track.get("Total Time"))
    return (artist, album, name, secs)


def describe_track(track):
    name = track.get("Name", "<no title>")
    artist = track.get("Artist", "<no artist>")
    album = track.get("Album", "<no album>")
    secs = ms_to_secs(track.get("Total Time"))
    loc = track.get("Location", "")
    dur = format_duration(secs)
    path = location_to_path(loc)
    base = f"{artist} – {name} ({album}) [{dur}]"
    if path:
        return f"{base}\n    {path}"
    return base


def load_library(path, mode="metadata"):
    try:
        with open(path, "rb") as f:
            pl = plistlib.load(f)
    except Exception as e:
        print(f"Error reading {path}: {e}", file=sys.stderr)
        sys.exit(1)

    tracks_dict = pl.get("Tracks", {})
    key_to_track = {}
    dup_keys = 0

    for _tid, track in tracks_dict.items():
        key = build_key(track, mode=mode)
        if not key:
            continue
        # keep the first one, count duplicates
        if key in key_to_track:
            dup_keys += 1
        else:
            key_to_track[key] = track

    return key_to_track, dup_keys


def main():
    parser = argparse.ArgumentParser(
        description="Diff two iTunes/Music.app library XML exports and "
                    "show tracks present in one but not the other."
    )
    parser.add_argument("library_a", help="Path to Library A XML (exported from Music/iTunes)")
    parser.add_argument("library_b", help="Path to Library B XML (exported from Music/iTunes)")
    parser.add_argument(
        "--by",
        choices=["metadata", "location"],
        default="metadata",
        help="How to identify tracks: "
             "'metadata' (Artist+Album+Name+Duration) or 'location' (file path). "
             "Default: metadata.",
    )
    args = parser.parse_args()

    print(f"Loading Library A from {args.library_a} …", file=sys.stderr)
    tracks_a, dups_a = load_library(args.library_a, mode=args.by)
    print(f"  {len(tracks_a)} unique track keys; {dups_a} duplicate keys", file=sys.stderr)

    print(f"Loading Library B from {args.library_b} …", file=sys.stderr)
    tracks_b, dups_b = load_library(args.library_b, mode=args.by)
    print(f"  {len(tracks_b)} unique track keys; {dups_b} duplicate keys", file=sys.stderr)

    keys_a = set(tracks_a.keys())
    keys_b = set(tracks_b.keys())

    only_in_a = sorted(keys_a - keys_b)
    only_in_b = sorted(keys_b - keys_a)

    print()
    print("========================================")
    print(" Tracks in A but NOT in B")
    print("========================================")
    if not only_in_a:
        print("(none)")
    else:
        for key in only_in_a:
            t = tracks_a[key]
            print(describe_track(t))
            print()

    print("========================================")
    print(" Tracks in B but NOT in A")
    print("========================================")
    if not only_in_b:
        print("(none)")
    else:
        for key in only_in_b:
            t = tracks_b[key]
            print(describe_track(t))
            print()


if __name__ == "__main__":
    main()

