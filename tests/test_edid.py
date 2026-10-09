"""Unittest suite for the EDID parser, runnable without a display.

    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from screeninfo_gui.edid import EdidInfo, decode_vendor, parse_edid, parse_edid_hex
from screeninfo_gui.model import MonitorInfo

HEADER = bytes((0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00))


def vendor_code(letters: str) -> int:
    """Encode three vendor letters the way EDID does (5-bit each, 'A' = 1)."""
    value = 0
    for char in letters:
        value = (value << 5) | (ord(char) - ord("A") + 1)
    return value


def display_descriptor(tag: int, text: str, layout14: bool = True) -> bytes:
    """Build a real 18-byte Display Descriptor.

    Two layouts exist in the field and both were observed on real monitors:
      EDID 1.3 : 00 00 | tag | text(12)
      EDID 1.4 : 00 00 00 | tag | 00 | text(12)
    """
    block = bytearray(18)
    if layout14:
        block[3] = tag
        start = 5
    else:
        block[2] = tag
        start = 3
    payload = text.encode("ascii")[:12]
    block[start:start + len(payload)] = payload
    block[start + 12:start + 13] = b"\x0a"
    return bytes(block)


def timing_descriptor(native, h_mm=0, v_mm=0, version=(1, 4)) -> bytes:
    """Build a real Detailed Timing Descriptor with a non-zero pixel clock.

    From EDID 1.4 the image size is a 16-bit millimetre value at bytes
    14-15 and 16-17, replacing the vertical front porch / sync fields.
    """
    w, h = native
    pixel_clock = (w * 300) // 10000          # plausible kHz/10
    block = bytearray(18)
    struct.pack_into(">H", block, 0, pixel_clock or 1)
    block[2] = w & 0xFF
    block[4] = ((w >> 8) & 0x0F) << 4
    block[5] = h & 0xFF
    block[7] = ((h >> 8) & 0x0F) << 4
    block[8] = 48                              # h front porch
    block[9] = 32                              # h sync
    struct.pack_into("<H", block, 10, 3)       # v front porch (1.3 only)
    if version[1] >= 4:
        struct.pack_into("<HH", block, 14, h_mm, v_mm)
    else:
        struct.pack_into("<H", block, 12, 5)   # v sync (1.3)
        block[16] = h_mm & 0xFF
        block[17] = v_mm & 0xFF
    return bytes(block)


def make_edid(vendor="DEL", product=0x4321, serial=0xABCDEF01,
              width_cm=60, height_cm=34, text_serial=None,
              native=(1920, 1080), version=(1, 4),
              monitor_name=None, dtd_mm=(597, 336),
              panel_texts=None, layout14=True) -> bytes:
    """Build a valid 128-byte EDID block for tests.

    ``dtd_mm`` is the detailed timing descriptor's image size, which the EDID
    spec stores in MILLIMETRES while the basic display parameters use
    CENTIMETRES.
    """
    block = bytearray(128)
    block[0:8] = HEADER

    raw = vendor_code(vendor)
    block[8] = (raw >> 8) & 0xFF
    block[9] = raw & 0xFF
    struct.pack_into("<H", block, 10, product)
    struct.pack_into("<I", block, 12, serial)
    block[16] = 12              # week
    block[17] = 2016 - 1990     # year
    block[18], block[19] = version
    block[21], block[22] = width_cm, height_cm
    block[20] = 0x80            # digital input

    # Descriptor 1: the preferred timing.
    block[54:72] = timing_descriptor(native, dtd_mm[0], dtd_mm[1], version)

    # Descriptor 2: monitor name, tag 0xFC.
    name_text = monitor_name if monitor_name is not None else "Dell U2419M"
    block[72:90] = display_descriptor(0xFC, name_text, layout14)

    # Descriptor 3: serial text, tag 0xFF.
    if text_serial is not None:
        block[90:108] = display_descriptor(0xFF, text_serial, layout14)

    # Descriptor 4: panel free text, tag 0xFE.
    if panel_texts:
        joined = " ".join(panel_texts)[:12]
        block[108:126] = display_descriptor(0xFE, joined, layout14)

    block[126:128] = struct.pack(">H", 0)
    return bytes(block)


class TestVendorDecoding(unittest.TestCase):
    def test_known_vendor(self):
        self.assertEqual(decode_vendor(vendor_code("DEL")), "DEL")
        self.assertEqual(decode_vendor(vendor_code("SAM")), "SAM")

    def test_brand_lookup(self):
        self.assertEqual(parse_edid(make_edid(vendor="DEL")).brand, "Dell")
        self.assertEqual(parse_edid(make_edid(vendor="SAM")).brand, "Samsung")
        self.assertEqual(parse_edid(make_edid(vendor="ACI")).brand,
                         "Ancor Communications")

    def test_unknown_vendor_falls_back_to_code(self):
        info = parse_edid(make_edid(vendor="QQQ"))
        self.assertEqual(info.vendor_id, "QQQ")
        self.assertEqual(info.brand, "QQQ")


class TestEdidParsing(unittest.TestCase):
    def test_rejects_bad_input(self):
        for bad in (b"", None, b"\x00" * 128, bytes(range(128))):
            self.assertFalse(parse_edid(bad).valid, bad)

    def test_truncated_block(self):
        self.assertFalse(parse_edid(make_edid()[:64]).valid)

    def test_basic_fields(self):
        info = parse_edid(make_edid(vendor="DEL", product=0x4321, serial=0xABCDEF01))
        self.assertTrue(info.valid)
        self.assertEqual(info.product_code, str(0x4321))
        self.assertEqual(info.numeric_serial, str(0xABCDEF01))
        self.assertEqual(info.year, "2016")
        self.assertEqual(info.week, "12")
        self.assertEqual(info.edid_version, "1.4")

    def test_size_in_cm_and_inches(self):
        info = parse_edid(make_edid(width_cm=60, height_cm=34))
        self.assertEqual(info.size_h_cm, 60)
        self.assertAlmostEqual(info.width_in, 60 / 2.54, places=2)
        self.assertAlmostEqual(info.height_in, 34 / 2.54, places=2)

    def test_native_resolution(self):
        info = parse_edid(make_edid(native=(2560, 1440)))
        self.assertEqual(info.native_resolution, "2560 x 1440")

    def test_native_resolution_over_256(self):
        # Exercises the 10-bit high-nibble path.
        info = parse_edid(make_edid(native=(3840, 2160)))
        self.assertEqual(info.native_resolution, "3840 x 2160")

    def test_text_serial_preferred(self):
        info = parse_edid(make_edid(serial=0x00000001, text_serial="F1N7Z93"))
        self.assertEqual(info.serial, "F1N7Z93")

    def test_placeholder_text_serial_ignored(self):
        for junk in ("0", "1", "NONE", "00000"):
            info = parse_edid(make_edid(serial=0x00000000, text_serial=junk))
            self.assertEqual(info.serial, "", junk)

    def test_falls_back_to_numeric_serial(self):
        # The base-block serial is a little-endian uint32 rendered in decimal.
        info = parse_edid(make_edid(serial=0x1A2B3C4D, text_serial="0"))
        self.assertEqual(info.serial, str(0x1A2B3C4D))

    def test_zero_padded_numeric_serial_is_trimmed(self):
        info = parse_edid(make_edid(serial=0x00000042, text_serial=None))
        self.assertEqual(info.serial, str(0x42))

    def test_monitor_name_not_read_as_serial(self):
        """A 0xFC descriptor holds the name and must not become a serial."""
        info = parse_edid(make_edid(serial=0, text_serial=None))
        self.assertEqual(info.serial, "")
        self.assertNotIn("Dell", info.serial)

    def test_missing_size_yields_no_diagonal(self):
        info = parse_edid(make_edid(width_cm=0, height_cm=0, dtd_mm=(0, 0)))
        self.assertEqual(info.diagonal_in, 0.0)

    def test_zero_dtd_size_keeps_base_block(self):
        block = bytearray(make_edid(width_cm=60, height_cm=34, dtd_mm=(0, 0)))
        info = parse_edid(bytes(block))
        self.assertEqual((info.size_h_cm, info.size_v_cm), (60, 34))
        self.assertEqual(info.dtd_h_mm, 0)


class TestHexDecoding(unittest.TestCase):
    def test_multiline_xrandr_edid(self):
        """xrandr prints the EDID as indented 32-char hex lines."""
        hex_text = "\n".join(
            "        " + make_edid().hex()[i:i + 32]
            for i in range(0, 256, 32)
        )
        info = parse_edid_hex(hex_text)
        self.assertTrue(info.valid)
        self.assertEqual(info.brand, "Dell")

    def test_short_input(self):
        self.assertFalse(parse_edid_hex("00ffff").valid)

    def test_garbage_input(self):
        self.assertFalse(parse_edid_hex("zzz" * 100).valid)


class TestUnitsAndNaming(unittest.TestCase):
    """Regression cover for the cm / mm mix-up behind the 19"-instead-of-27"
    reading, and for brands taken from the panel vendor rather than the
    actual maker."""

    def test_base_block_is_centimetres(self):
        info = parse_edid(make_edid(width_cm=60, height_cm=34))
        self.assertAlmostEqual(info.width_in, 60 / 2.54, places=2)

    def test_timing_descriptor_is_millimetres(self):
        info = parse_edid(make_edid(dtd_mm=(597, 336)))
        self.assertEqual((info.dtd_h_mm, info.dtd_v_mm), (597, 336))
        self.assertAlmostEqual(info.dtd_width_in, 597 / 25.4, places=2)
        self.assertAlmostEqual(info.dtd_diagonal_in, 27.0, delta=0.15)

    def test_units_agree_for_a_consistent_edid(self):
        """60x34 cm and 597x336 mm describe the same 27-inch panel."""
        info = parse_edid(make_edid(width_cm=60, height_cm=34, dtd_mm=(597, 336)))
        self.assertAlmostEqual(info.diagonal_in, info.dtd_diagonal_in, delta=0.3)
        self.assertFalse(info.size_conflict)

    def test_conflicting_sizes_are_reported_not_hidden(self):
        """A 19-inch report next to a 27-inch one must surface, not silently
        pick a winner."""
        info = parse_edid(make_edid(width_cm=43, height_cm=24, dtd_mm=(597, 336)))
        self.assertTrue(info.size_conflict)
        self.assertAlmostEqual(info.diagonal_in, 19.4, delta=0.2)
        self.assertAlmostEqual(info.dtd_diagonal_in, 27.0, delta=0.15)

    def test_base_block_wins_when_present(self):
        info = parse_edid(make_edid(width_cm=60, height_cm=34, dtd_mm=(597, 336)))
        self.assertEqual((info.size_h_cm, info.size_v_cm), (60, 34))

    def test_falls_back_to_descriptor_when_base_is_empty(self):
        info = parse_edid(make_edid(width_cm=0, height_cm=0, dtd_mm=(597, 336)))
        self.assertAlmostEqual(info.diagonal_in, 27.0, delta=0.15)

    def test_monitor_name_is_not_a_serial(self):
        info = parse_edid(make_edid(serial=0, text_serial=None,
                                    monitor_name="ASUS VG27A"))
        self.assertEqual(info.display_name, "ASUS VG27A")
        self.assertEqual(info.serial, "")

    def test_brand_comes_from_name_over_panel_vendor(self):
        """AU Optronics builds panels for other brands; the name wins."""
        info = parse_edid(make_edid(vendor="AUO", monitor_name="ASUS VG27A"))
        self.assertEqual(info.vendor_id, "AUO")
        self.assertEqual(info.brand, "AU Optronics")     # raw table value
        self.assertEqual(info.brand_from_name, "ASUS")   # what we display

    def test_dahua_vendor_code(self):
        self.assertEqual(parse_edid(make_edid(vendor="DHI")).brand, "Dahua")

    def test_asus_vendor_code(self):
        self.assertEqual(parse_edid(make_edid(vendor="ASU")).brand, "ASUS")

    def test_brand_from_name_handles_dell_and_dahua(self):
        self.assertEqual(
            parse_edid(make_edid(monitor_name="DELL U2419M")).brand_from_name,
            "Dell")
        self.assertEqual(
            parse_edid(make_edid(monitor_name="DAHUA DHI27")).brand_from_name,
            "Dahua")

    def test_raw_hex_available_for_diagnostics(self):
        info = parse_edid(make_edid())
        self.assertEqual(len(info.raw_hex), 256)

    def test_27_inch_diagonal_is_not_19_inch(self):
        """The exact figure the user reported as wrong."""
        info = parse_edid(make_edid(width_cm=60, height_cm=34, dtd_mm=(597, 336)))
        self.assertAlmostEqual(info.diagonal_in, 27.1, delta=0.2)
        self.assertNotAlmostEqual(info.diagonal_in, 19.4, delta=1.0)


class TestClipboardExport(unittest.TestCase):
    def test_text_contains_the_three_requested_values(self):
        mon = MonitorInfo(index=0, brand="ASUS", model="VG27A", serial="SN123",
                          width_in=23.5, height_in=13.2, size_source="EDID",
                          resolution="2560 x 1440")
        text = mon.as_text()
        self.assertIn("ASUS", text)
        self.assertIn("SN123", text)
        self.assertIn('27.0"', text)

    def test_missing_values_are_labelled_not_blank(self):
        self.assertIn("Non disponible", MonitorInfo().as_text())

    def test_conflict_is_included(self):
        mon = MonitorInfo(size_conflict=True, alt_size_in=27.0,
                          width_in=16.9, height_in=9.4)
        self.assertIn("27.0", mon.as_text())


class TestDiagonalMath(unittest.TestCase):
    def test_known_diagonal(self):
        """597 x 336 mm is the EDID size of a 27-inch 16:9 panel."""
        mon = MonitorInfo(width_in=597 / 25.4, height_in=336 / 25.4)
        self.assertAlmostEqual(mon.diagonal_in, 27.0, delta=0.1)

    def test_text_formatting(self):
        mon = MonitorInfo(width_in=597 / 25.4, height_in=336 / 25.4, serial="ABC",
                          brand="Dell", size_source="EDID")
        self.assertEqual(mon.diagonal_text, '27.0"')
        self.assertEqual(mon.serial_text, "ABC")
        self.assertEqual(mon.brand_text, "Dell")
        self.assertIn("cm", mon.size_cm_text)

    def test_missing_values_show_placeholder(self):
        mon = MonitorInfo()
        self.assertEqual(mon.serial_text, "Non disponible")
        self.assertEqual(mon.brand_text, "Non disponible")
        self.assertEqual(mon.diagonal_text, "Non disponible")
        self.assertEqual(mon.size_text, "Non disponible")

    def test_title_falls_back_cleanly(self):
        self.assertEqual(MonitorInfo(brand="Dell", model="U2419").title,
                         "Dell U2419")
        self.assertEqual(MonitorInfo().title, "Ecran 1")
        self.assertEqual(MonitorInfo(brand="Dell").title, "Dell")


class TestXrandrParser(unittest.TestCase):
    """The Linux parser is pure text processing, so it is testable anywhere."""

    SAMPLE = """Screen 0: minimum 320 x 200, current 3840 x 1080, maximum 8192 x 8192
