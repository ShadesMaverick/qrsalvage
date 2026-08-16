"""Draw the figures for the method page -- measured, not illustrated.

Every figure here is computed from the same code the solver runs on. The module maps come out
of :func:`structure_mask`, the brightness fields out of :func:`estimate_levels`, the objective
curve out of :func:`evaluate`, the probing order out of the very generator the search iterates.
Nothing is redrawn by hand.

That is not fastidiousness. A diagram of a method is a claim about the method, and a hand-drawn
one goes stale silently: the code changes, the picture keeps arguing for the old behaviour, and
the page becomes confidently wrong -- which is the exact failure mode this project exists to
avoid. Regenerating is one command, so the picture can always be made to tell the truth again.

Usage:
    python docs/make_method_figures.py
    python docs/make_method_figures.py --image fixtures/engraved-curved-medium.png
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from qrsalvage.core.decoding import _subsets_by_cost
from qrsalvage.core.geometry import evaluate
from qrsalvage.core.matrix import ModuleMatrix
from qrsalvage.core.pipeline import DEFAULT_SIZES, _attempt
from qrsalvage.core.qrspec import block_plan
from qrsalvage.core.sampling import estimate_levels, posterior_dark, sample_cells, warp
from qrsalvage.core.structure import modules_for_version, structure_mask

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "qrsalvage" / "web"

# The page's own tokens, plus two chart hues. The page pink is a heading colour and sits too
# light to carry a mark on the panel background, so the marks use a darker, more saturated step
# of the same hue. The pair was checked for colour-vision separation rather than chosen by eye,
# and no figure relies on hue alone: every series is also labelled where it is drawn.
FG = "#f2f4f5"
MUTED = "#93a3b0"
LINE = "#37485a"
FAINT = "#2e3d4c"
ROSE = "#e05a86"
BLUE = "#3f9ad8"

# Module maps read as what they are: a cell the standard pins is drawn at its true value, a cell
# that carries content is drawn in slate. So the figure is a picture of the code, not a key.
CELL_DARK = "#0e161d"
CELL_LIGHT = "#eef1f3"
CELL_DATA = "#42566a"

FONT = "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif"
MONO = "ui-monospace, 'Cascadia Code', 'SF Mono', Consolas, monospace"

SCALE = 12  # pixels per module in the rectified image, as the pipeline uses


# --------------------------------------------------------------------------------------- svg


@dataclass(frozen=True)
class Axis:
    """A linear map from data units to figure coordinates."""

    lo: float
    hi: float
    start: float
    end: float

    def __call__(self, value: float) -> float:
        span = self.hi - self.lo or 1.0
        return self.start + (value - self.lo) / span * (self.end - self.start)


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(
    x: float,
    y: float,
    body: str,
    *,
    size: float = 11,
    fill: str = MUTED,
    anchor: str = "start",
    font: str = FONT,
    weight: str = "400",
) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{font}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{esc(body)}</text>'
    )


def line(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    stroke: str = LINE,
    width: float = 1,
    dash: str | None = None,
) -> str:
    extra = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{stroke}" stroke-width="{width}"{extra}/>'
    )


def rect(
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    fill: str,
    rx: float = 0,
    opacity: float = 1.0,
    stroke: str | None = None,
) -> str:
    extra = f' stroke="{stroke}" stroke-width="1"' if stroke else ""
    return (
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{max(w, 0):.2f}" height="{max(h, 0):.2f}" '
        f'rx="{rx}" fill="{fill}" opacity="{opacity}"{extra}/>'
    )


def polyline(points, *, stroke: str, width: float = 2, dash: str | None = None) -> str:
    body = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    extra = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<polyline points="{body}" fill="none" stroke="{stroke}" stroke-width="{width}" '
        f'stroke-linejoin="round" stroke-linecap="round"{extra}/>'
    )


def area(points, baseline: float, *, fill: str, opacity: float) -> str:
    body = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    first, last = points[0][0], points[-1][0]
    return (
        f'<polygon points="{first:.2f},{baseline:.2f} {body} {last:.2f},{baseline:.2f}" '
        f'fill="{fill}" opacity="{opacity}"/>'
    )


def band(upper, lower, *, fill: str, opacity: float) -> str:
    body = " ".join(f"{x:.2f},{y:.2f}" for x, y in [*upper, *reversed(lower)])
    return f'<polygon points="{body}" fill="{fill}" opacity="{opacity}"/>'


def dot(x: float, y: float, *, fill: str, r: float = 2.6) -> str:
    # The 1px surface ring keeps overlapping samples countable instead of blurring into a blob.
    return (
        f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="{fill}" '
        f'stroke="#26333f" stroke-width="1"/>'
    )


def swatch(x: float, y: float, label: str, fill: str, *, stroke: str | None = None) -> str:
    return rect(x, y - 8, 11, 11, fill=fill, rx=2, stroke=stroke) + text(
        x + 17, y + 1, label, size=11
    )


def svg(width: float, height: float, parts) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'width="{width:.0f}" height="{height:.0f}" role="img">\n' + "\n".join(parts) + "\n</svg>\n"
    )


def nice_ticks(lo: float, hi: float, count: int = 4) -> list[float]:
    """Round tick values inside a range, so an axis never reads 137.4."""
    span = max(hi - lo, 1e-9)
    raw = span / max(count, 1)
    magnitude = 10 ** np.floor(np.log10(raw))
    step = float(min((s for s in (1, 2, 5, 10) if s * magnitude >= raw), default=10) * magnitude)
    first = np.ceil(lo / step) * step
    return [round(float(t), 6) for t in np.arange(first, hi + step / 2, step) if t <= hi]


def y_axis(ax: Axis, x: float, ticks, *, fmt="{:g}", grid_to: float | None = None) -> list[str]:
    """A recessive axis: hairline grid, no box, labels in muted ink."""
    parts = []
    for value in ticks:
        y = ax(value)
        if grid_to is not None:
            parts.append(line(x, y, grid_to, y, stroke=FAINT))
        parts.append(text(x - 7, y + 3.5, fmt.format(value), size=10, anchor="end", font=MONO))
    return parts


def x_axis(ax: Axis, y: float, ticks, *, fmt="{:g}") -> list[str]:
    parts = [line(ax(ax.lo), y, ax(ax.hi), y, stroke=LINE)]
    for value in ticks:
        x = ax(value)
        parts.append(line(x, y, x, y + 4, stroke=LINE))
        parts.append(text(x, y + 16, fmt.format(value), size=10, anchor="middle", font=MONO))
    return parts


# ----------------------------------------------------------------------------- measurements


@dataclass
class Measured:
    """One fixture, taken through the pipeline exactly as the solver takes it."""

    gray: np.ndarray
    corners: np.ndarray
    modules: int
    means: np.ndarray
    known_dark: np.ndarray
    known_light: np.ndarray
    fit: object
    matrix: ModuleMatrix
    wrong_known: int
    known_total: int


def measure(path: Path) -> Measured:
    image = cv2.imread(str(path))
    if image is None:
        raise SystemExit(f"cannot read {path}")

    # The private entry point on purpose: the figures need the rectified grey image and the
    # winning corners, which solve() has no reason to hand back to a caller that only wants text.
    _, gray, _, _, fits, _, _ = _attempt(image, DEFAULT_SIZES, False, None)
    if not fits:
        raise SystemExit(f"no grid could be fitted on {path}")
    best = min(fits, key=lambda f: (f.wrong_known, -f.quality))

    known_dark, known_light = structure_mask(best.modules)
    warped = warp(gray, best.corners, best.modules, SCALE)
    means, spread = sample_cells(warped, best.modules, SCALE)
    fit = estimate_levels(means, spread, known_dark, known_light)
    posterior = posterior_dark(means, fit)

    return Measured(
        gray=gray,
        corners=best.corners,
        modules=best.modules,
        means=means,
        known_dark=known_dark,
        known_light=known_light,
        fit=fit,
        matrix=ModuleMatrix(posterior, known_dark, known_light),
        wrong_known=best.wrong_known,
        known_total=best.known_total,
    )


# --------------------------------------------------------------------------------- figure 01


def figure_known(versions=(1, 3, 6)) -> tuple[str, list[str]]:
    """The cells the standard fixes, drawn at their true values, per version."""
    unit = 6
    gap = 40
    pad = 10
    maps = [(v, *structure_mask(modules_for_version(v))) for v in versions]
    widths = [modules_for_version(v) * unit for v, _, _ in maps]
    total = sum(widths) + gap * (len(maps) - 1)
    tallest = max(widths)
    height = pad + tallest + 46 + 22

    parts: list[str] = []
    notes: list[str] = []
    x = pad
    for (version, dark, light), width in zip(maps, widths, strict=True):
        n = modules_for_version(version)
        base = pad + tallest - width  # bottom-aligned, so the growth in size stays visible
        parts.append(rect(x - 1, base - 1, width + 2, width + 2, fill=CELL_DATA))
        # One path per colour rather than a rect per cell: three maps are 2 500 cells, and as
        # separate elements that is sixty kilobytes shipped inside the wheel for one picture.
        for mask, fill in ((dark, CELL_DARK), (light, CELL_LIGHT)):
            runs = []
            for r in range(n):
                c = 0
                while c < n:
                    if not mask[r, c]:
                        c += 1
                        continue
                    end = c
                    while end < n and mask[r, end]:
                        end += 1
                    runs.append(
                        f"M{x + c * unit:g} {base + r * unit:g}h{(end - c) * unit:g}v{unit:g}"
                        f"h-{(end - c) * unit:g}z"
                    )
                    c = end
            parts.append(f'<path d="{"".join(runs)}" fill="{fill}"/>')

        known = int(dark.sum() + light.sum())
        cells = n * n
        share = round(100 * known / cells)
        parts.append(
            text(
                x,
                pad + tallest + 20,
                f"version {version} · {n} × {n}",
                size=12,
                fill=FG,
                weight="600",
            )
        )
        parts.append(
            text(x, pad + tallest + 38, f"{known} / {cells} known · {share} %", size=11, font=MONO)
        )
        notes.append(f"version {version}: {n}x{n}, {known}/{cells} known ({share} %)")
        x += width + gap

    legend_y = height - 8
    parts.append(swatch(pad, legend_y, "fixed dark", CELL_DARK, stroke=LINE))
    parts.append(swatch(pad + 118, legend_y, "fixed light", CELL_LIGHT))
    parts.append(swatch(pad + 240, legend_y, "carries data", CELL_DATA))
    return svg(total + 2 * pad, height, parts), notes


# --------------------------------------------------------------------------------- figure 02


def figure_levels(m: Measured) -> tuple[str, list[str]]:
    """The two brightness fields along the timing row, with the samples they were fitted to.

    Row 6 is the one row that carries a known cell at every single column -- finder, separator,
    then the alternating timing pattern -- so both levels can be shown measured across the full
    width instead of extrapolated into the middle.
    """
    n = m.modules
    row = 6
    dark_curve = m.fit.dark[row]
    light_curve = m.fit.light[row]
    means = m.means[row]

    left, right, top, bottom = 46, 660, 22, 176
    # Padding proportional to the span, not a fixed number of grey values: on an image this
    # faint the whole signal is thirty grey values wide, and a fixed margin would squash it.
    low = float(min(dark_curve.min(), means.min()))
    high = float(max(light_curve.max(), means.max()))
    margin = 0.16 * (high - low)
    lo, hi = low - margin, high + margin
    ax = Axis(0, n - 1, left, right)
    ay = Axis(lo, hi, bottom, top)

    upper = [(ax(c), ay(light_curve[c])) for c in range(n)]
    lower = [(ax(c), ay(dark_curve[c])) for c in range(n)]
    mid = [(ax(c), ay((dark_curve[c] + light_curve[c]) / 2)) for c in range(n)]

    parts: list[str] = []
    parts += y_axis(ay, left, nice_ticks(lo, hi, 5), grid_to=right)
    parts.append(band(upper, lower, fill=BLUE, opacity=0.10))
    parts.append(polyline(mid, stroke=MUTED, width=1.5, dash="5 4"))
    parts.append(polyline(upper, stroke=BLUE))
    parts.append(polyline(lower, stroke=ROSE))

    for c in range(n):
        if m.known_dark[row, c]:
            parts.append(dot(ax(c), ay(means[c]), fill=ROSE))
        elif m.known_light[row, c]:
            parts.append(dot(ax(c), ay(means[c]), fill=BLUE))

    # The contrast, marked where it is narrowest -- the place the whole method has to survive.
    contrast = light_curve - dark_curve
    worst = int(np.argmin(contrast))
    xw = ax(worst)
    parts.append(line(xw, ay(dark_curve[worst]), xw, ay(light_curve[worst]), stroke=FG, width=1.5))
    parts.append(
        line(xw - 4, ay(light_curve[worst]), xw + 4, ay(light_curve[worst]), stroke=FG, width=1.5)
    )
    parts.append(
        line(xw - 4, ay(dark_curve[worst]), xw + 4, ay(dark_curve[worst]), stroke=FG, width=1.5)
    )
    # Below the caliper, in the empty margin: at the midpoint the label would sit on T.
    parts.append(
        text(
            xw,
            ay(dark_curve[worst]) + 20,
            f"C = {contrast[worst]:.0f}",
            size=11,
            fill=FG,
            anchor="middle",
            font=MONO,
        )
    )

    parts += x_axis(ax, bottom + 6, list(range(0, n, 4)))
    parts.append(text((left + right) / 2, bottom + 36, "module column", size=11, anchor="middle"))
    parts.append(text(8, top - 8, "grey value", size=11))

    parts.append(
        text(right + 6, ay(light_curve[-1]) + 4, "L", size=13, fill=BLUE, font=MONO, weight="600")
    )
    parts.append(
        text(right + 6, ay(dark_curve[-1]) + 4, "D", size=13, fill=ROSE, font=MONO, weight="600")
    )
    parts.append(
        text(
            right + 6,
            ay((dark_curve[-1] + light_curve[-1]) / 2) + 4,
            "T",
            size=13,
            fill=MUTED,
            font=MONO,
            weight="600",
        )
    )

    legend_y = bottom + 62
    parts.append(swatch(left, legend_y, "known-dark cells, and D fitted through them", ROSE))
    parts.append(swatch(left, legend_y + 20, "known-light cells, and L fitted through them", BLUE))
    parts.append(swatch(left, legend_y + 40, "T, their midpoint", MUTED))

    notes = [
        f"levels: contrast spans {contrast.min():.0f}..{contrast.max():.0f} grey values "
        f"across row {row}"
    ]
    return svg(700, legend_y + 56, parts), notes


# --------------------------------------------------------------------------------- figure 03


def figure_posterior(m: Measured, band_width: float = 0.15) -> tuple[str, list[str]]:
    """The same measurement read by a confident cell and by one that disagrees with itself.

    The two spreads are the extremes actually present in the image, not round numbers. Drawn at
    inner percentiles the two curves come out all but identical -- which is itself worth knowing,
    and is why the figure states the widths rather than leaving the reader to judge by eye.
    """
    sigma_clean = float(m.fit.sigma.min())
    sigma_noisy = float(m.fit.sigma.max())
    d_hat, l_hat = 0.0, 1.0  # working in units of the local contrast, where D and L are 0 and 1

    xs = np.linspace(-0.55, 1.55, 400)

    def posterior(sigma: float) -> np.ndarray:
        log_odds = ((xs - l_hat) ** 2 - (xs - d_hat) ** 2) / (2.0 * sigma**2)
        return 1.0 / (1.0 + np.exp(-np.clip(log_odds, -60.0, 60.0)))

    def inside_band(sigma: float) -> tuple[float, float]:
        """The range of measurements this cell would report as undecided."""
        within = xs[np.abs(posterior(sigma) - 0.5) < band_width]
        return float(within.min()), float(within.max())

    pad_l, pad_r, top, bottom = 46, 18, 26, 168
    panel = 322
    parts: list[str] = []

    # -- left panel: the two Gaussians the log-odds comes from
    ax = Axis(xs[0], xs[-1], pad_l, panel - pad_r)
    ay = Axis(0, 1.05, bottom, top)

    def bell(centre: float, sigma: float):
        values = np.exp(-((xs - centre) ** 2) / (2 * sigma**2))
        return [(ax(x), ay(v)) for x, v in zip(xs, values, strict=True)]

    dark_bell = bell(d_hat, sigma_clean)
    light_bell = bell(l_hat, sigma_clean)
    parts.append(area(dark_bell, bottom, fill=ROSE, opacity=0.16))
    parts.append(area(light_bell, bottom, fill=BLUE, opacity=0.16))
    parts.append(polyline(dark_bell, stroke=ROSE))
    parts.append(polyline(light_bell, stroke=BLUE))
    parts.append(line(ax(0.5), top, ax(0.5), bottom, stroke=MUTED, dash="4 4"))
    parts.append(text(ax(0.5), bottom + 30, "T", size=12, fill=MUTED, anchor="middle", font=MONO))
    parts.append(
        text(
            ax(d_hat),
            bottom + 30,
            "D",
            size=12,
            fill=ROSE,
            anchor="middle",
            font=MONO,
            weight="600",
        )
    )
    parts.append(
        text(
            ax(l_hat),
            bottom + 30,
            "L",
            size=12,
            fill=BLUE,
            anchor="middle",
            font=MONO,
            weight="600",
        )
    )
    parts.append(line(pad_l, bottom, panel - pad_r, bottom, stroke=LINE))
    parts.append(text(pad_l, top - 10, "the two levels a cell is scored against", size=11, fill=FG))

    # -- right panel: what that turns into, at two spreads
    off = panel + 14
    ax2 = Axis(xs[0], xs[-1], off + pad_l, off + panel - pad_r)
    ay2 = Axis(0, 1, bottom, top)

    parts.append(
        rect(
            off + pad_l,
            ay2(0.5 + band_width),
            (panel - pad_r - pad_l),
            ay2(0.5 - band_width) - ay2(0.5 + band_width),
            fill=MUTED,
            opacity=0.13,
        )
    )
    parts += y_axis(ay2, off + pad_l, [0, 0.5, 1], fmt="{:.1f}", grid_to=off + panel - pad_r)

    clean = [(ax2(x), ay2(p)) for x, p in zip(xs, posterior(sigma_clean), strict=True)]
    noisy = [(ax2(x), ay2(p)) for x, p in zip(xs, posterior(sigma_noisy), strict=True)]
    parts.append(polyline(noisy, stroke=ROSE, width=2, dash="6 4"))
    parts.append(polyline(clean, stroke=ROSE, width=2))
    parts.append(line(off + pad_l, bottom, off + panel - pad_r, bottom, stroke=LINE))

    parts.append(text(off + pad_l, top - 10, "P(dark)", size=11, fill=FG))
    parts.append(
        text(
            off + panel - pad_r, top - 10, f"uncertain band ±{band_width:g}", size=10, anchor="end"
        )
    )
    # How wide a measurement has to be doubted before the cell reports doubt. This is the whole
    # quantity the section argues about, and by eye the two curves look nearly identical -- so
    # it is drawn as a measured length rather than left to the reader's impression.
    widths = []
    for index, (sigma, colour, dash) in enumerate(
        ((sigma_clean, FG, None), (sigma_noisy, FG, "6 4"))
    ):
        first, last = inside_band(sigma)
        widths.append(last - first)
        y = ay2(0.5) + (18 if index else -18)
        parts.append(line(ax2(first), y, ax2(last), y, stroke=colour, width=2.5, dash=dash))
        parts.append(line(ax2(first), y - 4, ax2(first), y + 4, stroke=colour, width=1.5))
        parts.append(line(ax2(last), y - 4, ax2(last), y + 4, stroke=colour, width=1.5))
        # Labelled to the left, where the curves have already flattened: to the right they run
        # off the panel.
        parts.append(
            text(
                ax2(first) - 9,
                y + 4,
                f"σ = {sigma:.2f} → {last - first:.2f} wide",
                size=10,
                fill=FG if index == 0 else MUTED,
                anchor="end",
                font=MONO,
            )
        )

    parts.append(
        text(
            off,
            bottom + 52,
            "measured value, in units of the local contrast (D = 0, L = 1)",
            size=10,
            anchor="middle",
        )
    )

    notes = [
        f"posterior: sigma spans {sigma_clean:.3f}..{sigma_noisy:.3f}; the uncertain band is "
        f"{widths[0]:.2f} wide at the cleanest cell and {widths[1]:.2f} at the noisiest, "
        f"a factor of {widths[1] / widths[0]:.1f}"
    ]
    return svg(2 * panel + 14, bottom + 62, parts), notes


# --------------------------------------------------------------------------------- figure 04


def figure_objective(m: Measured, reach: float = 6.0, step: float = 0.25):
    """What the search follows, above what the result is judged by.

    The whole grid is slid sideways and both numbers are recorded at every offset. They are two
    different quantities on two different scales, so they get two panels rather than two axes.
    """
    offsets = np.arange(-reach, reach + step / 2, step)
    quality, wrong = [], []
    for delta in offsets:
        corners = m.corners.copy()
        corners[:, 0] += delta
        fit = evaluate(m.gray, corners, m.modules, SCALE, m.known_dark, m.known_light)
        quality.append(fit.quality)
        wrong.append(fit.wrong_known)
    quality = np.array(quality)
    wrong = np.array(wrong)

    left, right = 54, 664
    ax = Axis(-reach, reach, left, right)
    top_a, bottom_a = 26, 132
    top_b, bottom_b = 176, 282

    ay = Axis(float(quality.min()) - 0.03, float(quality.max()) + 0.03, bottom_a, top_a)
    by = Axis(0, float(wrong.max()) * 1.12 + 1, bottom_b, top_b)

    best = int(np.argmax(quality))
    parts: list[str] = []

    q_ticks = np.round(np.linspace(quality.min(), quality.max(), 3), 2)
    parts += y_axis(ay, left, list(q_ticks), fmt="{:.2f}", grid_to=right)
    parts.append(
        polyline([(ax(o), ay(q)) for o, q in zip(offsets, quality, strict=True)], stroke=ROSE)
    )
    parts.append(text(left, top_a - 10, "Q — mean tanh(4·margin), continuous", size=11, fill=FG))

    # A staircase, drawn as one: the count really is flat and then jumps, and smoothing it into
    # a line would hide the exact property the panel exists to show.
    stair: list[tuple[float, float]] = []
    for i, o in enumerate(offsets):
        stair.append((ax(o - step / 2), by(wrong[i])))
        stair.append((ax(o + step / 2), by(wrong[i])))
    w_max = int(wrong.max())
    w_ticks = sorted({0, int(wrong.min()), w_max})
    parts += y_axis(by, left, w_ticks, fmt="{:d}", grid_to=right)
    parts.append(polyline(stair, stroke=BLUE, width=2))
    parts.append(
        text(left, top_b - 10, "wrong known cells — integer, flat, then a jump", size=11, fill=FG)
    )

    guide = ax(offsets[best])
    parts.insert(0, line(guide, top_a - 4, guide, bottom_b, stroke=FG, width=1, dash="4 5"))
    parts.append(dot(guide, ay(quality[best]), fill=ROSE, r=3.4))
    parts.append(
        text(
            right,
            top_a - 10,
            f"best Q = {quality[best]:.3f} · {wrong[best]} wrong",
            size=10,
            fill=FG,
            anchor="end",
            font=MONO,
        )
    )

    parts += x_axis(ax, bottom_b + 6, [-6, -4, -2, 0, 2, 4, 6], fmt="{:+g}")
    parts.append(
        text(
            (left + right) / 2,
            bottom_b + 38,
            "the whole grid slid sideways, in pixels",
            size=11,
            anchor="middle",
        )
    )

    notes = [
        f"objective: Q peaks at {offsets[best]:+.2f} px with {wrong[best]} of "
        f"{m.known_total} known cells wrong; the count reaches {w_max} within ±{reach:g} px"
    ]
    return svg(700, bottom_b + 52, parts), notes


# --------------------------------------------------------------------------------- figure 05


def figure_probe(m: Measured, max_cells: int = 22, shown: int = 60):
    """The cost of doubting a cell, and the order the doubts are then combined in."""
    cost_field = m.matrix.flip_cost()
    order = np.argsort(cost_field, axis=None)
    order = [int(i) for i in order if np.isfinite(cost_field.flat[i])][:max_cells]
    costs = np.array([cost_field.flat[i] for i in order], dtype=np.float64)

    totals: list[float] = []
    labels: list[str] = []
    for subset in _subsets_by_cost(costs, shown):
        totals.append(float(costs[list(subset)].sum()))
        if len(labels) < 5:
            labels.append("{" + ",".join(str(i + 1) for i in subset) + "}")

    pad_l, top, bottom = 46, 26, 176
    panel = 336
    parts: list[str] = []

    # -- left: the ladder the order is built from
    ax = Axis(0, max_cells, pad_l, panel - 16)
    ay = Axis(0, float(costs.max()) * 1.1 + 1e-6, bottom, top)
    ticks = [0, round(costs.max() / 2, 1), round(float(costs.max()), 1)]
    parts += y_axis(ay, pad_l, ticks, fmt="{:g}", grid_to=panel - 16)
    width = (ax(1) - ax(0)) - 2  # 2 px of surface between neighbouring bars
    for i, c in enumerate(costs):
        parts.append(rect(ax(i) + 1, ay(c), width, bottom - ay(c), fill=ROSE, rx=2))
    parts.append(line(pad_l, bottom, panel - 16, bottom, stroke=LINE))
    parts.append(text(pad_l, top - 10, "flip cost per cell, cheapest first", size=11, fill=FG))
    parts.append(
        text(
            ax(0.5),
            ay(costs[0]) - 8,
            f"{costs[0]:.2f}",
            size=10,
            fill=FG,
            anchor="middle",
            font=MONO,
        )
    )
    parts.append(
        text(
            ax(max_cells - 0.5),
            ay(costs[-1]) - 8,
            f"{costs[-1]:.1f}",
            size=10,
            fill=FG,
            anchor="middle",
            font=MONO,
        )
    )
    parts.append(
        text(
            pad_l + (panel - 16 - pad_l) / 2,
            bottom + 26,
            f"the {max_cells} least certain cells",
            size=10,
            anchor="middle",
        )
    )

    # -- right: what the heap emits, and in which order
    off = panel + 18
    bx = Axis(1, len(totals), off + pad_l, off + panel - 16)
    by = Axis(0, max(totals) * 1.1, bottom, top)
    t_ticks = [0, round(max(totals) / 2, 1), round(max(totals), 1)]
    parts += y_axis(by, off + pad_l, t_ticks, fmt="{:g}", grid_to=off + panel - 16)
    parts.append(polyline([(bx(i + 1), by(t)) for i, t in enumerate(totals)], stroke=BLUE, width=2))
    parts.append(line(off + pad_l, bottom, off + panel - 16, bottom, stroke=LINE))
    parts.append(
        text(off + pad_l, top - 10, "total cost of each subset, as emitted", size=11, fill=FG)
    )
    for i in range(len(labels)):
        parts.append(dot(bx(i + 1), by(totals[i]), fill=BLUE, r=2.8))
    # Under the title, not on the curve: the first emissions bunch into the bottom-left corner,
    # where a label would sit on the axis and on its own data points.
    parts.append(
        text(off + pad_l, top + 12, "first out: " + " ".join(labels), size=10, fill=FG, font=MONO)
    )
    parts.append(
        text(
            off + pad_l + (panel - 16 - pad_l) / 2,
            bottom + 26,
            f"subsets in emission order (first {len(totals)})",
            size=10,
            anchor="middle",
        )
    )

    notes = [
        f"probing: cheapest cell costs {costs[0]:.2f}, the dearest of the {max_cells} "
        f"costs {costs[-1]:.1f}; "
        f"first subsets {' '.join(labels)}"
    ]
    return svg(2 * panel + 18, bottom + 42, parts), notes


# --------------------------------------------------------------------------------- figure 06


def figure_erasures(version: int = 1, ecc: str = "M"):
    """Why the third state is worth having: one budget, spent three ways.

    The smallest version is used deliberately. The arithmetic is identical at every size, and
    ten check symbols fit on a page at a width where the individual symbols are still countable
    -- which is the entire point of drawing it rather than stating the inequality.
    """
    plan = block_plan(version, ecc)
    t = plan.ec_per_block
    half = t // 2
    scenarios = [
        (half, 0, "decide every doubtful cell"),
        (half // 2, t - 2 * (half // 2), "decide some, abstain on the rest"),
        (0, t, "abstain on every doubtful cell"),
    ]

    pad_l, top = 300, 34
    cell = 26
    row_h = 52
    width = pad_l + t * cell + 20
    height = top + len(scenarios) * row_h + 40

    parts: list[str] = [
        text(
            16,
            top - 14,
            f"the correction budget of one block — a version {version}-{ecc} code "
            f"carries {t} check symbols",
            size=11,
            fill=FG,
        )
    ]

    for index, (errors, erasures, caption) in enumerate(scenarios):
        y = top + index * row_h
        parts.append(rect(pad_l, y, t * cell, cell, fill=FAINT, rx=3))
        x = pad_l
        for _ in range(errors):
            # An error is two symbols wide because that is literally what it costs.
            parts.append(rect(x + 1, y, 2 * cell - 2, cell, fill=ROSE, rx=3))
            parts.append(
                text(
                    x + cell,
                    y + 17,
                    "2",
                    size=11,
                    fill="#1b252e",
                    anchor="middle",
                    font=MONO,
                    weight="600",
                )
            )
            x += 2 * cell
        for _ in range(erasures):
            parts.append(rect(x + 1, y, cell - 2, cell, fill=BLUE, rx=3))
            parts.append(
                text(
                    x + cell / 2,
                    y + 17,
                    "1",
                    size=11,
                    fill="#1b252e",
                    anchor="middle",
                    font=MONO,
                    weight="600",
                )
            )
            x += cell
        parts.append(text(pad_l - 14, y + 6, caption, size=11, fill=FG, anchor="end"))
        parts.append(
            text(
                pad_l - 14,
                y + 23,
                f"{errors} decided wrong, {erasures} left unknown",
                size=10,
                anchor="end",
            )
        )
        parts.append(
            text(
                pad_l - 14,
                y + 39,
                f"2·{errors} + {erasures} = {2 * errors + erasures} ≤ {t}",
                size=10,
                fill=FG,
                anchor="end",
                font=MONO,
            )
        )

    legend_y = height - 12
    parts.append(swatch(16, legend_y, "an error costs two — one to find it, one to fix it", ROSE))
    parts.append(swatch(330, legend_y, "an erasure costs one, its place is known", BLUE))
    return svg(width, height, parts), [
        f"erasures: version {version}-{ecc} carries {t} check symbols per block over "
        f"{plan.blocks} block(s)"
    ]


# ---------------------------------------------------------------------------------- assembly


FIGURES = ("fig-known", "fig-levels", "fig-posterior", "fig-objective", "fig-probe", "fig-rs")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_image = ROOT / "fixtures" / "engraved-curved-hard.png"
    parser.add_argument("--image", type=Path, default=default_image)
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    m = measure(args.image)
    print(
        f"measured {args.image.name}: version grid {m.modules}x{m.modules}, "
        f"{m.wrong_known}/{m.known_total} known cells wrong\n"
    )

    built = {
        "fig-known": figure_known(),
        "fig-levels": figure_levels(m),
        "fig-posterior": figure_posterior(m),
        "fig-objective": figure_objective(m),
        "fig-probe": figure_probe(m),
        "fig-rs": figure_erasures(),
    }
    for name in FIGURES:
        body, notes = built[name]
        path = OUT / f"{name}.svg"
        path.write_text(body, encoding="utf-8")
        print(f"{path.relative_to(ROOT)}  {len(body) / 1024:.1f} kB")
        for note in notes:
            print(f"    {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
