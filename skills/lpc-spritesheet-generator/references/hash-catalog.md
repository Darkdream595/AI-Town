# LPC Hash Catalog

Complete grammar and validated values for one-shot character configuration via `location.hash`.

## Contents

- Hash grammar
- Validated key → example values (all confirmed working)
- Discovering new items and variants from item-metadata
- Hair palette names
- UI tree structure (expansion titles)
- 10 ready-made RPG character configs

## Hash grammar

```
#sex=male&body=Body_Color_light&head=Human_Male_light&expression=Neutral_light&key=Value_variant&...
```

- Param order does not matter, but put `sex` first — switching sex drops incompatible items.
- Female: `sex=female&head=Human_Female_light` (keep `body=Body_Color_light&expression=Neutral_light`).
- Skin tone: replace `light` in body/head/expression (`Body_Color_tan`, …) — "Match body color" keeps heads/ears synced.
- Value = display name, spaces → underscores, then `_` + variant. Spaces inside a variant stay literal (`Vest_green striped`).
- Omit variant → site default (`weapon=Hoe` → `Hoe (ceramic)`; `beard=Basic_Beard` → orange).
- Always confirm via the "Current Selections" panel text: `Name (variant)` per item.

## Validated key/value table

| Hash key | Example value (verified) | Renders as |
|---|---|---|
| sex | `male` / `female` | body type |
| body | `Body_Color_light` | Body Color (light) |
| head | `Human_Male_light`, `Human_Female_light` | Human Male/Female (light) |
| expression | `Neutral_light` | Neutral (light) |
| hair | `Bob_black`, `Plain_black`, `Long_tied_black`, `Bangslong_black`, `Ponytail_black` | hair (avoid `Messy` — bald render bug) |
| beard | `Basic_Beard` (default orange) | Basic Beard (orange) |
| ears | `Elven_ears_light` | Elven ears (light) |
| clothes | `Longsleeve_brown`, `Longsleeve_gray`, `Longsleeve_white`, `Shortsleeve_white`, `Robe_white`, `Robe_purple`, `Robe_brown` | shirts/robes |
| apron | `Apron_leather` | Apron (leather) |
| vest | `Vest_green striped` | Vest (green striped) |
| armour | `Leather_leather`, `Plate_steel` | Leather/Plate torso |
| chainmail | `Chainmail_steel` | Chainmail (steel) |
| legs | `Pants_brown`, `Pants_red`, `Pants_charcoal`, `Pants_leather`, `Armour_steel`, `Plain_skirt_purple`, `Plain_skirt_white`, `Plain_skirt_brown` | pants/armour legs/skirts |
| weapon | `Hoe_steel`, `Hammer_steel`, `Pickaxe_steel`, `Watering_can`, `Simple_staff_simple`, `Longsword_longsword`, `Normal_medium` (bow), `Wand` | tools/staves/swords/bows (all slot `weapon`, one at a time) |
| shield | `Kite_kite gray` | Kite shield |
| ammo | `Ammo_arrow` | bow arrows (pair with a bow) |
| charm | `Cross_amulet_gold_yellow` | Cross amulet |
| backpack | `Basket_round` | Basket (round) — good merchant bag |
| belt | `Mage_Belt` (default black) | Mage Belt |
| weapon_magic_crystal | `Crystal` (default blue) | Crystal — good potion substitute |
| quiver | `Quiver` | Quiver (quiver) |

Useful missing items and their substitutes: mug/bottle → `weapon=Watering_can`; potion → `weapon_magic_crystal=Crystal`; bag/pouch → `backpack=Basket_round`; holy symbol → `charm=Cross_amulet_gold_yellow`; robe-bottom → same-color `legs=Plain_skirt_<color>`; pitchfork/farmer shirt → none, use `clothes=Longsleeve_brown` + `weapon=Hoe_steel`.

## Discovering new items and variants

Item catalog lives in a JS chunk. In page context:

```js
// list asset chunks (name suffix changes per deploy)
const s=await (await fetch(location.pathname)).text();
[...s.matchAll(/assets\/[^"]+\.js/g)].map(m=>m[0]);
// import the item-metadata chunk (exports t)
const m=await import('./assets/item-metadata-DhgyBNqv.js'); window.__items=m.t;
// query: id, display name, slot key (type_name), variants, tree path
Object.entries(window.__items).filter(([id,v])=>/robe/i.test(id+v.name))
  .map(([id,v])=>({id,name:v.name,key:v.type_name,variants:v.variants,path:v.path}));
```

