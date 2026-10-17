"""AZ Shadow palette: the settings in the right palette column, two rows (Hugo, 2026-10-15, layout C):

- the reference glyph's name, its colour (the colour's alpha is the opacity: no slider, Hugo 2026-10-15);
- its alignment (left edges, advance-width centres, right edges) and where it shows (the current layer, or every
  layer in the tab), as icons with tooltips.

Glyphs makes one palette per document window; all of them and the reporter share one Prefs (shadow_core.prefs). As
AZ Context's, the section hides while View > Show AZ Shadow is off (Glyphs 4): the View menu turns it on and off.
Loaded by plugin.py; Glyphs finds AZShadowPalette through Info.plist's Principal Classes.
"""

from __future__ import annotations

import traceback
from typing import Any

import objc
import shadow_core as core
from AppKit import (
    NSColor,
    NSColorPanel,
    NSColorSpace,
    NSColorWell,
    NSControlSizeSmall,
    NSFont,
    NSFontWeightRegular,
    NSImage,
    NSMakeRect,
    NSSegmentDistributionFillEqually,
    NSSegmentedControl,
    NSTextAlignmentLeft,
    NSTextField,
    NSView,
    NSViewFrameDidChangeNotification,
    NSViewMinXMargin,
    NSViewNotSizable,
    NSViewWidthSizable,
)
from Foundation import (
    NSNotificationCenter,
    NSObject,
    NSUserDefaultsDidChangeNotification,
)
from GlyphsApp import UPDATEINTERFACE, Glyphs
from GlyphsApp.plugins import PalettePlugin

# (setting, SF Symbol, text where the symbol is missing, tooltip)
ALIGNMENTS = (
    ("LEFT", "text.alignleft", "L", "Left edges flush"),
    ("CENTER", "text.aligncenter", "C", "Advance widths centred"),
    ("RIGHT", "text.alignright", "R", "Right edges flush"),
)
SCOPES = (
    ("current", "square", "One", "The current layer only"),
    ("all", "rectangle.split.3x1", "All", "Every layer in the tab"),
)
PAD_X = 10.0
PAD_Y = 6.0  # below the second row (AZ Context's)
PAD_TOP = 0.0  # above the first row (AZ Context's)
ROW_GAP = 3.0
ROW_H = 22.0
GAP = 6.0  # between a row's controls
FIELD_SHARE = 0.8  # of the first row: the glyph field; the colour well takes the rest (Hugo, 2026-10-15)
FIELD_H = 19.0
WELL_H = 20.0
SEG_H = 20.0
SCOPE_W = 52.0
WIDTH = 220.0  # (a start: the view follows the column's width)
HEIGHT = PAD_Y + ROW_H + ROW_GAP + ROW_H + PAD_TOP
REPORTER_CLASS = "AZShadow"
SIDEBAR_CLASS = "GSSidebarStackView"  # Glyphs 4's palette column (an NSStackView)
COMPLETE_DELAY = 0.18  # s after the last keystroke before the glyph-name list opens (AZ-DynamicAnchors' debounce)
COMPLETE_MAX = 100  # ponytail: the first 100 matches in font order; raise it if a prefix ever needs more


def _reporter_on() -> bool:
    """True while View > Show AZ Shadow is on (the live set Glyphs draws)."""
    try:
        return any(type(reporter).__name__ == REPORTER_CLASS for reporter in Glyphs.activeReporters)
    except Exception:  # noqa: BLE001 (unreadable: keep the palette)
        return True


