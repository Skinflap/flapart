# SPDX-License-Identifier: GPL-3.0-or-later
try:
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication, QDockWidget, QToolTip, QPushButton
    from PyQt5.QtGui import QFontInfo, QPalette
except ImportError:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QDockWidget, QToolTip, QPushButton
    from PyQt6.QtGui import QFontInfo, QPalette
from krita import Krita, InfoObject
import json, pathlib, traceback, os, platform

def run():
    out=pathlib.Path(os.environ['FLAPART_QA_OUTPUT']); out.mkdir(parents=True, exist_ok=True)
    result={}
    owned_documents=[]
    keepalive=[]
    w=None
    (out/"stage.txt").write_text("entered")
    try:
        k=Krita.instance(); w=k.activeWindow()
        from flapart.studio import FlapartStudio
        studio=FlapartStudio(k)
        (out/"stage.txt").write_text("new canvas")
        studio.new_canvas(w,(64,64))
        (out/"stage.txt").write_text("canvas created")
        doc=k.activeDocument()
        owned_documents.append(doc)
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
        owned_documents.append(reopened)
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
        # Exercise the registered extension callback, never a freshly created callback.
        from flapart.studio import FlapartStudio
        registered=next(ext for ext in k.extensions() if isinstance(ext,FlapartStudio))
        for dialog in list(registered.dialogs): dialog.close()
        action=k.action('flapart_studio'); result['action']=bool(action)
        result['shortcut']=action.shortcut().toString()
        assert result['shortcut']=='Ctrl+Alt+F', 'Default Studio shortcut is unavailable'
        action.trigger()
        assert registered.dialogs and registered.dialogs[-1].isVisible(), 'Registered Studio action did not reopen'
        registered.dialogs[-1].close()
        action.trigger()
        result['action_reopens']=bool(registered.dialogs and registered.dialogs[-1].isVisible())
        assert result['action_reopens']
        studio=registered
        # Retain wrappers until asynchronous projection and final UI capture finish.
        keepalive.extend([doc,layer,reopened,nodes,drawing])
        QTimer.singleShot(700,lambda: finish(result,w,out,studio,owned_documents,keepalive))
    except Exception:
        result['error']=traceback.format_exc()
        finish(result,w,out,locals().get("studio"),owned_documents,keepalive)