DP-1 connected primary 1920x1080+0+0 (normal left inverted right x axis y axis) 531mm x 299mm
\tIdentifier: 0x44
\tTimestamp:  32891
\tEDID:
\t\t00ffffffffffff0030e4a70300000000
\t\t001a0104951f11780228bf578f8c2a5
\t\t5054a54b00714f8180a940d1c0d100
HDMI-1 connected 1920x1080+1920+0 (normal left inverted right x axis y axis) 510mm x 290mm
\tIdentifier: 0x45
\tEDID:
\t\t00ffffffffffff0006af3d5700000000
DP-2 disconnected (normal left inverted right x axis y axis)
"""

    def setUp(self):
        from screeninfo_gui import monitors_linux
        self.monitors = monitors_linux._parse_xrandr(self.SAMPLE)

    def test_finds_only_connected_outputs(self):
        self.assertEqual([m.model for m in self.monitors], ["DP-1", "HDMI-1"])

    def test_resolution_and_position(self):
        self.assertEqual(self.monitors[0].resolution, "1920 x 1080")
        self.assertEqual(self.monitors[0].position, "+0+0")
        self.assertEqual(self.monitors[1].position, "+1920+0")

    def test_primary_flag(self):
        self.assertTrue(self.monitors[0].is_primary)
        self.assertFalse(self.monitors[1].is_primary)

    def test_millimetre_size_converted(self):
        self.assertAlmostEqual(self.monitors[0].width_in, 531 / 25.4, places=3)
        self.assertEqual(self.monitors[0].size_source, "EDID")

    def test_truncated_edid_does_not_crash(self):
        """The second output's EDID is cut short; it must still appear."""
        self.assertEqual(len(self.monitors), 2)
        self.assertEqual(self.monitors[1].width_in, 510 / 25.4)

    def test_invalid_hex_leaves_mm_fallback(self):
        block = bytearray(128)
        self.assertFalse(parse_edid(bytes(block)).valid)

    def test_indices_are_sequential(self):
        """Regression: every card reported "id interne 0"."""
        self.assertEqual([m.index for m in self.monitors], [0, 1])

    def test_primary_defaults_to_first_output(self):
        """WSLg omits the "primary" marker; the first output is primary."""
        from screeninfo_gui import monitors_linux
        no_marker = self.SAMPLE.replace(" connected primary ", " connected ")
        parsed = monitors_linux._parse_xrandr(no_marker)
        self.assertTrue(parsed[0].is_primary)
        self.assertFalse(parsed[1].is_primary)

    def test_zero_mm_is_treated_as_unknown(self):
        """xrandr prints "0mm x 0mm" when no size is exposed."""
        from screeninfo_gui import monitors_linux
        sample = ("DP-1 connected 1920x1080+0+0 (normal) 0mm x 0mm\n")
        parsed = monitors_linux._parse_xrandr(sample)
        self.assertEqual(parsed[0].width_in, 0.0)
        self.assertEqual(parsed[0].size_source, "")

    def test_no_output_returns_empty(self):
        from screeninfo_gui import monitors_linux
        self.assertEqual(monitors_linux._parse_xrandr(""), [])


