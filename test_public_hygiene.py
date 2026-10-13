"""The repository is public: tracked files must not carry infrastructure or secrets.

Checks every tracked text file for public IPv4 addresses, personal email
addresses, private keys and Browser Bridge credentials. Host, device and
person names are private too, so they are not listed here: put one per line
in an untracked `.private-names` file (or BROWSER_BRIDGE_PRIVATE_NAMES,
comma-separated) and this test rejects them as well.
"""
import ipaddress
import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BINARY = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".xpi", ".zip", ".pyz", ".apk", ".jar", ".keystore", ".p12", ".woff", ".woff2"}
SKIP_DIRS = ("signed-artifacts/",)
ALLOWED_EMAIL_DOMAINS = ("example.com", "example.org", "example.net", "anthropic.com", "users.noreply.github.com")
RESERVED_TLDS = (".invalid", ".example", ".test", ".localhost")  # RFC 2606: never real mailboxes
IPV4 = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?![\w.])")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
SECRETS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"abb_client_[A-Za-z0-9_-]{16,}"),
    re.compile(r"BB1\.[A-Za-z0-9_-]{40,}"),
]


def tracked_files():
    names = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.decode().split("\0")
    for name in filter(None, names):
        path = ROOT / name
        if name.startswith(SKIP_DIRS) or path.suffix.lower() in BINARY or not path.is_file():
            continue
        try:
            yield name, path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue


def private_names():
    names = [n.strip() for n in os.environ.get("BROWSER_BRIDGE_PRIVATE_NAMES", "").split(",")]
    local = ROOT / ".private-names"
    if local.is_file():
        names += [line.strip() for line in local.read_text().splitlines() if line.strip() and not line.startswith("#")]
    return [n for n in names if n]


def public_ip(text):
    try:
        address = ipaddress.IPv4Address(text)
    except ValueError:
        return False  # version numbers such as 1.0.300.2
    return address.is_global


class PublicHygieneTest(unittest.TestCase):
    def test_no_public_addresses_emails_or_secrets(self):
        problems = []
        for name, text in tracked_files():
            for number, line in enumerate(text.splitlines(), 1):
                for match in IPV4.finditer(line):
                    if public_ip(match.group(1)):
                        problems.append(f"{name}:{number}: public IPv4 address")
                for match in EMAIL.finditer(line):
                    domain = match.group(1).lower()
                    if not domain.endswith(RESERVED_TLDS) and not any(domain == allowed or domain.endswith("." + allowed) for allowed in ALLOWED_EMAIL_DOMAINS):
                        problems.append(f"{name}:{number}: email address")
                if any(pattern.search(line) for pattern in SECRETS):
                    problems.append(f"{name}:{number}: key or credential")
        self.assertEqual(problems, [])

    def test_no_private_names(self):
        names = private_names()
        if not names:
            self.skipTest("no .private-names file or BROWSER_BRIDGE_PRIVATE_NAMES")
        pattern = re.compile("|".join(re.escape(n) for n in names), re.IGNORECASE)
        problems = [f"{name}:{number}: private name"
                    for name, text in tracked_files()
                    for number, line in enumerate(text.splitlines(), 1) if pattern.search(line)]
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