def finish(result,w,out,studio=None,owned_documents=(),keepalive=()):
    try:
        QToolTip.hideText()
        w.qwindow().grab().save(str(out/'main-window.png'))
        result['platform'] = platform.platform()
        result['process_architecture'] = {'AMD64':'x86_64','aarch64':'arm64'}.get(platform.machine(),platform.machine())
        if platform.system() == 'Darwin':
            import ctypes, errno
            system = ctypes.CDLL(None,use_errno=True)
            translated = ctypes.c_int()
            size = ctypes.c_size_t(ctypes.sizeof(translated))
            status = system.sysctlbyname(b'sysctl.proc_translated',ctypes.byref(translated),ctypes.byref(size),None,0)
            if status != 0 and ctypes.get_errno() != errno.ENOENT:
                raise OSError(ctypes.get_errno(),'Cannot identify native application translation mode')
            result['execution_mode'] = 'translated' if translated.value == 1 else 'native'
            result['hardware_architecture'] = 'arm64' if translated.value == 1 else result['process_architecture']
        # Observe the actual native process image, not embedded Python's sys.executable.
        import ctypes, hashlib
        if platform.system() == 'Darwin':
            library = ctypes.CDLL(None)
            get_image = library._NSGetExecutablePath
            get_image.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
            get_image.restype = ctypes.c_int
            size = ctypes.c_uint32(0)
            get_image(None, ctypes.byref(size))
            if not 1 <= size.value <= 32768:
                raise RuntimeError('Invalid native executable path size')
            buffer = ctypes.create_string_buffer(size.value)
            if get_image(buffer, ctypes.byref(size)) != 0:
                raise RuntimeError('Cannot read actual native executable path')
            image = pathlib.Path(os.fsdecode(buffer.value)).resolve(strict=True)
        elif platform.system() == 'Windows':
            library = ctypes.WinDLL('kernel32', use_last_error=True)
            get_image = library.GetModuleFileNameW
            get_image.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32]
            get_image.restype = ctypes.c_uint32
            buffer = ctypes.create_unicode_buffer(32768)
            length = get_image(None, buffer, len(buffer))
            if not 0 < length < len(buffer):
                raise ctypes.WinError(ctypes.get_last_error())
            image = pathlib.Path(buffer.value).resolve(strict=True)
            library.GetCurrentProcess.restype = ctypes.c_void_p
            query = library.IsWow64Process2
            query.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ushort), ctypes.POINTER(ctypes.c_ushort)]
            query.restype = ctypes.c_int
            process_machine = ctypes.c_ushort()
            native_machine = ctypes.c_ushort()
            if not query(library.GetCurrentProcess(), ctypes.byref(process_machine), ctypes.byref(native_machine)):
                raise ctypes.WinError(ctypes.get_last_error())
            machines = {0x8664: 'x86_64', 0xaa64: 'arm64', 0x14c: 'x86'}
            result['process_architecture'] = machines.get(process_machine.value or native_machine.value, 'unsupported')
            result['hardware_architecture'] = machines.get(native_machine.value, 'unsupported')
            result['execution_mode'] = 'native' if process_machine.value == 0 else 'translated'
        else:
            image = pathlib.Path('/proc/self/exe').resolve(strict=True)
        qt_image = pathlib.Path(QApplication.instance().applicationFilePath()).resolve(strict=True)
        if image != qt_image:
            raise RuntimeError('Qt application file differs from actual native process image')
        with image.open('rb') as executable_file:
            image_sha = hashlib.file_digest(executable_file, 'sha256').hexdigest()
        result['process_id'] = os.getpid()
        result['process_image'] = {'path': str(image), 'sha256': image_sha,
                                   'bytes': image.stat().st_size,
                                   'qt_application_file_path': str(qt_image)}
        result['native_engine_version'] = Krita.instance().version()
        result['application_font'] = QFontInfo(QApplication.instance().font()).family()
        dialog = studio.dialogs[-1] if studio and studio.dialogs else None
        if dialog is not None:
            dialog.grab().save(str(out/'studio.png'))
            result['dialog_font'] = QFontInfo(dialog.font()).family()
            result['dialog_visible'] = dialog.isVisible()
            result['guided_control_labels_raw'] = [button.text() for button in dialog.findChildren(QPushButton) if button.isVisible()]
            # KDE adds Qt keyboard mnemonics when the registered menu action opens.
            # Compare visible labels, preserving escaped literal ampersands.
            result['guided_controls'] = [label.replace('&&', '\0').replace('&', '').replace('\0', '&') for label in result['guided_control_labels_raw']]
            assert result['dialog_font'] == 'Syne Mono', 'Guided dialog did not resolve Syne Mono'
            assert result['dialog_visible']
            for text in ('Start drawing','Open a drawing…','Export PNG picture…'):
                assert text in result['guided_controls'], 'Missing guided control: '+text
        else:
            raise AssertionError('No visible Flapart Studio dialog')
        role = QPalette.Window if hasattr(QPalette,'Window') else QPalette.ColorRole.Window
        result['window_palette'] = QApplication.instance().palette().color(role).name()
        result['theme_setting'] = Krita.instance().readSetting('theme','Theme','')
        if os.environ.get('FLAPART_QA_EXPECT_COMPILED') == '1':
            assert result['application_font'] == 'Syne Mono', 'Compiled app font differs'
            assert result['window_palette'] == '#1f2128', 'Compiled app default theme differs'
    except Exception:
        result['error'] = traceback.format_exc()
    result['lifecycle'] = {'method':'qt-event-loop-exit','cleanup_started':False,
                           'qa_documents_closed':False,'qt_exit_requested':False,
                           'about_to_quit':False}
    def write_result():
        (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    def about_to_quit():
        result['lifecycle']['about_to_quit'] = True
        write_result()
    QApplication.instance().aboutToQuit.connect(about_to_quit)
    def close_normally():
        # This plugin runs only in a disposable QA profile. Close the two
        # documents created above, retaining their wrappers through cleanup.
        retained = keepalive
        result['lifecycle']['cleanup_started'] = True
        try:
            for document in owned_documents:
                document.waitForDone()
                document.setModified(False)
                assert document.close(), 'QA document did not close'
            result['lifecycle']['qa_documents_closed'] = True
            for top in QApplication.topLevelWidgets():
                if top.isVisible():
                    top.close()
        except Exception:
            result['error'] = result.get('error','') + traceback.format_exc()
        result['lifecycle']['qt_exit_requested'] = True
        write_result()
        QApplication.instance().exit(1 if 'error' in result else 0)
    write_result()
    QTimer.singleShot(100,close_normally)
QTimer.singleShot(3500,run)