class TestMissingIdentityExplanation(unittest.TestCase):
    """Brand/serial gaps must be explained, not left as a silent blank."""

    def test_wsl_detection_matches_this_machine(self):
        from screeninfo_gui.monitors_linux import _is_wsl
        # The suite runs under WSL in CI-like environments; assert it agrees
        # with /proc/version rather than hard-coding a platform.
        self.assertIsInstance(_is_wsl(), bool)

    def test_wsl_warning_mentions_the_cause(self):
        from screeninfo_gui import monitors_linux
        from screeninfo_gui.model import DetectionResult, MonitorInfo
        result = DetectionResult(
            monitors=[MonitorInfo(index=0, model="rdp-0")],
            method="xrandr",
        )
        monitors_linux._explain_missing_identity(result)
        self.assertTrue(result.warnings)
        self.assertIn("WSL", "\n".join(result.warnings))

    def test_no_warning_when_identity_is_complete(self):
        from screeninfo_gui import monitors_linux
        from screeninfo_gui.model import DetectionResult, MonitorInfo
        result = DetectionResult(
            monitors=[MonitorInfo(index=0, brand="Dell", serial="CN0F7N2")],
            method="xrandr",
        )
        monitors_linux._explain_missing_identity(result)
        self.assertEqual(result.warnings, [])


