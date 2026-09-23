#!/usr/bin/env bash
# Deploy the Travel Desk PWA to Cloudflare Pages (production).
#
# Builds a clean dist/ directory containing only the site files (shell, data,
# gate functions, manifest, icons) so stray working files in this folder can
# never break or bloat the deploy. Stamps the service-worker cache tag from a
# hash of the site's contents, so the tag changes whenever anything changes
# and never when nothing does. Nobody has to remember to bump a version string.
#
# Prerequisites: a Cloudflare account, a Pages project, and a KV namespace
# bound as TD (see wrangler.toml). Set the COOKIE_SECRET Pages secret once
# in the Cloudflare dashboard. Needs the wrangler CLI: `npm i -g wrangler`.
#
# Usage: ./deploy.sh [pages-project-name]   (default: travel-desk)
set -euo pipefail
cd "$(dirname "$0")"

PROJECT="${1:-${PAGES_PROJECT:-travel-desk}}"

# First run: seed your real trips.json from the sample. trips.json is
# git-ignored — your travel data never gets committed.
if [ ! -f trips.json ]; then
  cp trips.example.json trips.json
  echo "Seeded trips.json from trips.example.json — replace it with your own trips."
fi

# Auto-imagery: fill in airline logos and hotel photos for items that have
# enough details but no imagery yet. Idempotent — skips what's already set,
# never guesses at what's ambiguous. Runs before the logo gate so freshly
# fetched logos get their padding measured in the same run.
./autopopulate-images.py

# Logo clip check: fail before building anything if a logo's detail (text
# especially) would be cut off by an avatar container. Pad values live in
# the PHOTOS registry and are measured by the script — never guessed.
./check-logos.py

DIST="$PWD/dist"
rm -rf "$DIST"
mkdir -p "$DIST/functions/api"
cp index.html trips.json manifest.webmanifest login.html sw.js \
   icon-192.png icon-512.png icon-maskable-512.png apple-touch-icon.png \
   wrangler.toml "$DIST/"
mkdir -p "$DIST/img"
# Every image in img/ ships — never a hardcoded list, or a newly added
# image silently 404s (and the SW precache's addAll fails with it).
cp img/* "$DIST/img/" 2>/dev/null || true
cp functions/_middleware.js "$DIST/functions/"
cp functions/api/_auth.js functions/api/login.js functions/api/setup.js \
   functions/api/ping.js "$DIST/functions/api/"

HASH=$(cat "$DIST/index.html" "$DIST/trips.json" "$DIST/manifest.webmanifest" \
       "$DIST/login.html" \
       "$DIST/functions/_middleware.js" "$DIST/functions/api/_auth.js" \
       "$DIST/functions/api/login.js" "$DIST/functions/api/setup.js" \
       "$DIST/functions/api/ping.js" \
       "$DIST/icon-192.png" "$DIST/icon-512.png" \
       "$DIST/icon-maskable-512.png" "$DIST/apple-touch-icon.png" \
       "$DIST"/img/* \
       | shasum -a 256 | cut -c1-12)
TAG="travel-desk-${HASH}"

# Stamp the precache image list from whatever is actually in dist/img/,
# so the service worker and the bundle can never disagree.
python3 - "$DIST" << 'EOF'
import sys, os, glob
dist = sys.argv[1]
imgs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(dist, 'img', '*'))
              if os.path.isfile(p))
lines = '\n'.join("  './img/%s'," % n for n in imgs)
p = os.path.join(dist, 'sw.js')
s = open(p).read()
assert '/*__IMG_ASSETS__*/' in s, 'img asset marker missing in sw.js'
open(p, 'w').write(s.replace('/*__IMG_ASSETS__*/', lines))
print('stamped %d img assets into sw.js' % len(imgs))
EOF

if grep -q '__CACHE_TAG__' "$DIST/sw.js"; then
  sed -i.bak "s/__CACHE_TAG__/${TAG}/" "$DIST/sw.js"
else
  sed -i.bak "s/const CACHE = '[^']*'/const CACHE = '${TAG}'/" "$DIST/sw.js"
fi
rm -f "$DIST/sw.js.bak"
# Stamp the same tag into the page so its version probe can spot a newer build.
if grep -q '__CACHE_TAG__' "$DIST/index.html"; then
  sed -i.bak "s/__CACHE_TAG__/${TAG}/" "$DIST/index.html"
  rm -f "$DIST/index.html.bak"
fi

npx wrangler pages deploy "$DIST" --project-name "$PROJECT"

echo "Cache tag: ${TAG}"
echo "Deployed to Pages project: ${PROJECT} (see wrangler output above for the URL)"
