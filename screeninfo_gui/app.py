"""EDIMETER - PySide6 GUI showing each monitor's diagonal in inches,
brand and serial number behind a single button press.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QTimer, Qt, QThread, Signal
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from . import screens_from_qt
from .model import UNAVAILABLE, DetectionResult, MonitorInfo
from .theme import QSS

APP_NAME = "EDIMETER"


def _detect_platform():
    if sys.platform == "win32":
        from . import monitors_windows
        return monitors_windows, "Registre EDID / WMI"
    from . import monitors_linux
    return monitors_linux, "xrandr / EDID"


class _Worker(QThread):
    """Runs detection off the GUI thread so the window never freezes."""

    done = Signal(object)

    def __init__(self, backend, screens, parent=None):
        super().__init__(parent)
        self._backend = backend
        self.screens = screens

    def run(self):
        try:
            self.done.emit(self._backend.detect(self.screens))
        except Exception as exc:                      # never kill the GUI thread
            self.done.emit(DetectionResult(
                warnings=["Erreur inattendue: %s" % exc],
                method="erreur",
            ))


class _Field(QWidget):
    """A label above a value, with a muted style when the value is missing.

    ``field`` names the value so the caller can attach a copy button that
    copies this single field on its own.
    """

    def __init__(self, name, value, monitor_index=None, field=None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        head = QHBoxLayout()
        head.setSpacing(6)
        caption = QLabel(name)
        caption.setObjectName("FieldName")
        head.addWidget(caption)
        head.addStretch(1)
        if field and monitor_index is not None:
            head.addWidget(_copy_chip(monitor_index, field))
        layout.addLayout(head)

        is_unknown = (not value) or value == UNAVAILABLE
        self.value = QLabel(value if value else UNAVAILABLE)
        self.value.setObjectName("FieldUnknown" if is_unknown else "FieldValue")
        self.value.setWordWrap(True)
        self.value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.value)


def _copy_chip(monitor_index: int, field: str) -> QLabel:
    """Tiny square button that copies one field of one monitor."""
    chip = QLabel("copier")
    chip.setObjectName("CopyChip")
    chip.setAlignment(Qt.AlignCenter)
    chip.setCursor(Qt.CursorShape.PointingHandCursor)
    chip.setProperty("monitor_index", monitor_index)
    chip.setProperty("field", field)
    chip.setToolTip("Copier uniquement cette valeur")
    return chip


class MonitorCard(QFrame):
    """One monitor: title row, big diagonal figure, then the three fields."""

    def __init__(self, monitor: MonitorInfo, cursor_screen: MonitorInfo | None,
                 parent=None):
        super().__init__(parent)
        self.monitor = monitor
        is_cursor = bool(cursor_screen and cursor_screen.index == monitor.index)
        self.setObjectName("CardPrimary" if monitor.is_primary else "Card")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(14)

        # Title row with brand/model and status badges.
        head = QHBoxLayout()
        head.setSpacing(10)
        title = QLabel(monitor.title)
        title.setObjectName("CardTitle")
        head.addWidget(title)
        head.addStretch(1)

        if monitor.is_primary:
            badge = QLabel("PRINCIPAL")
            badge.setObjectName("Badge")
            head.addWidget(badge)
        if is_cursor:
            badge = QLabel("SOUS LE CURSEUR")
            badge.setObjectName("Badge")
            head.addWidget(badge)

        size_badge = QLabel(monitor.size_source or "taille inconnue")
        size_badge.setObjectName("BadgeSoft" if not monitor.size_source else "Badge")
        head.addWidget(size_badge)
        head.addWidget(self.copy_button())
        outer.addLayout(head)

        # Big diagonal figure beside the three requested values.
        body = QHBoxLayout()
        body.setSpacing(24)

        figure = QVBoxLayout()
        figure.setSpacing(0)
        has_size = monitor.diagonal_in > 0
        self.diagonal = QLabel(monitor.diagonal_text)
        self.diagonal.setObjectName("Diagonal" if has_size else "DiagonalUnknown")
        figure.addWidget(self.diagonal)
        caption = QLabel("diagonale" if has_size else "diagonale indisponible")
        caption.setObjectName("CardMeta")
        figure.addWidget(caption)
        figure.addStretch(1)
        body.addLayout(figure)

        grid = QGridLayout()
        grid.setHorizontalSpacing(22)
        grid.setVerticalSpacing(12)
        grid.addWidget(_Field("MARQUE", monitor.brand_text, monitor.index, "brand"),
                       0, 0)
        grid.addWidget(
            _Field("NUMERO DE SERIE", monitor.serial_text, monitor.index, "serial"),
            0, 1)
        grid.addWidget(_Field("TAILLE PHYSIQUE", monitor.size_text, monitor.index,
                              "size"), 1, 0)
        grid.addWidget(_Field("RESOLUTION", monitor.resolution), 1, 1)
        body.addLayout(grid, 1)
        outer.addLayout(body)

        # Secondary details line.
        details = [
            monitor.size_cm_text,
            monitor.position and "position %s" % monitor.position,
            "id interne %s" % monitor.index,
        ]
        if monitor.display_name and monitor.display_name != monitor.model_text:
            details.insert(0, "nom EDID %s" % monitor.display_name)
        line = QLabel("  ·  ".join(d for d in details if d))
        line.setObjectName("CardMeta")
        line.setWordWrap(True)
        outer.addWidget(line)

        # When the EDID contradicts itself, say so rather than presenting one
        # number as fact. Two monitors can also get swapped, which changes the
        # brand and the serial too, so the raw EDID is offered for checking.
        if monitor.size_conflict and monitor.alt_size_in:
            warn = QLabel(
                "Taille incohérente dans l'EDID : %.1f\" (paramètres de base) "
                "contre %.1f\" (descripteur de timing)."
                % (monitor.diagonal_in, monitor.alt_size_in)
            )
            warn.setObjectName("Warn")
            warn.setWordWrap(True)
            outer.addWidget(warn)

    def copy_button(self) -> QLabel:
        """Outline button that copies this monitor's details."""
        button = QLabel("Copier")
        button.setObjectName("CopyButton")
        button.setAlignment(Qt.AlignCenter)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("monitor_index", self.monitor.index)
        button.setToolTip(
            "Copier marque, numero de serie et details de %s" % self.monitor.title
        )
        return button


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(760, 620)
        self._backend, self._method_label = _detect_platform()
        self._result: DetectionResult | None = None
        self._worker: _Worker | None = None
        self._build()
        self._show_idle()

    # ---------- construction ----------
    def _build(self):
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Green header with the single action button.
        header = QFrame()
        header.setObjectName("Header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 18, 24, 18)
        header_layout.setSpacing(16)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        # Already an acronym: no underscores to expand.
        title = QLabel(APP_NAME)
        title.setObjectName("Title")
        self.subtitle = QLabel("Taille, marque et numero de serie de vos ecrans")
        self.subtitle.setObjectName("Subtitle")
        titles.addWidget(title)
        titles.addWidget(self.subtitle)
        header_layout.addLayout(titles)
        header_layout.addStretch(1)

        self.button = QLabel("Analyser mes ecrans")
        self.button.setObjectName("ScanButton")
        self.button.setAlignment(Qt.AlignCenter)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setMinimumWidth(190)
        self.button.installEventFilter(self)
        header_layout.addWidget(self.button, 0, Qt.AlignVCenter)

        self.copy_all = QLabel("Tout copier")
        self.copy_all.setObjectName("CopyButton")
        self.copy_all.setAlignment(Qt.AlignCenter)
        self.copy_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_all.setToolTip("Copier les informations de tous les ecrans")
        self.copy_all.setVisible(False)
        self.copy_all.installEventFilter(self)
        header_layout.addWidget(self.copy_all, 0, Qt.AlignVCenter)
        root_layout.addWidget(header)

        # Scrolling area for the cards.
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(24, 20, 24, 20)
        self.body_layout.setSpacing(14)
        # A trailing stretch keeps every card at its natural size instead of
        # being squeezed when several monitors do not fit on screen. Using
        # AlignTop here instead would break scrolling, because the cards would
        # still be compressed rather than allowed to overflow.
        self.body_layout.addStretch(1)
        self.scroll.setWidget(self.body)
        root_layout.addWidget(self.scroll, 1)

        footer = QFrame()
        footer.setObjectName("Footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 9, 24, 9)
        self.status = QLabel("Pret.")
        self.status.setObjectName("CardMeta")
        footer_layout.addWidget(self.status)
        footer_layout.addStretch(1)
        self.source = QLabel("source : %s" % self._method_label)
        self.source.setObjectName("CardMeta")
        footer_layout.addWidget(self.source)
        root_layout.addWidget(footer)

        self.setCentralWidget(root)

    def _clear_cards(self):
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # setParent(None) detaches it immediately; deleteLater alone
                # would leave the old card painted until the next event loop
                # turn, so stale cards briefly show behind the new ones.
                widget.setParent(None)
                widget.deleteLater()

    def _add_placeholder(self, title, message):
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 30, 24, 30)
        layout.setSpacing(8)
        heading = QLabel(title)
        heading.setObjectName("CardTitle")
        body = QLabel(message)
        body.setObjectName("CardMeta")
        body.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(body)
        layout.addStretch(1)
        # Minimum, not Maximum: a Maximum vertical policy hands the widget only
        # minimumSizeHint(), which ignores the height needed for wrapped text,
        # and the warning gets clipped. Minimum still lets the card grow but
        # not stretch, and the layout is top-aligned.
        card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.body_layout.addWidget(card)

    def _sync_scroll_height(self) -> None:
        """Make the scroll area actually scroll.

        With widgetResizable enabled, QScrollArea pins the inner widget to the
        viewport height and then compresses the layout, which clips the cards
        and swallows their text. Pinning an explicit minimum height restores
        scrolling. Recomputed on resize because word wrapping changes how many
        lines each warning needs.
        """
        self.body_layout.activate()
        self.body.setMinimumHeight(self.body_layout.sizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_scroll_height()

    def eventFilter(self, watched, event):
        """Click handling for the styled QLabels used as buttons.

        Qt does NOT propagate event filters down the parent chain, so every
        copy chip and per-card button has to be registered explicitly in
        _register_buttons. A filter installed on a widget that has no
        eventFilter() silently swallows the click.
        """
        if event.type() != QEvent.Type.MouseButtonPress:
            return super().eventFilter(watched, event)
        if watched is self.button:
            self._on_button_pressed(event)
            return True
        if watched is self.copy_all:
            self._copy_all_monitors(watched)
            return True
        # A Qt dynamic property is NOT a Python attribute: hasattr() on it is
        # always False, so it must be read through property(). Getting this
        # wrong makes the button silently dead.
        if watched.objectName() in ("CopyButton", "CopyChip"):
            monitor_index = watched.property("monitor_index")
            if monitor_index is None:
                return super().eventFilter(watched, event)
            field = watched.property("field")
            if field is not None:
                self._copy_field(watched, str(field))
            else:
                self._copy_one(int(monitor_index), watched)
            return True
        return super().eventFilter(watched, event)

    # ---------- clipboard ----------
    def _register_buttons(self, widget: QWidget) -> None:
        """Attach the click filter to every copy control under ``widget``.

        Event filters are not inherited by child widgets in Qt, so each chip
        and per-card button needs its own registration.
        """
        for child in widget.findChildren(QLabel):
            if child.objectName() in ("CopyButton", "CopyChip"):
                child.installEventFilter(self)

    def _flash(self, button: QLabel, text: str) -> None:
        """Confirm a copy on the button itself, then restore its label."""
        button.setProperty("restore_text", button.text())
        button.setText(text)
        QTimer.singleShot(1400, lambda: button.setText(
            button.property("restore_text") or "Copier"))

    def _copy(self, text: str, button: QLabel) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is None:
            self.status.setText("Presse-papiers indisponible.")
            return
        clipboard.setText(text)
        self.status.setText("Copie : %s" % text.replace("\n", " ").strip()[:70])
        self._flash(button, "Copie !")

    def _copy_field(self, button: QLabel, field: str) -> None:
        """Copy a single value (brand or serial) from one monitor."""
        if not self._result:
            return
        index = int(button.property("monitor_index"))
        for mon in self._result.monitors:
            if mon.index != index:
                continue
            value = {
                "brand": mon.brand_text,
                "serial": mon.serial_text,
                "size": mon.diagonal_text,
            }.get(field, "")
            if value:
                self._copy(value, button)
            return

    def _copy_one(self, index: int, button: QLabel) -> None:
        if not self._result:
            return
        for mon in self._result.monitors:
            if mon.index == index:
                self._copy(mon.as_text(), button)
                return

    def _copy_all_monitors(self, button: QLabel) -> None:
        if not self._result or not self._result.monitors:
            return
        self._copy("\n\n".join(m.as_text() for m in self._result.monitors), button)

    # ---------- states ----------
    def _show_idle(self):
        self._clear_cards()
        self.copy_all.setVisible(False)
        self._add_placeholder(
            "Pret a analyser",
            "Cliquez sur le bouton vert ci-dessus pour lire les informations "
            "de vos ecrans. Aucune donnee ne quitte votre machine.",
        )

    def _show_busy(self):
        self._clear_cards()
        self._add_placeholder("Analyse en cours...", "Lecture des informations EDID.")
        self.button.setEnabled(False)
        self.status.setText("Lecture des ecrans...")

    def _on_button_pressed(self, _event):
        """Entry point for the single button."""
        if not self.button.isEnabled():
            return
        self._show_busy()
        # QScreen objects belong to the GUI thread, so copy their values into
        # plain stubs before handing them to the worker.
        snapshot = screens_from_qt()
        self._worker = _Worker(self._backend, snapshot, parent=self)
        self._worker.done.connect(self._on_detected)
        self._worker.start()

    

    def _on_detected(self, result: DetectionResult):
        self._result = result
        self.button.setEnabled(True)
        self._clear_cards()

        if not result.monitors:
            self._add_placeholder(
                "Aucun ecran detecte",
                "\n".join(result.warnings) or
                "Aucun moniteur n'a pu etre identifie sur ce systeme.",
            )
            self.status.setText("Echec de la detection (%s)" % result.method)
            return

        cursor_screen = QApplication.screenAt(QCursor.pos())
        cursor_name = cursor_screen.name() if cursor_screen else None
        screens = self._worker.screens if self._worker else []
        cursor_monitor = None
        for mon, snap in zip(result.monitors, screens):
            if snap.name == cursor_name:
                cursor_monitor = mon
                break

        # Warnings come first: a pairing or a stale-EDID warning is the reason a
        # value looks wrong, so burying it under the screens defeats the point.
        if result.warnings:
            self._add_placeholder("Remarque", "\n\n".join(result.warnings))

        for mon in result.monitors:
            card = MonitorCard(mon, cursor_monitor)
            self._register_buttons(card)
            self.body_layout.addWidget(card)

        # "Tout copier" only makes sense once something has been detected.
        self.copy_all.setVisible(len(result.monitors) > 0)

        self._sync_scroll_height()

        self.status.setText(
            "%d ecran(s) detecte(s) via %s"
            % (len(result.monitors), result.method)
        )

        # Tooltips are invisible unless hovered, and these warnings explain a
        # missing value the user is looking straight at, so show them inline.
        if result.warnings:
            self.status.setToolTip("\n\n".join(result.warnings))


def main(argv=None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(QSS)

    font = QFont("Segoe UI" if sys.platform == "win32" else "DejaVu Sans", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())