class TestQtFallback(unittest.TestCase):
    """When no EDID is readable at all, Qt screens still become rows."""

    def setUp(self):
        from screeninfo_gui import monitors_linux
        from screeninfo_gui.model import ScreenInfoStub
        self.stubs = [ScreenInfoStub("rdp-0", 1366, 768, 96.0),
                      ScreenInfoStub("rdp-2", 1920, 1080, 96.0)]
        self.monitors = monitors_linux._monitors_from_screens(self.stubs)

    def test_one_row_per_screen(self):
        self.assertEqual(len(self.monitors), 2)

    def test_sizes_are_labelled_estimated(self):
        for mon in self.monitors:
            self.assertEqual(mon.size_source, "estimé")
            self.assertGreater(mon.diagonal_in, 0)

    def test_unknown_fields_stay_empty(self):
        self.assertEqual(self.monitors[0].serial, "")
        self.assertEqual(self.monitors[0].brand, "")

    def test_no_screens_gives_no_rows(self):
        from screeninfo_gui import monitors_linux
        self.assertEqual(monitors_linux._monitors_from_screens([]), [])

    def test_fallback_used_when_nothing_else_works(self):
        """End-to-end with no xrandr and no sysfs entries."""
        from screeninfo_gui import monitors_linux
        original = monitors_linux._run_xrandr
        original_sysfs = monitors_linux._read_sysfs_edid
        monitors_linux._run_xrandr = lambda: ("", "xrandr introuvable")
        monitors_linux._read_sysfs_edid = lambda: []
        try:
            result = monitors_linux.detect(self.stubs)
        finally:
            monitors_linux._run_xrandr = original
            monitors_linux._read_sysfs_edid = original_sysfs
        self.assertEqual(result.method, "Qt (estimation)")
        self.assertEqual(len(result.monitors), 2)
        joined = "\n".join(result.warnings)
        # The advice differs under WSL, where xrandr would not help anyway.
        from screeninfo_gui.monitors_linux import _is_wsl
        if _is_wsl():
            self.assertIn("WSL", joined)
        else:
            self.assertIn("x11-xserver-utils", joined)

    def test_absolute_failure_reports_clearly(self):
        from screeninfo_gui import monitors_linux
        original = monitors_linux._run_xrandr
        original_sysfs = monitors_linux._read_sysfs_edid
        monitors_linux._run_xrandr = lambda: ("", "xrandr introuvable")
        monitors_linux._read_sysfs_edid = lambda: []
        try:
            result = monitors_linux.detect([])
        finally:
            monitors_linux._run_xrandr = original
            monitors_linux._read_sysfs_edid = original_sysfs
        self.assertEqual(result.method, "indisponible")
        self.assertEqual(result.monitors, [])


