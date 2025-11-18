#!/usr/bin/env python3
import sys
from pathlib import Path

from mutagen import File
from mutagen.id3 import (
    ID3,
    ID3NoHeaderError,
    CHAP,
    CTOC,
    APIC,
    TIT2,
    CTOCFlags,
)


def print_header(title: str):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def analyze_container(path: Path):
    print_header("BASIC FILE / CONTAINER INFO")
    audio = File(path)
    if audio is None:
        print("mutagen.File() could not identify the file.")
        return

    print(f"mutagen class: {audio.__class__.__name__}")
    mime = getattr(audio, "mime", None)
    if mime:
        print(f"MIME types: {mime}")
    info = getattr(audio, "info", None)
    if info:
        # Avoid dumping too much, just some key fields if present
        for attr in ("bitrate", "sample_rate", "channels", "length"):
            if hasattr(info, attr):
                print(f"{attr}: {getattr(info, attr)}")


def analyze_id3(path: Path):
    print_header("ID3 TAG INFO")
    try:
        id3 = ID3(path)
    except ID3NoHeaderError:
        print("No ID3 tag found in this file.")
        return None

    print(f"ID3 version: {id3.version}")
    print(f"Number of top-level frames: {len(id3.keys())}")
    # Show a quick summary of frame IDs present
    frame_counts = {}
    for key in id3.keys():
        frame_id = key[:4]  # e.g. 'TIT2', 'APIC', 'CHAP', 'CTOC'
        frame_counts[frame_id] = frame_counts.get(frame_id, 0) + 1

    print("Frame counts by ID:")
    for k in sorted(frame_counts.keys()):
        print(f"  {k}: {frame_counts[k]}")
    return id3


def analyze_global_apic(id3: ID3):
    print_header("GLOBAL APIC (IMAGES NOT TIED TO CHAPTERS)")
    apics = id3.getall("APIC")
    if not apics:
        print("No global APIC frames found.")
        return

    for i, apic in enumerate(apics, start=1):
        assert isinstance(apic, APIC)
        print(f"APIC #{i}:")
        print(f"  mime:        {apic.mime}")
        print(f"  type (pic_type): {apic.type}  (0=Other, 3=Cover(front), 4=Cover(back), etc.)")
        print(f"  desc:        {apic.desc!r}")
        print(f"  data length: {len(apic.data)} bytes")


def analyze_ctoc(id3: ID3):
    print_header("CTOC (TABLE OF CONTENTS) FRAMES")
    ctocs = id3.getall("CTOC")
    if not ctocs:
        print("No CTOC frames found.")
        return

    for i, ctoc in enumerate(ctocs, start=1):
        assert isinstance(ctoc, CTOC)
        print(f"CTOC #{i}:")
        print(f"  element_id: {ctoc.element_id!r}")

        # Mutagen exposes a bitmask in .flags
        flags = getattr(ctoc, "flags", 0)
        is_top_level = bool(flags & CTOCFlags.TOP_LEVEL)
        is_ordered = bool(flags & CTOCFlags.ORDERED)

        print(f"  flags: {flags}")
        print(f"  is_top_level: {is_top_level}")
        print(f"  is_ordered:   {is_ordered}")

        print(f"  child chapter element_ids: {ctoc.child_element_ids}")

def analyze_chap(id3: ID3):
    print_header("CHAP (CHAPTER) FRAMES")
    chaps = id3.getall("CHAP")
    if not chaps:
        print("No CHAP frames found.")
        return

    for i, chap in enumerate(chaps, start=1):
        assert isinstance(chap, CHAP)
        print(f"CHAP #{i}:")
        print(f"  element_id:   {chap.element_id!r}")
        print(f"  start_time:   {chap.start_time} ms")
        print(f"  end_time:     {chap.end_time} ms")
        print(f"  start_offset: {chap.start_offset}")
        print(f"  end_offset:   {chap.end_offset}")

        if not chap.sub_frames:
            print("  (no subframes)")
            continue

        titles = []
        images = []
        others = []

        # chap.sub_frames is a dict: {frame_id: frame_or_list_of_frames}
        for sf_id, sf_value in chap.sub_frames.items():
            # Normalize to a list so we can iterate safely
            if isinstance(sf_value, list):
                frames = sf_value
            else:
                frames = [sf_value]

            for sf in frames:
                if isinstance(sf, TIT2):
                    titles.append(sf.text)
                elif isinstance(sf, APIC):
                    images.append(sf)
                else:
                    others.append((sf_id, sf))

        if titles:
            print("  TIT2 (chapter titles):")
            for t in titles:
                print(f"    - {t}")
        else:
            print("  TIT2 (chapter titles): none")

        if images:
            print("  APIC (per-chapter images):")
            for j, apic in enumerate(images, start=1):
                print(f"    APIC #{j}:")
                print(f"      mime:        {apic.mime}")
                print(f"      type:        {apic.type}")
                print(f"      desc:        {apic.desc!r}")
                print(f"      data length: {len(apic.data)} bytes")
        else:
            print("  APIC (per-chapter images): none")

        if others:
            print("  other subframes:")
            for sf_id, sf in others:
                print(f"    - {sf_id}: {sf.__class__.__name__}")


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} path/to/file.mp3")
        sys.exit(1)

    path = Path(sys.argv[1])

    if not path.is_file():
        print(f"File not found: {path}")
        sys.exit(1)

    analyze_container(path)
    id3 = analyze_id3(path)
    if id3 is None:
        return

    analyze_global_apic(id3)
    analyze_ctoc(id3)
    analyze_chap(id3)


if __name__ == "__main__":
    main()

