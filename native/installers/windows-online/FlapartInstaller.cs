// SPDX-License-Identifier: GPL-3.0-or-later
// Compile on Windows CI with .NET Framework csc; no PowerShell required on user PCs.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Text;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

static class FlapartInstaller {
    static readonly JavaScriptSerializer Json = new JavaScriptSerializer();
    static readonly string Source = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
    static string Text(Dictionary<string,object> data,string key) { object value; if (!data.TryGetValue(key,out value) || !(value is string)) throw new Exception("Invalid release field: "+key); return (string)value; }
    static Dictionary<string,object> Read(string path) { return Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(path)); }
    static string Hash(string path) { using(var stream=File.OpenRead(path)) using(var sha=SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-","").ToLowerInvariant(); }
    static void Check(bool condition,string message) { if(!condition)throw new Exception(message); }
    static bool Match(string value,string expression) { return System.Text.RegularExpressions.Regex.IsMatch(value,expression); }
    static void Relative(string name) {
        Check(!String.IsNullOrEmpty(name) && !name.StartsWith("/") && name.IndexOfAny(new[]{'\\',':'})<0 && !Match(name,@"[\x00-\x1f]"),"Unsafe archive filename.");
        foreach(var part in name.TrimEnd('/').Split('/'))Check(part.Length>0 && part!="." && part!=".." && !part.EndsWith(".") && !part.EndsWith(" ") && !Match(part,@"^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)"),"Nonportable archive filename.");
    }
    static void NoLinks(string path) { for(var current=Path.GetFullPath(path); !String.IsNullOrEmpty(current); current=Path.GetDirectoryName(current))if(Directory.Exists(current)||File.Exists(current))Check((File.GetAttributes(current)&FileAttributes.ReparsePoint)==0,"Choose an installation folder without links or redirects."); }
    static Dictionary<string,object> Release() {
        var data=Read(Path.Combine(Source,"release.json"));
        Check(Text(data,"status")=="qualified" && Text(data,"kind")=="namespaced-compiled-fork" && Text(data,"platform")=="windows-x86_64" && Text(data,"profileNamespace")=="flapart-native","This installer candidate has no qualified independent Windows runtime yet. Nothing was installed.");
        Check(Match(Text(data,"version"),@"^[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?$")&&Match(Text(data,"sha256"),@"^[a-f0-9]{64}$"),"Invalid release pin.");
        var uri=new Uri(Text(data,"url"));Check(uri.Scheme=="https" && uri.Host=="accounts.flaptown.com" && Match(uri.AbsolutePath,@"^/flapsoft/downloads/[A-Za-z0-9][A-Za-z0-9._-]{0,150}$") && uri.Query=="" && uri.Fragment=="","Invalid download location.");
        Relative(Text(data,"executable"));Check(Text(data,"executable").EndsWith("/krita.exe"),"Native executable pin missing.");return data;
    }
    static void Download(string url,string target,Action<string> progress) {
        ServicePointManager.SecurityProtocol=SecurityProtocolType.Tls12;
        var request=(HttpWebRequest)WebRequest.Create(url);request.AllowAutoRedirect=false;request.Timeout=120000;request.ReadWriteTimeout=120000;
        using(var response=(HttpWebResponse)request.GetResponse()) {
            Check(response.StatusCode==HttpStatusCode.OK && response.ContentLength<=4L*1024*1024*1024,"Unexpected download response.");
            using(var input=response.GetResponseStream())using(var output=File.Create(target)) {
                var buffer=new byte[1024*1024];long total=0;int count;
                while((count=input.Read(buffer,0,buffer.Length))>0){total+=count;Check(total<=4L*1024*1024*1024,"Download exceeds size limit.");output.Write(buffer,0,count);progress("Downloading… "+total/(1024*1024)+" MiB");}
            }
        }
    }
    static void Extract(string archive,string output) {
        Directory.CreateDirectory(output);
        using(var archiveStream=File.OpenRead(archive)) using(var zip=new ZipArchive(archiveStream,ZipArchiveMode.Read,false)) {
            Check(zip.Entries.Count<=100000,"Too many archive entries.");var seen=new HashSet<string>(StringComparer.OrdinalIgnoreCase);long bytes=0;
            foreach(var entry in zip.Entries) {
                Relative(entry.FullName);Check(seen.Add(entry.FullName.TrimEnd('/')),"Duplicate archive path.");
                Check(((entry.ExternalAttributes>>16)&0xF000)!=0xA000,"Archive links are not accepted.");bytes+=entry.Length;Check(bytes<=8L*1024*1024*1024,"Expanded runtime exceeds size limit.");
            }
            foreach(var entry in zip.Entries) {
                string path=Path.GetFullPath(Path.Combine(output,entry.FullName));Check(path.StartsWith(Path.GetFullPath(output)+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase),"Archive path escapes installation.");
                if(entry.FullName.EndsWith("/"))Directory.CreateDirectory(path);else{Directory.CreateDirectory(Path.GetDirectoryName(path));using(var input=entry.Open())using(var outputFile=new FileStream(path,FileMode.CreateNew)){input.CopyTo(outputFile);}}
            }
        }
    }
    static string ReadZone(string path) { try { return File.ReadAllText(path+":Zone.Identifier"); } catch(IOException) { return null; } }
    static void WriteJson(string path,Dictionary<string,object> data) { File.WriteAllText(path,Json.Serialize(data),new UTF8Encoding(false)); }
    static void Install(string destination,string archiveInput,bool shortcut,Action<string> progress) {
        Check(Environment.Is64BitOperatingSystem,"This package needs 64-bit Windows.");var release=Release();destination=Path.GetFullPath(destination);NoLinks(destination);
        string marker=Path.Combine(destination,"flapart-install.json");
        if(Directory.Exists(destination))Check(File.Exists(marker)&&Text(Read(marker),"product")=="Flapart Studio","That folder is not a recognized Flapart installation. Choose a new folder.");
        Directory.CreateDirectory(destination);
        using(var locked=new FileStream(Path.Combine(destination,".install-lock"),FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None)) {
            if(!File.Exists(marker))WriteJson(marker,new Dictionary<string,object>{{"product","Flapart Studio"},{"status","not yet installed"}});
            string stage=Path.Combine(destination,".staging-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(stage);
            try {
                string archive=Path.Combine(stage,"runtime.zip");if(archiveInput!=null){Check(new FileInfo(archiveInput).Length<=4L*1024*1024*1024,"Archive is too large.");File.Copy(archiveInput,archive);}else Download(Text(release,"url"),archive,progress);
                progress("Checking your download…");Check(Hash(archive)==Text(release,"sha256"),"Download checksum failed. Your current installation was not changed.");
                string payload=Path.Combine(stage,"payload");progress("Preparing your studio…");Extract(archive,payload);string executable=Text(release,"executable");Check(File.Exists(Path.Combine(payload,executable)),"Native executable is missing.");
                string releaseId=Text(release,"version")+"-"+Text(release,"sha256").Substring(0,12);string releases=Path.Combine(destination,"releases");Directory.CreateDirectory(releases);string final=Path.Combine(releases,releaseId);Check(!Directory.Exists(final),"This release is already installed. Use your existing Flapart shortcut.");
                // Use a per-release launcher so updates never overwrite a running executable.
                File.Copy(Assembly.GetExecutingAssembly().Location,Path.Combine(payload,"Flapart Studio.exe"));
                string font=Path.Combine(Source,"SyneMono-Regular.ttf");if(File.Exists(font))File.Copy(font,Path.Combine(payload,"SyneMono-Regular.ttf"));
                // Mark the downloaded engine for standard Windows user review. No SmartScreen override.
                string zone=Path.Combine(payload,executable)+":Zone.Identifier";
                if(ReadZone(Path.Combine(payload,executable))==null) {
                    if(archiveInput==null)File.WriteAllText(zone,"[ZoneTransfer]\r\nZoneId=3\r\nHostUrl="+Text(release,"url")+"\r\n");
                    else { string archiveZone=ReadZone(archiveInput);if(archiveZone!=null)File.WriteAllText(zone,archiveZone); }
                }
                Directory.Move(payload,final);
                var record=new Dictionary<string,object>{{"product","Flapart Studio"},{"version",Text(release,"version")},{"release",releaseId},{"executable",executable},{"sha256",Text(release,"sha256")},{"profileNamespace","flapart-native"}};
                string pending=Path.Combine(stage,"receipt.json");WriteJson(pending,record);
                // Launcher reads the parent receipt; prior launchers remain compatible and intact.
                if(File.Exists(marker))File.Replace(pending,marker,Path.Combine(destination,"flapart-install.previous.json"));else File.Move(pending,marker);
                if(shortcut)Shortcut(Path.Combine(final,"Flapart Studio.exe"),destination,Path.Combine(final,executable));
                progress("Installed. Open Flapart Studio from Start. Drawing and export work offline.");
            } finally { if(Directory.Exists(stage))Directory.Delete(stage,true); }
        }
    }
    static void Shortcut(string launcher,string root,string icon) {
        Type type=Type.GetTypeFromProgID("WScript.Shell");object shell=Activator.CreateInstance(type);object link=type.InvokeMember("CreateShortcut",BindingFlags.InvokeMethod,null,shell,new object[]{Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs),"Flapart Studio.lnk")});
        Type lt=link.GetType();lt.InvokeMember("TargetPath",BindingFlags.SetProperty,null,link,new object[]{launcher});lt.InvokeMember("Arguments",BindingFlags.SetProperty,null,link,new object[]{"--launch"});lt.InvokeMember("WorkingDirectory",BindingFlags.SetProperty,null,link,new object[]{root});lt.InvokeMember("IconLocation",BindingFlags.SetProperty,null,link,new object[]{icon+",0"});lt.InvokeMember("Save",BindingFlags.InvokeMethod,null,link,null);
    }
    static void Launch(bool wait) {
        string root=Path.GetFullPath(Path.Combine(Source,"..",".."));var record=Read(Path.Combine(root,"flapart-install.json"));Check(Text(record,"product")=="Flapart Studio"&&Text(record,"profileNamespace")=="flapart-native"&&Match(Text(record,"release"),@"^[A-Za-z0-9.-]+$")&&!Text(record,"release").Contains(".."),"Installation record is invalid.");Relative(Text(record,"executable"));
        string exe=Path.Combine(root,"releases",Text(record,"release"),Text(record,"executable"));Check(File.Exists(exe),"The native runtime is missing. Reinstall from Flapsoft.");Environment.SetEnvironmentVariable("FLAPART_NATIVE","1");var process=Process.Start(new ProcessStartInfo(exe){UseShellExecute=true,WorkingDirectory=Path.GetDirectoryName(exe)});if(wait){Check(process!=null,"No native process started; review any Windows security prompt yourself.");if(!process.WaitForExit(180000)){process.Kill();throw new Exception("Native test did not finish; no security approval was automated.");}Check(process.ExitCode==0,"Native application reported an error.");}
    }
    static string Option(string[] args,string name) { for(int i=0;i<args.Length;i++)if(args[i]==name){Check(i+1<args.Length,"Missing value for "+name);return args[i+1];}return null; }
    static bool Has(string[] args,string flag) { return Array.IndexOf(args,flag)>=0; }
    [STAThread] static int Main(string[] args) {
        Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
        try {
            if(Has(args,"--launch") || !File.Exists(Path.Combine(Source,"release.json"))){Launch(Has(args,"--wait"));return 0;}
            string destination=Option(args,"--destination")??Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Programs","FlapartStudio");
            if(Has(args,"--quiet")){Install(destination,Option(args,"--archive"),!Has(args,"--no-shortcut"),delegate(string s){Console.WriteLine(s);});return 0;}
            ShowInstaller(destination);return 0;
        } catch(Exception error){if(Has(args,"--quiet"))Console.Error.WriteLine(error.Message);else MessageBox.Show(error.Message,"Flapart Studio",MessageBoxButtons.OK,MessageBoxIcon.Information);return 1;}
    }
    static void ShowInstaller(string destination) {
        var form=new Form{Text="Flapart Studio · setup",Width=650,Height=410,StartPosition=FormStartPosition.CenterScreen,BackColor=Color.FromArgb(31,33,40),ForeColor=Color.FromArgb(222,214,206),FormBorderStyle=FormBorderStyle.FixedDialog,MaximizeBox=false};
        var fonts=new PrivateFontCollection();string fontPath=Path.Combine(Source,"SyneMono-Regular.ttf");if(File.Exists(fontPath))fonts.AddFontFile(fontPath);form.Font=fonts.Families.Length>0?new Font(fonts.Families[0],10):new Font("Segoe UI",10);
        var title=new Label{Text="Your own art studio.",Left=28,Top=26,Width=570,Height=36,Font=new Font(form.Font.FontFamily,20)};
        var intro=new Label{Text="Full native painting with a simpler starting point.\nYour Krita settings and creations stay separate.\nInternet is needed for setup; painting works offline afterwards.",Left=28,Top=77,Width=580,Height=78};
        var path=new TextBox{Text=destination,Left=28,Top=177,Width=460};var browse=new Button{Text="folder…",Left=500,Top=174,Width=104,Height=33};
        var status=new Label{Text="No administrator password. No account required.",Left=28,Top=224,Width=575,Height=65};
        var install=new Button{Text="install Flapart",Left=28,Top=300,Width=210,Height=44,BackColor=Color.FromArgb(191,139,111),ForeColor=Color.FromArgb(31,33,40),FlatStyle=FlatStyle.Flat};
        var cancel=new Button{Text="close",Left=480,Top=300,Width=124,Height=44};bool busy=false;
        browse.Click+=delegate{using(var chooser=new FolderBrowserDialog{Description="Choose a new Flapart application folder",SelectedPath=path.Text})if(chooser.ShowDialog()==DialogResult.OK)path.Text=Path.Combine(chooser.SelectedPath,"FlapartStudio");};
        cancel.Click+=delegate{form.Close();};form.FormClosing+=delegate(object sender,FormClosingEventArgs e){if(busy)e.Cancel=true;};
        install.Click+=async delegate{busy=true;install.Enabled=false;browse.Enabled=false;path.Enabled=false;cancel.Enabled=false;string selected=path.Text;try{await Task.Run(delegate{Install(selected,null,true,delegate(string message){form.BeginInvoke((Action)delegate{status.Text=message;});});});install.Text="installed";}catch(Exception error){status.Text=error.Message;install.Enabled=true;}finally{busy=false;browse.Enabled=true;path.Enabled=true;cancel.Enabled=true;}};
        form.Controls.AddRange(new Control[]{title,intro,path,browse,status,install,cancel});Application.Run(form);fonts.Dispose();
    }
}
