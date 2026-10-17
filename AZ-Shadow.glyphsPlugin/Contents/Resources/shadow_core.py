"""AZ Shadow's logic without AppKit: the settings, the alignment offset, the draw gate and the focus AZ Argus'
report sets (``shadow.focus``). Spec: AZ-Argus/docs/superpowers/specs/2026-10-15-az-shadow-design.md."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import cache
from typing import TypeVar

from GlyphsApp import Glyphs

PREF = "com.hugojourdan.AZShadow."
ALIGNMENTS = ("LEFT", "CENTER", "RIGHT")
SCOPES = ("current", "all")
DEFAULT_RGB = (0.0, 0.48, 1.0)  # system blue, AZ Argus' fallback
# light: the edited layer while the Select tool is on, so its outline and nodes read through
FILL_ALPHA = 0.15  # x opacity
STROKE_ALPHA = 0.30  # x opacity
# strong: the edited layer under any other tool (Text...) and the tab's other layers (scope All), so the shadow reads
# over ink (Hugo, 2026-10-15; all four alphas picked live with a tuning panel)
STRONG_FILL_ALPHA = 0.60  # x opacity
STRONG_STROKE_ALPHA = 0.75  # x opacity
# the width difference: under each shadowed layer, while width_diff is on (Hugo, 2026-10-15)
WIDTH_LABEL_GAP = 100.0  # font units under the layer's bounds (the label's top; centred on the advance width)
WIDTH_LABEL_SIZE = 11.0  # pt on screen, at any zoom; monospaced, Medium
# AZ Argus' keys from before the split (2026-10): read while Shadow's own are unset, never written
ARGUS_KEYS = {
    "opacity": "com.hugojourdan.AZArgus.ghostOpacity",
    "color": "com.hugojourdan.AZArgus.ghostColor",
    "scope": "com.hugojourdan.AZArgus.ghostScope",
}

T = TypeVar("T")


@dataclass
class Prefs:
    glyph: str = "H"
    opacity: float = 1.0
    color: tuple[float, float, float] = DEFAULT_RGB
    alignment: str = "CENTER"
    scope: str = "all"
    width_diff: bool = False  # the width difference with the shadow under each layer; no control: Glyphs.defaults (README)


def as_glyph(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return str(value).strip() or None


def as_opacity(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0.0, min(1.0, float(value)))


def as_color(value: object) -> tuple[float, float, float] | None:
    """(r, g, b) in 0..1, clamped; from any iterable but a string (Glyphs.defaults hands back an NSArray)."""
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        return None
    try:
        parts = [max(0.0, min(1.0, float(c))) for c in value]
    except (TypeError, ValueError):
        return None
    return (parts[0], parts[1], parts[2]) if len(parts) >= 3 else None


def as_bool(value: object) -> bool | None:
    """A bool; Glyphs.defaults hands one back as an NSNumber (an int subclass): 0 / 1 read as a bool too."""
    if isinstance(value, bool):
        return value
    return bool(value) if isinstance(value, int) and value in (0, 1) else None


def as_alignment(value: object) -> str | None:
    return str(value) if isinstance(value, str) and value in ALIGNMENTS else None


def as_scope(value: object) -> str | None:
    return str(value) if isinstance(value, str) and value in SCOPES else None


VALIDATORS: dict[str, Callable[[object], object]] = {
    "glyph": as_glyph,
    "opacity": as_opacity,
    "color": as_color,
    "alignment": as_alignment,
    "scope": as_scope,
    "width_diff": as_bool,
}


def _load(name: str, valid: Callable[[object], T | None], default: T) -> T:
    """Shadow's saved value for ``name``, else AZ Argus' old one, else ``default``."""
    for key in (PREF + name, ARGUS_KEYS.get(name)):
        if key is not None:
            value = valid(Glyphs.defaults[key])
            if value is not None:
                return value
    return default


def load_prefs() -> Prefs:
    default = Prefs()
    return Prefs(
        glyph=_load("glyph", as_glyph, default.glyph),
        opacity=_load("opacity", as_opacity, default.opacity),
        color=_load("color", as_color, default.color),
        alignment=_load("alignment", as_alignment, default.alignment),
        scope=_load("scope", as_scope, default.scope),
        width_diff=_load("width_diff", as_bool, default.width_diff),
    )


@cache
def prefs() -> Prefs:
    """The one Prefs the reporter and every window's palette share (loaded on first use; the palette changes it)."""
    return load_prefs()


def save(prefs: Prefs, name: str, value: object) -> bool:
    """A setting changed in the palette: validated, then on ``prefs`` and in Glyphs.defaults. False when refused."""
    valid = VALIDATORS[name](value)
    if valid is None:
        return False
    setattr(prefs, name, valid)
    Glyphs.defaults[PREF + name] = list(valid) if isinstance(valid, tuple) else valid
    return True


def reload(prefs: Prefs, name: str) -> bool:
    """``name`` re-read from Glyphs.defaults into ``prefs`` (a setting with no control, set from the Macro panel). True
    when it changed."""
    value = _load(name, VALIDATORS[name], getattr(Prefs(), name))
    if value == getattr(prefs, name):
        return False
    setattr(prefs, name, value)
    return True


def offset_x(alignment: str, target: tuple[float, float, float], ref: tuple[float, float, float]) -> float:
    """How far right the reference outline moves. ``target`` / ``ref``: (bounds x, bounds width, advance width) of the
    drawn layer and of the reference layer. LEFT and RIGHT flush the bounds' edges, CENTER the advance widths'
    centres."""
    target_x, target_w, target_advance = target
    ref_x, ref_w, ref_advance = ref
    if alignment == "LEFT":
        return target_x - ref_x
    if alignment == "RIGHT":
        return target_x - ref_x + target_w - ref_w
    return target_advance / 2.0 - ref_advance / 2.0


def width_diff(width: float, ref_width: float) -> str | None:
    """A layer's advance width against the shadow's: (width - ref_width) / ref_width in %, one decimal, signed with a
    true minus ("−19.4%", "+5.6%", "0.0%"); None for a zero-width reference."""
    if not ref_width:
        return None
    diff = (width - ref_width) / ref_width * 100.0
    text = f"{abs(diff):.1f}%"
    return text if text == "0.0%" else f"{'+' if diff > 0 else '−'}{text}"


def wanted(name: str | None, font: object, reference: str, has_shapes: bool, focus: Focus) -> bool:
    """Whether a layer of glyph ``name`` in ``font`` gets the ghost: not the reference glyph itself, not an empty layer
    (an undrawn slot would read as the reference glyph), and inside AZ Argus' focus when it has one."""
    return name is not None and name != reference and has_shapes and focus.allows(font, name)


class Focus:
    """``shadow.focus`` v1 in the suite registry: AZ Argus' report narrows the ghost to its selected rows' glyphs."""

    VERSION = 1

    def __init__(self, redraw: Callable[[], None] | None = None) -> None:
        self.font: object = None
        self.names: frozenset[str] = frozenset()
        self._redraw = redraw

    def focus(self, font: object, names: Iterable[str] | None) -> None:
        """The ghost narrowed to ``names`` in ``font``; empty or None: every glyph again."""
        self.names = frozenset(str(name) for name in names) if names else frozenset()
        self.font = font if self.names else None
        if self._redraw is not None:
            self._redraw()

    def allows(self, font: object, name: str) -> bool:
        return not self.names or self.font != font or name in self.names
