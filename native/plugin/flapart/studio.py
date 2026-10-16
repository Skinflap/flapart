# SPDX-License-Identifier: GPL-3.0-or-later
"""Flapart's reversible, local-first native workspace. No credentials or uploads."""
from pathlib import Path
import os
from krita import Extension, Krita, InfoObject
try:
    from PyQt5.QtCore import QUrl, QTimer
    from PyQt5.QtGui import QDesktopServices, QFont, QFontDatabase, QIcon
    from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QPushButton, QLabel, QComboBox, QFileDialog, QMessageBox, QDockWidget, QScrollArea, QWidget, QApplication)
except ImportError:
    from PyQt6.QtCore import QUrl, QTimer
    from PyQt6.QtGui import QDesktopServices, QFont, QFontDatabase, QIcon
    from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QPushButton, QLabel, QComboBox, QFileDialog, QMessageBox, QDockWidget, QScrollArea, QWidget, QApplication)
YES = QMessageBox.StandardButton.Yes
NO = QMessageBox.StandardButton.No

STYLE = '''QWidget { font-family: "Syne Mono"; font-size: 14px; }
QDialog { background:#1f2128; color:#ede8e1; }
QLabel { color:#ede8e1; } QPushButton,QComboBox { background:#292c35;
color:#ede8e1; border:1px solid #bf8b6f; border-radius:4px; padding:12px; }
QPushButton:hover { background:#373b47; } QPushButton:focus { border:2px solid #c2b4a5; }'''

