"""AZ Shadow: a reference glyph (H by default) drawn faintly over layers in the Edit view (AZ Argus' "H ghost"
until 2026-10; in front of the outline since Hugo, 2026-10-15, not behind it). Settings in its palette (shadow_palette); AZ Argus' report narrows it to its selected rows
(shadow.focus). The logic without AppKit lives in shadow_core."""

from __future__ import annotations

import traceback
from typing import Any

import objc
import shadow_core as core
from AppKit import (
    NSAffineTransform,
    NSAttributedString,
    NSBezierPath,
    NSColor,
    NSEvenOddWindingRule,
    NSFont,
    NSFontAttributeName,
    NSFontWeightMedium,
    NSForegroundColorAttributeName,
    NSGraphicsContext,
    NSPoint,
)
from GlyphsApp import Glyphs
from GlyphsApp.plugins import ReporterPlugin

PLUGIN_ID = "com.hugojourdan.AZShadow"
SELECT_TOOL = "GlyphsToolSelect"  # the Select tool's class (its "Select All Layers" sibling starts the same)

FOCUS = core.Focus(redraw=lambda: Glyphs.redraw())
try:
    import _hj_suite

    _registry = getattr(_hj_suite, "REGISTRY", None)
    if _registry is not None and hasattr(_registry, "register"):
        _registry.register("shadow.focus", lambda: FOCUS, version=core.Focus.VERSION, plugin_id=PLUGIN_ID)
except Exception:  # noqa: BLE001 (no suite registry: AZ Shadow alone, no AZ Argus link)
    traceback.print_exc()


def _identity(obj: Any) -> int:
    """A layer's ObjC identity, the same for every PyObjC proxy of it (a test's fake: its Python id)."""
    try:
        return objc.pyobjc_id(obj)
    except TypeError:
        return id(obj)


