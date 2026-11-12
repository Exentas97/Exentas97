"""Builds the animated SVG assets for the GitHub profile README.

Everything is self-contained: fonts are subset + embedded, photos are embedded,
and all motion is CSS inside the SVG (GitHub strips scripts, but plays SVG CSS).

Run:  python scripts/build_assets.py   (from the github-profile folder)
Needs: fonttools, Pillow. Font files are passed via FONT_DIR (see bottom).
"""
import base64
import io
import math
import os
import re
import sys
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.subset import Subsetter, Options
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, 'assets')
SITE = os.path.abspath(os.path.join(ROOT, '..', 'app', 'img'))
FONT_DIR = os.environ.get('FONT_DIR', os.path.join(HERE, 'fonts'))
os.makedirs(OUT, exist_ok=True)

INK, INK2, DIM, MUTED = '#070b1f', '#26304f', '#4f5878', '#8b93b3'
BLUE, BLUE2, CYAN, ICE, BG = '#2f6bff', '#1a3dff', '#5fd4ff', '#cfe4ff', '#f7f9ff'
FIG_BLUE = '#0d99ff'

# ---------------------------------------------------------------- fonts
_fonts = {}


def _load(name, file, wght):
    key = (name, wght)
    if key not in _fonts:
        f = TTFont(os.path.join(FONT_DIR, file))
        instantiateVariableFont(f, {'wght': wght}, inplace=True)
        _fonts[key] = f
    return _fonts[key]


FONTS = {
    'U': ('unbounded.ttf', 800),   # display
    'U5': ('unbounded.ttf', 500),  # display, lighter
    'M': ('geistmono.ttf', 500),   # mono labels
}


def font(family):
    file, w = FONTS[family]
    return _load(family, file, w)


def measure(family, text, size, ls_em=0.0):
    f = font(family)
    cmap, hmtx, upm = f.getBestCmap(), f['hmtx'], f['head'].unitsPerEm
    w = 0
    for ch in text:
        g = cmap.get(ord(ch))
        w += (hmtx[g][0] if g else upm * 0.6) / upm * size
    return w + ls_em * size * max(0, len(text) - 1)


def font_css(used):
    """used: {family: text}. Returns @font-face rules with per-file subsets."""
    css = []
    for fam, text in used.items():
        file, w = FONTS[fam]
        f = TTFont(os.path.join(FONT_DIR, file))
        instantiateVariableFont(f, {'wght': w}, inplace=True)
        opts = Options()
        opts.flavor = 'woff'
        opts.layout_features = ['kern', 'liga']
        sub = Subsetter(opts)
        sub.populate(text=''.join(sorted(set(text + ' '))))
        sub.subset(f)
        f.flavor = 'woff'
        buf = io.BytesIO()
        f.save(buf)
        b64 = base64.b64encode(buf.getvalue()).decode()
        css.append(f"@font-face{{font-family:'{fam}';src:url(data:font/woff;base64,{b64}) format('woff');}}")
    return ''.join(css)


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def img_b64(path, width=None, height=None, fmt='WEBP', quality=82, crop=None):
    im = Image.open(path)
    if crop:
        im = im.crop(crop)
    if width or height:
        w, h = im.size
        if width and not height:
            height = round(h * width / w)
        if height and not width:
            width = round(w * height / h)
        im = im.resize((width, height), Image.LANCZOS)
    buf = io.BytesIO()
    if fmt == 'JPEG':
        im.convert('RGB').save(buf, 'JPEG', quality=quality, optimize=True, progressive=True)
        mime = 'image/jpeg'
    else:
        im.save(buf, 'WEBP', quality=quality, method=6)
        mime = 'image/webp'
    return f'data:{mime};base64,' + base64.b64encode(buf.getvalue()).decode(), im.size


def svg_doc(w, h, css, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{esc(title)}">'
            f'<title>{esc(title)}</title><style>{css}</style>{body}</svg>')


def write(name, content):
    p = os.path.join(OUT, name)
    with open(p, 'w', encoding='utf-8') as fh:
        fh.write(content)
    print(f'  {name:<26} {len(content.encode()) / 1024:6.1f} KB')


STAR = 'M0,-1 C0.12,-0.12 0.12,-0.12 1,0 C0.12,0.12 0.12,0.12 0,1 C-0.12,0.12 -0.12,0.12 -1,0 C-0.12,-0.12 -0.12,-0.12 0,-1Z'
ARROW = 'M3 2.5V19l4.6-4.2 3 6.7 3-1.3-2.9-6.6 6.3-.2z'


def star(cx, cy, r, fill):
    return f'<path d="{STAR}" transform="translate({cx:.1f} {cy:.1f}) scale({r})" fill="{fill}"/>'


# ---------------------------------------------------------------- keyframe helper
class Timeline:
    """Builds per-element @keyframes from (time, transform, opacity) stops on one master clock."""

    def __init__(self, total):
        self.T = total
        self.css = []
        self.n = 0

    def track(self, stops, ease='cubic-bezier(.65,0,.35,1)', infinite=False):
        """stops: list of (t_seconds, transform_str, opacity or None). Returns class name."""
        self.n += 1
        name = f'k{self.n}'
        frames = []
        for i, (t, tr, op) in enumerate(stops):
            pct = max(0.0, min(100.0, t / self.T * 100))
            parts = []
            if tr is not None:
                parts.append(f'transform:{tr}')
            if op is not None:
                parts.append(f'opacity:{op}')
            if i < len(stops) - 1:
                parts.append(f'animation-timing-function:{ease}')
            frames.append(f'{pct:.3f}%{{{";".join(parts)}}}')
        # hold first stop from 0%
        if stops and stops[0][0] > 0:
            t, tr, op = stops[0]
            parts = []
            if tr is not None:
                parts.append(f'transform:{tr}')
            if op is not None:
                parts.append(f'opacity:{op}')
            frames.insert(0, f'0%{{{";".join(parts)}}}')
        # hold the last stop to the end of the clock; otherwise CSS drifts the element
        # back to its untransformed spot (finished cursors crept back to the corner)
        if stops and stops[-1][0] < self.T:
            t, tr_, op = stops[-1]
            parts = []
            if tr_ is not None:
                parts.append(f'transform:{tr_}')
            if op is not None:
                parts.append(f'opacity:{op}')
            frames.append(f'100%{{{";".join(parts)}}}')
        self.css.append(f'@keyframes {name}{{{"".join(frames)}}}'
                        f'.{name}{{animation:{name} {self.T}s linear both}}')
        return name

    def out(self):
        return ''.join(self.css)


