"""API/syntax check with official .NETFramework refs. Not a native Windows test."""
from pathlib import Path
import tempfile,urllib.request,zipfile,subprocess,hashlib,json
root=Path(__file__).parent
url='https://api.nuget.org/v3-flatcontainer/microsoft.netframework.referenceassemblies.net48/1.0.3/microsoft.netframework.referenceassemblies.net48.1.0.3.nupkg'
with tempfile.TemporaryDirectory(prefix='flapart-installer-refs-') as temp:
 temp=Path(temp);package=temp/'refs.zip'
 with urllib.request.urlopen(url,timeout=60) as source,package.open('wb') as out:
  while chunk:=source.read(1048576):out.write(chunk)
 with zipfile.ZipFile(package) as z:z.extractall(temp/'refs')
 refs=temp/'refs/build/.NETFramework/v4.8';names=['mscorlib','System','System.Core','System.Windows.Forms','System.Drawing','System.Web.Extensions','System.IO.Compression']
 sdks=subprocess.check_output(['dotnet','--list-sdks'],text=True).splitlines();version=sdks[-1].split()[0];base=Path(sdks[-1].split('[',1)[1].rstrip(']'));compiler=base/version/'Roslyn/bincore/csc.dll'
 command=['dotnet',str(compiler),'-nologo','-noconfig','-nostdlib','-target:winexe','-platform:anycpu','-optimize+','-out:'+str(root/'Install Flapart.exe')]+['-reference:'+str(refs/(n+'.dll')) for n in names]+[str(root/'FlapartInstaller.cs')]
 subprocess.run(command,check=True)
 (root/'compile-result.json').write_text(json.dumps({'compiled':True,'target':'.NET Framework4.8 Windows GUI executable','compiler':'Roslyn from .NETSDK'+version+' on Linux','native_execution':False,'reference_package_url':url,'reference_package_sha256':hashlib.sha256(package.read_bytes()).hexdigest(),'source_sha256':hashlib.sha256((root/'FlapartInstaller.cs').read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256((root/'Install Flapart.exe').read_bytes()).hexdigest()},indent=2)+'\n')
 print('Windows GUI installer cross-compiled. Native execution is a separate gate.')
