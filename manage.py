#!/usr/bin/env python3
"""SteamOS installer derived from scawp's automount project; see LICENSE.md."""
import json, os, pwd, re, subprocess, sys
from pathlib import Path
BASE = Path(__file__).resolve().parent
ETC = Path('/etc')
STATE = ETC / 'steamdeck-automount'
SUPPORTED = {'ntfs', 'exfat', 'ext4', 'btrfs'}
SYSTEM_LABELS = {'rootfs', 'home', 'var', 'esp', 'efi', 'recovery', 'swap'}

def run(*args, **kw):
    return subprocess.run(args, check=True, text=True, **kw)

def disks():
    data = json.loads(run('lsblk', '--json', '--paths', '--output', 'NAME,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,TRAN,RM,SIZE', capture_output=True).stdout)
    result = []
    def visit(d, external=False):
        external = external or d.get('tran') == 'usb' or bool(d.get('rm')) or bool(re.fullmatch(r'/dev/mmcblk\d+(p\d+)?', d['name']))
        mounts = d.get('mountpoints') or []
        protected = (d.get('label') or '').lower() in SYSTEM_LABELS or any(m and (m == '/' or m.startswith(('/boot', '/efi', '/esp', '/var', '/home', '/usr', '/opt', '/srv', '/nix', '/root'))) for m in mounts)
        if d.get('fstype') in SUPPORTED and d.get('uuid') and d.get('type') in {'disk', 'part'} and not protected:
            result.append(dict(d, external=external))
        for child in d.get('children', []):
            visit(child, external)
    for disk in data['blockdevices']:
        visit(disk)
    return result

def rules(uuids):
    header = '# Managed by Steam Deck Auto Mount\nSUBSYSTEM!="block", GOTO="sdmed_end"\n'
    header += 'ACTION=="remove", RUN+="/bin/systemctl stop --no-block external-drive-mount@%k.service"\n'
    header += 'ACTION!="add", GOTO="sdmed_end"\nENV{ID_FS_TYPE}!="ntfs|exfat|btrfs|ext4", GOTO="sdmed_end"\n'
    action = 'RUN+="/bin/systemctl start --no-block external-drive-mount@%k.service"\n'
    header += 'ENV{ID_BUS}=="usb", ' + action
    header += 'KERNEL=="mmcblk[0-9]*", ' + action
    for uuid in uuids:
        if not re.fullmatch(r'[A-Za-z0-9-]+', uuid):
            raise ValueError('Invalid filesystem UUID')
        header += f'ENV{{ID_FS_UUID}}=="{uuid}", ' + action
    return header + 'LABEL="sdmed_end"\n'

def write(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(content)
    temp.chmod(mode)
    temp.replace(path)

def root_install(uid, selected):
    account = pwd.getpwuid(uid)
    if uid == 0 or not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_-]*\$?', account.pw_name):
        raise ValueError('Select a regular local user')
    # Recheck selection after elevation, using current block-device metadata.
    allowed = {d['uuid'] for d in disks() if not d['external']}
    if not set(selected) <= allowed:
        raise ValueError('Selected internal partition is missing or protected; run setup again')
    worker = (BASE / 'automount.sh').read_text()
    write(STATE / 'automount.sh', worker, 0o755)
    config = dict(user=account.pw_name, uid=uid, gid=account.pw_gid, home=account.pw_dir, internal_uuids=selected)
    write(STATE / 'config.json', json.dumps(config, indent=2) + '\n')
    service = f'''[Unit]
Description=Steam Deck external drive automount (%i)
Wants=udisks2.service
After=udisks2.service
[Service]
Type=oneshot
RemainAfterExit=true
Environment=TARGET_USER={account.pw_name}
Environment=TARGET_UID={uid}
Environment=TARGET_GID={account.pw_gid}
ExecStart=/etc/steamdeck-automount/automount.sh add %i
ExecStop=/etc/steamdeck-automount/automount.sh remove %i
'''
    write(ETC / 'systemd/system/external-drive-mount@.service', service)
    write(ETC / 'udev/rules.d/99-steamos-automount.rules', rules(selected))
    write(ETC / 'atomic-update.conf.d/external-drive-automount.conf', '/etc/udev/rules.d/99-steamos-automount.rules\n/etc/systemd/system/external-drive-mount@.service\n/etc/steamdeck-automount/automount.sh\n/etc/steamdeck-automount/config.json\n')
    run('systemctl', 'daemon-reload')
    run('udevadm', 'control', '--reload-rules')
    # Preserve the first KDE configuration for manual recovery; do not re-enable
    # broad KDE mounting on uninstall because it may prompt for system partitions.
    kde = Path(account.pw_dir) / '.config/kded_device_automounterrc'
    if kde.exists():
        text = kde.read_text()
        backup = kde.with_name(kde.name + '.before-auto-mount')
        if not backup.exists():
            backup.write_text(text)
            os.chown(backup, uid, account.pw_gid)
        kde.write_text(text.replace('AutomountEnabled=true', 'AutomountEnabled=false'))
    failures = []
    for d in disks():
        if d['external'] or d['uuid'] in selected:
            if subprocess.run(['findmnt', '-rn', '-S', d['name']], stdout=subprocess.DEVNULL).returncode == 0:
                continue
            if subprocess.run(['systemctl', 'restart', f"external-drive-mount@{Path(d['name']).name}.service"]).returncode:
                failures.append(d['name'])
    if failures:
        raise RuntimeError('Setup saved, but these drives failed to mount: ' + ', '.join(failures))
    print('Installed.')

