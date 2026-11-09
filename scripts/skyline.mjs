// Contribution Skyline: your real GitHub contribution calendar as an isometric
// cobalt city. Each day is a block, height = how much you shipped that day.
// Blocks drop in week by week.
//
// Usage: node scripts/skyline.mjs <github-username> [out.svg]
// Reads the public calendar at github.com/users/<user>/contributions (no token).

import { writeFileSync } from 'node:fs';

const user = process.argv[2] || 'Exentas97';
const out = process.argv[3] || 'assets/skyline.svg';

const res = await fetch(`https://github.com/users/${user}/contributions`, {
  headers: { 'User-Agent': `${user}-profile-skyline` }
});
if (!res.ok) throw new Error(`GitHub returned ${res.status}`);
const html = await res.text();

// day cells: id="contribution-day-component-<weekday>-<week>" data-level="0..4"
const days = new Map();
for (const m of html.matchAll(/data-date="(\d{4}-\d{2}-\d{2})"\s+id="contribution-day-component-(\d+)-(\d+)"\s+data-level="(\d)"/g)) {
  days.set(`contribution-day-component-${m[2]}-${m[3]}`, { date: m[1], dow: +m[2], week: +m[3], level: +m[4], count: 0 });
}
// exact counts live in the tooltips
for (const m of html.matchAll(/for="(contribution-day-component-\d+-\d+)"[^>]*>([^<]*)<\/tool-tip>/g)) {
  const d = days.get(m[1]);
  const n = m[2].match(/^(\d[\d,]*) contribution/);
  if (d) d.count = n ? +n[1].replace(/,/g, '') : 0;
}
const cells = [...days.values()];
if (!cells.length) throw new Error('No contribution cells found — GitHub markup may have changed.');

const total = cells.reduce((s, d) => s + d.count, 0);
const max = Math.max(1, ...cells.map(d => d.count));
const weeks = Math.max(...cells.map(d => d.week)) + 1;
const best = cells.reduce((a, b) => (b.count > a.count ? b : a));
let streak = 0, longest = 0;
for (const d of [...cells].sort((a, b) => a.date.localeCompare(b.date))) {
  streak = d.count ? streak + 1 : 0;
  longest = Math.max(longest, streak);
}
const activeDays = cells.filter(d => d.count).length;

// ---- isometric geometry
// a shallow dimetric view: the 53 weeks run wide across the card, the 7 days recede
const W = 1200, H = 560;
const A = [16.4, 3.4];                     // one week step  (right, slightly down)
const B = [-9, 7.2];                       // one day step   (left, down)
const ox = W / 2 - ((weeks - 1) * A[0] + 6 * B[0]) / 2 - B[0] / 2, oy = 232;
const iso = (w, d) => [ox + w * A[0] + d * B[0], oy + w * A[1] + d * B[1]];
const height = d => (d.count ? 8 + Math.pow(d.count / max, 0.55) * 130 : 0);
const shades = [
  ['#dfe5f5', '#cdd6ee', '#bcc7e6'],      // empty lot
  ['#9db8ff', '#7d9dff', '#6688f5'],
  ['#5f8bff', '#4673ff', '#3a63ec'],
  ['#2f6bff', '#2456e6', '#1c48cc'],
  ['#1a3dff', '#132fd1', '#0e25a8']
];

// draw back-to-front so nearer blocks overlap farther ones
const depth = d => d.week * A[1] + d.dow * B[1];
const order = [...cells].sort((a, b) => depth(a) - depth(b) || a.week - b.week);
let blocks = '';
const gap = 0.12; // a sliver of street between blocks
for (const d of order) {
  const h = height(d);
  const [x0, y0] = iso(d.week + gap / 2, d.dow + gap / 2);
  const a = [A[0] * (1 - gap), A[1] * (1 - gap)], b = [B[0] * (1 - gap), B[1] * (1 - gap)];
  const p0 = [x0, y0], p1 = [x0 + a[0], y0 + a[1]], p3 = [x0 + b[0], y0 + b[1]], p2 = [p1[0] + b[0], p1[1] + b[1]];
  const up = p => [p[0], p[1] - h];
  const [top, front, side] = shades[d.level];
  const delay = (0.3 + d.week * 0.035 + d.dow * 0.012).toFixed(3);
  const P = (pts) => pts.map(p => p.map(v => v.toFixed(1)).join(',')).join(' ');
  let g = '';
  if (h > 0) {
    g += `<polygon points="${P([up(p3), up(p2), p2, p3])}" fill="${front}"/>`;   // front face (along the weeks)
    g += `<polygon points="${P([up(p1), up(p2), p2, p1])}" fill="${side}"/>`;    // right face (along the days)
  }
  g += `<polygon points="${P([up(p0), up(p1), up(p2), up(p3)])}" fill="${top}"/>`;
  const title = `<title>${d.date}: ${d.count} contribution${d.count === 1 ? '' : 's'}</title>`;
  blocks += h
    ? `<g class="b" style="animation-delay:${delay}s">${title}${g}</g>`
    : `<g class="f" style="animation-delay:${delay}s">${title}${g}</g>`;
}

const fmt = n => n.toLocaleString('en-US');
const nice = s => new Date(s + 'T00:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
const stat = (x, label, value) =>
  `<text x="${x}" y="506" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" font-size="11" letter-spacing="2" fill="#2f6bff">${label}</text>` +
  `<text x="${x}" y="536" font-family="'Segoe UI',Inter,system-ui,sans-serif" font-weight="800" font-size="26" fill="#070b1f">${value}</text>`;

const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${user}'s contribution skyline: ${total} contributions in the last year">
<title>${user} — contribution skyline</title>
<style>
.b{animation:drop .7s cubic-bezier(.34,1.4,.64,1) both}
.f{animation:fade .5s ease-out both}
@keyframes drop{from{transform:translateY(-140px);opacity:0}}
@keyframes fade{from{opacity:0}}
.dot{animation:pl 1.6s ease-in-out infinite}@keyframes pl{50%{opacity:.25}}
</style>
<defs>
<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f7f9ff"/><stop offset="1" stop-color="#e9efff"/></linearGradient>
<linearGradient id="sc" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".55"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<clipPath id="c"><rect width="${W}" height="${H}" rx="24"/></clipPath>
</defs>
<g clip-path="url(#c)">
<rect width="${W}" height="${H}" fill="url(#bg)"/>
<circle cx="180" cy="120" r="260" fill="#5fd4ff" opacity=".14"/>
<text x="40" y="54" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" font-size="12" letter-spacing="2" fill="#2f6bff"><tspan class="dot">●</tspan> LIVE · UPDATED DAILY</text>
<text x="40" y="96" font-family="'Segoe UI',Inter,system-ui,sans-serif" font-weight="800" font-size="34" letter-spacing="-1" fill="#070b1f">Contribution <tspan fill="#1a3dff">Skyline</tspan></text>
<text x="40" y="122" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" font-size="12" fill="#4f5878">one block per day · height = what I shipped</text>
<g>${blocks}</g>
<line x1="40" y1="478" x2="${W - 40}" y2="478" stroke="#d5dcef"/>
${stat(40, 'LAST 12 MONTHS', fmt(total))}
${stat(300, 'ACTIVE DAYS', fmt(activeDays))}
${stat(520, 'LONGEST STREAK', `${longest} day${longest === 1 ? '' : 's'}`)}
${stat(780, 'BEST DAY', `${best.count} · ${nice(best.date)}`)}
</g>
</svg>`;

writeFileSync(out, svg);
console.log(`skyline: ${cells.length} days, ${total} contributions, ${weeks} weeks -> ${out}`);
