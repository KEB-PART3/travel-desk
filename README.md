# Travel Desk

Your upcoming travel on one offline-first board: flights, hotels, confirmation numbers, and what needs doing next. A password-gated PWA you deploy to Cloudflare Pages; a personal AI agent keeps `trips.json` current from your inbox.

**The pattern:** the repo is the board, your agent is the curator. You (or your agent) edit `trips.json`, run `./deploy.sh`, and the board updates. The agent mines your Gmail for confirmations, watches for schedule changes, and sources imagery — you just open the app.

## Setup

**Prerequisites:** a Cloudflare account, Node.js, and an AI agent with Gmail/calendar access (Claude, Muse, or similar).

1. **Create a KV namespace** in the Cloudflare dashboard (Workers & Pages → KV → Create). Paste its ID into `wrangler.toml` (`id = "…"`). Each owner gets their own namespace — never share one.
2. **Create a Pages project** in the Cloudflare dashboard. Set a `COOKIE_SECRET` environment variable on it (any long random string).
3. **Install wrangler:** `npm i -g wrangler`, then `wrangler login`.
4. **Deploy:** `./deploy.sh [your-pages-project-name]`
5. **Set your passphrase:** open the deployed URL. First visit asks you to choose a passphrase (pick four uncommon words). It's hashed (PBKDF2, 100k iterations) into your KV — nobody handling deployment ever sees it. Login lasts 30 days per device.

`trips.json` is git-ignored. The repo ships `trips.example.json` (two fabricated trips); the first deploy seeds `trips.json` from it. Replace it with your real trips.

## Pointing your agent at this repo

Give your agent this repo and say: *"Set up my Travel Desk."* Everything it needs is here:

- **`SCHEMA.md`** — the data contract for `trips.json`. The page shell is fixed; only `trips.json` changes between deploys.
- **`trips.example.json`** — the shape of a trip, a day, and the item kinds (`fly`, `car`, `stay`, `ticket`, `table`, `event`, `todo`).
- **`photos.js` → `PHOTOS` registry** — images are registered by key; events reference keys, never paths. Alt text is written from opening the file. Like `trips.json`, `photos.js` is yours: git-ignored, seeded from `photos.example.js` on first deploy, and the only file auto-imagery writes to — `index.html` is never modified per install.

The agent's standing job: read your Gmail for booking confirmations, add trips once they have a hotel, flight, or calendar hold (booked travel only — not exploratory browsing), keep confirmation numbers on the item where you'd read them aloud (check-in, first flight), never invent unknown values (`Not found`, not a guess), and run `./deploy.sh` after changes. Deploy-day rule: schedule changes, cancellations, and expiring refund windows ship the same day.

When the agent adds a hotel stay, it saves the property's official website in a `website` field on the stay item (see `SCHEMA.md`) — that's the one detail that unlocks automatic photos.

**Imagery fills itself in.** Every `./deploy.sh` runs `autopopulate-images.py` first: any flight with a recognizable airline name gets the airline's official logo as its row icon, and any hotel stay with a `website` gets the property's own hero photo as a marquee card. It only acts when the details are sufficient — an unparseable airline or a stay with no website is skipped with a log line, never guessed at. Logo padding is measured automatically so the logo gate (below) passes in the same run. Anything it gets wrong is a one-line registry swap.

**Photo guidelines** (they matter more than you'd think):

- Hotel and resort photos must be *of the actual property*, sourced from the property's own website — never generic stock. (`autopopulate-images.py` uses the site's `og:image` hero photo for this.)
- When adding a stay, save the property's official website in the item's `website` field — without it, no photo can be fetched automatically.
- Branded events get the official logo; unbranded events get an evocative image.
- A `photo` alone doesn't render — the item also needs `marquee: true` (hero card) or `banner: true` (slim card). ~2–3 marquees per trip max.
- The marquee crops to ~2:1, 190px tall, centered. Audition candidates: simulate the crop and *look at it* before committing. Prefer landscape with the subject in the vertical center; portrait shots get decapitated.
- Logos render contain-fit on a light tile, never cropped. Run `./check-logos.py` after adding one — it measures the padding each logo needs and fails the deploy if a mark would clip.
- Every stay's check-in is a full-bleed marquee hero: set `photo` (the property's best real photo) + `marquee: true` on the check-in item, with no `avatar` — the big image only, no small chip beneath it. Hotel heroes are exempt from the 2–3 marquee budget.

**Past trips are kept, not pruned.** Days are never deleted from `trips.json`. The board splits them automatically: **Upcoming** shows current and future days; **Past Trips** collects elapsed days under their trip header, most recent first.

## Make it yours

- **Name:** "Travel Desk" appears in `index.html` (`<title>`, `apple-mobile-web-app-title`, the `.brand` header), `login.html` (`.brand`), and `manifest.webmanifest` (`name`, `short_name`). Search-and-replace across those three files.
- **Icons:** replace `icon-192.png`, `icon-512.png`, `icon-maskable-512.png`, and `apple-touch-icon.png` (180×180). The maskable one needs its subject inside the center 80%. The default is a generic suitcase — swap in anything.
- **Theme color:** `theme_color` in `manifest.webmanifest` (browser chrome when installed).

## Project structure

```
index.html            the app shell (fixed — you edit data, not this)
trips.json            your trips (git-ignored, never committed)
trips.example.json    fabricated sample trips; seeds trips.json on first deploy
photos.js             your PHOTOS image registry (git-ignored, never committed)
photos.example.js     sample registry; seeds photos.js on first deploy
SCHEMA.md             the data contract your agent follows
img/                  your photos and logos, registered in PHOTOS
functions/            password gate + login/setup API (Cloudflare Pages Functions)
deploy.sh             logo gate → clean dist/ build → SW cache stamping → Pages deploy
autopopulate-images.py  deploy-time imagery: airline logos + hotel photos for
                        items with sufficient details (runs inside deploy.sh,
                        before the logo gate)
check-logos.py        fails the deploy if a logo would be clipped
```

## Privacy

Your travel data lives in `trips.json` (git-ignored) and your Cloudflare KV (passphrase hash). Neither is in this repo. `img/` holds your photos and logos and *is* committed with the repo — if you'd rather keep it out, add `img/` to `.gitignore` (the app works the same; images just won't travel with clones). If a stranger could infer when your house is empty from something in the repo, it doesn't belong here.