class FlapartStudio(Extension):
    def __init__(self, parent):
        super().__init__(parent)
        self.hidden_docks = {}
        self.dialogs = []

    def setup(self):
        QFontDatabase.addApplicationFont(str(Path(__file__).with_name('SyneMono-Regular.ttf')))
        if os.environ.get('FLAPART_NATIVE') == '1':
            QApplication.instance().setFont(QFont('Syne Mono', 10))
            QApplication.instance().setWindowIcon(QIcon(str(Path(__file__).with_name('sigil.svg'))))
            QTimer.singleShot(2000, self.welcome)

    def welcome(self):
        window = Krita.instance().activeWindow()
        if window:
            self.show_studio(window)

    def createActions(self, window):
        action = window.createAction('flapart_studio', 'Flapart Studio', 'tools/scripts')
        action.triggered.connect(self.welcome)

    def trigger(self, name):
        action = Krita.instance().action(name)
        if action:
            action.trigger()
        else:
            QMessageBox.information(None, 'Flapart', 'This tool is unavailable in this Krita build. The full menus remain available.')

    def new_canvas(self, window, size):
        width, height = size
        doc = Krita.instance().createDocument(width, height, 'Untitled Flapart', 'RGBA', 'U8', '', 144.0)
        if not doc:
            QMessageBox.warning(None, 'Flapart', 'The canvas could not be created. Try a smaller size.')
            return
        layer = doc.createNode('Draw here', 'paintlayer')
        doc.rootNode().addChildNode(layer, None)
        doc.setActiveNode(layer)
        window.addView(doc)
        doc.refreshProjection()

    def focus_canvas(self, window):
        qwindow = window.qwindow()
        key = id(qwindow)
        if key in self.hidden_docks:
            for dock in self.hidden_docks.pop(key):
                try:
                    dock.show()
                except RuntimeError:
                    pass
            return
        # Preserve menus, toolbars and all editing functionality; only hide currently visible docks.
        docks = [dock for dock in qwindow.findChildren(QDockWidget) if dock.isVisible()]
        self.hidden_docks[key] = docks
        for dock in docks:
            dock.hide()

    def export_png(self, window, destination=None):
        doc = Krita.instance().activeDocument()
        if not doc:
            QMessageBox.information(window.qwindow(), 'Flapart', 'Open or create a canvas first.')
            return False
        path, _ = QFileDialog.getSaveFileName(window.qwindow(), 'Export a picture', '', 'PNG picture (*.png)')
        if not path:
            return False
        if not path.lower().endswith('.png'):
            path += '.png'
        # If adding an extension changed the selected path, ask before overwriting that actual path.
        if Path(path).exists():
            if QMessageBox.question(window.qwindow(), 'Replace picture?', 'Replace the existing picture at this location?',
                                    YES | NO, NO) != YES:
                return False
        doc.waitForDone()
        config = InfoObject()
        for key, value in {'alpha': True, 'compression': 6, 'forceSRGB': True,
                           'storeAuthor': False, 'storeMetaData': False}.items():
            config.setProperty(key, value)
        original_batchmode = doc.batchmode()
        try:
            doc.setBatchmode(True)
            exported = doc.exportImage(path, config)
        finally:
            doc.setBatchmode(original_batchmode)
        if not exported:
            QMessageBox.warning(window.qwindow(), 'Export failed', 'Your drawing is still open. Choose another location and try again.')
            return False
        if destination:
            QMessageBox.information(window.qwindow(), 'Picture exported',
                'Your PNG is saved. Flapart will open in your browser. Import this PNG, then choose Save to profile or Post to Town Hall. Your layered original stays here.')
            QDesktopServices.openUrl(QUrl('https://flaptown.com/flapart/?from=native&destination=' + destination))
        return True

    def show_studio(self, window):
        dialog = QDialog(window.qwindow())
        dialog.setWindowTitle('Flapart · Flaptown Advancements')
        dialog.setFont(QFont('Syne Mono', 11))
        dialog.setStyleSheet(STYLE)
        dialog.resize(640, 680)
        outer = QVBoxLayout(dialog)
        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setStyleSheet('background:#1f2128;')
        scroll.setWidget(content)
        outer.addWidget(scroll)
        layout = QVBoxLayout(content)
        title = QLabel('FLAPART\nA little less friction. All your art tools.')
        title.setWordWrap(True)
        title.setMinimumHeight(52)
        layout.addWidget(title)
        note = QLabel('Create locally, save an editable original, export a picture, or share when you choose. The full Krita menus and brush engines remain available.')
        note.setWordWrap(True)
        note.setMinimumHeight(72)
        layout.addWidget(note)
        sizes = QComboBox()
        for label, size in [('Square · 1600 × 1600', (1600,1600)), ('Landscape · 1920 × 1080', (1920,1080)), ('Portrait · 1200 × 1600', (1200,1600))]:
            sizes.addItem(label, size)
        layout.addWidget(sizes)
        def add(label, callback):
            button = QPushButton(label)
            button.clicked.connect(callback)
            layout.addWidget(button)
        def start():
            self.new_canvas(window, sizes.currentData())
            dialog.close()
        add('Start drawing', start)
        add('Open a drawing…', lambda: self.trigger('file_open'))
        add('Save editable original…', lambda: self.trigger('file_save_as'))
        add('Export PNG picture…', lambda: self.export_png(window))
        add('Save picture to my profile…', lambda: self.export_png(window, 'profile'))
        add('Share picture to Town Hall…', lambda: self.export_png(window, 'townhall'))
        def focus():
            self.focus_canvas(window)
            dialog.close()
        add('Focus canvas / restore panels', focus)
        add('Brush settings', lambda: self.trigger('show_brush_editor'))
        add('Flapsoft · source and help', lambda: QDesktopServices.openUrl(QUrl('https://flaptown.com/flapsoft/')))
        add('Back to drawing', dialog.close)
        footer = QLabel('Ctrl + Alt + F opens this panel. Esc returns to drawing. Sharing opens your browser; no automatic uploads.')
        footer.setWordWrap(True)
        layout.addWidget(footer)
        self.dialogs.append(dialog)
        dialog.finished.connect(lambda: self.dialogs.remove(dialog))
        dialog.show()
