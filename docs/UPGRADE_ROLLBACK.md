# Upgrade and package rollback

Run the usual installer from the new checkout. Before replacing the installed
MCP zipapp it validates archive checksums and required entrypoints, then saves
the previous package under the same package lock. Backups are private files:

```text
~/.local/share/android-browser-bridge/android-browser-mcp.pyz.bak-YYYYMMDDTHHMMSSZ-HEX
```

To restore an existing backup, supply its exact path:

```sh
python3 install.py --rollback-package "$HOME/.local/share/android-browser-bridge/android-browser-mcp.pyz.bak-TIMESTAMP-SUFFIX"
```

Use an actual filename created by this installer. The rollback accepts only
regular, non-symlink package backups in the standard package directory, validates
them, backs up the current package and atomically restores the selected bytes.
It does not start a build, access credentials, alter Codex/Claude settings, or
restart broker/client processes. Do not combine this flag with registration or
installation flags. Reopen the intended client session separately to load the
restored package.

This command rolls back package code only. It does not downgrade the Firefox
extension, revert data/schema migrations, restore configuration, or guarantee
compatibility with a broker or extension from another release. Keep matching
release assets and consult their compatibility notes before downgrading.
Archive checks establish package structure and integrity, not publisher signing.
Backups remain until the user removes them; they are never silently overwritten.

Validation: `python3 -m unittest -q test_install_rollback`.
