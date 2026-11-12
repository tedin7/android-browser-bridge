"""Entry point of android-browser-mcp.pyz (build.py copies it as __main__.py).

The package is extracted once per archive content into a private cache directory, so
Python reuses the compiled bytecode on later starts instead of recompiling every module
in a fresh temporary directory. If that directory cannot be used safely, the archive is
extracted into a temporary directory as before.
"""
import hashlib
import os
import runpy
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

CACHE_NAME = "android-browser-bridge"


def cache_base():
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / CACHE_NAME


def private_directory(path):
    info = path.lstat()
    return path.is_dir() and not path.is_symlink() and info.st_uid == os.geteuid() and not info.st_mode & 0o077


def cached_extraction(archive_path, base=None):
    """Return the private extraction of this archive, or None when it cannot be used safely."""
    try:
        with open(archive_path, "rb") as stream:
            digest = hashlib.sha256(stream.read()).hexdigest()[:32]
        base = Path(base) if base is not None else cache_base()
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not private_directory(base):
            return None
        directory = base / digest
        if not directory.exists():
            staging = tempfile.mkdtemp(prefix=".extract-", dir=base)
            try:
                with zipfile.ZipFile(archive_path) as archive:
                    archive.extractall(staging)
                os.rename(staging, directory)  # atomic: other starts see all files or none
            except OSError:
                if not directory.exists():
                    raise
            finally:
                shutil.rmtree(staging, ignore_errors=True)
        if not private_directory(directory) or not (directory / "launcher.py").is_file():
            return None
        return directory
    except (OSError, zipfile.BadZipFile):
        return None


def run(directory):
    sys.path.insert(0, str(directory))
    runpy.run_path(str(Path(directory) / "launcher.py"), run_name="__main__")


def main():
    directory = cached_extraction(sys.argv[0])
    if directory is not None:
        return run(directory)
    with tempfile.TemporaryDirectory(prefix="browser-bridge-") as fallback:
        with zipfile.ZipFile(sys.argv[0]) as archive:
            archive.extractall(fallback)
        run(fallback)


if __name__ == "__main__":
    main()
