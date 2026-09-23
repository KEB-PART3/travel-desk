#!/usr/bin/env python3
"""Logo clip-violation check for the Travel Desk.

The rule: a dominant badge/mark may bleed to the container edge, but
secondary detail — especially lettering — must clear the container's
boundary by a legible margin:
  - row chip (40px rounded square): >= 5 CSS px from the tile edge
  - marquee rounded square (52px, r=14): >= 4 CSS px from the rounded-square edge
  - row chip rounded square (40px, r=11): >= 5 CSS px from the rounded-square edge
Clearance is measured from DETAIL pixels (artwork edges minus the exempt
dominant mark — the largest connected component when it is more than
MARK_SHARE of all artwork) to the container's true boundary (rounded
corners included, via a signed distance function), rendering the logo
geometrically as the page does: tile background, registry pad as an inset
(the page insets via a wrapper, not img padding — same geometry), contain-fit
at 10x.

So the Pops starburst may touch the container, but the "Boston Pops"
wordmark — descenders included — must stand 5px off the row chip's edges
and 4px off the marquee tile's edges. National's green field and United's
globe are each a single dominant mark and pass untouched.

For every logo in the PHOTOS registry (contain-fit entries) and every
avatar container, the script reports the MINIMUM pad (CSS px) each logo
needs per container. Exit 1 if any logo's current pad is below its
minimum — deploy.sh runs this first so a violating logo can never ship.

Usage: ./check-logos.py
"""
import os, re, sys, math
from collections import deque
from PIL import Image, ImageDraw, ImageFilter
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCALE = 10            # render at 10x for subpixel-ish accuracy
BG_TOL = 30           # RGB euclidean distance that counts as "content"
MAX_PAD = 24          # give up searching past this many CSS px of pad
MARK_SHARE = 0.40     # largest component above this share of artwork = the mark; may bleed
# minimum CSS-px clearance secondary detail must keep from the boundary
EDGE_BAR = {'mq-avatar': 4, 'row-avatar': 5}

# (label, css_size_px, shape, corner_radius_px or None)
CONTAINERS = [
    ('mq-avatar', 52, 'rounded', 14),
    ('row-avatar', 40, 'rounded', 11),
]


def load_logos():
    """Parse the PHOTOS registry out of index.html: name -> {file, pad}."""
    s = open(os.path.join(HERE, 'index.html')).read()
    m = re.search(r'(?:const|let|var)\s+PHOTOS\s*=\s*\{(.*?)\n\};', s, re.S)
    if not m:
        print('PHOTOS registry not found in index.html', file=sys.stderr)
        sys.exit(2)
    block = m.group(1)
    # Strip JS comments so commented-out examples never parse as entries.
    block = re.sub(r'/\*.*?\*/', '', block, flags=re.S)
    block = re.sub(r'//[^\n]*', '', block)
    logos = {}
    for em in re.finditer(r"'([\w-]+)'\s*:\s*\{((?:[^{}]|\{[^{}]*\})*)\}", block):
        name, body = em.group(1), em.group(2)
        if "fit:'contain'" not in body:
            continue  # photographs aren't logos
        src = re.search(r"src:'([^']+)'", body).group(1)
        pad = 0
        pm = re.search(r'pad:(\d+|\{[^}]*\})', body)
        if pm:
            v = pm.group(1)
            if v.startswith('{'):
                pad = {k: int(n) for k, n in re.findall(r'(\w+):(\d+)', v)}
            else:
                pad = int(v)
        logos[name] = {'file': src, 'pad': pad}
    return logos


def pad_for(pad, container):
    if isinstance(pad, dict):
        key = 'mq' if container == 'mq-avatar' else 'row'
        return pad.get(key, 0)
    return pad


