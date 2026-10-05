# trips.json — schema v1

The page shell is fixed. **Only `trips.json` changes between deploys.**

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-09-21",      // YYYY-MM-DD. Drives the staleness warning.
  "generatedBy": "claude",           // or "muse" — whoever produced this run
  "trips": [ ... ]
}
```

Trips are ordered by `start`, soonest first. The hero card spotlights the next
trip that hasn't ended — an in-progress trip is labeled "Now traveling".

### Upcoming / Past Trips

Days are never deleted. The **Upcoming** tab shows trips that haven't ended,
with only their current and future days; **Past Trips** collects every elapsed
day under its trip header, most recent trip first. Days move between the two
views automatically as their dates pass — nothing is ever removed from the
data. The selected tab persists in `localStorage`.

## Trip

```json
{
  "id": "boston-2609",               // stable slug; never reuse across trips
  "title": "Boston — Family Weekend",
  "where": "Boston College",
  "start": "2026-09-24",             // YYYY-MM-DD
  "end":   "2026-09-27",
  "status": "ok | warn | crit | idea",
  "who":   "one line of prose",
  "coords": [42.3355, -71.1675],      // optional [lat, lon] of the destination.
                                      // Trips starting within 10 days show a live
                                      // "Pack for this" forecast strip. Omit when
                                      // the location is unknown — never invent.
  "days":  [ ... ],                  // optional — omit for unbooked trips
  "refs":  [ ... ],                  // optional — undated facts only
  "todos": [ ... ],
  "notes": "optional prose shown under 'Read on it'"
}
```

`status` drives the pill: `ok` On track · `warn` Gaps · `crit` Action needed · `idea` Planning.

## Day

```json
{ "d": "2026-09-25", "note": "optional right-aligned label", "items": [ ... ] }
```

## Item — one row on the timeline

```json
{
  "time":  "6:00 PM",                // "" renders as "all day"
  "z":     "ET",                     // PT | ET | CET | Taipei — REQUIRED whenever time is set
  "title": "Doors open — Pops on the Heights",
  "kind":  "fly | car | stay | ticket | table | event | todo",
  "refs":  [["Tix order", "41434132"]],        // tap-to-copy chips
  "det":   "prose; inline HTML allowed (<b> only)",
  "links": [["View / print tickets", "https://…", ""]],  // 3rd slot "ghost" for secondary
  "map":   "900 Boylston St, Boston, MA 02115"           // optional postal address.
                                                         // Renders a 📍 Map pill in the action row
                                                         // opening Google Maps for the address. Omit when
                                                         // the location is unknown — never invent.
  "marquee": true,                 // promote to a full-bleed hero card (2–3 per trip max)
  "photo":   "alumni-stadium",     // registry key in photos.js PHOTOS → hero image
  "avatar":  "bc-logo",            // registry key → badge. Marquee: 52px circle in the card
                                  // body. Row: 40px rounded-square chip at the row's start
  "banner": true                   // all-day item → slim photo banner card (photo required).
                                  // The time collapses away; the banner IS the all-day statement
  "website": "https://www.examplehotel.com"  // optional, on stay items: the
                                  // property's official website. autopopulate-images.py
                                  // fetches the property's hero photo from it automatically.
}
```

**Timezone is a UI rule, not a preference.** Every `time` carries a `z`. Times are local to where the event happens and are never converted. A row without a zone label is a bug.

`refs` on an item are what you'd read out at a counter. Put the same confirmation on every row that needs it — a car number belongs on both pickup and return. Item refs render in a right-aligned meta column (StudyCoach DUE-style); links and buttons stay under the details.

**UI paradigm (locked 2026-09-22).** Three elements, three jobs — never mix them:
- **Kind tag** (next to the title): what *category* the row is — Flight, Car, Dinner, Event. A label, not an action.
- **Ref chips** (right meta column): numbers you *read out or copy* — confirmation codes, loyalty numbers, seat assignments. One layout everywhere: small-caps label above, bold value below, both left-aligned. Tap copies the value.
- **Action pills** (under the details): things you *do* — Call, 📍 Map, Buy tickets, View tickets. `.btn` pill style, including the Map pill generated from `map`.

**Description rubric.** `det` answers "what the traveler needs to know at a glance" — one line when possible. The title already says what's happening; don't restate it. Addresses live behind the 📍 Map pill, not in the prose.

**Flight pairing.** A flight's takeoff and landing are one row. Both legs share a `flight` id; the takeoff leg also carries `route`. The pair renders once, anchored where the takeoff sits in the timeline (works across days and with other flights interleaved between the legs — never rely on adjacency).

```json
{ "time": "2:05 PM", "z": "PT", "title": "Depart SFO", "kind": "fly",
  "flight": "bos-out", "route": "SFO → BOS",
  "refs": [["United", "JXNDPM"]], "det": "UA 2634 to Boston · …" }
{ "time": "10:57 PM", "z": "ET", "title": "Land at Logan", "kind": "fly",
  "flight": "bos-out", "det": "Six hours in the air, three hours forward" }
