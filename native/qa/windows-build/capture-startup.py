#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Capture only a test process's visible windows on disposable Windows CI."""
import argparse,ctypes,ctypes.wintypes as w,json,pathlib,os,platform
p=argparse.ArgumentParser();p.add_argument('--pid',type=int,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
assert platform.system()=='Windows' and os.environ.get('CI')=='true'
a.output.mkdir(parents=True,exist_ok=True);u=ctypes.WinDLL('user32',use_last_error=True);callback=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
u.GetWindowTextLengthW.argtypes=[w.HWND];u.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int];u.GetClassNameW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int];u.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)];u.IsWindowVisible.argtypes=[w.HWND];u.EnumWindows.argtypes=[callback,w.LPARAM];u.EnumChildWindows.argtypes=[w.HWND,callback,w.LPARAM]
def label(hwnd):
 text=ctypes.create_unicode_buffer(max(1,u.GetWindowTextLengthW(hwnd)+1));u.GetWindowTextW(hwnd,text,len(text));kind=ctypes.create_unicode_buffer(256);u.GetClassNameW(hwnd,kind,len(kind));return {'text':text.value,'class':kind.value}
windows=[]
@callback
def visit(hwnd,_):
 pid=w.DWORD();u.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
 if pid.value!=a.pid or not u.IsWindowVisible(hwnd):return True
 row=label(hwnd);row['children']=[]
 @callback
 def child(h,_):
  item=label(h)
  if item['text']:row['children'].append(item)
  return True
 u.EnumChildWindows(hwnd,child,0);windows.append(row);return True
u.EnumWindows(visit,0);(a.output/'startup-windows.json').write_text(json.dumps({'process_id':a.pid,'windows':windows},indent=2)+'\n')
