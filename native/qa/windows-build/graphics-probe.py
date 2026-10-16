#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native ANGLE WARP shader/readback and OS D3D provenance gate."""
import argparse,ctypes as c,hashlib,json,os,pathlib,platform,sys,traceback,zipfile
p=argparse.ArgumentParser();p.add_argument('--runtime-root',type=pathlib.Path,required=True);p.add_argument('--archive',type=pathlib.Path);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--runtime-scope',choices=['relocated-package','installed-runtime']);p.add_argument('--sdk-diagnostic',action='store_true');p.add_argument('--additional-dll-dir',type=pathlib.Path);a=p.parse_args()
assert platform.system()=='Windows' and sys.getwindowsversion().major>=10
root=a.runtime_root.resolve();choices=[x for x in (root,root/'Flapart-Studio') if (x/'bin').is_dir() and (x/'python').is_dir()];assert len(choices)==1;prefix=choices[0]
assert a.sdk_diagnostic or (a.archive and a.runtime_scope and not a.additional_dll_dir),'Final mode needs archive, runtime scope and no external DLL directory'
assert pathlib.Path(sys.executable).resolve().is_relative_to(prefix/'python'),'Run with candidate embedded Python'
assert pathlib.Path(sys.base_prefix).resolve().is_relative_to(prefix),'Interpreter prefix outside candidate'
a.output.parent.mkdir(parents=True,exist_ok=True)
receipt={'schema_version':2,'target_platform':'windows-x86_64','process_architecture':{'amd64':'x86_64','x86_64':'x86_64'}.get(platform.machine().lower(),platform.machine().lower()),'platform':platform.platform(),'runtime_scope':a.runtime_scope or 'sdk-diagnostic','sdk_diagnostic':a.sdk_diagnostic,'archive_bound':not a.sdk_diagnostic,'release_qualified':False,'passed':False,'native_execution':True,'renderer_requested':'ANGLE D3D11 WARP','physical_gpu_tested':False,'modules':{}}
z=None
if not a.sdk_diagnostic:
 archive=a.archive.resolve();receipt['payload_sha256']=hashlib.sha256(archive.read_bytes()).hexdigest();z=zipfile.ZipFile(archive)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def candidate_file(path):
 path=path.resolve();assert path.is_relative_to(root),(str(path),'Outside candidate')
 rel=path.relative_to(root).as_posix();digest=sha(path)
 if z:
  info=z.getinfo(rel);assert info.file_size==path.stat().st_size and hashlib.sha256(z.read(info)).hexdigest()==digest,('Archive bytes differ',rel)
 return {'path':rel,'sha256':digest}
handles=[os.add_dll_directory(str(prefix/'bin')),os.add_dll_directory(str(prefix/'python'))]
if a.additional_dll_dir:handles.append(os.add_dll_directory(str(a.additional_dll_dir.resolve())))
os.environ['PATH']=str(prefix/'bin')+os.pathsep+str(pathlib.Path(os.environ['SystemRoot'])/'System32')+os.pathsep+os.environ['SystemRoot']
for key in ['QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH','PYTHONPATH','PYTHONHOME','QT_OPENGL','QT_ANGLE_PLATFORM','QT_D3DCOMPILER_DLL']:os.environ.pop(key,None)
os.environ.update(QT_PLUGIN_PATH=str(prefix/'plugins'),QT_OPENGL='angle',QT_ANGLE_PLATFORM='warp',QT_D3DCOMPILER_DLL='d3dcompiler_47.dll')
sys.path.insert(0,str(prefix/'lib/site-packages'))
k=c.WinDLL('kernel32',use_last_error=True);k.GetModuleHandleW.argtypes=[c.c_wchar_p];k.GetModuleHandleW.restype=c.c_void_p;k.GetModuleFileNameW.argtypes=[c.c_void_p,c.c_wchar_p,c.c_uint32]
def loaded(name):
 h=k.GetModuleHandleW(name);assert h,('Not loaded',name);buf=c.create_unicode_buffer(32768);assert k.GetModuleFileNameW(h,buf,len(buf));return pathlib.Path(buf.value).resolve()
