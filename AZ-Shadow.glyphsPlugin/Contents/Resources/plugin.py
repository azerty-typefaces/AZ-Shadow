"""AZ-Shadow.glyphsPlugin: imports the reporter and the palette so Glyphs' loader finds the classes listed in
Info.plist's Principal Classes."""

from __future__ import annotations

import os
import sys
import traceback

import objc
from GlyphsApp.plugins import GeneralPlugin

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shadow_reporter  # noqa: F401  defines AZShadow

try:
    import shadow_palette  # noqa: F401  defines AZShadowPalette
except Exception:  # noqa: BLE001
    traceback.print_exc()

    # A listed principal class that fails to load drops the WHOLE bundle, reporter included: stand in a do-nothing
    # class under the same name (AZ Context's way).
    class AZShadowPalette(GeneralPlugin):
        @objc.python_method
        def settings(self) -> None:
            return  # no name: no menu item; no view: never shown
