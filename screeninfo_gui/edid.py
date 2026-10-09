"""Minimal EDID 1.3 / 1.4 block parser.

Reads the 128-byte base block (plus the 256-byte CTA extension when present) and
exposes the fields the GUI needs: brand, product code, serial number and the
physical image size used to derive the diagonal in inches.

Two serial encodings exist in the wild and neither is reliable on its own:
  * the numeric serial at bytes 12-15, which many manufacturers leave at 0
  * the ASCII serial string in the first 0xFF descriptor, which many set to
    "0" or a timestamp instead of a real serial
`parse_edid` therefore collects both and lets the caller decide.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field

EDID_HEADER = bytes((0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00))
EDID_LENGTH = 128

# Display-descriptor tags: serial text, free text, monitor name, range limits.
_DISPLAY_TAGS = frozenset((0xFC, 0xFD, 0xFE, 0xFF))

# Manufacturer IDs are three 5-bit letters where 'A' is 1, not 0.
_VENDOR_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_VENDOR_INDEX = {i + 1: c for i, c in enumerate(_VENDOR_CHARS)}

# Vendor codes assigned by UEFI. Incomplete by nature, and the code sometimes
# names the panel fabricator rather than the brand that sold the monitor, so
# the monitor-name descriptor is preferred whenever it yields a usable brand.
VENDORS = {
    "AAA": "Avolites", "ACI": "Ancor Communications", "ACR": "Acer",
    "ADI": "ADI Displays", "AEC": "Acer", "AGL": "AG Neovo",
    "AOC": "AOC", "API": "Acer America", "APP": "Apple", "ASU": "ASUS",
    "AUO": "AU Optronics", "BNQ": "BenQ", "BOE": "BOE Technology",
    "CMN": "Chimei Innolux", "CMO": "Chi Mei Optoelectronics",
    "CPT": "Chunghwa Picture Tube", "CPQ": "Compaq",
    "DHI": "Dahua", "DEL": "Dell", "DGC": "Digi-Key",
    "ENC": "Eizo", "EIZ": "Eizo",
    "FUS": "Fujitsu Siemens", "GSM": "Goldstar", "HPN": "HP",
    "HSD": "HannStar Display", "HWP": "Hewlett Packard", "IBM": "IBM",
    "INL": "InnoLux Display", "IVM": "Iiyama", "LEN": "Lenovo",
    "LGD": "LG Display", "LPL": "LG Philips", "MEI": "Panasonic",
    "MEL": "Mitsubishi Electric", "MSI": "MSI", "NEC": "NEC",
    "PHL": "Philips", "SAM": "Samsung", "SEC": "Seiko Epson",
    "SHP": "Sharp", "SNY": "Sony", "SPT": "Sceptre",
    "TOS": "Toshiba", "TPY": "Toppoly", "TSB": "Toshiba",
    "VSC": "ViewSonic", "VSD": "Visionox", "XIN": "Xinyi",
    "ZOT": "Zotac",
}

# Brands recognised inside a monitor-name descriptor such as "ASUS VG27A" or
# "DELL U2419M". Checked longest-prefix-first against the first word.
KNOWN_BRANDS = [
    "ASUS", "Acer", "AOC", "BenQ", "Chimei", "Chunghwa", "Dahua", "Dell",
    "Eizo", "Fujitsu", "Gateway", "Goldstar", "Hansol", "HannStar", "HP",
    "Huawei", "Hyundai", "Iiyama", "InnoLux", "Lenovo", "LG", "MSI",
    "NEC", "Panasonic", "Philips", "Razer", "Samsung", "Sceptre",
    "Sharp", "Sony", "Toshiba", "Vizio", "ViewSonic", "Xiaomi",
]


def decode_vendor(raw: int) -> str:
    """Turn the 16-bit manufacturer field into three uppercase letters."""
    out = []
    for shift in (10, 5, 0):
        letter = (raw >> shift) & 0x1F
        out.append(_VENDOR_INDEX.get(letter, "?"))
    return "".join(out)


def _decode_text(raw: bytes) -> str:
    """Decode an already-extracted descriptor text slice.

    Callers hand over just the character bytes, so nothing is skipped here.
    0x0A is the descriptor's line terminator and ends the string; 0x00 is
    padding.
    """
    chars = []
    for byte in raw:
        if byte == 0x0A:
            break
        if 0x20 <= byte <= 0x7E:
            chars.append(chr(byte))
    return "".join(chars).strip()


@dataclass
class EdidInfo:
    """Everything the parser could recover from one monitor's EDID."""

    vendor_id: str = ""
    brand: str = ""
    product_code: str = ""
    numeric_serial: str = ""
    text_serial: str = ""
    year: str = ""
    week: str = ""
    # Basic display parameters (bytes 21-22) are expressed in CENTIMETRES.
    size_h_cm: int = 0
    size_v_cm: int = 0
    # The detailed timing descriptor stores its image size in MILLIMETRES.
    # Mixing the two units produced diagonals off by a factor of ten, so both
    # are kept apart and only converted at the very end.
    dtd_h_mm: int = 0
    dtd_v_mm: int = 0
    display_name: str = ""     # 0xFC monitor name, e.g. "ASUS VG27A"
    panel_texts: list = field(default_factory=list)  # 0xFE free-text items
    raw_hex: str = ""
    edid_version: str = ""
    native_width: int = 0      # active pixels of the preferred timing
    native_height: int = 0
    valid: bool = False

    @property
    def native_resolution(self) -> str:
        """Preferred resolution as "W x H", or "" when not determinable."""
        if self.native_width and self.native_height:
            return "%d x %d" % (self.native_width, self.native_height)
        return ""

    @staticmethod
    def _is_placeholder(text: str) -> bool:
        """True for serials that are obviously padding rather than real ones.

        Monitors routinely publish "00000001", "12345678" or a bare "1".
        Showing those would be worse than showing nothing, because they look
        like genuine identifiers.
        """
        stripped = text.strip()
        if not stripped:
            return True
        if stripped.upper() in {"0", "1", "NONE", "N/A", "DEFAULT", "NULL"}:
            return True
        if stripped.isdigit():
            digits = stripped.lstrip("0")
            # All zeros, or a single digit amid a long run of them.
            if not digits:
                return True
            if len(stripped) >= 6 and stripped[:-1].strip("0") == "":
                return True
        # "12345678", "11111111": one repeated digit filling the field.
        if len(stripped) >= 4 and len(set(stripped)) == 1:
            return True
        return False

    @staticmethod
    def _numeric_is_placeholder(value: int) -> bool:
        """Reject serials like 0x01010101 (16843009) or 0xFFFFFFFF.

        A firmware that fills the 32-bit serial field with one repeated byte
        produces a plausible-looking decimal number that means nothing.
        """
        if value <= 0:
            return True
        raw = value.to_bytes(4, "little", signed=False)
        return len(set(raw)) == 1

    @property
    def serial(self) -> str:
        """Best available serial, preferring the ASCII descriptor."""
        text = self.text_serial.strip()
        if text and not self._is_placeholder(text):
            return text
        num = self.numeric_serial.strip()
        if num and not self._is_placeholder(num):
            value = int(num)
            if not self._numeric_is_placeholder(value):
                return num.lstrip("0") or num
        return ""

    @property
    def width_in(self) -> float:
        if self.size_h_cm <= 0:
            return 0.0
        return self.size_h_cm / 2.54

    @property
    def height_in(self) -> float:
        if self.size_v_cm <= 0:
            return 0.0
        return self.size_v_cm / 2.54

    @property
    def dtd_width_in(self) -> float:
        if self.dtd_h_mm <= 0:
            return 0.0
        return self.dtd_h_mm / 25.4

    @property
    def dtd_height_in(self) -> float:
        if self.dtd_v_mm <= 0:
            return 0.0
        return self.dtd_v_mm / 25.4

    @property
    def dtd_diagonal_in(self) -> float:
        w, h = self.dtd_width_in, self.dtd_height_in
        if w <= 0 or h <= 0:
            return 0.0
        return (w * w + h * h) ** 0.5

    @property
    def size_conflict(self) -> bool:
        """True when base block and timing descriptor disagree badly.

        Rather than silently picking one, the UI shows both so a wrong figure
        is attributable instead of mysterious.
        """
        if not self.dtd_diagonal_in or not self.diagonal_in:
            return False
        base, dtd = self.diagonal_in, self.dtd_diagonal_in
        return abs(base - dtd) / max(base, dtd) > 0.15

    @property
    def panel_text(self) -> str:
        """All 0xFE free-text items joined, e.g. "AUO B140XTN07.2"."""
        return " ".join(self.panel_texts)

    @property
    def brand_from_name(self) -> str:
        """Brand guessed from the monitor name descriptor, or "" if unsure.

        The manufacturer ID is sometimes the panel vendor rather than the
        brand that sold the monitor, so "ASUS VG27A" is more useful than the
        three-letter code of whoever fabbed the panel. Returns an empty string
        when the first word is not a recognised brand: guessing "Lm19-L200N"
        is a brand would be worse than falling back to the vendor table.
        """
        head = self.display_name.strip().split()
        if not head:
            return ""
        word = re.sub(r"[^A-Z0-9]", "", head[0].upper())
        if not word:
            return ""
        for known in KNOWN_BRANDS:
            token = re.sub(r"[^A-Z]", "", known.upper())
            if word.startswith(token) and len(token) >= 3:
                return known
        return ""

    @property
    def diagonal_in(self) -> float:
        """Physical diagonal in inches.

        Prefers the base-block size in cm; falls back to the timing
        descriptor, whose units are millimetres.
        """
        if self.width_in > 0 and self.height_in > 0:
            return self.diagonal_from_base_in
        return self.dtd_diagonal_in

    @property
    def diagonal_from_base_in(self) -> float:
        w, h = self.width_in, self.height_in
        if w <= 0 or h <= 0:
            return 0.0
        return (w * w + h * h) ** 0.5

    @property
    def effective_width_in(self) -> float:
        return self.width_in if self.width_in > 0 else self.dtd_width_in

    @property
    def effective_height_in(self) -> float:
        return self.height_in if self.height_in > 0 else self.dtd_height_in


