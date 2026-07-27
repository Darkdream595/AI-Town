#!/usr/bin/env python3
"""
LPC spritesheet slicer.

Cuts every frame (all animations x directions x frames) out of Universal LPC
Spritesheet Character Generator PNG exports.

Layout facts (validated against the generator's renderer source + pixel tests):
  - Base region is a 64 px grid; rows 0..53.
  - Direction order inside every 4-row block: north, west, south, east.
  - hurt  = row 20 only (south); climb = row 21 only (north).
  - Extended region starts at row 54 and only exists when the character uses
    oversized weapons/tools. Each extended animation uses frames of
    frame_px x frame_px (128 or 192) and occupies 4 direction bands of
    frame_px/64 rows each. Sheet width = frames_of_widest_anim * frame_px.

Usage:
  python slice.py <input_dir> <output_dir> [--names names.json]

  input_dir : folder with raw LPC sheet PNGs (one per character)
  output_dir: frames are written to <output_dir>/<character>/<character>_<anim>_<dir>_<i>.png
  --names   : optional JSON mapping character -> list of extended animation
              names, e.g. {"human_guard": ["slash_oversize",
              "slash_reverse_oversize", "thrust_oversize"]}
              Order must match top-to-bottom order in the sheet (row 54 down).
              Without it, extended anims are named extra0, extra1, ...

Fully transparent frames (padding when an anim has fewer frames than the
sheet's widest) are skipped automatically.
"""

import json
import os
import sys

from PIL import Image

CELL = 64
DIRS = ["north", "west", "south", "east"]

# name, first row, number of 64px rows (4 = full direction block,
# 1 = single-direction row), frames per direction, fixed direction for
# single-row anims
BASE = [
    ("spellcast",     0, 4,  7, None),
    ("thrust",        4, 4,  8, None),
    ("walk",          8, 4,  9, None),
    ("slash",        12, 4,  6, None),
    ("shoot",        16, 4, 13, None),
    ("hurt",         20, 1,  6, "south"),
    ("climb",        21, 1,  6, "north"),
    ("idle",         22, 4,  2, None),
    ("jump",         26, 4,  5, None),
    ("sit",          30, 4,  3, None),
    ("emote",        34, 4,  3, None),
    ("run",          38, 4,  8, None),
    ("combat_idle",  42, 4,  2, None),
    ("1h_backslash", 46, 4, 13, None),
    ("1h_halfslash", 50, 4,  6, None),
]
BASE_ROWS = 54  # extended region starts here


def is_empty(tile):
    """True when the tile has no visible pixel."""
    alpha = tile.getchannel("A")
    lo, hi = alpha.getextrema()
    return hi == 0


def save(tile, out_dir, stem):
    if is_empty(tile):
        return False
    tile.save(os.path.join(out_dir, stem + ".png"))
    return True


def slice_base(img, char, out_dir):
    count, anims = 0, []
    for name, row0, nrows, frames, fixed_dir in BASE:
        anims.append(name)
        dirs = [fixed_dir] if fixed_dir else DIRS
        for band, d in enumerate(dirs):
            y = (row0 + band) * CELL
            for f in range(frames):
                tile = img.crop((f * CELL, y, (f + 1) * CELL, y + CELL))
                if save(tile, out_dir, f"{char}_{name}_{d}_{f}"):
                    count += 1
    return count, anims


def detect_extras(img):
    """Return list of (frame_px, n_anims) for the extended region, or []."""
    w, h = img.size
    rows = h // CELL
    extra_rows = rows - BASE_ROWS
    if extra_rows <= 0:
        return []
    for fp in (192, 128):
        band_rows = 4 * (fp // CELL)
        if w % fp == 0 and extra_rows % band_rows == 0:
            return [(fp, extra_rows // band_rows)]
    raise ValueError(
        f"cannot auto-detect extended layout: {w}x{h} "
        f"({extra_rows} extra rows) - pass explicit config"
    )


def slice_extras(img, char, out_dir, names):
    w, _ = img.size
    detected = detect_extras(img)
    if not detected:
        return 0, []
    count, anims = 0, []
    row = BASE_ROWS
    idx = 0
    for frame_px, n in detected:
        frames = w // frame_px
        band_rows = frame_px // CELL
        for _ in range(n):
            name = names[idx] if idx < len(names) else f"extra{idx}"
            idx += 1
            anims.append(name)
            for band, d in enumerate(DIRS):
                y = (row + band * band_rows) * CELL
                for f in range(frames):
                    x = f * frame_px
                    tile = img.crop((x, y, x + frame_px, y + frame_px))
                    if save(tile, out_dir, f"{char}_{name}_{d}_{f}"):
                        count += 1
            row += 4 * band_rows
    return count, anims


def main():
    argv = sys.argv[1:]
    names_map = {}
    if "--names" in argv:
        i = argv.index("--names")
        with open(argv[i + 1], encoding="utf-8") as fh:
            names_map = json.load(fh)
        del argv[i:i + 2]
    if len(argv) != 2:
        sys.exit(__doc__)
    in_dir, out_root = argv

    total = 0
    for fn in sorted(os.listdir(in_dir)):
        if not fn.lower().endswith(".png"):
            continue
        char = os.path.splitext(fn)[0]
        img = Image.open(os.path.join(in_dir, fn)).convert("RGBA")
        out_dir = os.path.join(out_root, char)
        os.makedirs(out_dir, exist_ok=True)
        n_base, anims = slice_base(img, char, out_dir)
        n_extra, extra_anims = slice_extras(
            img, char, out_dir, names_map.get(char, []))
        anims += extra_anims
        total += n_base + n_extra
        print(f"{char:<20} files={n_base + n_extra:<4} anims={len(anims)}")
        print(f"    {','.join(anims)}")
    print(f"TOTAL FILES: {total}")


if __name__ == "__main__":
    main()
