import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import os
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('manager', Path(__file__).with_name('manage.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class SetupTests(unittest.TestCase):
    def test_device_selection(self):
        tree = {'blockdevices': [
            {'name': '/dev/nvme0n1', 'children': [
                dict(name='/dev/nvme1n1p1', type='part', fstype='btrfs', label='rootfs', uuid='root', mountpoints=[None]),
                dict(name='/dev/nvme1n1p2', type='part', fstype='ntfs', label='data', uuid='DATA-1', mountpoints=[None])]},
            {'name': '/dev/sda', 'tran': 'usb', 'children': [dict(name='/dev/sda1', type='part', fstype='ext4', label='backup', uuid='USB-1', mountpoints=[None])]}]}
        with patch.object(m, 'run', return_value=SimpleNamespace(stdout=json.dumps(tree))):
            found = m.disks()
        self.assertEqual([(d['uuid'], d['external']) for d in found], [('DATA-1', False), ('USB-1', True)])
        self.assertNotIn('nvme1n1p2', m.rules(['DATA-1']))
        with self.assertRaises(ValueError):
            m.rules(['bad"uuid'])

    def test_worker_rejects_unselected_internal_partition(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            worker = root/'automount.sh'
            shutil.copyfile(Path(__file__).with_name('automount.sh'), worker)
            (root/'config.json').write_text(json.dumps({'internal_uuids': ['SHARE']}))
            for name, output in [('lsblk', 'UNSELECTED'), ('udevadm', 'ID_BUS=nvme')]:
                command = root/name
                command.write_text('#!/bin/sh\nprintf "%s\\n" "' + output + '"\n')
                command.chmod(0o755)
            env = dict(os.environ, PATH=str(root)+':'+os.environ['PATH'], TARGET_USER='tester', TARGET_UID='1234', TARGET_GID='1234')
            for action in ['add', 'retrigger']:
                result = subprocess.run(['bash', str(worker), action, 'nvme0n1p10'], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('Ignoring unselected internal partition', result.stdout)

    def test_install_remove_twice(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            home = root/'home'; home.mkdir()
            kde = home/'.config/kded_device_automounterrc'; kde.parent.mkdir(); kde.write_text('[General]\nAutomountEnabled=true\n')
            account = SimpleNamespace(pw_name='tester', pw_gid=1234, pw_dir=str(home))
            inventory = [dict(name='/dev/sda1', uuid='USB-1', external=True), dict(name='/dev/nvme1n1p2', uuid='DATA-1', external=False)]
            calls = []
            def command(*args, **kwargs):
                calls.append(args)
                return SimpleNamespace(stdout='', returncode=0)
            def direct(args, **kwargs):
                calls.append(tuple(args))
                return SimpleNamespace(returncode=0 if args[0]=='findmnt' and args[-1]=='/dev/sda1' else (1 if args[0]=='findmnt' else 0))
            with patch.object(m, 'ETC', root/'etc'), patch.object(m, 'STATE', root/'etc/steamdeck-automount'), patch.object(m.pwd, 'getpwuid', return_value=account), patch.object(m.os, 'chown'), patch.object(m, 'disks', return_value=inventory), patch.object(m, 'run', side_effect=command), patch.object(m.subprocess, 'run', side_effect=direct):
                for _ in range(2): m.root_install(1234, ['DATA-1'])
                service = (m.ETC/'systemd/system/external-drive-mount@.service').read_text()
                self.assertIn('TARGET_USER=tester', service)
                self.assertIn('TARGET_UID=1234', service)
                self.assertNotIn(str(home), service)
                self.assertIn('DATA-1', (m.ETC/'udev/rules.d/99-steamos-automount.rules').read_text())
                for file in (m.ETC/'atomic-update.conf.d/external-drive-automount.conf').read_text().splitlines():
                    self.assertTrue((m.ETC/file.removeprefix('/etc/')).is_file(), file)
                self.assertIn('AutomountEnabled=false', kde.read_text())
                self.assertIn('AutomountEnabled=true', kde.with_name(kde.name+'.before-auto-mount').read_text())
                self.assertIn(('systemctl','restart','external-drive-mount@nvme1n1p2.service'), calls)
                self.assertNotIn(('systemctl','restart','external-drive-mount@sda1.service'), calls)
                for _ in range(2): m.root_remove()
                self.assertFalse(m.STATE.exists())
                self.assertTrue(kde.exists())
                with self.assertRaises(ValueError): m.root_install(1234, ['SYSTEM-UUID'])

if __name__ == '__main__': unittest.main()