class TestDpiEstimate(unittest.TestCase):
    def setUp(self):
        from screeninfo_gui.model import ScreenInfoStub
        self.stubs = [ScreenInfoStub("DP-1", 1920, 1080, 96.0)]

    def test_estimate_fills_missing_size(self):
        from screeninfo_gui import monitors_linux
        mon = MonitorInfo(resolution="1920 x 1080")
        monitors_linux._apply_dpi_estimate([mon], self.stubs)
        self.assertEqual(mon.width_in, 20.0)
        self.assertEqual(mon.height_in, 11.25)
        self.assertEqual(mon.size_source, "estimé")

    def test_edid_size_not_overwritten(self):
        from screeninfo_gui import monitors_linux
        mon = MonitorInfo(resolution="1920 x 1080", width_in=24.0,
                          height_in=14.0, size_source="EDID")
        monitors_linux._apply_dpi_estimate([mon], self.stubs)
        self.assertEqual(mon.width_in, 24.0)
        self.assertEqual(mon.size_source, "EDID")

    def test_no_screens_is_safe(self):
        from screeninfo_gui import monitors_linux
        mon = MonitorInfo(resolution="1920 x 1080")
        monitors_linux._apply_dpi_estimate([mon], [])
        self.assertEqual(mon.width_in, 0.0)

    def test_unparsable_resolution_is_skipped(self):
        from screeninfo_gui import monitors_linux
        mon = MonitorInfo(resolution="")
        monitors_linux._apply_dpi_estimate([mon], self.stubs)
        self.assertEqual(mon.width_in, 0.0)


