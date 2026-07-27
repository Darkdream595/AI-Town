---
name: lpc-spritesheet-slicer
description: Slice Universal LPC Spritesheet Character Generator PNG exports into individual animation frames (all animations x directions x frames) as game-ready PNG files. Use when asked to cut/split/extract LPC spritesheets, LPC frame extraction, 64x64 grid slicing, walk/spellcast/slash frame extraction, or converting a downloaded LPC sheet into per-frame assets. Covers the full validated layout (15 base animations + oversized weapon animations at 128/192 px), direction order, auto-detection of extended regions, and batch processing.
---

# LPC Spritesheet Slicer

Cut LPC generator spritesheet PNGs into per-frame files named
`{character}_{animation}_{direction}_{frame}.png` using
`scripts/slice.py` (Pillow only, no other deps).

## Layout facts (validated — do not re-derive)

**Base region — every sheet, 64 px grid, rows 0–53.** Direction order inside
every 4-row block is always `north, west, south, east`:

| animation    | rows  | frames/dir | notes              |
|--------------|-------|------------|--------------------|
| spellcast    | 0–3   | 7          |                    |
| thrust       | 4–7   | 8          |                    |
| walk         | 8–11  | 9          | col 0 = standing   |
| slash        | 12–15 | 6          |                    |
| shoot        | 16–19 | 13         |                    |
| hurt         | 20    | 6          | **south only**     |
| climb        | 21    | 6          | **north only**     |
| idle         | 22–25 | 2          |                    |
| jump         | 26–29 | 5          |                    |
| sit          | 30–33 | 3          |                    |
| emote        | 34–37 | 3          |                    |
| run          | 38–41 | 8          |                    |
| combat_idle  | 42–45 | 2          |                    |
| 1h_backslash | 46–49 | 13         |                    |
| 1h_halfslash | 50–53 | 6          |                    |

`hurt` having only a south row and `climb` only a north row is the official
LPC layout, not missing data. Walk's renderer cycle is columns 1–8, but slice
all 9 columns (column 0 is the standing frame).

**Extended region — starts at row 54, exists only for oversized weapons/tools.**
Each extended animation uses square frames of `frame_px` (128 or 192) and
occupies 4 direction bands of `frame_px/64` rows (128 px → 8 rows total,
192 px → 12 rows total), same N/W/S/E order. Sheet width =
`frame_px × frames_of_the_widest_animation`. Shorter animations are padded
with transparent columns — the script skips fully transparent frames, so
auto-detection stays correct.

Known item → extended animation names (from item metadata `animations` field):

| item (hash value)              | animation(s), top-to-bottom from row 54                | frame px |
|--------------------------------|--------------------------------------------------------|----------|
| `weapon=Hammer`                | tool_hammer (9 frames)                                 | 128      |
| `weapon=Pickaxe`               | tool_axe (10 frames)                                   | 128      |
| `weapon=Normal_medium` (bow)   | walk_128 (9 frames)                                    | 128      |
| `weapon_magic_crystal=...`     | thrust_oversize (8 frames)                             | 192      |
| `weapon=Longsword_longsword`   | slash_oversize (6), slash_reverse_oversize (6), thrust_oversize (8) | 192 |

A sheet with no extended region is exactly 832×3456 px (13 cols × 54 rows).

## How to run

```bash
python scripts/slice.py <raw_dir> <output_dir> [--names names.json]
```

- One PNG per character in `raw_dir`; filename (minus `.png`) becomes the
  character name.
- Output: `<output_dir>/<character>/<character>_<anim>_<dir>_<frame>.png`.
- Extended animations are auto-detected from sheet width/height. Without
  `--names` they are called `extra0`, `extra1`, … top-to-bottom. Pass a JSON
  map to get real names (order = top-to-bottom starting at row 54):

```json
{
  "human_guard": ["slash_oversize", "slash_reverse_oversize", "thrust_oversize"],
  "dwarf_blacksmith": ["tool_hammer"],
  "dwarf_miner": ["tool_axe"],
  "human_hunter": ["walk_128"],
  "elf_alchemist": ["thrust_oversize"]
}
```

## Verification (do this after slicing)

1. **Counts**: a base-only character yields 352 files (15 anims). Extended
   regions add `frames × 4` per anim (e.g. tool_hammer +36, guard's three
   oversize anims +72 after empty-frame skipping).
2. **Eyeball a contact sheet**: paste `walk` frames 0–2 for all 4 directions
   into one image at 3× nearest-neighbor and confirm north = back view,
   south = front view, west/east = correct profiles. For 128/192 px anims
   check the character is complete inside each tile (not split across tiles);
   if tiles are split, the extended auto-detection picked the wrong frame
   size — inspect the sheet and report instead of guessing.

## Gotchas

- Never infer direction from column order — direction bands are **rows**;
  columns are frames.
- Sheets are RGBA with transparent padding; always skip empty tiles rather
  than emitting blank frames.
- If a future LPC version adds base animations, row offsets shift. Re-derive
  from the renderer constants (`lt`/`ut` in the generator's JS) or from a
  row-wise ink (alpha-sum) profile before slicing.
