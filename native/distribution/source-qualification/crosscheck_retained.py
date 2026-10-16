#!/usr/bin/env python3
"""Read-only parser comparison against LLVM on four retained SDK examples."""
import json,re,subprocess
from pathlib import Path
from native_metadata import parse
from qualify_sources import sha
root=Path(__file__).resolve().parents[2];out=Path(__file__).with_name('retained-crosscheck');out.mkdir(exist_ok=True)
files={'windows-qtnetwork':root/'qa/windows-build/audit-sdk-casefold/bin/Qt5Network.dll','windows-python':root/'qa/windows-build/audit-sdk-casefold/bin/python313.dll','macos-qtnetwork':root/'qa/macos-build/audit-sdk-casefold/lib/QtNetwork.framework/Versions/5/QtNetwork','macos-python':root/'qa/macos-build/audit-sdk-casefold/lib/Python.framework/Versions/3.13/Python'}
results=[]
for label,path in files.items():
 data=parse(path.read_bytes());command=['llvm-readobj','--file-header','--coff-imports',str(path)] if label.startswith('windows') else ['llvm-objdump','--macho','--private-headers','--arch=all',str(path)]
 text=subprocess.check_output(command,text=True);(out/(label+'.llvm.txt')).write_text(text)
 if label.startswith('windows'):
  imports=sorted(set(re.findall(r'^  Name: (.+)$',text,re.M)));architectures=sorted(set(re.findall(r'^Arch: (.+)$',text,re.M)));assert imports==data['native_dependencies'],(label,imports,data['native_dependencies']);assert architectures==data['architectures'];comparisons={'imports':True,'architectures':True,'delay_import_directory_present':bool(re.search(r'DelayImportTableRVA: 0x[1-9A-Fa-f]',text))}
 else:
  sections=re.split(r'^.* \(architecture (\w+)\):\n',text,flags=re.M);llvm=[]
  for i in range(1,len(sections),2):
   arch,body=sections[i:i+2];imports=[]
   for block in re.split(r'Load command \d+\n',body):
    if re.search(r'cmd LC_(?:LOAD_DYLIB|LOAD_WEAK_DYLIB|REEXPORT_DYLIB|LAZY_LOAD_DYLIB|LOAD_UPWARD_DYLIB)\b',block):imports.append(re.search(r'^\s+name (.+) \(offset \d+\)$',block,re.M).group(1))
   uuid=re.findall(r'^\s+uuid ([A-Fa-f0-9-]+)$',body,re.M);llvm.append({'architecture':arch,'dependencies':sorted(set(imports)),'uuid':uuid[0].lower() if uuid else None})
  ours=[{'architecture':s['architecture'],'dependencies':sorted(set(s['dependencies'])),'uuid':s['uuid']} for s in data['slices']];assert sorted(llvm,key=lambda x:x['architecture'])==sorted(ours,key=lambda x:x['architecture']),(label,llvm,ours);comparisons={'all_slice_imports':True,'all_slice_uuids':True,'architectures':True}
 results.append({'sample':label,'path':str(path.relative_to(root)),'sha256':sha(path),'parsed':data,'comparison':comparisons,'llvm_output_sha256':sha(out/(label+'.llvm.txt'))})
receipt={'scope':'read-only retained SDK binary parser comparison; no native execution or release qualification','passed':True,'llvm_version':subprocess.check_output(['llvm-readobj','--version'],text=True).splitlines()[0],'samples':results};(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'passed':True,'samples':len(results),'native_execution':False}))