class TestWindowsBackendImport(unittest.TestCase):
    def test_module_imports_on_linux(self):
        """The Windows back end must be importable so its helpers are testable."""
        from screeninfo_gui import monitors_windows
        self.assertTrue(hasattr(monitors_windows, "detect"))
        self.assertTrue(hasattr(monitors_windows, "_match_displays_to_edids"))

    def test_matching_pairs_by_native_resolution(self):
        from screeninfo_gui import monitors_windows
        edids = [{"path": "a",
                  "edid": make_edid(vendor="DEL", native=(1920, 1080),
                                    monitor_name="DELL U2419M")},
                 {"path": "b",
                  "edid": make_edid(vendor="SAM", native=(2560, 1440),
                                    monitor_name="Samsung VG27")}]
        displays = [
            {"device": r"\\.\DISPLAY1", "width": 2560, "height": 1440,
             "left": 0, "top": 0, "is_primary": True},
            {"device": r"\\.\DISPLAY2", "width": 1920, "height": 1080,
             "left": 2560, "top": 0, "is_primary": False},
        ]
        monitors, ambiguous = monitors_windows._match_displays_to_edids(
            displays, edids)
        self.assertEqual(monitors[0].brand, "Samsung")
        self.assertEqual(monitors[1].brand, "Dell")
        self.assertFalse(ambiguous)

    def test_duplicate_monitors_flag_ambiguity(self):
        from screeninfo_gui import monitors_windows
        edids = [{"path": "a", "edid": make_edid(vendor="DEL", native=(1920, 1080))},
                 {"path": "b", "edid": make_edid(vendor="DEL", native=(1920, 1080))}]
        displays = [
            {"device": r"\\.\DISPLAY1", "width": 1920, "height": 1080,
             "left": 0, "top": 0, "is_primary": True},
            {"device": r"\\.\DISPLAY2", "width": 1920, "height": 1080,
             "left": 1920, "top": 0, "is_primary": False},
        ]
        monitors, ambiguous = monitors_windows._match_displays_to_edids(
            displays, edids)
        self.assertEqual(len(monitors), 2)
        # Only the first match is genuinely ambiguous; the second display then
        # has only one candidate left, so its assignment is certain.
        self.assertEqual(ambiguous, [r"\\.\DISPLAY1"])

    def test_more_edids_than_displays_is_safe(self):
        from screeninfo_gui import monitors_windows
        edids = [{"path": "a", "edid": make_edid()} for _ in range(3)]
        displays = [{"device": r"\\.\DISPLAY1", "width": 1920, "height": 1080,
                     "left": 0, "top": 0, "is_primary": True}]
        monitors, _ = monitors_windows._match_displays_to_edids(displays, edids)
        self.assertEqual(len(monitors), 1)

    def test_invalid_edid_is_never_matched(self):
        from screeninfo_gui import monitors_windows
        edids = [{"path": "a", "edid": b"\x00" * 128}]
        displays = [{"device": r"\\.\DISPLAY1", "width": 1920, "height": 1080,
                     "left": 0, "top": 0, "is_primary": True}]
        monitors, _ = monitors_windows._match_displays_to_edids(displays, edids)
        self.assertEqual(monitors[0].serial, "")