```

## Ref — undated facts

```json
{ "k": "Passports", "v": "Unverified", "state": "ok | partial | missing", "c": "optional detail" }
```

Only for things with no date. Anything dated goes on the timeline.

## Todo

```json
{
  "id":  "tw-24h",                   // stable; the done/dropped state keys off it
  "t":   "short imperative",
  "m":   "why it matters now",
  "sev": "crit | warn | info",
  "pri": 0,                          // optional; lower sorts first, overrides sev
  "due": "tonight"                   // optional; replaces the severity chip text
}
```

Needs a verb and a reason. Observations go in `det` or `notes`, never here.

**Never change a todo `id`.** the traveler's done/dropped state is stored against it in `localStorage`; a renamed id resurrects something he dismissed.

## Rules for each run

- **Archiving:** drop a trip once `end` is more than 7 days past. Don't accumulate history — this is a forward-looking board.
- **Mid-week changes:** a cancellation, a schedule change, or a closing refund window does not wait for Monday. Regenerate and redeploy same-day.
- **Never invent.** Unsourced field → `"Not found"`, meaning *not located*, not *not booked*.
- **Standing facts:** Boston — staying with friends. Taiwan — family house. Neither is a lodging gap.
- Bump `schemaVersion` only if the shell changes shape; the shell ignores unknown keys.

---

# Row cleanup (adopted 2026-09-22 from Claude's UI pass — ported into this shell)

The paradigm: **kind tag = category · place link = where · refs = read-out values · one button = the thing to press.** Rows were carrying five rounded shapes each; now at most two.

## `item.place` — the venue is a link on its own name

```json
"place": "Conte Forum"
```

Renders as a quiet text link with a small pin glyph (`Conte Forum`) above the detail line — a pin says *location*, where an arrow would only say *leaves the page*. The shell builds a Google Maps **search query** from `place` + `trip.city` (falling back to `trip.where`, with an optional per-item `city` override) — a venue name resolves, and nothing has to be transcribed, so nothing can be transcribed wrong. There is no Map button anymore.

**Do not repeat the venue or the street address in `det`.** The link carries it.

## `trip.city` / `item.city` — disambiguates the map search

```json
"city": "Boston, MA"
```

`"The Capital Grille"` alone is ambiguous; `"The Capital Grille, Boston, MA"` is not. Falls back to `trip.where`. Use `item.city` when one item is in a different city than the trip (e.g. a Munich hotel on the Dolomites trip).

## `item.links` — first entry is the only button

`links[0]` renders as the single filled button on the row: the one thing you'd press standing on the sidewalk. **Order the array accordingly** — `Call …` before `Edit reservation`. `links[1..]` render as plain text links inside the Details drawer — but a drawer needs something to hide: long `det` always earns one, otherwise the drawer only appears with two or more items, and a lone link renders inline under the button.

## `item.addr` — optional, drawer only

The full street address, when it is genuinely needed (an unmarked entrance, a specific gate, the right branch of a chain). Never shown on the row.

## `item.refs` — read-out values, not controls

Rendered as small-caps label + mono value, with no border, fill, or underline. Tap still copies, and still flashes green. These are values the traveler reads aloud at a counter, never buttons.

`refs` vs `facts` is a behaviour split, not a layout preference:

- `refs` — values the traveler reads out or types somewhere else: confirmation numbers, record locators, seat assignments, loyalty IDs. Copyable on tap.
- `facts` — values he only reads: price, vehicle class, what's included. Not copyable.

If something sitting in `facts` wants to be copied, it belongs in `refs`.

**Label the value, not the vendor.** Every ref label names what the number *is* — `Reservation number`, `Confirmation number`, `Seats` — never the vendor (`National`, `United`). The vendor already appears in the title or description; the label's job is to say what the number is for, so the traveler knows which number to read out. This holds for every reservation number in the data, not just rental cars.

**Refs stack vertically**, one per line like rows in a table — never side by side. Three across would be noise; three rows is a list.

## Dedupe rule: one fact, one place

A value in `refs` must not also appear in `det`; a venue in `place` must not appear in `det`. The shell renders duplicates faithfully — deduping is the data's job.

## One shape, one meaning

Every visual form on a row has exactly one job, and nothing borrows another's:

- **Filled button** — the one thing you'd press standing on the sidewalk. Never more than one per row (`links[0]`).
- **Small-caps label + mono value** — tap to copy. `refs` only: confirmation numbers, record locators, seats, loyalty IDs. (No underline — it was found noisy; the green "Copied" flash is the only feedback.)
- **Pin + text link** — a place. `item.place` → Maps search on the venue name. No street address on the row.
- **Plain text link** — a secondary action. `links[1..]`: Tuesday-afternoon work, not 7pm-at-the-door work.
- **Plain text, no affordance** — read-only. `facts`: price, vehicle class, what's included.
- **Coloured chip** — what kind of thing this is. `item.kind`, set by the generator, never tappable.

If you find yourself wanting a second filled button, or wanting to copy something in `facts`, the data is in the wrong field — not the shell in the wrong shape.