try:
 receipt['interpreter']=candidate_file(pathlib.Path(sys.executable))
 # Preload only the operating system's compiler; never an application copy.
 compiler=c.WinDLL('d3dcompiler_47.dll',winmode=0x800)
 compiler_path=loaded('d3dcompiler_47.dll');assert compiler_path.parent.samefile(pathlib.Path(os.environ['SystemRoot'])/'System32')
 receipt['system_d3dcompiler']={'source':'Windows/System32','sha256':sha(compiler_path)}
 from PyQt5 import QtCore,QtGui
 app=QtGui.QGuiApplication([]);fmt=QtGui.QSurfaceFormat();fmt.setRenderableType(QtGui.QSurfaceFormat.OpenGLES);fmt.setVersion(2,0)
 surface=QtGui.QOffscreenSurface();surface.setFormat(fmt);surface.create();assert surface.isValid()
 context=QtGui.QOpenGLContext();context.setFormat(fmt);assert context.create() and context.makeCurrent(surface)
 assert context.isOpenGLES(), 'Requested ANGLE ES context was not created'
 gles_path=loaded('libGLESv2.dll');egl_path=loaded('libEGL.dll');receipt['modules']['libGLESv2']=candidate_file(gles_path);receipt['modules']['libEGL']=candidate_file(egl_path)
 gl=c.WinDLL(str(gles_path))
 def fn(name,result,args):
  f=getattr(gl,name);f.restype=result;f.argtypes=args;return f
 getstr=fn('glGetString',c.c_char_p,[c.c_uint]);renderer=getstr(0x1F01).decode();version=getstr(0x1F02).decode();receipt.update(renderer=renderer,gl_version=version)
 assert 'ANGLE' in renderer and ('Microsoft Basic Render Driver' in renderer or 'WARP' in renderer),('Not software ANGLE WARP',renderer)
 program=QtGui.QOpenGLShaderProgram();assert program.addShaderFromSourceCode(QtGui.QOpenGLShader.Vertex,'attribute vec2 position; void main(){gl_Position=vec4(position,0.0,1.0); }'),program.log()
 assert program.addShaderFromSourceCode(QtGui.QOpenGLShader.Fragment,'precision mediump float; void main(){gl_FragColor=vec4(1.0,0.0,0.0,1.0); }'),program.log()
 program.bindAttributeLocation('position',0);assert program.link() and program.bind(),program.log()
 fbo=QtGui.QOpenGLFramebufferObject(16,16);assert fbo.isValid() and fbo.bind()
 fn('glViewport',None,[c.c_int]*4)(0,0,16,16)
 fn('glClearColor',None,[c.c_float]*4)(0,0,0,1);fn('glClear',None,[c.c_uint])(0x4000)
 buffer=c.c_uint();fn('glGenBuffers',None,[c.c_int,c.POINTER(c.c_uint)])(1,c.byref(buffer));fn('glBindBuffer',None,[c.c_uint,c.c_uint])(0x8892,buffer.value)
 vertices=(c.c_float*6)(-1,-1,3,-1,-1,3);fn('glBufferData',None,[c.c_uint,c.c_ssize_t,c.c_void_p,c.c_uint])(0x8892,c.sizeof(vertices),vertices,0x88E4)
 fn('glEnableVertexAttribArray',None,[c.c_uint])(0);fn('glVertexAttribPointer',None,[c.c_uint,c.c_int,c.c_uint,c.c_ubyte,c.c_int,c.c_void_p])(0,2,0x1406,0,0,None)
 fn('glDrawArrays',None,[c.c_uint,c.c_int,c.c_int])(0x0004,0,3)
 pixel=(c.c_ubyte*4)();fn('glReadPixels',None,[c.c_int]*4+[c.c_uint,c.c_uint,c.c_void_p])(8,8,1,1,0x1908,0x1401,pixel)
 receipt['readback_rgba']=list(pixel);assert list(pixel)==[255,0,0,255]
 assert fn('glGetError',c.c_uint,[])()==0
 assert loaded('d3dcompiler_47.dll')==compiler_path
 for name in ('Qt5Core.dll','Qt5Gui.dll','python313.dll'):receipt['modules'][name]=candidate_file(loaded(name))
 receipt['modules']['PyQt5.QtGui']=candidate_file(pathlib.Path(QtGui.__file__))
 receipt['modules']['PyQt5.QtCore']=candidate_file(pathlib.Path(QtCore.__file__))
 receipt.update(passed=True,shader_compiled=True,shader_linked=True,triangle_rendered=True,system_d3dcompiler_origin_verified=True)
except Exception as error:receipt.update(error=repr(error),traceback=traceback.format_exc())
finally:
 if z:z.close()
 a.output.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if not receipt['passed']:raise SystemExit(1)