class AZShadow(ReporterPlugin):
    """Glyphs calls ``foreground`` for the edited layer and ``inactiveLayerForeground`` for the tab's other layers
    (drawn when the scope is All)."""

    @objc.python_method
    def settings(self) -> None:
        self.menuName = "AZ Shadow"
        self.shadowPrefs = core.prefs()  # (shared: the palette changes it, the next frame draws it)
        self._outlineCache = {}  # (reference layer identity, its lastOperation) -> NSBezierPath or None
        self._colorCache = None  # ((rgb, opacity), {strong: (fill, stroke)})

    @objc.python_method
    def foreground(self, layer: Any) -> None:
        self._draw(layer, strong=not self._selectToolActive(layer))

    @objc.python_method
    def inactiveLayerForeground(self, layer: Any) -> None:
        if self.shadowPrefs.scope == "all":
            self._draw(layer, strong=True)

    @objc.python_method
    def _draw(self, layer: Any, strong: bool) -> None:
        try:
            ghost = self._ghostFor(layer)
            if ghost is None:
                return
            path, dx, ref_width = ghost
            fill, stroke = self._colors(strong)
            NSGraphicsContext.saveGraphicsState()
            try:
                if dx:
                    move = NSAffineTransform.transform()
                    move.translateXBy_yBy_(dx, 0.0)
                    move.concat()
                fill.set()
                path.fill()
                path.setLineWidth_(1.0 / self._viewScale())  # (one screen pixel at any zoom, as Glyphs' outlines)
                stroke.set()
                path.stroke()
            finally:
                NSGraphicsContext.restoreGraphicsState()
            if self.shadowPrefs.width_diff:
                self._drawWidthDiff(layer, ref_width)
        except Exception:  # noqa: BLE001 (a draw callback must never raise)
            traceback.print_exc()  # (a frame never raises)

    @objc.python_method
    def _drawWidthDiff(self, layer: Any, ref_width: float) -> None:
        """The layer's advance width against the shadow's, in % (shadow_core.width_diff), centred on the advance width,
        its top WIDTH_LABEL_GAP units under the layer's bounds: monospaced Medium, WIDTH_LABEL_SIZE pt on screen, in the
        shadow's colour and opacity (drawn here, not with drawTextAtPoint: that one takes only the label font)."""
        width = float(layer.width or 0)
        text = core.width_diff(width, ref_width)
        if text is None:
            return
        r, g, b = self.shadowPrefs.color
        label = NSAttributedString.alloc().initWithString_attributes_(text, {
            NSFontAttributeName: NSFont.monospacedSystemFontOfSize_weight_(core.WIDTH_LABEL_SIZE / self._viewScale(),
                                                                           NSFontWeightMedium),
            NSForegroundColorAttributeName: NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b,
                                                                                             self.shadowPrefs.opacity),
        })
        size = label.size()
        label.drawAtPoint_(NSPoint(width / 2.0 - size.width / 2.0,
                                   layer.bounds.origin.y - core.WIDTH_LABEL_GAP - size.height))

    @objc.python_method
    def _selectToolActive(self, layer: Any) -> bool:
        """True while ``layer``'s window has the Select tool (the edited layer then gets the light shadow). Read from
        the layer's own window, as GSFont.tool does, but never through Glyphs.font (a round-trip per frame)."""
        try:
            tool = layer.parent.parent.parent.windowController().toolEventDelegate()
            if tool.respondsToSelector_("currentTool"):  # (a GSToolGroup: its picked tool)
                tool = tool.currentTool()
            return str(tool.className()).startswith(SELECT_TOOL)
        except Exception:  # noqa: BLE001 (no window or tool: the light shadow, as before)
            return True

    @objc.python_method
    def _ghostFor(self, layer: Any) -> tuple[Any, float, float] | None:
        """The reference glyph's outline for ``layer``, how far right to move it and its advance width, or None when
        ``layer`` gets no ghost (shadow_core.wanted; a reference glyph or layer the font lacks; a reference with no outline)."""
        glyph = layer.parent
        if glyph is None or glyph.parent is None:
            return None
        font = glyph.parent
        prefs = self.shadowPrefs
        has_shapes = len(layer.paths) > 0 or len(layer.components) > 0
        if not core.wanted(glyph.name, font, prefs.glyph, has_shapes, FOCUS):
            return None
        ref_glyph = font.glyphs[prefs.glyph]
        ref_layer = ref_glyph.layers[layer.associatedMasterId] if ref_glyph is not None else None
        if ref_layer is None:
            return None
        path = self._outline(ref_layer)
        if path is None:
            return None
        target, ref = layer.bounds, ref_layer.bounds
        ref_advance = float(ref_layer.width or 0)
        dx = core.offset_x(prefs.alignment,
                           (target.origin.x, target.size.width, float(layer.width or 0)),
                           (ref.origin.x, ref.size.width, ref_advance))
        return path, dx, ref_advance

    @objc.python_method
    def _outline(self, ref_layer: Any) -> Any:
        """The reference layer's outline: components decomposed, overlaps removed, even-odd; None when empty.
        Cached per layer object and its lastOperation (its latest edit, its components' included; glyph.lastChange
        does not move on a node drag)."""
        key = (_identity(ref_layer), ref_layer.lastOperation())
        if key in self._outlineCache:
            return self._outlineCache[key]
        path = None
        decomposed = ref_layer.copyDecomposedLayer()
        if decomposed is not None:
            try:
                decomposed.removeOverlap()
            except Exception:  # noqa: BLE001, S110 (an outline Glyphs can't merge: drawn as it is)
                pass
            path = NSBezierPath.bezierPath()
            for gs_path in decomposed.paths:
                bezier = gs_path.bezierPath
                if bezier is not None:
                    path.appendBezierPath_(bezier)
            if path.elementCount() == 0:
                path = None
            else:
                path.setWindingRule_(NSEvenOddWindingRule)
        if len(self._outlineCache) > 64:  # ponytail: crude cap; the reference glyph rarely changes
            self._outlineCache.clear()
        self._outlineCache[key] = path
        return path

    @objc.python_method
    def _colors(self, strong: bool) -> tuple[Any, Any]:
        """The fill and stroke colours for the current colour and opacity: light (the edited layer under the Select
        tool) or strong (any other tool, and the tab's other layers: it reads over ink). Rebuilt when the colour or
        opacity changes."""
        prefs = self.shadowPrefs
        key = (prefs.color, prefs.opacity)
        if self._colorCache is None or self._colorCache[0] != key:
            r, g, b = prefs.color
            base = NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, 1.0)
            pairs = {
                is_strong: (base.colorWithAlphaComponent_(fill * prefs.opacity),
                            base.colorWithAlphaComponent_(stroke * prefs.opacity))
                for is_strong, fill, stroke in ((False, core.FILL_ALPHA, core.STROKE_ALPHA),
                                                (True, core.STRONG_FILL_ALPHA, core.STRONG_STROKE_ALPHA))
            }
            self._colorCache = (key, pairs)
        return self._colorCache[1][strong]

    @objc.python_method
    def _viewScale(self) -> float:
        """Edit-view scale, never zero (not ``_scale``: GSReporter's ivar of that name shadows a method)."""
        try:
            scale = float(self.getScale())
        except Exception:  # noqa: BLE001 (no view scale yet: one unit per pixel)
            return 1.0
        return scale if scale > 0.0 else 1.0