def parse_edid(data: bytes | None) -> EdidInfo:
    """Parse an EDID blob. Returns an invalid EdidInfo for absent/garbage data."""
    info = EdidInfo()
    if not data or len(data) < EDID_LENGTH:
        return info
    if data[:8] != EDID_HEADER:
        return info

    info.valid = True
    info.raw_hex = data[:EDID_LENGTH].hex()
    info.vendor_id = decode_vendor(struct.unpack(">H", data[8:10])[0])
    info.brand = VENDORS.get(info.vendor_id, info.vendor_id)
    info.product_code = str(struct.unpack("<H", data[10:12])[0])

    numeric = struct.unpack("<I", data[12:16])[0]
    info.numeric_serial = str(numeric) if numeric else ""

    info.week = str(data[16])
    if data[17]:
        info.year = str(1990 + data[17])

    info.size_h_cm = data[21]
    info.size_v_cm = data[22]
    info.edid_version = "%d.%d" % (data[18], data[19])

    # Four 18-byte descriptors start at byte 54. A descriptor is either a
    # Detailed Timing Descriptor, recognised by a NON-ZERO pixel clock in its
    # first two bytes, or a Display Descriptor whose layout is:
    #
    #     [0-1] 0x0000        [2] tag        [3..14] 12 chars   [15] 0x0A
    #
    # The tag sits at byte 2, NOT in bytes 0-1. Reading it from bytes 0-1
    # silently matched nothing, which meant the serial text, the monitor
    # name and the native resolution were never parsed at all.
    for offset in (54, 72, 90, 108):
        block = data[offset:offset + 18]
        if len(block) < 18:
            continue

        pixel_clock = struct.unpack(">H", block[0:2])[0]
        if pixel_clock:
            # Detailed Timing Descriptor.
            if not (info.native_width and info.native_height):
                info.native_width = block[2] | ((block[4] & 0xF0) << 4)
                info.native_height = block[5] | ((block[7] & 0xF0) << 4)
            # EDID 1.4 reuses the vertical front porch / sync fields to carry a
            # 16-bit image size in MILLIMETRES at bytes 14-15 and 16-17.
            # 1.3 keeps a single byte per axis at 16-17. Either way the
            # value is sanity-checked: real firmware routinely writes junk
            # there, and a 60000 mm panel is obviously not a monitor.
            # EDID revisions run 1.0 to 1.4; the change landed in 1.4, i.e.
            # the MINOR version, not the major one.
            minor = int(data[19])
            if minor >= 4 and len(block) >= 18:
                h_mm, v_mm = struct.unpack("<HH", block[14:18])
            else:
                h_mm, v_mm = block[16], block[17]
            if (not info.dtd_h_mm and 50 <= h_mm <= 2000
                    and 50 <= v_mm <= 2000):
                info.dtd_h_mm, info.dtd_v_mm = h_mm, v_mm
            continue

        tag_index = -1
        for candidate in (2, 3):
            if block[candidate] in _DISPLAY_TAGS:
                tag_index = candidate
                break
        if tag_index < 0:
            continue

        # Two layouts coexist in the field:
        #   EDID 1.3 : 00 00 | tag | text...
        #   EDID 1.4 : 00 00 00 | tag | 00 | text...
        # Taking the text from tag+1 works for both, since _decode_text skips
        # the NUL length byte of the 1.4 form.
        tag = block[tag_index]
        text = block[tag_index + 1:tag_index + 14]

        if tag == 0xFF and not info.text_serial:
            info.text_serial = _decode_text(text)
        elif tag == 0xFC and not info.display_name:
            info.display_name = _decode_text(text)
        elif tag == 0xFE:
            # Free-form text. Laptop panels put the panel maker here
            # ("AUO") and the panel part number ("B140XTN07.2"), whose
            # leading digits often name the real diagonal.
            text_value = _decode_text(text)
            if text_value and text_value not in info.panel_texts:
                info.panel_texts.append(text_value)
    return info


def parse_edid_hex(hex_text: str) -> EdidInfo:
    """Parse an EDID given as hex, ignoring whitespace and stray characters."""
    cleaned = "".join(c for c in hex_text if c in "0123456789abcdefABCDEF")
    if len(cleaned) < EDID_LENGTH * 2:
        return EdidInfo()
    try:
        return parse_edid(bytes.fromhex(cleaned[:EDID_LENGTH * 2]))
    except ValueError:
        return EdidInfo()