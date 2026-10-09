"""Qt stylesheet: white dominant, black text, green accents."""

ACCENT = "#00A63E"
ACCENT_DARK = "#007D2E"
ACCENT_LIGHT = "#E6F6EC"
INK = "#0E0E0E"
INK_SOFT = "#5A5A5A"
PAPER = "#FFFFFF"
EDGE = "#DCDCDC"

QSS = """
QWidget {
    background: %(paper)s;
    color: %(ink)s;
    font-family: "Segoe UI", "DejaVu Sans", "Noto Sans", sans-serif;
}

/* Containers paint their own background; labels must stay transparent or a
   white-on-green header would become white text on a white label. */
QLabel, QFrame#Card QLabel, #FieldValue, #FieldName, #FieldUnknown {
    background: transparent;
}

#Header {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 %(accent)s, stop:1 %(accent_dark)s);
}
#Title {
    color: #FFFFFF;
    font-size: 22px;
    font-weight: 700;
}
#Subtitle {
    color: #E8FFF0;
    font-size: 12px;
}

#ScanButton {
    background: %(ink)s;
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 13px 30px;
    font-size: 14px;
    font-weight: 700;
}
#ScanButton:hover  { background: #242424; }
#ScanButton:pressed{ background: %(accent_dark)s; }
#ScanButton:disabled { background: #B8B8B8; color: #EEEEEE; }

/* Secondary action: outline rather than filled, so it stays subordinate to
   the black primary button next to it. */
#CopyButton {
    background: #FFFFFF;
    color: %(ink)s;
    border: 1px solid %(ink)s;
    border-radius: 8px;
    padding: 11px 22px;
    font-size: 13px;
    font-weight: 700;
}
#CopyButton:hover   { background: %(accent_light)s; border-color: %(accent)s;
                      color: %(accent_dark)s; }
#CopyButton:pressed { background: %(accent)s; color: #FFFFFF; }

/* Small chip that copies a single field next to its caption. */
#CopyChip {
    background: #FFFFFF;
    color: %(accent_dark)s;
    border: 1px solid %(accent)s;
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 9px;
    font-weight: 700;
}
#CopyChip:hover  { background: %(accent)s; color: #FFFFFF; }
#CopyChip:pressed{ background: %(accent_dark)s; color: #FFFFFF; }

#Card {
    background: %(paper)s;
    border: 1px solid %(edge)s;
    border-radius: 12px;
}
#CardPrimary { border: 2px solid %(accent)s; }

#Diagonal {
    color: %(accent)s;
    font-size: 40px;
    font-weight: 800;
}
#DiagonalUnknown { color: #A0A0A0; font-size: 20px; font-weight: 700; }

#CardTitle { font-size: 16px; font-weight: 700; color: %(ink)s; }
#CardMeta   { font-size: 12px; color: %(ink_soft)s; }

/* Flags a value the EDID contradicts elsewhere; needs to stand out. */
#Warn {
    font-size: 12px;
    font-weight: 700;
    color: #B3261E;
    background: #FDECEA;
    border: 1px solid #F3B4AD;
    border-radius: 6px;
    padding: 4px 8px;
}

#FieldName {
    font-size: 11px;
    font-weight: 700;
    color: %(ink_soft)s;
    letter-spacing: 1px;
}
#FieldValue { font-size: 13px; color: %(ink)s; }
#FieldUnknown { font-size: 13px; color: #A0A0A0; font-style: italic; }

#Badge {
    background: %(accent_light)s;
    color: %(accent_dark)s;
    border: 1px solid %(accent)s;
    border-radius: 10px;
    padding: 2px 9px;
    font-size: 10px;
    font-weight: 700;
}
#BadgeSoft {
    background: #F2F2F2;
    color: %(ink_soft)s;
    border: 1px solid %(edge)s;
    border-radius: 10px;
    padding: 2px 9px;
    font-size: 10px;
    font-weight: 700;
}

#Footer {
    background: %(paper)s;
    border-top: 1px solid %(edge)s;
    color: %(ink_soft)s;
    font-size: 11px;
}
""" % {
    "accent": ACCENT,
    "accent_dark": ACCENT_DARK,
    "accent_light": ACCENT_LIGHT,
    "ink": INK,
    "ink_soft": INK_SOFT,
    "paper": PAPER,
    "edge": EDGE,
}