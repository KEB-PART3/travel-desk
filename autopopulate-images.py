#!/usr/bin/env python3
"""Auto-populate imagery for the Travel Desk.

Runs on every deploy (wired into deploy.sh, before check-logos.py). Scans
trips.json for items that have *sufficient details* but no imagery yet, and
fills them in:

  - kind=fly with a parseable airline name  -> the airline's official logo
    (icon declared on the airline's own homepage, else its apple-touch-icon,
    else the Google favicon service), attached as the row's avatar chip.
  - kind=stay with a `website` URL           -> the property's own hero image
    (og:image), attached as a marquee photo.

Sufficient details is the gate: a flight whose airline can't be identified,
or a stay with no website, is skipped with a log line — never guessed at.
(For stays, the agent saves the property's official site in `website` when
it creates the trip; that's the one detail this script can't find itself.)

Idempotent: items that already have a photo/avatar are untouched, and
registry keys are never duplicated. New logos get their padding measured
with check-logos.py's own geometry so the logo gate passes on the same run.

Usage: ./autopopulate-images.py [trips.json]
"""
import importlib.util
import json
import os
import re
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(HERE, 'img')
INDEX = os.path.join(HERE, 'index.html')
TIMEOUT = 20
MAX_MARQUEES_PER_TRIP = 3

# Airline name (normalized) -> official website domain. The script fetches
# {domain}/apple-touch-icon.png first, then falls back to the Google favicon
# service. Extend this map when a new airline appears in the data.
AIRLINE_DOMAINS = {
    'united': 'united.com',
    'united airlines': 'united.com',
    'southwest': 'southwest.com',
    'southwest airlines': 'southwest.com',
    'alaska': 'alaskaair.com',
    'alaska airlines': 'alaskaair.com',
    'delta': 'delta.com',
    'delta air lines': 'delta.com',
    'american': 'aa.com',
    'american airlines': 'aa.com',
    'jetblue': 'jetblue.com',
    'hawaiian': 'hawaiianairlines.com',
    'hawaiian airlines': 'hawaiianairlines.com',
    'lufthansa': 'lufthansa.com',
    'british airways': 'ba.com',
    'air france': 'airfrance.com',
    'eva': 'evaair.com',
    'eva air': 'evaair.com',
    'china airlines': 'china-airlines.com',
    'cathay pacific': 'cathaypacific.com',
    'singapore airlines': 'singaporeair.com',
    'ana': 'ana.co.jp',
    'all nippon airways': 'ana.co.jp',
    'japan airlines': 'jal.com',
    'jal': 'jal.com',
    'virgin atlantic': 'virginatlantic.com',
    'emirates': 'emirates.com',
    'qatar airways': 'qatarairways.com',
    'turkish airlines': 'turkishairlines.com',
    'air canada': 'aircanada.com',
    'aeromexico': 'aeromexico.com',
    'qantas': 'qantas.com',
    'korean air': 'koreanair.com',
    'asiana': 'flyasiana.com',
    'asiana airlines': 'flyasiana.com',
}

UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0 Safari/537.36'}


def log(msg):
    print(f'[autopopulate] {msg}')


def slugify(s):
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', s.lower())).strip('-')


def fetch_bytes(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        ctype = r.headers.get_content_type()
        return r.read(), ctype, r.url


def image_size(data):
    """(width, height, format) or None if not an image."""
    from PIL import Image
    import io
    try:
        im = Image.open(io.BytesIO(data))
        im.verify()
        im = Image.open(io.BytesIO(data))
        return im.size[0], im.size[1], im.format
    except Exception:
        return None


# ---------------------------------------------------------------- logos ---

def airline_name_from_title(title):
    """'Alaska Airlines AS 404' -> 'Alaska Airlines'. None if unparseable."""
    m = re.search(r'([A-Z0-9]{2})\s*(\d{2,4})', title or '')
    if not m:
        return None
    name = re.sub(r'[\s\xb7\-|\u2013]+$', '', title[:m.start()]).strip()
    if not name or name.lower() in (
            'depart', 'departs', 'land', 'lands', 'arrive', 'arrives', 'flight'):
        return None
    return name


def airline_domain(name):
    n = name.lower().strip()
    if n in AIRLINE_DOMAINS:
        return AIRLINE_DOMAINS[n]
    for suffix in (' airlines', ' airways', ' air lines', ' air'):
        if n.endswith(suffix):
            short = n[:-len(suffix)]
            if short in AIRLINE_DOMAINS:
                return AIRLINE_DOMAINS[short]
    return None


ICON_LINK = re.compile(r'<link[^>]+rel=["\'](?:apple-touch-icon|icon)[^>]*>', re.I)
MIN_LOGO_PX = 32  # a slightly soft real logo beats no logo; swaps are one line


def discover_icon(domain):
    """Find an icon the airline itself declares in its homepage <head>.
    Returns a URL or None."""
    try:
        html, ctype, final = fetch_bytes(f'https://{domain}/')
    except Exception as e:
        log(f'icon discovery failed ({domain}): {e}')
        return None
    if 'html' not in ctype:
        return None
    best = None
    for m in ICON_LINK.finditer(html.decode('utf-8', 'replace')[:200000]):
        tag = m.group(0)
        href = re.search(r'href=["\']([^"\']+)', tag)
        if not href or href.group(1).startswith('data:'):
            continue
        url = urllib.parse.urljoin(final, href.group(1).strip())
        sizes = re.search(r'sizes=["\'](\d+)x\d+', tag)
        rank = ('apple-touch-icon' in tag, int(sizes.group(1)) if sizes else 0)
        if best is None or rank > best[0]:
            best = (rank, url)
    return best[1] if best else None


def fetch_logo(domain):
    """(png_bytes, source_url) or (None, reason). Chain: homepage-declared
    icon -> conventional apple-touch-icon.png path -> Google favicon service."""
    urls = []
    discovered = discover_icon(domain)
    if discovered:
        urls.append(discovered)
    urls += [f'https://{domain}/apple-touch-icon.png',
             f'https://www.google.com/s2/favicons?domain={domain}&sz=128']
    for url in urls:
        try:
            data, ctype, final = fetch_bytes(url)
        except Exception as e:
            log(f'logo fetch failed ({domain}): {e}')
            continue
        if not ctype.startswith('image'):
            continue
        sized = image_size(data)
        if not sized:
            continue
        w, h, _fmt = sized
        if min(w, h) < MIN_LOGO_PX:
            continue
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(data)).convert('RGBA')
        out = io.BytesIO()
        im.save(out, 'PNG')
        return out.getvalue(), final
    return None, 'no usable logo found'


