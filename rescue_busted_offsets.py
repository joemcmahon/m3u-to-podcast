#!/usr/bin/env python3
"""
Attempt to "rescue" chapterized MP3s where CHAP byte offsets have been
written with bogus sentinel values (e.g., 0xFFFFFFFF / 4294967295),
while preserving:

- chapter start/end times (in ms),
- chapter titles,
- per-chapter APIC artwork,
- all other tags,
- and all audio data.

This script:

  1. Copies the input MP3 to an output path (so the original is untouched).
  2. Loads ID3 tags from the *output* file.
  3. For each CHAP frame:
       - If start_offset or end_offset look like "nil" values
         (e.g., >= 0xFFFFFF00), they are set to 0.
  4. Saves the updated tags as ID3v2.3.

Usage:

    python rescue_chap_offsets.py broken.mp3
    python rescue_chap_offsets.py broken.mp3 fixed.mp3
    python rescue_chap_offsets.py --in-place broken.mp3

If the output path is omitted, it defaults to:

    broken.rescued.mp3

With --in-place the file itself is fixed. Before touching it, a backup is copied
next to it as "<name>.before-rescue.mp3" (numbered if that name is taken); use
--no-backup to skip the backup. A file that needs no fixing is left untouched.
"""

import argparse
import shutil
import sys
from pathlib import Path

from mutagen import MutagenError
from mutagen.id3 import (
    ID3,
    ID3NoHeaderError,
    CHAP,
)


# Heuristic for "bogus" offsets: near-uint32-max sentinel values
NIL_OFFSET_THRESHOLD = 0xFFFFFF00  # 4294967040


def debug(msg: str):
    print(f"[DEBUG] {msg}")


def load_id3(path: Path) -> ID3:
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        raise SystemExit(f"[ERROR] No ID3 tag found in {path}")
    except MutagenError as e:
        raise SystemExit(f"[ERROR] Failed to load ID3 from {path}: {e}")
    return tags


def is_nil_offset(value: int) -> bool:
    """
    Return True if 'value' looks like a sentinel "no offset" value,
    e.g. 0xFFFFFFFF or something very close to that.
    """
    if value is None:
        return False
    if value >= NIL_OFFSET_THRESHOLD:
        return True
    return False


def rescue_chap_offsets(tags: ID3) -> int:
    """
    Modify CHAP frames in-place:
    - any start_offset / end_offset that looks like a bogus sentinel
      (0xFFFFFFFF, etc.) is reset to 0.

    Returns the number of CHAP frames modified.
    """
    chap_frames = tags.getall("CHAP")
    if not chap_frames:
        print("[INFO] No CHAP frames found; nothing to do.")
        return 0

    print(f"[INFO] Found {len(chap_frames)} CHAP frame(s).")

    changed = 0
    for chap in chap_frames:
        # chap.start_offset and chap.end_offset are ints
        so = getattr(chap, "start_offset", None)
        eo = getattr(chap, "end_offset", None)

        new_so = so
        new_eo = eo

        if so is not None and is_nil_offset(so):
            new_so = 0
        if eo is not None and is_nil_offset(eo):
            new_eo = 0

        if new_so != so or new_eo != eo:
            print(
                f"[INFO] CHAP {chap.element_id!r}: "
                f"start_offset {so} -> {new_so}, "
                f"end_offset {eo} -> {new_eo}"
            )
            chap.start_offset = new_so
            chap.end_offset = new_eo
            changed += 1

    return changed


def unique_backup_path(path: Path) -> Path:
    """<name>.before-rescue.mp3, or <name>.before-rescue-2.mp3, ... never an existing file."""
    candidate = path.with_name(f"{path.stem}.before-rescue{path.suffix}")
    n = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}.before-rescue-{n}{path.suffix}")
        n += 1
    return candidate


def rescue_in_place(input_path: Path, backup: bool) -> None:
    print(f"[INFO] Loading ID3 tags from {input_path}")
    tags = load_id3(input_path)
    modified = rescue_chap_offsets(tags)

    if modified == 0:
        print("[INFO] No CHAP offsets needed fixing. File left untouched.")
        return

    if backup:
        backup_path = unique_backup_path(input_path)
        print(f"[INFO] Backing up {input_path} → {backup_path}")
        shutil.copy2(input_path, backup_path)
        if backup_path.stat().st_size != input_path.stat().st_size:
            raise SystemExit(f"[ERROR] Backup size mismatch; {input_path} not modified.")

    print(f"[INFO] Saving updated ID3 tags to {input_path} as v2.3 (in place)")
    tags.save(input_path, v2_version=3)
    print(f"[INFO] Done. Modified {modified} CHAP frame(s).")


def main():
    parser = argparse.ArgumentParser(
        description="Reset bogus CHAP byte offsets (e.g. 0xFFFFFFFF written by some editors) to 0.")
    parser.add_argument("input", type=Path, help="MP3 with chapters")
    parser.add_argument("output", type=Path, nargs="?",
                        help="Where to write the fixed copy (default: <name>.rescued.mp3)")
    parser.add_argument("--in-place", action="store_true",
                        help="Fix the file itself (a backup is made first)")
    parser.add_argument("--no-backup", action="store_true",
                        help="With --in-place: do not keep a backup copy")
    args = parser.parse_args()

    input_path = args.input
    if not input_path.is_file():
        print(f"[ERROR] Input file not found: {input_path}")
        sys.exit(1)

    if args.in_place:
        if args.output:
            parser.error("--in-place cannot be combined with an output path")
        rescue_in_place(input_path, backup=not args.no_backup)
        print("[INFO] Rescue run complete.")
        return
    if args.no_backup:
        parser.error("--no-backup only applies with --in-place")

    output_path = args.output or input_path.with_suffix(".rescued.mp3")

    if output_path.exists():
        print(f"[ERROR] Output file already exists: {output_path}")
        print("       Refusing to overwrite. Choose a different output path.")
        sys.exit(1)

    # 1. Copy original → output
    print(f"[INFO] Copying {input_path} → {output_path}")
    shutil.copy2(input_path, output_path)

    # 2. Load tags from the *output* file
    print(f"[INFO] Loading ID3 tags from {output_path}")
    tags = load_id3(output_path)

    # 3. Try to rescue CHAP offsets
    modified = rescue_chap_offsets(tags)

    if modified == 0:
        print("[INFO] No CHAP offsets needed fixing. Tags unchanged.")
    else:
        # 4. Save tags as ID3v2.3
        print(f"[INFO] Saving updated ID3 tags to {output_path} as v2.3")
        tags.save(output_path, v2_version=3)
        print(f"[INFO] Done. Modified {modified} CHAP frame(s).")

    print("[INFO] Rescue run complete.")


if __name__ == "__main__":
    main()

