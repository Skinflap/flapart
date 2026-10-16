# SPDX-License-Identifier: GPL-3.0-or-later
try:
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication, QDockWidget, QToolTip
except ImportError:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QDockWidget, QToolTip
from krita import Krita, InfoObject
import json, pathlib, traceback, os, platform

def run():
    out=pathlib.Path(os.environ['FLAPART_QA_OUTPUT']); out.mkdir(parents=True, exist_ok=True)
    result={}
    (out/"stage.txt").write_text("entered")
    try:
        k=Krita.instance(); w=k.activeWindow()
        from flapart.studio import FlapartStudio
        studio=FlapartStudio(k)
        (out/"stage.txt").write_text("new canvas")
        studio.new_canvas(w,(64,64))
        (out/"stage.txt").write_text("canvas created")
        doc=k.activeDocument()
        doc.setBatchmode(True)
        result['canvas']=[doc.width(),doc.height()]
        layer=doc.activeNode()
        layer.setPixelData(bytes([70,110,191,255])*64*64,0,0,64,64)
        (out/"stage.txt").write_text("pixel data written")
        doc.refreshProjection(); doc.waitForDone()
        (out/"stage.txt").write_text("exporting")
        from flapart import studio as module
        module.QFileDialog.getSaveFileName = lambda *args: (str(out/'helper-export.png'), '')
        module.QMessageBox.question = lambda *args: module.YES
        module.QMessageBox.information = lambda *args: None
        opened = []
        module.QDesktopServices.openUrl = lambda url: opened.append(url.toString()) or True
        doc.setBatchmode(False)
        result['png'] = studio.export_png(w, 'profile')
        result['batchmode_restored'] = not doc.batchmode()
        result['browser_handoff'] = opened
        doc.setBatchmode(True)
        result['kra']=doc.saveAs(str(out/'drawing.kra'))
        reopened=k.openDocument(str(out/'drawing.kra'))
        nodes = reopened.rootNode().childNodes()
        drawing = next(node for node in nodes if node.name() == 'Draw here')
        result['round_trip'] = [reopened.width(), reopened.height(), drawing.name()]
        result['round_trip_pixel'] = list(bytes(drawing.pixelData(32,32,1,1)))
        docks = w.qwindow().findChildren(QDockWidget)
        before = {d.objectName(): d.isVisible() for d in docks}
        studio.focus_canvas(w)
        result['focus_hides_panels'] = all(not d.isVisible() for d in docks)
        studio.focus_canvas(w)
        result['focus_restores_panels'] = before == {d.objectName(): d.isVisible() for d in docks}
        studio.show_studio(w)
        result['action']=bool(k.action('flapart_studio'))
        QTimer.singleShot(700,lambda: finish(result,w,out))
    except Exception:
        result['error']=traceback.format_exc()
        finish(result,w,out)

def finish(result,w,out):
    QToolTip.hideText()
    w.qwindow().grab().save(str(out/'studio.png'))
    result['platform'] = platform.platform()
    result['native_engine_version'] = Krita.instance().version()
    (out/'result.json').write_text(json.dumps(result,indent=2))
    import os
    os._exit(0)
QTimer.singleShot(3500,run)