# ---------------------------------------------------------- hotel photos ---

OG_IMAGE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', re.I)
OG_IMAGE_REV = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', re.I)


def fetch_hotel_photo(website, place):
    """(img_bytes, ext, source_url) or (None, None, reason)."""
    try:
        html, ctype, final = fetch_bytes(website)
    except Exception as e:
        return None, None, f'site fetch failed: {e}'
    if 'html' not in ctype:
        return None, None, f'site returned {ctype}'
    text = html.decode('utf-8', 'replace')
    m = OG_IMAGE.search(text) or OG_IMAGE_REV.search(text)
    if not m:
        return None, None, 'no og:image on the property site'
    img_url = urllib.parse.urljoin(final, m.group(1).strip())
    try:
        data, img_ctype, _ = fetch_bytes(img_url)
    except Exception as e:
        return None, None, f'photo fetch failed: {e}'
    if not img_ctype.startswith('image'):
        return None, None, f'og:image returned {img_ctype}'
    sized = image_size(data)
    if not sized:
        return None, None, 'og:image is not a decodable image'
    w, h, fmt = sized
    # The marquee crops ~2:1 centered: demand a decent landscape original.
    if w < 800 or w / max(h, 1) < 1.25:
        return None, None, f'photo too small or not landscape ({w}x{h})'
    ext = {'JPEG': '.jpg', 'JPG': '.jpg', 'PNG': '.png',
           'WEBP': '.webp', 'GIF': '.gif'}.get(fmt, '.jpg')
    return data, ext, img_url


# --------------------------------------------------------------- registry ---

def load_registry():
    s = open(INDEX).read()
    if not re.search(r'const\s+PHOTOS\s*=\s*\{(?:.*?\n)\};', s, re.S):
        log('PHOTOS registry not found in index.html — skipping registry writes')
        return None
    return s


def registry_has(s, key):
    return re.search(r"'" + re.escape(key) + r"'\s*:", s) is not None


def registry_add(s, key, entry_js):
    """Insert a new entry before the closing }; of PHOTOS. Re-anchors on
    every call so repeated inserts stay correct."""
    m = re.search(r'(const\s+PHOTOS\s*=\s*\{(?:.*?\n))\};', s, re.S)
    insertion = f"  /* auto-populated by autopopulate-images.py */\n  {entry_js}\n"
    return s[:m.end(1)] + insertion + s[m.end(1):]


def measure_pad(path):
    """Minimum CSS-px pad per container, using check-logos.py's geometry.
    Returns a pad value (int, or {row,mq} dict) or None if the artwork can't
    be made container-consistent."""
    spec = importlib.util.spec_from_file_location(
        'check_logos', os.path.join(HERE, 'check-logos.py'))
    cl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cl)
    from PIL import Image
    import io

    data = open(path, 'rb').read()
    for attempt in range(4):
        native = cl.analyze_logo(path)
        mins = {}
        for cname, size, shape, radius in cl.CONTAINERS:
            best = None
            for p in range(0, cl.MAX_PAD + 1):
                if cl.detail_clearance_px(native, size, shape, radius, p) \
                        >= cl.EDGE_BAR[cname]:
                    best = p
                    break
            mins[cname] = best
        vals = [v for v in mins.values() if v is not None]
        if len(vals) == len(cl.CONTAINERS) and max(vals) - min(vals) <= 2:
            if max(vals) == min(vals):
                return max(vals)
            return {'row': mins['row-avatar'], 'mq': mins['mq-avatar']}
        # Inconsistent across containers: bake a transparent margin into the
        # artwork and re-measure, so one pad value fits everywhere.
        im = Image.open(io.BytesIO(data)).convert('RGBA')
        w, h = im.size
        mx, my = round(w * 0.12), round(h * 0.12)
        canvas = Image.new('RGBA', (w + 2 * mx, h + 2 * my), (0, 0, 0, 0))
        canvas.paste(im, (mx, my), im)
        canvas.save(path, 'PNG')
        data = open(path, 'rb').read()
    return None