class AZShadowPalette(PalettePlugin):
    @objc.python_method
    def settings(self) -> None:
        self.name = "AZ Shadow"
        self._last_state = None
        view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, HEIGHT))
        view.setAutoresizingMask_(NSViewWidthSizable)
        self._view = view
        top = PAD_Y + ROW_H + ROW_GAP
        self.glyphField = self._place(self._glyph_field(), PAD_X, top, 0.0, FIELD_H, NSViewNotSizable)
        self.colorWell = self._place(self._color_well(), PAD_X, top, 0.0, WELL_H, NSViewNotSizable)
        self._layout_first_row()
        scope_x = WIDTH - PAD_X - SCOPE_W
        self.alignmentControl = self._place(self._segments(ALIGNMENTS, "azShadowAlignment:"), PAD_X, PAD_Y,
                                            scope_x - GAP - PAD_X, SEG_H, NSViewWidthSizable)
        self.scopeControl = self._place(self._segments(SCOPES, "azShadowScope:"), scope_x, PAD_Y, SCOPE_W, SEG_H,
                                        NSViewMinXMargin)
        self.dialog = view
        self.min = HEIGHT
        self.max = HEIGHT
        # Registered here, not in start(): a secondary class in a multi-class bundle does not reliably get start()
        # (AZ-DynamicAnchors' palette).
        Glyphs.addCallback(self.update, UPDATEINTERFACE)
        # Toggling the reporter in the View menu rewrites GSVisibleReporters, so a defaults change is the cue to
        # re-check the palette's visibility.
        NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self, "azShadowDefaultsChanged:", NSUserDefaultsDidChangeNotification, None
        )
        view.setPostsFrameChangedNotifications_(True)
        NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self, "azShadowLayout:", NSViewFrameDidChangeNotification, view
        )

    @objc.python_method
    def start(self) -> None:
        return

    @objc.python_method
    def __del__(self) -> None:
        try:
            Glyphs.removeCallback(self.update)
            NSNotificationCenter.defaultCenter().removeObserver_(self)
        except Exception:  # noqa: BLE001, S110 (Glyphs tearing down: nothing left to unhook)
            pass

    @objc.python_method
    def _place(self, control: Any, x: float, row_y: float, width: float, height: float, mask: int) -> Any:
        """``control`` at ``x``, centred in the row at ``row_y``, added to the view."""
        control.setFrame_(NSMakeRect(x, row_y + (ROW_H - height) / 2, width, height))
        control.setAutoresizingMask_(mask)
        self._view.addSubview_(control)
        return control

    @objc.python_method
    def _layout_first_row(self) -> None:
        """The glyph field FIELD_SHARE of the first row, the colour well the rest, at the column's width (set here on
        every resize: autoresizing springs would drift off the split, and the gap between them with it)."""
        width = max(self._view.frame().size.width - 2 * PAD_X - GAP, 0.0)
        field_w = round(width * FIELD_SHARE)
        for control, x, control_w in ((self.glyphField, PAD_X, field_w),
                                      (self.colorWell, PAD_X + field_w + GAP, width - field_w)):
            frame = control.frame()
            control.setFrame_(NSMakeRect(x, frame.origin.y, control_w, frame.size.height))

    @objc.python_method
    def _glyph_field(self) -> Any:
        field = NSTextField.alloc().init()
        field.setControlSize_(NSControlSizeSmall)
        field.setFont_(NSFont.monospacedSystemFontOfSize_weight_(NSFont.smallSystemFontSize(), NSFontWeightRegular))
        field.setAlignment_(NSTextAlignmentLeft)
        field.setUsesSingleLineMode_(True)
        field.cell().setScrollable_(True)
        field.setToolTip_("The glyph drawn over: a name (H, n.alt) or a character")
        field.setDelegate_(self)
        return field

    @objc.python_method
    def _color_well(self) -> Any:
        well = NSColorWell.alloc().init()
        well.setToolTip_("Colour and opacity (the colour panel's opacity slider)")
        if well.respondsToSelector_("setSupportsAlpha:"):  # macOS 14+
            well.setSupportsAlpha_(True)
        else:
            NSColorPanel.sharedColorPanel().setShowsAlpha_(True)
        well.setTarget_(self)
        well.setAction_("azShadowColor:")
        return well

    @objc.python_method
    def _segments(self, items: tuple[tuple[str, str, str, str], ...], selector: str) -> Any:
        """One segment per item, one picked: its SF Symbol where there is one, else its text; its tooltip."""
        control = NSSegmentedControl.alloc().init()
        control.setSegmentCount_(len(items))
        control.setControlSize_(NSControlSizeSmall)
        control.setFont_(NSFont.systemFontOfSize_(NSFont.smallSystemFontSize()))
        control.cell().setTrackingMode_(0)  # select one
        for k, (_setting, symbol, text, tip) in enumerate(items):
            image = None
            if hasattr(NSImage, "imageWithSystemSymbolName_accessibilityDescription_"):
                image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(symbol, tip)
            if image is not None:
                control.setImage_forSegment_(image, k)
            else:
                control.setLabel_forSegment_(text, k)
            control.setToolTip_forSegment_(tip, k)
        control.setSegmentDistribution_(NSSegmentDistributionFillEqually)
        control.setTarget_(self)
        control.setAction_(selector)
        return control

    @objc.python_method
    def _font(self) -> Any:
        """This window's font (AZ Context's; never Glyphs.font, a WindowServer round-trip per call)."""
        try:
            controller = self.windowController()
            document = controller.document() if controller is not None else None
            return document.font if document is not None else None
        except Exception:  # noqa: BLE001 (no window yet: no font)
            return None

    @objc.python_method
    def _completions(self, typed: str, keep: int) -> list[str]:
        """The font's glyph names longer than ``typed`` and starting with it (any case; the typed case first), in font
        order; the first
        ``keep`` characters exactly as typed (the field editor replaces only what follows them). Only longer names: a
        picked name is then always partly selected, which is how azShadowComplete_ tells it from typing."""
        font = self._font() if typed else None
        if font is None:
            return []
        names = font.valueForKey_("glyphs").valueForKey_("name") or []  # (one bridge crossing for the whole font)
        lower = typed.lower()
        matches = (str(name) for name in names if name is not None)
        found = [name for name in matches
                 if len(name) > len(typed) and name.lower().startswith(lower) and name[:keep] == typed[:keep]]
        found.sort(key=lambda name: not name.startswith(typed))  # the typed case first (stable: font order inside)
        return found[:COMPLETE_MAX]

    @objc.python_method
    def update(self, sender: object = None) -> None:
        try:
            self._apply_visibility()
            self._sync()
        except Exception:  # noqa: BLE001 (a palette refresh must never raise into Glyphs)
            traceback.print_exc()

    @objc.python_method
    def _apply_visibility(self) -> None:
        """Show the palette only while the reporter is on (AZ Context's rule): hide its whole sidebar section, header
        included. Glyphs 4's column is a stack view that detaches hidden sections, so the rest moves up; Glyphs 3's
        sidebar is not, so there the palette always shows."""
        section = self._view
        while section is not None and section.superview() is not None:
            if type(section.superview()).__name__ == SIDEBAR_CLASS:
                hidden = not _reporter_on()
                if bool(section.isHidden()) != hidden:
                    section.setHidden_(hidden)
                return
            section = section.superview()

    @objc.python_method
    def _sync(self, force: bool = False) -> None:
        """Mirror the shared settings onto the controls. Runs on every UPDATEINTERFACE, so it bails when nothing it
        shows has changed (another window's palette changed them: shown on this one's next update)."""
        prefs = core.prefs()
        state = (prefs.glyph, prefs.opacity, prefs.color, prefs.alignment, prefs.scope)
        if state == self._last_state and not force:
            return
        self._last_state = state
        if self.glyphField.currentEditor() is None:  # never rewrite the field mid-typing
            self.glyphField.setStringValue_(prefs.glyph)
        r, g, b = prefs.color
        self.colorWell.setColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, prefs.opacity))
        self.alignmentControl.setSelectedSegment_([item[0] for item in ALIGNMENTS].index(prefs.alignment))
        self.scopeControl.setSelectedSegment_([item[0] for item in SCOPES].index(prefs.scope))

    @objc.python_method
    def _save(self, changes: dict[str, object]) -> None:
        """Changed settings: saved (refused values save nothing), drawn once, mirrored back."""
        saved = [core.save(core.prefs(), name, value) for name, value in changes.items()]
        if any(saved):
            Glyphs.redraw()
        self._sync(force=True)

    # ObjC action / delegate selectors (NO @objc.python_method)

    def controlTextDidChange_(self, notification: Any) -> None:
        """The glyph name, saved per keystroke (drawn once the font has that glyph); a pause in typing opens the list of
        the font's glyph names that start with it."""
        try:
            field = notification.object()
            self._save({"glyph": str(field.stringValue() or "")})
            editor = field.currentEditor()
            if editor is not None:
                NSObject.cancelPreviousPerformRequestsWithTarget_selector_object_(self, "azShadowComplete:", editor)
                self.performSelector_withObject_afterDelay_("azShadowComplete:", editor, COMPLETE_DELAY)
        except Exception:  # noqa: BLE001 (an action must never raise into AppKit)
            traceback.print_exc()

    def azShadowComplete_(self, editor: Any) -> None:
        """Open the glyph-name list: only while the field is still being edited, not while a name from the list is
        previewed (its untyped tail is selected; read here, not in controlTextDidChange_, which AppKit posts before it
        selects that tail), and only when there is a match (an empty list beeps)."""
        try:
            if (self.glyphField.currentEditor() == editor and editor.selectedRange().length == 0
                    and self._completions(str(editor.string()), 0)):
                editor.complete_(None)
        except Exception:  # noqa: BLE001 (an action must never raise into AppKit)
            traceback.print_exc()

    def control_textView_completions_forPartialWordRange_indexOfSelectedItem_(
        self, control: Any, text_view: Any, words: Any, char_range: Any, index: int
    ) -> tuple[list[str], int]:
        """The field editor's completions: whole glyph names, matched on everything typed (its own word range stops
        at "." and "_"). Returns (completions, -1): PyObjC's inout index, -1 = no row preselected, so nothing is typed
        into the field until a name is picked."""
        try:
            typed = str(text_view.string())[: char_range.location + char_range.length]
            names = self._completions(typed, char_range.location)
            return [name[char_range.location:] for name in names], -1
        except Exception:  # noqa: BLE001 (an action must never raise into AppKit)
            traceback.print_exc()
            return [], -1

    def azShadowColor_(self, sender: Any) -> None:
        """The colour's RGB is the colour, its alpha the opacity."""
        try:
            color = sender.color()
            rgb = color.colorUsingColorSpace_(NSColorSpace.deviceRGBColorSpace()) if color is not None else None
            if rgb is not None:
                self._save({
                    "color": (float(rgb.redComponent()), float(rgb.greenComponent()), float(rgb.blueComponent())),
                    "opacity": float(rgb.alphaComponent()),
                })
        except Exception:  # noqa: BLE001 (an action must never raise into AppKit)
            traceback.print_exc()

    def azShadowAlignment_(self, sender: Any) -> None:
        try:
            k = int(sender.selectedSegment())
            if 0 <= k < len(ALIGNMENTS):
                self._save({"alignment": ALIGNMENTS[k][0]})
        except Exception:  # noqa: BLE001 (an action must never raise into AppKit)
            traceback.print_exc()

    def azShadowScope_(self, sender: Any) -> None:
        try:
            k = int(sender.selectedSegment())
            if 0 <= k < len(SCOPES):
                self._save({"scope": SCOPES[k][0]})
        except Exception:  # noqa: BLE001 (an action must never raise into AppKit)
            traceback.print_exc()

    def azShadowDefaultsChanged_(self, notification: Any) -> None:
        """Any defaults write; re-check on the next main-loop turn, once the View-menu toggle has updated the active
        reporters (and off any background thread that wrote a default). Also how the width difference, which has no
        control, follows Glyphs.defaults set from the Macro panel."""
        self.performSelectorOnMainThread_withObject_waitUntilDone_("azShadowCheckReporter:", None, False)

    def azShadowLayout_(self, _notification: Any) -> None:
        """The palette's view was resized (the column's width changed)."""
        try:
            self._layout_first_row()
        except Exception:  # noqa: BLE001 (a palette refresh must never raise into Glyphs)
            traceback.print_exc()

    def azShadowCheckReporter_(self, _sender: Any) -> None:
        try:
            self._apply_visibility()
            if core.reload(core.prefs(), "width_diff"):
                Glyphs.redraw()
        except Exception:  # noqa: BLE001 (a palette refresh must never raise into Glyphs)
            traceback.print_exc()

    @objc.python_method
    def __file__(self) -> str:
        """Please leave this method unchanged (SDK convention)."""
        return __file__