Fields: `name` → hash value base (spaces→underscores); `type_name` → hash key; `variants` (may be `[]` → use a palette name or omit); `path` → tree location (matches UI expansion titles); `required` → compatible body types.

Test any candidate by appending it to the hash and reading Current Selections 400 ms later — invalid entries are silently dropped.

## Hair palette names

From the recolor modal (use lowercase): orange, ash, platinum, white, gray, blonde, sandy, strawberry, gold, ginger, carrot, redhead, red, light brown, chestnut, dark brown, dark gray, black, raven, rose (scroll for more). Verified: `black`, `red`. Multi-word names: test `dark_brown` vs `dark brown` via Current Selections. Note `brown` is NOT a hair color (invalid) — cloth palette has it, hair palette does not.

## UI tree structure (expansion titles)

Top level: `Body Type` (Male/Female/Teen/Child/Muscular/Pregnant buttons), `Body`, `Head`, `Hair`, `Headwear`, `Arms`, `Torso`, `Legs`, `Feet`, `Tools`, `Weapons`, plus `License Filters`, `Animation Filters`.

Under `Hair`: `Beards`, `Mustaches`, `Extensions`, `Afro`, `Curly`, `Bald / Shaved`, `Short`, `Spiky`, `Pigtails`, `Bob`, `Braids, Ponytails, Updos`, `Long`, `Xlong`.

Leaves expand to a clickable `.variant-item` preview canvas (applies default variant) plus palette rows that open a recolor modal.

## 10 ready-made RPG configs (all verified end-to-end)

```
1. human_farmer    #sex=male&body=Body_Color_light&head=Human_Male_light&expression=Neutral_light&hair=Bob_black&clothes=Longsleeve_brown&legs=Pants_brown&weapon=Hoe_steel
2. elf_mage        #sex=female&body=Body_Color_light&head=Human_Female_light&expression=Neutral_light&ears=Elven_ears_light&hair=Long_tied_black&clothes=Robe_purple&legs=Plain_skirt_purple&weapon=Simple_staff_simple
3. dwarf_blacksmith#sex=male&body=Body_Color_light&head=Human_Male_light&expression=Neutral_light&hair=Plain_black&beard=Basic_Beard&clothes=Longsleeve_gray&apron=Apron_leather&legs=Pants_brown&weapon=Hammer_steel
4. halfling_merchant#sex=male&body=Body_Color_light&head=Human_Male_light&expression=Neutral_light&hair=Plain_black&clothes=Shortsleeve_white&vest=Vest_green striped&legs=Pants_red&backpack=Basket_round
5. human_guard     #sex=male&body=Body_Color_light&head=Human_Male_light&expression=Neutral_light&hair=Plain_black&chainmail=Chainmail_steel&legs=Armour_steel&weapon=Longsword_longsword&shield=Kite_kite gray
6. human_priest    #sex=female&body=Body_Color_light&head=Human_Female_light&expression=Neutral_light&hair=Bangslong_black&clothes=Robe_white&legs=Plain_skirt_white&charm=Cross_amulet_gold_yellow&weapon=Simple_staff_simple
7. human_innkeeper #sex=male&body=Body_Color_light&head=Human_Male_light&expression=Neutral_light&hair=Plain_black&clothes=Longsleeve_white&legs=Pants_brown&weapon=Watering_can
8. elf_alchemist   #sex=female&body=Body_Color_light&head=Human_Female_light&expression=Neutral_light&ears=Elven_ears_light&hair=Long_tied_black&clothes=Robe_brown&legs=Plain_skirt_brown&belt=Mage_Belt&weapon_magic_crystal=Crystal
9. human_hunter    #sex=male&body=Body_Color_light&head=Human_Male_light&expression=Neutral_light&hair=Bob_black&armour=Leather_leather&legs=Pants_leather&weapon=Normal_medium&ammo=Ammo_arrow&quiver=Quiver
10. dwarf_miner    #sex=male&body=Body_Color_light&head=Human_Male_light&expression=Neutral_light&hair=Plain_black&beard=Basic_Beard&clothes=Longsleeve_gray&legs=Pants_charcoal&weapon=Pickaxe_steel
```

Typical output: `character-spritesheet.png`, RGBA, 832–1536 × 3456–5760 px (64 px frames; wider/taller when items support more animations).
