"""Package upgrade/rollback never changes connection or agent configuration."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
import install


def package(path, version):
    with ZipFile(path, 'w') as archive:
        for name in install.PACKAGE_MEMBERS:
            archive.writestr(name, '# fixture version '+version+'\n')


class PackageRollbackTests(unittest.TestCase):
    def test_upgrade_private_backup_and_rollback_preserve_configuration(self):
        with tempfile.TemporaryDirectory() as temporary, patch('install.Path.home', return_value=Path(temporary)):
            home = Path(temporary)
            root = home/'checkout';root.mkdir()
            destination = home/'.local/share/android-browser-bridge';destination.mkdir(parents=True)
            target = destination/install.PACKAGE_NAME
            package(target, 'old');original = target.read_bytes()
            package(root/install.PACKAGE_NAME, 'new');updated = (root/install.PACKAGE_NAME).read_bytes()
            state = home/'.local/state/android-browser-bridge';state.mkdir(parents=True)
            credential = state/'connection.json';credential.write_text('private-fixture-state')
            config = destination/'mcp-config.json';config.write_text('unrelated-config')
            with patch('install.subprocess.run'):
                install._install_package(root, destination)
            self.assertEqual(target.read_bytes(), updated)
            backups = list(destination.glob(install.PACKAGE_NAME+'.bak-*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)
            self.assertEqual(backups[0].stat().st_mode&0o777, 0o600)
            with patch('install._codex_executable', side_effect=AssertionError('No registration')), patch('install.ensure_persistent_broker', side_effect=AssertionError('No broker restart')), patch('install.discover_connection_profile', side_effect=AssertionError('No credential access')), patch('sys.argv', ['install.py','--rollback-package',str(backups[0])]), contextlib.redirect_stdout(io.StringIO()):
                install.main()
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(len(list(destination.glob(install.PACKAGE_NAME+'.bak-*'))), 2)
            self.assertEqual(credential.read_text(), 'private-fixture-state')
            self.assertEqual(config.read_text(), 'unrelated-config')
            self.assertEqual(sorted(path.name for path in state.iterdir()), ['connection.json'])

    def test_invalid_new_package_cannot_replace_current(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)/'root';root.mkdir()
            destination = Path(temporary)/'install';destination.mkdir()
            target = destination/install.PACKAGE_NAME;package(target,'current');before = target.read_bytes()
            with ZipFile(root/install.PACKAGE_NAME,'w') as archive:
                archive.writestr('__main__.py','incomplete fixture')
            with patch('install.subprocess.run'), self.assertRaises(ValueError):
                install._install_package(root,destination)
            self.assertEqual(target.read_bytes(), before)
            self.assertEqual(list(destination.glob('*.bak-*')), [])

    def test_rollback_rejects_symlink_wrong_directory_and_invalid_archive(self):
        with tempfile.TemporaryDirectory() as temporary, patch('install.Path.home', return_value=Path(temporary)):
            home = Path(temporary);destination=home/'.local/share/android-browser-bridge';destination.mkdir(parents=True)
            target=destination/install.PACKAGE_NAME;package(target,'current');before=target.read_bytes()
            name=install.PACKAGE_NAME+'.bak-20261012T120000Z-'+'a'*16
            backup=destination/name;backup.write_text('not a zip')
            with self.assertRaises(ValueError):install.rollback_package(backup)
            self.assertEqual(target.read_bytes(),before)
            backup.unlink();backup.symlink_to(target)
            with self.assertRaises(ValueError):install.rollback_package(backup)
            self.assertEqual(target.read_bytes(),before)
            outside=home/name;package(outside,'other')
            with self.assertRaises(ValueError):install.rollback_package(outside)
            self.assertEqual(target.read_bytes(),before)


if __name__ == '__main__':
    unittest.main()
