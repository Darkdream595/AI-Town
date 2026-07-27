# LPC Generator Troubleshooting

Failure modes observed on the Universal LPC Spritesheet Character Generator and their fixes.

## Contents

- Clicking does nothing
- Modal popups
- Selection stuck but not rendered
- Download problems
- Page hangs / unresponsive
- Hash not applying

## Clicking does nothing

Synthetic `el.click()` (and full `pointerdown→click` JS sequences) are ignored by much of this app (Svelte). Use CDP trusted input for every click:

```
cdp Input.dispatchMouseEvent {type:"mousePressed", x, y, button:"left", clickCount:1}
cdp Input.dispatchMouseEvent {type:"mouseReleased", x, y, button:"left", clickCount:1}
```

Coordinate discipline (re-renders shift layout between calls):

1. `scrollIntoView({block:'center', behavior:'instant'})` — instant, never smooth.
2. Wait 400–600 ms, read `getBoundingClientRect()` center.
3. Verify with `document.elementFromPoint(x,y)` before clicking.
4. Click immediately; do not run other DOM mutations in between.

## Modal popups

A recolor/color-picker modal may appear (e.g. after clicking a palette row). It blocks the UI and can swallow a selection.

- Close with CDP Escape: `Input.dispatchKeyEvent` type `keyDown` + `keyUp`, `key:"Escape"`, `code:"Escape"`, `windowsVirtualKeyCode:27`.
- Detect overlays: any element with `position:fixed` or `zIndex>50` and size >100×100.
- After closing, re-apply the hash and re-verify both Current Selections and the canvas preview.

## Selection stuck but not rendered

Symptom: item shows in Current Selections but sprite is bald / item missing.

- `Messy` hair: known site bug — never use it; `Bob`/`Plain`/`Long_tied`/`Bangslong` render fine.
- A modal appeared mid-flow and the confirming click never happened: close modal (Escape), re-apply hash, re-check the 4× canvas extract.
- Always verify pixels, not just the selections text: find canvas `width===256 && height===64`, redraw 4× with `imageSmoothingEnabled=false`, `toDataURL`, view the file.

## Download problems

- File appears as GUID `.tmp` in Downloads at a frozen size: normal — it finalizes into `character-spritesheet.png` within ~10–60 s. Poll every 2–3 s for up to 2 min.
- Browser-level `Browser.setDownloadBehavior` / `Page.setDownloadBehavior` are NOT available through the webbridge CDP passthrough — downloads always go to the user's Downloads folder. Move each file out immediately; the next download reuses `character-spritesheet.png` or becomes `character-spritesheet (1).png`.
- No file at all after clicking: the click missed. Re-measure button coords (verify `elementFromPoint` returns the `BUTTON` with text `Spritesheet (PNG)`) and click again.
- If downloads keep failing, fallback: extract the full-sheet canvas (the largest canvas, e.g. 832×3456) via `toDataURL('image/png')` and save it directly — same pixels as the export.

## Page hangs / unresponsive

- Caused by overriding `navigator.clipboard.writeText/readText` (clipboard permission bubble blocks JS forever) or a JS `alert()`.
- `alert()`: dismiss via CDP `Page.handleJavaScriptDialog {accept:true}`.
- Otherwise `navigate` to reload the page (state in hash is lost — rebuild it). After reload the tree needs 5–10 s before queries work.

## Hash not applying

- Wait ≥1 s after setting `location.hash`, then read Current Selections.
- Invalid key or variant = silently ignored. Check spelling against `references/hash-catalog.md` or discover live values from the item-metadata chunk.
- Switching `sex` drops items not valid for the new body — set `sex` first, everything else after.
- Canvas array order shifts as the tree expands/collapses — locate the preview canvas by dimensions (`256×64`), never by fixed index.
