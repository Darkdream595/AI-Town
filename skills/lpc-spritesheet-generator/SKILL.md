---
name: lpc-spritesheet-generator
description: Generate RPG character sprite sheets (PNG) from the Universal LPC Spritesheet Character Generator website (sanderfrenken.github.io / liberatedpixelcup.github.io) by driving the user's real browser with kimi-webbridge. Use when asked to create LPC characters, RPG sprites, pixel-art NPC sheets, configure body/hair/torso/legs/weapons on the LPC generator, or batch-download character spritesheets. Covers one-shot URL-hash configuration, UI tree fallback, preview verification, and the download/rename pipeline.
---

# LPC Spritesheet Generator

Drive the Universal LPC Spritesheet Character Generator through kimi-webbridge (local daemon `http://127.0.0.1:10086`) to configure characters and export full spritesheet PNGs.

**Read `references/hash-catalog.md` before configuring** — it has every validated hash key/value, the item-discovery recipe, and ready-made character configs. **Read `references/troubleshooting.md` when anything fails** (clicks ignored, modals, stalled downloads).

## Hard-won facts (do not relearn)

- Site redirects to `https://liberatedpixelcup.github.io/Universal-LPC-Spritesheet-Character-Generator/`.
- App state lives in the **URL hash**. Setting `location.hash = '...'` reconfigures the whole character instantly (hashchange listener, ~1 s). This is the "one-shot" configuration path — far more reliable than clicking the tree.
- After reload, the item tree takes 5–10 s to render. Wait and re-query before concluding anything is missing.
- Synthetic `el.click()` is **unreliable** on this app. Use CDP trusted input (`Input.dispatchMouseEvent` pressed+released) for every real click.
- The `Messy` hair style does not render (selection sticks, sprite stays bald). Use `Bob`, `Plain`, `Long_tied`, or `Bangslong` instead.
- Never override `navigator.clipboard` — it hangs the page JS permanently.

## Pipeline (per character)

### 1. Open the site

One session per batch task (e.g. `session: "lpc-sprites"`); set `group_title` on first navigate. On Windows, POST every request body from a file with `curl.exe --data-binary "@file"`.

```
{"action":"navigate","args":{"url":"https://liberatedpixelcup.github.io/Universal-LPC-Spritesheet-Character-Generator/","newTab":true,"group_title":"LPC sprite 生成"},"session":"lpc-sprites"}
```

### 2. Configure with one URL hash (preferred)

Set `location.hash` via `evaluate`, wait ~1.2 s, done. Format:

```
#sex=<male|female>&body=Body_Color_light&head=Human_Male_light|Human_Female_light&expression=Neutral_light&<key>=<Name_underscored>[_variant]&...
```

- Keys come from the item's `type_name`: `hair`, `beard`, `ears`, `clothes`, `apron`, `vest`, `armour`, `chainmail`, `legs`, `weapon`, `shield`, `ammo`, `charm`, `backpack`, `belt`, `weapon_magic_crystal`, … (full table + validated values in `references/hash-catalog.md`).
- Value = item display name with spaces → underscores, plus optional `_variant` (color/material). Omitting the variant applies the default (e.g. `weapon=Hoe` → `Hoe (ceramic)`).
- Invalid keys/values are **silently ignored** — always verify in step 3.
- Multiple slots coexist: `weapon=Longsword_longsword&shield=Kite_kite gray`, `weapon=Normal_medium&ammo=Ammo_arrow`, `hair=...+beard=...`.
- `sex` change may drop incompatible items — put `sex` first in the hash.

### 3. Verify selection AND rendering

Two checks, both required:

1. **Current Selections text** — read the `h3` "Current Selections" parent text; every configured item must appear as `Name (variant)`.
2. **Rendered preview** — hair and key items sometimes stick in selections but fail to render (see `Messy` bug, and modals that swallow clicks). Extract the animation-preview canvas (find the canvas with `width===256 && height===64` — canvas order shifts) at 4× nearest-neighbor and LOOK at it:

```js
const c=[...document.querySelectorAll('canvas')].find(x=>x.width===256&&x.height===64);
const o=document.createElement('canvas');o.width=c.width*4;o.height=c.height*4;
const x=o.getContext('2d');x.imageSmoothingEnabled=false;x.drawImage(c,0,0,o.width,o.height);
o.toDataURL('image/png')   // save to file, view it
```

If a hair/item is missing from pixels but present in selections: re-apply the hash, check for a modal overlay (press Escape via CDP `Input.dispatchKeyEvent` key 27), or swap to a known-good item (`Bob_black`).

### 4. Download "Spritesheet (PNG)"

1. Locate the button: `[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Spritesheet (PNG)')`, `scrollIntoView({block:'center',behavior:'instant'})`, read `getBoundingClientRect()` center.
2. CDP-click it: `Input.dispatchMouseEvent` `mousePressed` then `mouseReleased` at those coords (`button:"left"`, `clickCount:1`).
3. File lands in the user's Downloads as `character-spritesheet.png`. A GUID-named `.tmp` may sit at a fixed size for 10–60 s — **it finalizes on its own**; poll every 2–3 s for up to 2 min.
4. Immediately move/rename to the target name (next download reuses the name or appends ` (1)`).

`scripts/wait-and-move.sh <target.png>` implements the poll-and-move; `scripts/page-eval.sh <js-file>` wraps a Windows-safe webbridge evaluate call.

### 5. Next character

No reset needed — set the next full hash (include `sex`, `body`, `head`, `expression` every time) and repeat from step 3.

## UI tree fallback (when hash route is unavailable)

Top-level expansion titles: `Body Type` (buttons Male/Female/Teen/Child/Muscular/Pregnant), `Body`, `Head`, `Hair`, `Headwear`, `Arms`, `Torso`, `Legs`, `Feet`, `Tools`, `Weapons`, plus `License Filters`, `Animation Filters`.
Under `Hair`: `Beards`, `Mustaches`, `Extensions`, `Afro`, `Curly`, `Bald / Shaved`, `Short`, `Spiky`, `Pigtails`, `Bob`, `Braids, Ponytails, Updos`, `Long`, `Xlong`.

Every level — category, subcategory, leaf, and the leaf's `.variant-item` canvas — must be clicked with CDP trusted events (measure coords fresh after each re-render; use `scrollIntoView({behavior:'instant'})` and verify with `elementFromPoint`). Clicking the leaf canvas applies the default variant; color rows under it open a recolor modal that needs a confirming click — close strays with CDP Escape. Prefer the hash route whenever possible.

## Reference files

- `references/hash-catalog.md` — hash grammar, validated key/value table, item-metadata discovery, hair palette names, 10 ready RPG configs.
- `references/troubleshooting.md` — click/modal/download/rendering failures and fixes.