def tr(x, y, extra=''):
    return f'translate({x:.1f}px,{y:.1f}px){extra}'


def cursor_svg(cls, name, color, fs=11):
    tw = measure('M', name, fs) + 14
    return (f'<g class="{cls}"><g transform="scale(.95)">'
            f'<path d="{ARROW}" fill="{color}" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></g>'
            f'<rect x="14" y="17" width="{tw:.1f}" height="19" rx="9.5" fill="{color}"/>'
            f'<text x="{14 + tw / 2:.1f}" y="30" text-anchor="middle" font-family="M" font-size="{fs}" fill="#fff">{esc(name)}</text></g>')


# ================================================================ 1. HERO
def build_hero():
    W, H = 1200, 600
    T = 4.2
    tl = Timeline(T)
    FX, FY, FW, FH = 70, 96, 1060, 470
    used_U, used_M = 'REDWANRAHAT', ''

    def P(u, v):
        return FX + u * FW, FY + v * FH

    parts = []
    # ---- canvas card + chrome
    parts.append(f'<defs><pattern id="dots" width="20" height="20" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#cdd2dc"/></pattern>'
                 f'<clipPath id="card"><rect width="{W}" height="{H}" rx="22"/></clipPath>'
                 f'<clipPath id="frame"><rect x="{FX}" y="{FY}" width="{FW}" height="{FH}"/></clipPath>'
                 f'<linearGradient id="name" x1="0" y1="0" x2="0" y2="1"><stop offset=".25" stop-color="{INK}"/><stop offset=".6" stop-color="{INK2}"/><stop offset="1" stop-color="{BLUE2}"/></linearGradient>'
                 f'<linearGradient id="tape" x1="0" x2="1"><stop offset="0" stop-color="{BLUE2}"/><stop offset=".55" stop-color="{BLUE}"/><stop offset="1" stop-color="#4f86ff"/></linearGradient>'
                 f'<radialGradient id="g1" cx=".14" cy=".42" r=".42"><stop offset="0" stop-color="{CYAN}" stop-opacity=".5"/><stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></radialGradient>'
                 f'<radialGradient id="g2" cx=".88" cy=".85" r=".45"><stop offset="0" stop-color="{BLUE}" stop-opacity=".38"/><stop offset="1" stop-color="{BLUE}" stop-opacity="0"/></radialGradient>'
                 f'<radialGradient id="g3" cx=".5" cy=".95" r=".6"><stop offset="0" stop-color="#d7e4ff"/><stop offset="1" stop-color="#d7e4ff" stop-opacity="0"/></radialGradient>'
                 f'<filter id="sh" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="14" stdDeviation="16" flood-color="#070b1f" flood-opacity=".22"/></filter>'
                 f'</defs>')
    parts.append(f'<g clip-path="url(#card)"><rect width="{W}" height="{H}" fill="#eef0f4"/><rect width="{W}" height="{H}" fill="url(#dots)"/>')

    # frame label + frame (drawn by Redwan)
    used_M += 'Hero — Desktop'
    k_label = tl.track([(0.42, None, 0), (0.5, None, 1)])
    parts.append(f'<text class="{k_label}" x="{FX}" y="{FY - 9}" font-family="M" font-size="11" fill="#7a8090">Hero — Desktop</text>')
    k_frame = tl.track([(0.45, 'scale(0)', 1), (0.92, 'scale(1)', 1)], ease='cubic-bezier(.45,0,.25,1)')
    parts.append(f'<g transform="translate({FX} {FY})"><g class="{k_frame}" style="transform-origin:0 0">'
                 f'<rect width="{FW}" height="{FH}" fill="{BG}" filter="url(#sh)"/><rect width="{FW}" height="{FH}" fill="url(#g3)"/></g></g>')

    # ---- frame contents (clipped like a real Figma frame)
    parts.append('<g clip-path="url(#frame)">')
    k_glow = tl.track([(1.05, None, 0), (1.8, None, 1)], ease='ease-out')
    parts.append(f'<g class="{k_glow}"><rect x="{FX}" y="{FY}" width="{FW}" height="{FH}" fill="url(#g1)"/><rect x="{FX}" y="{FY}" width="{FW}" height="{FH}" fill="url(#g2)"/></g>')

    # back tape (info), behind the photo
    info = 'FULL-STACK DEVELOPER  •  DHAKA, BANGLADESH  •  '
    used_U += info
    seg = measure('U5', info, 15, 0.2)
    bx0, by0 = FX - 40, FY + FH * 0.55
    k_bt = tl.track([(1.85, 'scaleX(0)', 1), (2.3, 'scaleX(1)', 1)], ease='cubic-bezier(.45,0,.25,1)')
    k_btx = tl.track([(2.25, None, 0), (2.45, None, 1)])
    reps = int(1300 / seg) + 3
    parts.append(f'<g transform="rotate(4 {FX + FW / 2} {by0 + 17})"><g class="{k_bt}" style="transform-origin:{bx0}px {by0}px">'
                 f'<rect x="{bx0}" y="{by0}" width="{FW + 80}" height="34" fill="{INK}"/></g>'
                 f'<g class="{k_btx}"><g class="mq-r" style="--d:-{seg:.1f}px">'
                 f'<text x="{bx0}" y="{by0 + 23}" font-family="U5" font-size="15" letter-spacing="3" fill="rgba(255,255,255,.88)">{esc(info * reps)}</text></g></g></g>')

    # dashed placeholders + letters of REDWAN, each carried by its own cursor
    size = 178
    ls = -0.05
    name = 'REDWAN'
    total = measure('U', name, size, ls)
    x = FX + (FW - total) / 2
    base = FY + 52 + size * 0.73
    letters, homes = [], []
    for ch in name:
        w = measure('U', ch, size)
        letters.append((ch, x))
        homes.append((x + w / 2, base - size * 0.36))
        x += w + ls * size
    k_ph = tl.track([(0.9, None, 0), (1.0, None, 1), (1.75, None, 1), (1.95, None, 0)])
    parts.append(f'<g class="{k_ph}">' + ''.join(
        f'<text x="{lx:.1f}" y="{base:.1f}" font-family="U" font-size="{size}" fill="none" stroke="{BLUE}" stroke-width="1.2" stroke-dasharray="5 4" opacity=".55">{ch}</text>'
        for ch, lx in letters) + '</g>')
    by_name = ['Design', 'Motion', 'Type', 'UX', 'Brand', 'Copy']
    colors = ['#8b3dff', '#ff2a4a', '#f59e0b', '#0aa36b', '#ec4899', '#0d9488']
    cursors = []
    cx, cy = FX + FW / 2, FY + FH / 2
    for i, ((ch, lx), (hx, hy)) in enumerate(zip(letters, homes)):
        a = math.radians(-165 + i * 30)
        fx, fy = cx + math.cos(a) * 900, cy + math.sin(a) * 620
        t0, d = 0.8 + i * 0.09, 0.72
        kl = tl.track([(t0, tr(fx - hx, fy - hy), 1), (t0 + d, tr(0, 0), 1)])
        parts.append(f'<text class="{kl}" x="{lx:.1f}" y="{base:.1f}" font-family="U" font-size="{size}" fill="url(#name)">{ch}</text>')
        ex = -120 if hx < W / 2 else W + 60
        kc = tl.track([(t0, tr(fx, fy), 1), (t0 + d, tr(hx, hy), 1), (t0 + d + 0.08, tr(hx, hy), 1), (t0 + d + 0.55, tr(ex, hy + 30), 1)])
        cursors.append((kc, by_name[i], colors[i]))

    # portrait, dragged up by Dev
    pdata, (pw, ph) = img_b64(os.path.join(SITE, 'avatars', 'hero-portrait.webp'), height=400, quality=80)
    px, py = FX + (FW - pw) / 2, FY + FH - ph
    grab = (px + pw / 2, py + ph * 0.3)
    kp = tl.track([(1.0, tr(0, 460), 1), (1.85, tr(0, 0), 1)])
    parts.append(f'<g class="{kp}"><g class="float"><image href="{pdata}" x="{px:.1f}" y="{py:.1f}" width="{pw}" height="{ph}" filter="url(#sh)"/></g></g>')
    kdev = tl.track([(1.0, tr(grab[0], grab[1] + 460), 1), (1.85, tr(*grab), 1), (1.95, tr(*grab), 1), (2.45, tr(-120, grab[1] + 60), 1)])
    cursors.append((kdev, 'Dev', '#0f172a'))
    kg = tl.track([(1.78, None, 0), (1.82, None, 1), (2.15, None, 1), (2.45, None, 0)])
    parts.append(f'<rect class="{kg}" x="{FX + FW / 2 - 0.5}" y="{FY}" width="1" height="{FH}" fill="#f24822"/>')

    # front tape (RAHAT ✦), in front of the photo, drawn by Ops
    fs = 46
    seg_w = measure('U', 'RAHAT', fs, -0.04) + 70
    reps = int(1400 / seg_w) + 3
    tx0, ty0, th = FX - 40, FY + FH * 0.67, 74
    k_ft = tl.track([(2.05, 'scaleX(0)', 1), (2.5, 'scaleX(1)', 1)], ease='cubic-bezier(.45,0,.25,1)')
    k_ftx = tl.track([(2.45, None, 0), (2.65, None, 1)])
    items = ''
    for r in range(reps):
        x0 = tx0 + 24 + r * seg_w
        items += f'<text x="{x0:.1f}" y="{ty0 + th / 2 + fs * 0.36:.1f}" font-family="U" font-size="{fs}" letter-spacing="-1.8" fill="#fff">RAHAT</text>'
        items += star(x0 + seg_w - 36, ty0 + th / 2, 15, CYAN)
    parts.append(f'<g transform="rotate(-3 {FX + FW / 2} {ty0 + th / 2})"><g class="{k_ft}" style="transform-origin:{tx0}px {ty0}px">'
                 f'<rect x="{tx0}" y="{ty0}" width="{FW + 80}" height="{th}" fill="url(#tape)"/></g>'
                 f'<g class="{k_ftx}"><g class="mq-l" style="--d:-{seg_w:.1f}px">{items}</g></g></g>')
    parts.append('</g>')  # end frame clip

    # nav pill (dropped by Frontend)
    nw, nh = 400, 40
    nx, ny = FX + (FW - nw) / 2, FY + 14
    used_U += 'REDWAN'
    used_M += "Let's talk Work About Skills"
    kn = tl.track([(1.15, tr(130, -170), 1), (1.75, tr(0, 0), 1)])
    nav = (f'<rect x="{nx}" y="{ny}" width="{nw}" height="{nh}" rx="20" fill="#fff" filter="url(#sh)"/>'
           f'<circle cx="{nx + 22}" cy="{ny + 20}" r="9" fill="{INK}"/>'
           f'<text x="{nx + 38}" y="{ny + 25}" font-family="U" font-size="12" fill="{INK}">REDWAN</text>'
           + ''.join(f'<text x="{nx + 140 + i * 52}" y="{ny + 25}" font-family="M" font-size="10.5" fill="{DIM}">{w}</text>' for i, w in enumerate(['Work', 'About', 'Skills']))
           + f'<rect x="{nx + nw - 96}" y="{ny + 5}" width="90" height="30" rx="15" fill="{BLUE}"/>'
           f'<text x="{nx + nw - 51}" y="{ny + 24}" text-anchor="middle" font-family="M" font-size="11" fill="#fff">Let\'s talk</text>')
    parts.append(f'<g class="{kn}">{nav}</g>')
    kfe = tl.track([(1.15, tr(nx + nw / 2 + 130, ny + 20 - 170), 1), (1.75, tr(nx + nw / 2, ny + 20), 1), (1.85, tr(nx + nw / 2, ny + 20), 1), (2.35, tr(W + 60, ny + 60), 1)])
    cursors.append((kfe, 'Frontend', '#0891b2'))

    # corner captions (SEO, Backend)
    capL, capR = 'FULL-STACK DEVELOPER', 'DHAKA, BANGLADESH'
    capL2, capR2 = 'Websites, web apps, e-commerce', 'From first pixel to final deploy.'
    used_M += capL + capR + capL2 + capR2
    lx_, rx_, cy_ = FX + 22, FX + FW - 22, FY + FH - 34
    kcl = tl.track([(1.9, tr(-260, 120), 1), (2.5, tr(0, 0), 1)])
    kcr = tl.track([(2.0, tr(260, 120), 1), (2.6, tr(0, 0), 1)])
    parts.append(f'<g class="{kcl}"><text x="{lx_}" y="{cy_}" font-family="M" font-size="10" letter-spacing="1" fill="{BLUE}">{capL}</text>'
                 f'<text x="{lx_}" y="{cy_ + 17}" font-family="M" font-size="11" fill="{DIM}">{capL2}</text></g>')
    parts.append(f'<g class="{kcr}"><text x="{rx_}" y="{cy_}" text-anchor="end" font-family="M" font-size="10" letter-spacing="1" fill="{BLUE}">{capR}</text>'
                 f'<text x="{rx_}" y="{cy_ + 17}" text-anchor="end" font-family="M" font-size="11" fill="{DIM}">{capR2}</text></g>')
    cursors.append((tl.track([(1.9, tr(lx_ - 260 + 40, cy_ + 120), 1), (2.5, tr(lx_ + 40, cy_), 1), (2.6, tr(lx_ + 40, cy_), 1), (3.05, tr(-120, cy_ + 40), 1)]), 'SEO', '#65a30d'))
    cursors.append((tl.track([(2.0, tr(rx_ + 260 - 40, cy_ + 120), 1), (2.6, tr(rx_ - 40, cy_), 1), (2.7, tr(rx_ - 40, cy_), 1), (3.15, tr(W + 60, cy_ + 40), 1)]), 'Backend', '#ea580c'))

    # QA + Ops draw the tapes; Art switches on the glow
    def along(x0, y0, deg, frac, length):
        r = math.radians(deg)
        return x0 + math.cos(r) * frac * length, y0 + math.sin(r) * frac * length
    L = FW + 80
    bs = along(bx0, by0 + 17, 4, 0.06, L)
    be = along(bx0, by0 + 17, 4, 0.94, L)
    cursors.append((tl.track([(1.45, tr(-120, by0 + 120), 1), (1.85, tr(*bs), 1), (2.3, tr(*be), 1), (2.38, tr(*be), 1), (2.85, tr(W + 60, be[1] + 40), 1)]), 'QA', '#16a34a'))
    fs_ = along(tx0, ty0 + th / 2, -3, 0.06, L)
    fe_ = along(tx0, ty0 + th / 2, -3, 0.94, L)
    cursors.append((tl.track([(1.65, tr(-120, H + 40), 1), (2.05, tr(*fs_), 1), (2.5, tr(*fe_), 1), (2.58, tr(*fe_), 1), (3.05, tr(W + 60, fe_[1] + 60), 1)]), 'Ops', '#ca8a04'))
    ga = P(0.24, 0.45)
    cursors.append((tl.track([(0.6, tr(-120, 260), 1), (1.0, tr(*ga), 1), (1.12, tr(*ga), 1), (1.6, tr(-120, ga[1] + 40), 1)]), 'Art', '#a855f7'))

    # Client pins a comment
    cmx, cmy = P(0.72, 0.2)
    used_M += 'Ship it, looks fire C'
    kcm = tl.track([(2.85, 'scale(.4)', 0), (3.15, 'scale(1)', 1)], ease='cubic-bezier(.34,1.56,.64,1)')
    parts.append(f'<g transform="translate({cmx:.1f} {cmy:.1f})"><g class="{kcm}" style="transform-origin:0 0">'
                 f'<path d="M0 22 A11 11 0 1 1 11 33 L0 33Z" fill="#ef4444" transform="translate(0 -22)"/>'
                 f'<text x="11" y="5" text-anchor="middle" font-family="M" font-size="11" fill="#fff">C</text>'
                 f'<rect x="28" y="-18" width="150" height="30" rx="9" fill="#fff" filter="url(#sh)"/>'
                 f'<text x="40" y="2" font-family="M" font-size="11.5" fill="{INK}">Ship it, looks fire</text></g></g>')
    cursors.append((tl.track([(2.3, tr(W + 60, -40), 1), (2.82, tr(cmx, cmy), 1), (2.95, tr(cmx, cmy), 1), (3.4, tr(W + 60, cmy + 60), 1)]), 'Client', '#ef4444'))

    # ---- top bar (Figma-style chrome)
    used_M += 'Portfolio / Hero Share +10'
    bar = (f'<rect width="{W}" height="44" fill="#fff"/><rect y="44" width="{W}" height="1" fill="#e3e5ea"/>'
           f'<rect x="14" y="9" width="26" height="26" rx="7" fill="{INK}"/><text x="27" y="27" text-anchor="middle" font-family="U" font-size="12" fill="#fff">R</text>'
           f'<text x="52" y="27" font-family="M" font-size="12" fill="#7a8090">Portfolio <tspan fill="#b3b8c4">/</tspan> <tspan fill="{INK}">Hero</tspan></text>')
    tools_x = W / 2 - 80
    icons = [
        '<path d="M5 3l14 8-6 1.5L10 19z" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linejoin="round"/>',
        '<path d="M8 3v18M16 3v18M3 8h18M3 16h18" stroke="currentColor" stroke-width="1.6"/>',
        '<rect x="4" y="5" width="16" height="14" rx="1.5" stroke="currentColor" stroke-width="1.6" fill="none"/>',
        '<path d="M5 5h14M12 5v14" stroke="currentColor" stroke-width="1.8"/>',
        '<rect x="3.5" y="5" width="17" height="14" rx="2" stroke="currentColor" stroke-width="1.6" fill="none"/><circle cx="9" cy="10" r="1.6" fill="currentColor"/>',
    ]
    # active tool follows the action: frame -> text -> image -> rect -> move
    active = [(0, 0.1), (1, 0.12), (3, 0.75), (4, 0.98), (2, 1.8), (0, 3.4)]
    for i, ic in enumerate(icons):
        stops = [(0, None, 0)]
        for idx, t in active:
            stops.append((t, None, 1 if idx == i else 0))
        stops.sort(key=lambda s: s[0])
        clean = []
        for s in stops:  # hard switches
            if clean:
                clean.append((s[0] - 0.001, None, clean[-1][2]))
            clean.append(s)
        k = tl.track(clean, ease='linear')
        bx = tools_x + i * 36
        bar += (f'<rect class="{k}" x="{bx}" y="7" width="30" height="30" rx="7" fill="{FIG_BLUE}"/>'
                f'<g transform="translate({bx + 7} 14) scale(.67)" style="color:#444b5a">{ic}</g>')
    avs = [('R', '#1a3dff'), ('D', '#8b3dff'), ('M', '#ff2a4a'), ('T', '#f59e0b'), ('U', '#0aa36b')]
    ax = W - 250
    for i, (ch, c) in enumerate(avs):
        bar += f'<circle cx="{ax + i * 18}" cy="22" r="12" fill="{c}" stroke="#fff" stroke-width="2"/><text x="{ax + i * 18}" y="26" text-anchor="middle" font-family="M" font-size="10" fill="#fff">{ch}</text>'
    bar += (f'<text x="{ax + 98}" y="26" font-family="M" font-size="11" fill="#7a8090">+10</text>'
            f'<rect x="{W - 112}" y="9" width="64" height="26" rx="7" fill="{FIG_BLUE}"/><text x="{W - 80}" y="26" text-anchor="middle" font-family="M" font-size="11.5" fill="#fff">Share</text>')
    kplay = tl.track([(3.62, None, 0), (3.66, None, 1)], ease='linear')
    bar += (f'<rect class="{kplay}" x="{W - 41}" y="7" width="30" height="30" rx="7" fill="#e5f4ff"/>'
            f'<path d="M{W - 31} 15v14l11-7z" fill="#444b5a"/><path class="{kplay}" d="M{W - 31} 15v14l11-7z" fill="{FIG_BLUE}"/>')
    kbar = tl.track([(0, tr(0, -46), 1), (0.45, tr(0, 0), 1)], ease='cubic-bezier(.16,1,.3,1)')
    parts.append(f'<g class="{kbar}">{bar}</g>')

    # Redwan: draws the frame, leaves, comes back to press play
    play = (W - 26, 22)
    kr = tl.track([(0, tr(380, H + 40), 1), (0.42, tr(FX, FY), 1), (0.92, tr(FX + FW, FY + FH), 1), (1.4, tr(W + 60, FY + FH + 40), 1),
                   (3.0, tr(W + 60, -40), 1), (3.55, tr(*play), 1), (3.95, tr(*play), 1), (4.2, tr(*play), 0)])
    cursors.insert(0, (kr, 'Redwan', BLUE2))
    for k, n, c in cursors:
        used_M += n
        parts.append(cursor_svg(k, n, c))
    parts.append('</g>')  # card clip
    parts.append(f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="22" fill="none" stroke="#dfe3ea"/>')

    css = (font_css({'U': used_U + 'R', 'U5': info, 'M': used_M})
           + '.mq-l{animation:mql 9s linear infinite}.mq-r{animation:mql 12s linear infinite reverse}'
           + '@keyframes mql{to{transform:translateX(var(--d))}}'
           + '.float{animation:fl 6s ease-in-out 2s infinite}@keyframes fl{50%{transform:translateY(-8px)}}'
           + tl.out())
    write('hero.svg', svg_doc(W, H, css, ''.join(parts), 'Redwan Rahat — a team of cursors builds the hero, live'))


# ================================================================ 2. SECTION TITLES
def build_title(file, index, words, accent, dark=False):
    W, H = 1200, 110
    text = ' '.join(words)
    fs = 46
    x = 0
    spans = ''
    for w in words:
        spans += f'<tspan fill="{(CYAN if dark else BLUE2) if w == accent else ("#f0f3ff" if dark else INK)}">{esc(w)} </tspan>'
    lab = f'({index})'
    tw = measure('U', text, fs, -0.03)
    css = (font_css({'U': text, 'M': lab})
           + '.ln{stroke-dasharray:1200;stroke-dashoffset:1200;animation:dr 1.6s cubic-bezier(.65,0,.35,1) .2s forwards}@keyframes dr{to{stroke-dashoffset:0}}'
           + '.tx{animation:up .9s cubic-bezier(.16,1,.3,1) both}@keyframes up{from{transform:translateY(40px);opacity:0}}'
           + '.dot{animation:pl 2.4s ease-in-out infinite}@keyframes pl{50%{opacity:.25}}')
    body = (f'<defs><clipPath id="c"><rect width="{W}" height="86"/></clipPath></defs>'
            f'<circle class="dot" cx="6" cy="22" r="4" fill="{BLUE}"/>'
            f'<text x="20" y="27" font-family="M" font-size="13" letter-spacing="2" fill="{BLUE}">{lab}</text>'
            f'<g clip-path="url(#c)"><text class="tx" x="0" y="80" font-family="U" font-size="{fs}" letter-spacing="-1.4">{spans}</text></g>'
            f'<line class="ln" x1="{min(tw + 30, W - 40):.0f}" y1="68" x2="{W}" y2="68" stroke="{BLUE}" stroke-opacity=".35" stroke-width="1.5"/>'
            f'<line x1="0" y1="{H - 1}" x2="{W}" y2="{H - 1}" stroke="{"#30363d" if dark else "#dfe3ea"}"/>')
    write(file, svg_doc(W, H, css, body, text))


# ================================================================ 3. ABOUT: typing editor + roles
def build_about():
    W, H = 1200, 470
    lines = [
        [('const ', '#c792ea'), ('redwan', '#82aaff'), (' = {', '#cfd6ff')],
        [('  role', '#7fdbca'), (': ', '#cfd6ff'), ('"Full-stack developer"', '#c3e88d'), (',', '#cfd6ff')],
        [('  based', '#7fdbca'), (': ', '#cfd6ff'), ('"Dhaka, Bangladesh"', '#c3e88d'), (',', '#cfd6ff')],
        [('  building', '#7fdbca'), (': [', '#cfd6ff'), ('"SolasArc"', '#c3e88d'), (', ', '#cfd6ff'), ('"Blusshy"', '#c3e88d'), ('],', '#cfd6ff')],
        [('  stack', '#7fdbca'), (': [', '#cfd6ff'), ('"React"', '#c3e88d'), (', ', '#cfd6ff'), ('"Next.js"', '#c3e88d'), (', ', '#cfd6ff'), ('"Django"', '#c3e88d'), ('],', '#cfd6ff')],
        [('  ships', '#7fdbca'), (': ', '#cfd6ff'), ('"first pixel → final deploy"', '#c3e88d'), (',', '#cfd6ff')],
        [('  openToWork', '#7fdbca'), (': ', '#cfd6ff'), ('true', '#f78c6c'), (',', '#cfd6ff')],
        [('};', '#cfd6ff')],
    ]
    used_M = 'redwan.ts 12345678 '
    EX, EY, EW, EH = 0, 0, 640, H
    fs, lh = 15.5, 34
    cw = measure('M', 'a', fs)
    css_k = []
    body = [f'<rect x="{EX}" y="{EY}" width="{EW}" height="{EH}" rx="18" fill="#0b1024"/>'
            f'<rect x="{EX}" y="{EY + 46}" width="{EW}" height="1" fill="#1d2440"/>']
    for i, c in enumerate(['#ff5f57', '#febc2e', '#28c840']):
        body.append(f'<circle cx="{EX + 24 + i * 20}" cy="{EY + 23}" r="6" fill="{c}"/>')
    body.append(f'<rect x="{EX + 96}" y="{EY + 10}" width="118" height="28" rx="7" fill="#151c38"/>'
                f'<text x="{EX + 112}" y="{EY + 29}" font-family="M" font-size="12" fill="#cfd6ff">redwan.ts</text>')
    covers = []
    t = 0.5
    y0 = EY + 92
    for i, segs in enumerate(lines):
        text = ''.join(s for s, _ in segs)
        used_M += text
        y = y0 + i * lh
        n = len(text)
        dur = max(0.25, n * 0.028)
        lw = n * cw + 4
        body.append(f'<text x="{EX + 22}" y="{y}" font-family="M" font-size="12.5" fill="#3b4570">{i + 1}</text>')
        body.append(f'<text x="{EX + 52}" y="{y}" font-family="M" font-size="{fs}" xml:space="preserve">'
                    + ''.join(f'<tspan fill="{c}">{esc(s)}</tspan>' for s, c in segs) + '</text>')
        # a cover slides right one character at a time = typing
        css_k.append(f'.cv{i}{{animation:cv{i} {dur:.2f}s steps({n}) {t:.2f}s both}}@keyframes cv{i}{{from{{transform:translateX(0)}}to{{transform:translateX({lw:.1f}px)}}}}')
        covers.append(f'<rect class="cv{i}" x="{EX + 50}" y="{y - fs}" width="{EW - 70}" height="{fs + 9}" fill="#0b1024"/>')
        css_k.append(f'.cr{i}{{animation:cr{i} {dur:.2f}s steps({n}) {t:.2f}s both, crv{i} .01s {t + dur:.2f}s forwards}}'
                     f'@keyframes cr{i}{{from{{transform:translateX(0);opacity:1}}to{{transform:translateX({lw - 4:.1f}px);opacity:1}}}}'
                     f'@keyframes crv{i}{{to{{opacity:{1 if i == len(lines) - 1 else 0}}}}}')
        covers.append(f'<rect class="cr{i}" x="{EX + 52}" y="{y - fs + 2}" width="9" height="{fs + 4}" fill="{CYAN}" opacity="0"/>')
        t += dur + 0.12
    css_k.append('.blink{animation:bk 1s steps(1) infinite}@keyframes bk{50%{opacity:0}}')
    # covers slide right as they "type"; clip them to the editor so they never show outside it
    body.append(f'<defs><clipPath id="ed"><rect x="{EX + 46}" y="{EY + 50}" width="{EW - 52}" height="{EH - 56}"/></clipPath></defs>'
                f'<g clip-path="url(#ed)">{"".join(covers)}</g>')

    # right: roles timeline
    RX = 680
    roles = [
        ('Present', 'Chief Executive Officer', 'SolasArc'),
        ('Present', 'Founder & Lead Developer', 'Blusshy'),
        ('Present', 'Senior SEO Executive', 'Trinet Marketing'),
        ('2020 — Now', 'Full-Stack Web Developer', 'Independent'),
        ('2025 — Now', 'B.Sc. Computer Science & Eng.', 'BUBT'),
    ]
    used_U = 'NOW'
    body.append(f'<text x="{RX}" y="24" font-family="M" font-size="12" letter-spacing="2" fill="{BLUE}">WHERE I SHIP</text>')
    used_M += 'WHERE I SHIP'
    body.append(f'<line class="tline" x1="{RX + 9}" y1="52" x2="{RX + 9}" y2="{H - 20}" stroke="{BLUE}" stroke-opacity=".3" stroke-width="2"/>')
    css_k.append(f'.tline{{stroke-dasharray:{H};stroke-dashoffset:{H};animation:dr 1.8s cubic-bezier(.65,0,.35,1) .3s forwards}}@keyframes dr{{to{{stroke-dashoffset:0}}}}')
    for i, (when, role, org) in enumerate(roles):
        y = 50 + i * 82
        d = 0.5 + i * 0.22
        used_M += when + org
        used_U += role
        css_k.append(f'.rc{i}{{animation:rc .8s cubic-bezier(.16,1,.3,1) {d:.2f}s both}}')
        accent = i < 2
        body.append(f'<g class="rc{i}">'
                    f'<circle cx="{RX + 9}" cy="{y + 34}" r="7" fill="{BLUE2 if accent else "#fff"}" stroke="{BLUE2}" stroke-width="2"/>'
                    f'<rect x="{RX + 30}" y="{y}" width="{W - RX - 30}" height="68" rx="14" fill="{"#fff" if not accent else BLUE2}" stroke="{"#e3e5ea" if not accent else BLUE2}"/>'
                    f'<text x="{RX + 50}" y="{y + 29}" font-family="U5" font-size="16" fill="{"#fff" if accent else INK}">{esc(role)}</text>'
                    f'<text x="{RX + 50}" y="{y + 52}" font-family="M" font-size="12" fill="{ICE if accent else DIM}">{esc(org)}</text>'
                    f'<text x="{W - 20}" y="{y + 52}" text-anchor="end" font-family="M" font-size="11" fill="{CYAN if accent else MUTED}">{esc(when)}</text></g>')
    css_k.append('@keyframes rc{from{transform:translateX(60px);opacity:0}}')
    css = font_css({'M': used_M, 'U5': used_U}) + ''.join(css_k)
    write('about.svg', svg_doc(W, H, css, ''.join(body), 'About Redwan Rahat'))


# ================================================================ 4. STACK: three marquee rows of skill pills
SKILL_ROWS = [
    [('html5', 'HTML5'), ('css3', 'CSS3'), ('javascript', 'JavaScript'), ('typescript', 'TypeScript'), ('react', 'React'), ('nextdotjs', 'Next.js'),
     ('vuedotjs', 'Vue'), ('astro', 'Astro'), ('vite', 'Vite'), ('reactquery', 'React Query'), ('tailwindcss', 'Tailwind'), ('sass', 'Sass'),
     ('bootstrap', 'Bootstrap'), ('framer', 'Framer Motion'), ('greensock', 'GSAP'), ('threedotjs', 'Three.js'), ('webgl', 'WebGL')],
    [('nodedotjs', 'Node.js'), ('express', 'Express'), ('python', 'Python'), ('django', 'Django'), ('php', 'PHP'), ('stripe', 'Stripe'),
     ('mysql', 'MySQL'), ('postgresql', 'PostgreSQL'), ('mongodb', 'MongoDB'), ('firebase', 'Firebase'), ('supabase', 'Supabase'),
     ('wordpress', 'WordPress'), ('woocommerce', 'WooCommerce'), ('shopify', 'Shopify'), ('elementor', 'Elementor'), ('webflow', 'Webflow'), ('wix', 'Wix')],
    [('vercel', 'Vercel'), ('netlify', 'Netlify'), ('hostinger', 'Hostinger'), ('cpanel', 'cPanel'), ('cloudflare', 'Cloudflare'), ('render', 'Render'),
     ('railway', 'Railway'), ('docker', 'Docker'), ('nginx', 'Nginx'), ('githubactions', 'GitHub Actions'), ('git', 'Git'), ('github', 'GitHub'),
     ('figma', 'Figma'), ('npm', 'npm'), ('pnpm', 'pnpm'), ('googleanalytics', 'Analytics'), ('notion', 'Notion'), ('openai', 'ChatGPT'), ('claude', 'Claude')],
]


def icon_paths(slug):
    p = os.path.join(SITE, 'skills', slug + '.svg')
    if not os.path.exists(p):
        return ''
    return ''.join(re.findall(r'<path d="([^"]+)"', open(p, encoding='utf-8').read()))


def build_stack():
    W, H = 1200, 300
    fs, ph, gap = 15, 52, 12
    used = ''
    rows_svg, css, defs_rows = [], [], []
    for r, row in enumerate(SKILL_ROWS):
        y = 22 + r * 90
        x = 0
        pills = ''
        for slug, label in row:
            used += label
            tw = measure('M', label, fs)
            w = 22 + 24 + 12 + tw + 22
            d = icon_paths(slug)
            dark = (r + row.index((slug, label))) % 5 == 0
            fill, txt, ic = (BLUE2, '#fff', '#fff') if dark else ('#fff', INK, BLUE2)
            pills += (f'<g transform="translate({x:.1f} {y})"><rect width="{w:.1f}" height="{ph}" rx="{ph / 2}" fill="{fill}" stroke="{"#e1e6f2" if not dark else BLUE2}"/>'
                      + (f'<path d="{d}" transform="translate(22 14) scale(1)" fill="{ic}"/>' if d else '')
                      + f'<text x="{22 + 24 + 12}" y="{ph / 2 + 5.5}" font-family="M" font-size="{fs}" fill="{txt}">{esc(label)}</text></g>')
            x += w + gap
        seg = x
        dur = seg / (38 + r * 6)
        css.append(f'.r{r}{{animation:mq{r} {dur:.1f}s linear infinite{" reverse" if r % 2 else ""}}}@keyframes mq{r}{{to{{transform:translateX(-{seg:.1f}px)}}}}')
        defs_rows.append(f'<g id="row{r}">{pills}</g>')
        rows_svg.append(f'<g class="r{r}"><use href="#row{r}"/><use href="#row{r}" x="{seg:.1f}"/></g>')
    body = (f'<defs><linearGradient id="f" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".07" stop-color="#fff"/><stop offset=".93" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
            f'<mask id="m"><rect width="{W}" height="{H}" fill="url(#f)"/></mask>{"".join(defs_rows)}</defs>'
            f'<g mask="url(#m)">{"".join(rows_svg)}</g>')
    write('stack.svg', svg_doc(W, H, font_css({'M': used}) + ''.join(css), body, 'Tech stack'))


# ================================================================ 5. PROJECT CARDS
PROJECTS = [
    ('lambo', 'work_lamborghini_temerario.png', 'Lamborghini Temerario', 'Automotive showcase', 'lambowebsiteprojectredwanrahat.vercel.app'),
    ('redlunar', 'work_redlunar.png', 'RedLunar Esports', 'Esports brand', 'redlunar-esports.vercel.app'),
    ('solasarc', 'work_solasarc.png', 'SolasArc', 'Software agency', 'solasarc.com'),
    ('purrnote', 'work_notes.png', 'Purrnote', 'Note-taking app', 'note-taking-website-seven.vercel.app'),
    ('blusshy', 'work_blusshy.png', 'Blusshy', 'E-commerce', 'blusshy.com'),
    ('uniparking', 'work_uni_parking.png', 'Uni Parking', 'Management platform', 'uni-parking-project.vercel.app'),
]


def build_project(i, slug, shot, title, tag, url):
    W, H = 600, 430
    data, (iw, ih) = img_b64(os.path.join(SITE, 'works', shot), width=1120, fmt='JPEG', quality=70)
    sx, sy, sw = 16, 52, W - 32
    sh = 300
    num = f'{i + 1:02d}'
    used_M = url + tag.upper() + num + 'LIVE ↗'
    css = (font_css({'U': title, 'M': used_M})
           + '.kb{animation:kb 14s ease-in-out infinite alternate;transform-origin:50% 0}@keyframes kb{from{transform:scale(1)}to{transform:scale(1.08) translateY(-10px)}}'
           + '.sh{animation:sh 5.5s ease-in-out infinite}@keyframes sh{0%,55%{transform:translateX(-200px)}100%{transform:translateX(760px)}}'
           + '.dot{animation:pl 1.6s ease-in-out infinite}@keyframes pl{50%{opacity:.3}}')
    body = (f'<defs><clipPath id="s"><rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" rx="10"/></clipPath>'
            f'<linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".35"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>'
            f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="22" fill="#fff" stroke="#e1e6f2"/>'
            + ''.join(f'<circle cx="{30 + k * 16}" cy="27" r="5" fill="{c}"/>' for k, c in enumerate(['#ff5f57', '#febc2e', '#28c840']))
            + f'<rect x="88" y="14" width="{W - 104}" height="26" rx="13" fill="#f2f4f9"/>'
            f'<circle class="dot" cx="104" cy="27" r="4" fill="#28c840"/>'
            f'<text x="116" y="31.5" font-family="M" font-size="11.5" fill="{DIM}">{esc(url)}</text>'
            f'<g clip-path="url(#s)"><rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" fill="#eef0f4"/>'
            f'<g class="kb"><image href="{data}" x="{sx}" y="{sy}" width="{sw}" height="{sw * ih / iw:.1f}" preserveAspectRatio="xMidYMin slice"/></g>'
            f'<rect class="sh" x="{sx}" y="{sy}" width="160" height="{sh}" fill="url(#g)" transform="skewX(-12)"/></g>'
            f'<text x="24" y="{sy + sh + 46}" font-family="U" font-size="22" fill="{INK}">{esc(title)}</text>'
            f'<text x="24" y="{sy + sh + 68}" font-family="M" font-size="11" letter-spacing="1.5" fill="{BLUE}">{num}  ·  {esc(tag.upper())}</text>'
            f'<rect x="{W - 98}" y="{sy + sh + 24}" width="76" height="34" rx="17" fill="{BLUE2}"/>'
            f'<text x="{W - 60}" y="{sy + sh + 46}" text-anchor="middle" font-family="M" font-size="12" fill="#fff">LIVE ↗</text>')
    write(f'project-{slug}.svg', svg_doc(W, H, css, body, f'{title} — {tag}'))


# ================================================================ 6. FOOTER
def build_footer():
    W, H = 1200, 330
    l1, l2a, l2b = "LET'S BUILD", 'SOMETHING', 'LIMITLESS.'
    used_U = l1 + l2a + l2b + 'RAHAT'
    used_M = 'rahatofc912@gmail.com  ·  exentas.com  ·  Dhaka, GMT+6 OPEN FOR PROJECTS'
    fs = 64
    seg_w = measure('U', 'RAHAT', 34, -0.04) + 56
    reps = int(1500 / seg_w) + 3
    items = ''
    for r in range(reps):
        x0 = 20 + r * seg_w
        items += f'<text x="{x0:.1f}" y="{247:.1f}" font-family="U" font-size="34" letter-spacing="-1.4" fill="#fff">RAHAT</text>' + star(x0 + seg_w - 28, 235, 11, CYAN)
    css = (font_css({'U': used_U, 'M': used_M})
           + '.mq{animation:mq 8s linear infinite}@keyframes mq{to{transform:translateX(-' + f'{seg_w:.1f}' + 'px)}}'
           + '.a{animation:up 1s cubic-bezier(.16,1,.3,1) both}.b{animation:up 1s cubic-bezier(.16,1,.3,1) .15s both}@keyframes up{from{transform:translateY(80px);opacity:0}}'
           + '.dot{animation:pl 1.6s ease-in-out infinite}@keyframes pl{50%{opacity:.25}}')
    body = (f'<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BLUE2}"/><stop offset="1" stop-color="#0c1a9e"/></linearGradient>'
            f'<linearGradient id="t" x1="0" x2="1"><stop offset="0" stop-color="{INK}"/><stop offset="1" stop-color="#101633"/></linearGradient>'
            f'<clipPath id="c"><rect width="{W}" height="{H}" rx="24"/></clipPath><clipPath id="tx"><rect width="{W}" height="190"/></clipPath></defs>'
            f'<g clip-path="url(#c)"><rect width="{W}" height="{H}" fill="url(#bg)"/>'
            f'<circle cx="1050" cy="40" r="260" fill="{CYAN}" opacity=".12"/>'
            f'<g clip-path="url(#tx)"><text class="a" x="40" y="96" font-family="U" font-size="{fs}" letter-spacing="-3" fill="#fff">{esc(l1)}</text>'
            f'<text class="b" x="40" y="166" font-family="U" font-size="{fs}" letter-spacing="-3" fill="#fff">{l2a} <tspan fill="{CYAN}">{l2b}</tspan></text></g>'
            f'<g transform="rotate(-2.5 600 236)"><rect x="-40" y="206" width="1300" height="60" fill="url(#t)"/><g class="mq">{items}</g></g>'
            f'<circle class="dot" cx="48" cy="300" r="5" fill="#4ade80"/>'
            f'<text x="62" y="304" font-family="M" font-size="12" letter-spacing="1.5" fill="#fff">OPEN FOR PROJECTS</text>'
            f'<text x="{W - 40}" y="304" text-anchor="end" font-family="M" font-size="12" fill="{ICE}">rahatofc912@gmail.com  ·  exentas.com  ·  Dhaka, GMT+6</text></g>')
    write('footer.svg', svg_doc(W, H, css, body, "Let's build something limitless"))


if __name__ == '__main__':
    print('Building assets ->', OUT)
    build_hero()
    for dark in (False, True):  # GitHub swaps these with its light / dark theme via <picture>
        sfx = '-dark' if dark else ''
        build_title(f'title-about{sfx}.svg', '01', ['WHO', 'I', 'AM'], 'AM', dark)
        build_title(f'title-stack{sfx}.svg', '02', ['THE', 'TOOLKIT'], 'TOOLKIT', dark)
        build_title(f'title-work{sfx}.svg', '03', ['THINGS', "I'VE", 'SHIPPED'], 'SHIPPED', dark)
        build_title(f'title-pulse{sfx}.svg', '04', ['THE', 'PULSE'], 'PULSE', dark)
    build_about()
    build_stack()
    for i, p in enumerate(PROJECTS):
        build_project(i, *p)
    build_footer()
    print('done')
