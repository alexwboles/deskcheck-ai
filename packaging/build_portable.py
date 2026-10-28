"""Reproducible local portable build. No publishing, installs, signing or paid APIs."""
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

root = Path(__file__).resolve().parents[1]
output = root/".qa-output"/("portable-v0.2.0-"+uuid.uuid4().hex[:8])
if output.exists():
    raise SystemExit("Build output already exists; choose a new version instead of overwriting")
output.mkdir(parents=True)
subprocess.run([sys.executable,"-m","PyInstaller","--clean","--noconfirm",
    "--name","DeskCheck","--onedir","--console","--paths",str(root),
    "--add-data",str(root/"deskcheck"/"assets")+os.pathsep+"deskcheck/assets",
    "--distpath",str(output),"--workpath",str(output/"build"),
    "--specpath",str(output),str(root/"packaging"/"entry.py")],cwd=root,check=True)
app = output/"DeskCheck"
compiler = Path("C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe")
subprocess.run([str(compiler),"/nologo","/target:winexe","/reference:System.Windows.Forms.dll",
    "/out:"+str(app/"DeskCheck Desktop.exe"),str(root/"packaging"/"DesktopLauncher.cs")],check=True)
subprocess.run([str(compiler),"/nologo","/target:winexe","/reference:System.Windows.Forms.dll",
    "/reference:System.Drawing.dll","/reference:System.Web.Extensions.dll",
    "/out:"+str(app/"DeskCheckSample.exe"),str(root/"test"/"Fixture.cs")],check=True)
for name in ("LICENSE","README.md"):
    shutil.copy2(root/name,app/name)
shutil.copytree(root/"examples",app/"examples",ignore=shutil.ignore_patterns("runs","baselines"))
shutil.copytree(root/"docs",app/"docs")
notices = app/"THIRD-PARTY-LICENSES"
notices.mkdir()
for package in ("pyinstaller","PyYAML","Pillow"):
    dist = metadata.distribution(package)
    for file in dist.files or []:
        if "license" in str(file).lower() or "copying" in str(file).lower():
            source = dist.locate_file(file)
            if source.is_file():
                shutil.copy2(source,notices/(package+"-"+source.name))
    (notices/(package+"-METADATA.txt")).write_text(dist.read_text("METADATA") or package,encoding="utf-8")
# The runtime carries Python/Tcl/Tk license texts; preserve them explicitly.
for path in Path(sys.base_prefix).rglob("LICENSE*"):
    if path.is_file() and "site-packages" not in str(path) and path.stat().st_size < 200000:
        shutil.copy2(path,notices/("runtime-"+"-".join(path.relative_to(sys.base_prefix).parts)))
print(json.dumps({"status":"built","app":str(app),"unsigned":True}))
