#!/usr/bin/env python3
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import tempfile
import shutil
import zipapp

root = Path(__file__).resolve().parent
with ZipFile(root / "android-browser-bridge.xpi", "w", ZIP_DEFLATED) as archive:
    for file in sorted((root / "extension").iterdir()):
        if file.is_file():
            archive.write(file, file.name)
print(root / "android-browser-bridge.xpi")
with tempfile.TemporaryDirectory() as directory:
    staging = Path(directory)
    for name in ("bridge.py", "mcp_server.py", "mcp_guidance.py", "browser_navigation.py", "command_order.py", "launcher.py", "connection.py", "install.html", "android-browser-bridge.xpi"):
        shutil.copy2(root / name, staging / name)
    (staging / "__main__.py").write_text('''import sys, tempfile, zipfile, runpy
from pathlib import Path
with tempfile.TemporaryDirectory(prefix="browser-bridge-") as directory:
    with zipfile.ZipFile(sys.argv[0]) as archive:
        archive.extractall(directory)
    sys.path.insert(0, directory)
    runpy.run_path(str(Path(directory) / "launcher.py"), run_name="__main__")
''')
    zipapp.create_archive(staging, root / "android-browser-mcp.pyz", interpreter="/usr/bin/env python3", compressed=True)
print(root / "android-browser-mcp.pyz")
with ZipFile(root / "android-browser-bridge-bundle.zip", "w", ZIP_DEFLATED) as archive:
    names = ["AGENTS.md", "README.md", "LICENSE", "PRIVACY.md", "RELEASE_NOTES.md", "bridge.py", "mcp_server.py", "mcp_guidance.py", "browser_navigation.py", "command_order.py", "launcher.py", "connection.py", "install.py", "agent_integration.py", "build.py", "test_bridge.py", "test_navigation.py", "test_attach.py", "test_setup.py", "test_extension.js", "test_firefox.py", "profile_android.py", "profile_client.py", "test_page.html", "smoke_mcp.py", "install.html", "android-browser-bridge.xpi", "android-browser-mcp.pyz"]
    if (root / "interaction_suite.py").exists(): names.append("interaction_suite.py")
    for optional in ("test_multiserver.js", "test_multiserver_firefox.py", "test_options.js"):
        if (root / optional).exists(): names.append(optional)
    for name in names:
        archive.write(root / name, name)
    for directory in ("extension", "docs", "agent-skills"):
        for file in sorted((root / directory).rglob("*")):
            if file.is_file():
                archive.write(file, file.relative_to(root))
print(root / "android-browser-bridge-bundle.zip")