def pad_js(pad):
    if isinstance(pad, dict):
        return '{row:%d,mq:%d}' % (pad['row'], pad['mq'])
    return str(pad)


# ------------------------------------------------------------------- main ---

def main():
    trips_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'trips.json')
    if not os.path.exists(trips_path):
        log(f'{trips_path} not found — nothing to do')
        return 0
    data = json.load(open(trips_path))
    trips = data.get('trips', data) if isinstance(data, dict) else data

    os.makedirs(IMG_DIR, exist_ok=True)
    html = load_registry()
    if html is None:
        log('no PHOTOS registry — nothing to do')
        return 0

    added, skipped = 0, 0
    dirty_data, dirty_html = False, False

    for trip in trips:
        marquees = sum(1 for d in trip.get('days', [])
                       for it in d.get('items', []) if it.get('marquee'))
        for day in trip.get('days', []):
            for it in day.get('items', []):
                kind = it.get('kind')

                # ---- airline logos ----
                if kind == 'fly' and not it.get('avatar'):
                    name = airline_name_from_title(it.get('title', ''))
                    if not name:
                        log(f"skip flight '{it.get('title')}' — airline not parseable")
                        skipped += 1
                        continue
                    domain = airline_domain(name)
                    if not domain:
                        log(f"skip '{name}' — no domain mapping "
                            f"(add it to AIRLINE_DOMAINS in autopopulate-images.py)")
                        skipped += 1
                        continue
                    key = 'airline-' + slugify(name)
                    if registry_has(html, key):
                        it['avatar'] = key
                        dirty_data = True
                        continue
                    png, src = fetch_logo(domain)
                    if png is None:
                        log(f"skip '{name}' logo — {src}")
                        skipped += 1
                        continue
                    fname = f'{key}.png'
                    with open(os.path.join(IMG_DIR, fname), 'wb') as f:
                        f.write(png)
                    pad = measure_pad(os.path.join(IMG_DIR, fname))
                    if pad is None:
                        os.remove(os.path.join(IMG_DIR, fname))
                        log(f"skip '{name}' logo — artwork not container-consistent")
                        skipped += 1
                        continue
                    entry = (f"'{key}':{{src:'img/{fname}',fit:'contain',"
                             f"tile:'light',pad:{pad_js(pad)},\n"
                             f"    alt:'{name} logo'}} ,")
                    html = registry_add(html, key, entry)
                    it['avatar'] = key
                    dirty_data = dirty_html = True
                    added += 1
                    log(f"added logo '{key}' from {src} (pad {pad_js(pad)})")

                # ---- hotel photos ----
                if kind == 'stay' and not it.get('photo'):
                    place = it.get('place') or ''
                    website = it.get('website') or ''
                    if not place or not website:
                        log(f"skip stay '{place or it.get('title')}' — needs "
                            f"place + website for auto photo")
                        skipped += 1
                        continue
                    if marquees >= MAX_MARQUEES_PER_TRIP:
                        log(f"skip stay '{place}' — trip already has "
                            f"{MAX_MARQUEES_PER_TRIP} marquees")
                        skipped += 1
                        continue
                    key = 'stay-' + slugify(place)
                    if registry_has(html, key):
                        it['photo'] = key
                        it['marquee'] = True
                        marquees += 1
                        dirty_data = True
                        continue
                    data_bytes, ext, src = fetch_hotel_photo(website, place)
                    if data_bytes is None:
                        log(f"skip stay '{place}' photo — {src}")
                        skipped += 1
                        continue
                    fname = f'{key}{ext}'
                    with open(os.path.join(IMG_DIR, fname), 'wb') as f:
                        f.write(data_bytes)
                    alt = f'{place} — photo from the property\u2019s website'
                    entry = (f"'{key}':{{src:'img/{fname}',\n"
                             f"    alt:'{alt}'}} ,")
                    html = registry_add(html, key, entry)
                    it['photo'] = key
                    it['marquee'] = True
                    marquees += 1
                    dirty_data = dirty_html = True
                    added += 1
                    log(f"added photo '{key}' from {src}")

    if dirty_html and html is not None:
        open(INDEX, 'w').write(html)
    if dirty_data:
        with open(trips_path, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write('\n')
    log(f'done: {added} added, {skipped} skipped')
    return 0


if __name__ == '__main__':
    sys.exit(main())