def background_of(img):
    """Median color of the 1px border — the tile/field color."""
    w, h = img.size
    border = []
    border += [img.getpixel((x, 0)) for x in range(w)]
    border += [img.getpixel((x, h - 1)) for x in range(w)]
    border += [img.getpixel((0, y)) for y in range(h)]
    border += [img.getpixel((w - 1, y)) for y in range(h)]
    rs = sorted(p[0] for p in border)
    gs = sorted(p[1] for p in border)
    bs = sorted(p[2] for p in border)
    n = len(rs)
    return (rs[n // 2], gs[n // 2], bs[n // 2])


def label_components(mask):
    """4-connected components of a binary ('L') mask -> (label_image, counts)."""
    w, h = mask.size
    px = mask.load()
    lab = [[-1] * w for _ in range(h)]
    counts = []
    cur = 0
    for y in range(h):
        for x in range(w):
            if not px[x, y] or lab[y][x] != -1:
                continue
            q = deque([(x, y)])
            lab[y][x] = cur
            n = 0
            while q:
                cx, cy = q.popleft()
                n += 1
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < w and 0 <= ny < h and px[nx, ny] and lab[ny][nx] == -1:
                        lab[ny][nx] = cur
                        q.append((nx, ny))
            counts.append(n)
            cur += 1
    return lab, counts


def analyze_logo(path):
    """Returns (bg, content_mask, exempt_mask) at the artwork's native size.

    exempt_mask covers the dominant mark (largest component above MARK_SHARE),
    or None when the artwork has no dominant mark (e.g. a pure wordmark)."""
    art = Image.open(path).convert('RGBA')
    comp = Image.new('RGB', art.size, (255, 255, 255))  # tile:'light'
    comp.paste(art, mask=art.split()[3])
    bg = background_of(comp)
    w, h = comp.size
    px = comp.load()
    content = Image.new('L', (w, h), 0)
    cp = content.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if math.dist((r, g, b), bg) > BG_TOL:
                cp[x, y] = 255
    exempt = None
    sw = 160
    small = content.resize((sw, max(1, round(sw * h / w))), Image.NEAREST)
    lab, counts = label_components(small)
    total = sum(counts)
    if total:
        big = max(range(len(counts)), key=lambda i: counts[i])
        if counts[big] / total > MARK_SHARE:
            m = Image.new('L', small.size, 0)
            mp = m.load()
            for y in range(small.height):
                for x in range(small.width):
                    if lab[y][x] == big:
                        mp[x, y] = 255
            # back to native res, dilated generously to cover resampling fringe
            exempt = m.resize((w, h), Image.NEAREST).filter(ImageFilter.MaxFilter(13))
    return bg, content, exempt


def detail_clearance_px(native, size, shape, radius, pad_px):
    """Minimum CSS-px distance from any DETAIL pixel (artwork minus the
    exempt mark) to the container's boundary, rendering as the page does.
    Uses the exact signed distance function of the circle / rounded rect.
    Returns inf when there is no detail (pure mark)."""
    _bg, content, exempt = native
    S = size * SCALE
    box = (size - 2 * pad_px) * SCALE
    w, h = content.size
    sc = box / max(w, h)  # object-fit:contain — scale up or down to fill
    nw, nh = round(w * sc), round(h * sc)
    c = content.resize((nw, nh), Image.NEAREST)
    ox, oy = (S - nw) // 2, (S - nh) // 2
    C = Image.new('L', (S, S), 0)
    C.paste(c, (ox, oy))
    if exempt is not None:
        E = Image.new('L', (S, S), 0)
        E.paste(exempt.resize((nw, nh), Image.NEAREST), (ox, oy))
        C = Image.composite(Image.new('L', (S, S), 0), C, E)
    a = np.asarray(C)
    ys, xs = np.nonzero(a)
    if len(xs) == 0:
        return float('inf')
    cx = cy = (S - 1) / 2.0
    if shape == 'circle':
        d = np.abs(S / 2.0 - np.hypot(xs - cx, ys - cy))
    else:  # rounded rect: standard SDF, |d| = distance to boundary
        r = (radius or 0) * SCALE
        b = S / 2.0
        qx = np.abs(xs - cx) - b + r
        qy = np.abs(ys - cy) - b + r
        d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) \
            + np.minimum(np.maximum(qx, qy), 0) - r
        d = np.abs(d)
    return float(d.min()) / SCALE


def main():
    html = open(os.path.join(HERE, 'index.html')).read()
    # Static guard: padding must never sit on an <img> again. Chrome sizes
    # object-fit content to the border box, ignoring img padding, so the
    # artwork overflows its insets and gets chopped (2026-09-22 Pops logo).
    # Padded logos render through the .avatar-pad wrapper instead.
    bad = re.findall(r'<img\b[^>]*\bstyle="[^"]*padding', html)
    if bad:
        print(f'VIOLATION: {len(bad)} <img> tag(s) carry inline padding — '
              'use the .avatar-pad wrapper (Chrome ignores img padding for object-fit)')
        sys.exit(1)
    logos = load_logos()
    if not logos:
        print('no logos found in registry')
        return
    native = {n: analyze_logo(os.path.join(HERE, L['file'])) for n, L in logos.items()}
    print(f'{"logo":<16}{"container":<12}{"bar":>4}{"min-pad":>8}{"current":>8}  status')
    failed = False
    min_pads = {}
    for name, L in sorted(logos.items()):
        min_pads[name] = {}
        for cname, size, shape, radius in CONTAINERS:
            bar = EDGE_BAR[cname]
            min_pad = None
            for p in range(0, MAX_PAD + 1):
                if detail_clearance_px(native[name], size, shape, radius, p) >= bar:
                    min_pad = p
                    break
            min_pads[name][cname] = min_pad
            cur = pad_for(L['pad'], cname)
            ok = min_pad is not None and cur >= min_pad
            failed = failed or not ok
            need = str(min_pad) if min_pad is not None else '>24'
            print(f'{name:<16}{cname:<12}{bar:>4}{need:>8}{cur:>8}  {"OK" if ok else "VIOLATION"}')
    # Cross-container consistency: one logo, one treatment. If the artwork
    # needs a materially different inset per container, the treatment isn't
    # uniform (the 2026-09-22 circle-vs-square Pops split) — fix the artwork
    # or the containers, don't paper over it with per-container numbers.
    CONSISTENCY_TOL = 2
    for name, mp in sorted(min_pads.items()):
        vals = [v for v in mp.values() if v is not None]
        if len(vals) > 1 and max(vals) - min(vals) > CONSISTENCY_TOL:
            detail = ', '.join(f'{c} needs {v}' for c, v in sorted(mp.items()))
            print(f'INCONSISTENT: {name} needs different insets per container '
                  f'({detail}) — make the artwork container-agnostic')
            failed = True
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
