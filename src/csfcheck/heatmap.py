"""Function-by-category heat map of the profile, drawn as SVG on the server.

One row per CSF function, one cell per category. A cell's colour is the
share of its target reached (red at none, amber at half, green at all of
it) and its bar shows current against target on the 0-3 scale. Categories
that do not apply to the organisation are grey.
"""

from __future__ import annotations

import textwrap
from xml.sax.saxutils import escape

from .catalog import Catalog
from .engine import Result
from .rollup import Rollup, by_category

LABEL_W, CELL_W, CELL_H, GAP, TOP = 150, 168, 100, 6, 8
STOPS = ((0.0, (0xF4, 0xA6, 0xA6)), (0.5, (0xFD, 0xE6, 0x8A)), (1.0, (0xA7, 0xE3, 0xB5)))
NOT_APPLICABLE = "#e5e7eb"


def attainment_colour(attainment: float | None) -> str:
    """Hex colour for a share of target reached (``None`` means not applicable)."""
    if attainment is None:
        return NOT_APPLICABLE
    x = min(max(attainment, 0.0), 1.0)
    for (x0, c0), (x1, c1) in zip(STOPS, STOPS[1:]):
        if x <= x1:
            t = (x - x0) / (x1 - x0)
            return "#" + "".join(f"{round(a + (b - a) * t):02x}" for a, b in zip(c0, c1))
    return "#" + "".join(f"{v:02x}" for v in STOPS[-1][1])


def _cell(x: int, y: int, c: Rollup) -> list[str]:
    tip = f"{c.id} {c.title}: "
    if c.current is None:
        tip += f"not applicable ({c.excluded} subcategories excluded)"
    else:
        tip += (f"current {c.current:.2f}, target {c.target:.2f}, {c.at_target} of {c.assessed} "
                f"subcategories at target")
    out = [
        f'<g class="cell" data-category="{c.id}">',
        f"<title>{escape(tip)}</title>",
        f'<rect x="{x}" y="{y}" width="{CELL_W}" height="{CELL_H}" rx="6" '
        f'fill="{attainment_colour(c.attainment)}" stroke="#ffffff" stroke-width="1"/>',
        f'<text x="{x + 10}" y="{y + 19}" class="cid">{c.id}</text>',
    ]
    for i, line in enumerate(textwrap.wrap(c.title, 27, max_lines=2, placeholder="...")):
        out.append(f'<text x="{x + 10}" y="{y + 36 + 13 * i}" class="ctitle">{escape(line)}</text>')
    if c.current is None:
        out.append(f'<text x="{x + 10}" y="{y + 80}" class="cnum">not applicable</text>')
    else:
        track = CELL_W - 20
        scale = track / 3
        out += [
            f'<text x="{x + 10}" y="{y + 72}" class="cnum">{c.current:.1f} of {c.target:.1f}</text>',
            f'<text x="{x + CELL_W - 10}" y="{y + 72}" class="cpct" text-anchor="end">'
            f"{round(100 * c.attainment)}%</text>",
            f'<rect x="{x + 10}" y="{y + 80}" width="{track}" height="8" rx="2" fill="#ffffff" fill-opacity="0.7"/>',
            f'<rect x="{x + 10}" y="{y + 80}" width="{c.current * scale:.1f}" height="8" rx="2" '
            f'fill="#1f3864" class="current"/>',
            f'<line x1="{x + 10 + c.target * scale:.1f}" x2="{x + 10 + c.target * scale:.1f}" '
            f'y1="{y + 76}" y2="{y + 92}" stroke="#b91c1c" stroke-width="2" class="target"/>',
        ]
    out.append("</g>")
    return out


def render_svg(catalog: Catalog, result: Result) -> str:
    grid = by_category(catalog, result)
    cols = max(len(cells) for cells in grid.values())
    width = LABEL_W + cols * (CELL_W + GAP)
    legend_y = TOP + len(grid) * (CELL_H + GAP) + 14
    height = legend_y + 34
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" '
        f'height="{height}" role="img" aria-labelledby="hm-title" class="heatmap">',
        '<title id="hm-title">CSF 2.0 profile: current against target by category</title>',
        "<style>text{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;fill:#111827}"
        ".fid{font-size:15px;font-weight:700}.ftitle{font-size:12px;fill:#4b5563}"
        ".cid{font-size:13px;font-weight:700}.ctitle{font-size:11px}.cnum{font-size:12px}"
        ".cpct{font-size:12px;font-weight:700}.legend{font-size:11px;fill:#4b5563}</style>",
    ]
    for row, (fid, cells) in enumerate(grid.items()):
        y = TOP + row * (CELL_H + GAP)
        parts.append(f'<text x="0" y="{y + 40}" class="fid">{fid}</text>')
        parts.append(f'<text x="0" y="{y + 58}" class="ftitle">{escape(catalog.functions[fid].title.capitalize())}</text>')
        for col, cell in enumerate(cells):
            parts += _cell(LABEL_W + col * (CELL_W + GAP), y, cell)

    # Legend: the colour ramp, the bar and the target tick.
    x = LABEL_W
    for i, share in enumerate((0, 0.25, 0.5, 0.75, 1)):
        parts.append(f'<rect x="{x + 34 * i}" y="{legend_y}" width="34" height="12" '
                     f'fill="{attainment_colour(share)}"/>')
    parts += [
        f'<text x="{x}" y="{legend_y + 26}" class="legend">0%</text>',
        f'<text x="{x + 170}" y="{legend_y + 26}" class="legend" text-anchor="end">100% of target</text>',
        f'<rect x="{x + 200}" y="{legend_y}" width="12" height="12" fill="{NOT_APPLICABLE}"/>',
        f'<text x="{x + 218}" y="{legend_y + 10}" class="legend">not applicable</text>',
        f'<rect x="{x + 320}" y="{legend_y + 2}" width="40" height="8" fill="#1f3864"/>',
        f'<text x="{x + 366}" y="{legend_y + 10}" class="legend">current (0-3)</text>',
        f'<line x1="{x + 460}" x2="{x + 460}" y1="{legend_y - 2}" y2="{legend_y + 14}" stroke="#b91c1c" stroke-width="2"/>',
        f'<text x="{x + 468}" y="{legend_y + 10}" class="legend">target</text>',
        "</svg>",
    ]
    return "\n".join(parts)