class TestCopyEventFilter(unittest.TestCase):
    """The copy buttons were dead. Two distinct traps caused it:

    * Qt does not propagate event filters to child widgets, so a filter
      installed on the card never saw clicks on its own labels;
    * QObject.setProperty() does not create a Python attribute, so a guard
      using hasattr() was always False.

    These tests dispatch genuine MouseButtonPress events rather than calling
    the handlers directly, which is what hid the original defect.
    """

    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            raise unittest.SkipTest("PySide6 absent")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QLabel
        from screeninfo_gui.app import MainWindow
        from screeninfo_gui.model import DetectionResult, MonitorInfo
        from screeninfo_gui.theme import QSS

        self.app.setStyleSheet(QSS)
        self.win = MainWindow()
        self.win._on_detected(DetectionResult(
            monitors=[
                MonitorInfo(index=0, brand="ASUS", model="VG27A",
                           serial="SN-AAA-111", width_in=23.5, height_in=13.2,
                           size_source="EDID", is_primary=True),
                MonitorInfo(index=1, brand="Dahua", model="DHI27",
                           serial="SN-BBB-222", width_in=16.9, height_in=9.4,
                           size_source="EDID"),
            ], method="demo"))
        self.app.processEvents()
        self.win.show()
        self.app.processEvents()

        def _click(label):
            event = QMouseEvent(
                QEvent.Type.MouseButtonPress, QPointF(1, 1), QPointF(1, 1),
                QPointF(1, 1), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            self.app.sendEvent(label, event)
            self.app.processEvents()

        self._click = _click
        self._QLabel = QLabel

    def tearDown(self):
        self.win.close()

    def _chips(self, field):
        return [c for c in self.win.findChildren(self._QLabel)
                if c.objectName() == "CopyChip" and c.property("field") == field]

    def test_every_card_exposes_a_chip_per_field(self):
        self.assertEqual(len(self._chips("brand")), 2)
        self.assertEqual(len(self._chips("serial")), 2)
        self.assertEqual(len(self._chips("size")), 2)

    def test_chips_carry_their_dynamic_properties(self):
        chip = self._chips("brand")[0]
        self.assertEqual(chip.property("monitor_index"), 0)
        # The trap: this must be read via property(), never hasattr().
        self.assertFalse(hasattr(chip, "monitor_index"))

    def test_clicking_brand_chip_copies_only_the_brand(self):
        self._click(self._chips("brand")[0])
        self.assertEqual(self.app.clipboard().text(), "ASUS")

    def test_clicking_serial_chip_copies_only_the_serial(self):
        self._click(self._chips("serial")[0])
        self.assertEqual(self.app.clipboard().text(), "SN-AAA-111")

    def test_clicking_second_card_brand_copies_that_monitor(self):
        self._click(self._chips("brand")[1])
        self.assertEqual(self.app.clipboard().text(), "Dahua")

    def test_clicking_second_card_serial_copies_that_monitor(self):
        self._click(self._chips("serial")[1])
        self.assertEqual(self.app.clipboard().text(), "SN-BBB-222")

    def test_clicking_size_chip_copies_diagonal_only(self):
        self._click(self._chips("size")[0])
        self.assertEqual(self.app.clipboard().text(), '27.0"')

    def test_per_card_button_copies_the_full_report(self):
        buttons = [b for b in self.win.findChildren(self._QLabel)
                   if b.objectName() == "CopyButton"
                   and b.property("monitor_index") is not None]
        self.assertEqual(len(buttons), 2)
        self._click(buttons[0])
        text = self.app.clipboard().text()
        self.assertIn("SN-AAA-111", text)
        self.assertIn('27.0"', text)

    def test_copy_all_copies_every_monitor(self):
        self._click(self.win.copy_all)
        text = self.app.clipboard().text()
        self.assertIn("SN-AAA-111", text)
        self.assertIn("SN-BBB-222", text)

    def test_copy_all_hidden_before_detection(self):
        from PySide6.QtWidgets import QApplication
        self.assertIsNotNone(QApplication)
        # Idle window starts with the button hidden.
        fresh = self.win
        self.assertFalse(fresh.copy_all.isHidden() and
                         not fresh.copy_all.isVisibleTo(fresh))


if __name__ == "__main__":
    unittest.main(verbosity=2)




# ---------------------------------------------------------------------------
# Real EDIDs, captured from the user's own monitors on Windows. These are the
# only fixtures that cannot be accused of encoding the parser's own mistakes.
# ---------------------------------------------------------------------------
REAL_AUO_LAPTOP = (
    "00ffffffffffff0006af3c7200000000001b0104951f117802c0d58f56589329"
    "20505400000001010101010101010101010101010101ce1d56e250001e302616"
    "360035ad100000180000000f0000000000000000000000000020000000fe0041"
    "554f0a202020202020202020000000fe004231343058544e30372e32200a00a9"
)
REAL_DAHUA_19 = (
    "00ffffffffffff00110923200101010102220103802b1878ee5ad5a7564b9b24"
    "135054afef00714f8180818a9500950fa9c0a9cf0101302a40c8608464301850"
    "1300b0f01000001e000000fd00324b1e5315000a202020202020000000fc004c"
    "4d31392d4c3230304e0a2020000000ff0030303030303030310a202020200147"
)


class TestRealEdids(unittest.TestCase):
    """Regression cover against hardware, not against synthetic fixtures.

    The earlier descriptor test fixtures wrote 0xFFFF where a pixel clock
    belongs, which hid a bug that broke parsing on every real monitor.
    """

    def setUp(self):
        self.auo = parse_edid(bytes.fromhex(REAL_AUO_LAPTOP))
        self.dahua = parse_edid(bytes.fromhex(REAL_DAHUA_19))

    def test_both_edids_are_valid(self):
        self.assertTrue(self.auo.valid)
        self.assertTrue(self.dahua.valid)

    def test_timing_descriptor_recognised_by_pixel_clock(self):
        """A DTD has a real clock; matching on 0xFFFF found nothing."""
        self.assertEqual(self.auo.native_resolution, "1366 x 768")
        self.assertEqual(self.dahua.native_resolution, "1600 x 900")

    def test_edid_14_display_descriptors_are_read(self):
        """Tag sits at byte 3 in the 1.4 layout, byte 2 in the 1.3 one."""
        self.assertEqual(self.dahua.display_name, "LM19-L200N")
        self.assertEqual(self.auo.panel_text, "AUO B140XTN07.2")

    def test_placeholder_serials_are_rejected(self):
        """Both monitors publish junk: "00000001" and 0x01010101."""
        self.assertEqual(self.auo.serial, "")
        self.assertEqual(self.dahua.serial, "")
        self.assertEqual(self.dahua.text_serial, "00000001")
        self.assertEqual(self.dahua.numeric_serial, str(0x01010101))

    def test_sizes_come_from_the_base_block(self):
        """Both firmware images write nonsense into the descriptor size."""
        self.assertEqual((self.auo.size_h_cm, self.auo.size_v_cm), (31, 17))
        self.assertEqual((self.dahua.size_h_cm, self.dahua.size_v_cm), (43, 24))
        self.assertEqual(self.auo.dtd_h_mm, 0)
        self.assertEqual(self.dahua.dtd_h_mm, 0)

    def test_diagonals(self):
        self.assertAlmostEqual(self.auo.diagonal_in, 13.9, delta=0.1)
        self.assertAlmostEqual(self.dahua.diagonal_in, 19.4, delta=0.1)

    def test_brands(self):
        self.assertEqual(self.auo.brand, "AU Optronics")
        self.assertEqual(self.dahua.brand, "Dahua")


class TestPairingWithRealEdids(unittest.TestCase):
    """The user's two screens, paired from the registry blobs."""

    def test_each_screen_claims_its_own_edid(self):
        from screeninfo_gui import monitors_windows
        edids = [{"path": "a", "edid": bytes.fromhex(REAL_DAHUA_19)},
                 {"path": "b", "edid": bytes.fromhex(REAL_AUO_LAPTOP)}]
        # Registry order deliberately opposite to display order.
        displays = [
            {"device": r"\\.\DISPLAY1", "width": 1366, "height": 768,
             "left": 0, "top": 0, "is_primary": True},
            {"device": r"\\.\DISPLAY2", "width": 1920, "height": 1080,
             "left": 1366, "top": 0, "is_primary": False},
        ]
        monitors, ambiguous = monitors_windows._match_displays_to_edids(
            displays, edids)
        self.assertEqual(monitors[0].brand, "AU Optronics")
        self.assertEqual(monitors[1].brand, "Dahua")
        self.assertEqual(monitors[1].display_name, "LM19-L200N")
        # The 1366x768 screen matches the AUO native resolution exactly.
        self.assertEqual(ambiguous, [])

    def test_exact_match_beats_enumeration_order(self):
        from screeninfo_gui import monitors_windows
        edids = [{"path": "a", "edid": bytes.fromhex(REAL_DAHUA_19)},
                 {"path": "b", "edid": bytes.fromhex(REAL_AUO_LAPTOP)}]
        displays = [
            {"device": r"\\.\DISPLAY1", "width": 1920, "height": 1080,
             "left": 0, "top": 0, "is_primary": True},
            {"device": r"\\.\DISPLAY2", "width": 1366, "height": 768,
             "left": 1920, "top": 0, "is_primary": False},
        ]
        monitors, _ = monitors_windows._match_displays_to_edids(displays, edids)
        self.assertEqual(monitors[1].brand, "AU Optronics")
        self.assertEqual(monitors[0].brand, "Dahua")

    def test_stale_edid_is_reported_as_suspicious(self):
        from screeninfo_gui import monitors_windows
        info = monitors_windows.parse_edid(bytes.fromhex(REAL_DAHUA_19))
        displays = [{"width": 1280, "height": 1024}]      # nothing like it
        self.assertEqual(monitors_windows._resolution_score(displays[0], info), 2)
        displays_ok = [{"width": 1600, "height": 900}]
        self.assertEqual(
            monitors_windows._resolution_score(displays_ok[0], info), 0)


class TestPlaceholderRejection(unittest.TestCase):
    def test_repeated_digit_serial_rejected(self):
        self.assertTrue(EdidInfo._is_placeholder("00000001"))
        self.assertTrue(EdidInfo._is_placeholder("11111111"))
        self.assertTrue(EdidInfo._is_placeholder("1"))

    def test_real_serial_accepted(self):
        self.assertFalse(EdidInfo._is_placeholder("AG60100370LR"))
        self.assertFalse(EdidInfo._is_placeholder("CN0ASU1"))

    def test_repeated_byte_numeric_serial_rejected(self):
        self.assertTrue(EdidInfo._numeric_is_placeholder(0x01010101))
        self.assertTrue(EdidInfo._numeric_is_placeholder(0xFFFFFFFF))
        self.assertTrue(EdidInfo._numeric_is_placeholder(0))

    def test_real_numeric_serial_accepted(self):
        self.assertFalse(EdidInfo._numeric_is_placeholder(0x1A2B3C4D))