def root_remove():
    rule = ETC / 'udev/rules.d/99-steamos-automount.rules'
    rule.unlink(missing_ok=True)
    run('udevadm', 'control', '--reload-rules')
    units = run('systemctl', 'list-units', '--all', '--plain', '--no-legend', 'external-drive-mount@*.service', capture_output=True).stdout
    names = [line.split()[0] for line in units.splitlines() if line.strip()]
    if names:
        # Stopping the legacy worker only cleans compatibility symlinks; it does
        # not unmount data filesystems.
        run('systemctl', 'stop', *names)
    for relative in ['systemd/system/external-drive-mount@.service', 'atomic-update.conf.d/external-drive-automount.conf', 'atomic-update.conf.d/two-drive-automount.conf', 'steamdeck-automount/automount.sh', 'steamdeck-automount/config.json']:
        (ETC / relative).unlink(missing_ok=True)
    if STATE.exists() and not any(STATE.iterdir()):
        STATE.rmdir()
    run('systemctl', 'daemon-reload')
    print('Uninstalled.')

def show_status():
    print('Automatically mount drives at startup and when connected.')
    service = ETC / 'systemd/system/external-drive-mount@.service'
    rule = ETC / 'udev/rules.d/99-steamos-automount.rules'
    worker = STATE / 'automount.sh'
    config = STATE / 'config.json'
    if not service.exists() and not rule.exists() and not config.exists():
        print('Status: Not installed')
        return
    if not service.exists() or not rule.exists():
        print('Status: Incomplete installation')
    elif config.exists() and worker.exists():
        print('Status: Installed')
    elif not config.exists():
        print('Status: Previous version installed')
    else:
        print('Status: Incomplete installation')
    try:
        rule_text = rule.read_text() if rule.exists() else ''
        if config.exists():
            saved = json.loads(config.read_text())
            uuids = saved.get('internal_uuids', [])
            if 'ENV{ID_BUS}=="usb"' in rule_text:
                print('Enabled: USB drives, SD cards')
            available = disks()
            known = {d['uuid']: d for d in available}
            for d in available:
                if d['external'] and 'ENV{ID_BUS}=="usb"' in rule_text:
                    print(f"  {d.get('label') or '(no label)'} ({d['name']})")
            if uuids:
                print('Internal partitions:')
            for uuid in uuids:
                d = known.get(uuid)
                if d:
                    print(f"  {d.get('label') or '(no label)'} ({d['name']})")
                else:
                    print(f'  {uuid} (not connected or unavailable)')
            if not uuids:
                print('Internal partitions: None')
        elif rule_text:
            if 'sd[a-z]' in rule_text:
                print('Enabled: USB drives')
            if 'mmcblk' in rule_text:
                print('Enabled: SD cards')
            uuids = re.findall(r'ENV\{ID_FS_UUID\}=="([^"\n]+)"', rule_text)
            known = {d['uuid']: d for d in disks()}
            for uuid in uuids:
                d = known.get(uuid)
                print(f"Enabled: {d.get('label') or d['name']} ({d['name']})" if d else f'Enabled: {uuid}')
            if not uuids:
                print('Partition matching: Previous-version rules')
    except (OSError, ValueError, subprocess.CalledProcessError):
        print('Enabled partitions: Unable to read configuration')

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else ''
    if action == 'status':
        show_status()
        return
    if action.startswith('root-'):
        if os.geteuid() != 0:
            raise RuntimeError('Administrator privileges required')
        if action == 'root-install':
            root_install(int(sys.argv[2]), sys.argv[3:])
        elif action == 'root-remove':
            root_remove()
        else:
            raise ValueError('Unknown operation')
        return
    if action == 'install':
        if os.getuid() == 0:
            raise ValueError('Run this installer as your normal desktop user, without sudo')
        for name in ['lsblk', 'findmnt', 'sudo', 'systemctl', 'udevadm', 'busctl', 'jq', 'flock', 'hexdump']:
            import shutil
            if not shutil.which(name):
                raise RuntimeError('Missing dependency: ' + name)
        internal = [d for d in disks() if not d['external']]
        print('Internal data partitions:')
        for i, d in enumerate(internal, 1):
            print(f"{i}) {d['name']} | {d.get('label') or '(no label)'} | {d['size']} | {d['fstype']} | {d['uuid']}")
        raw = input('Select numbers, or Enter to skip: ').strip()
        indices = raw.split()
        if any(not x.isdigit() or not 1 <= int(x) <= len(internal) for x in indices):
            raise ValueError('Invalid selection; no changes made')
        selected = list(dict.fromkeys(internal[int(x)-1]['uuid'] for x in indices))
        run('sudo', sys.executable, str(BASE / 'manage.py'), 'root-install', str(os.getuid()), *selected)
    elif action == 'remove':
        run('sudo', sys.executable, str(BASE / 'manage.py'), 'root-remove')
    else:
        raise ValueError('Usage: manage.py install|remove')

if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError, EOFError, KeyboardInterrupt) as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)
