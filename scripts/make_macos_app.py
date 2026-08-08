from pathlib import Path
import argparse
import plistlib
import shutil
import shlex
import stat
import subprocess
import sys


APP_NAME = 'Scholardew Valley'
BUNDLE_ID = 'com.bethyini.scholardewvalley'
ROOT = Path(__file__).resolve().parents[1]
SOURCE_ICON = ROOT / 'graphics' / 'ui' / 'app_icon.png'
DIST_DIR = ROOT / 'dist'
APP_PATH = DIST_DIR / f'{APP_NAME}.app'
ICONSET_PATH = DIST_DIR / 'AppIcon.iconset'
ICNS_PATH = APP_PATH / 'Contents' / 'Resources' / 'AppIcon.icns'
USER_APPLICATIONS_DIR = Path.home().joinpath('Applications')


def run(command):
    subprocess.run(command, check=True)


def make_iconset():
    if not SOURCE_ICON.exists():
        raise SystemExit(f'Missing source icon: {SOURCE_ICON}')

    if ICONSET_PATH.exists():
        shutil.rmtree(ICONSET_PATH)
    ICONSET_PATH.mkdir(parents=True)

    icon_sizes = (
        ('icon_16x16.png', 16),
        ('icon_16x16@2x.png', 32),
        ('icon_32x32.png', 32),
        ('icon_32x32@2x.png', 64),
        ('icon_128x128.png', 128),
        ('icon_128x128@2x.png', 256),
        ('icon_256x256.png', 256),
        ('icon_256x256@2x.png', 512),
        ('icon_512x512.png', 512),
        ('icon_512x512@2x.png', 1024),
    )
    for filename, size in icon_sizes:
        run(['sips', '-z', str(size), str(size), str(SOURCE_ICON), '--out', str(ICONSET_PATH / filename)])

    ICNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    run(['iconutil', '-c', 'icns', str(ICONSET_PATH), '-o', str(ICNS_PATH)])


def write_info_plist():
    plist = {
        'CFBundleDevelopmentRegion': 'en',
        'CFBundleDisplayName': APP_NAME,
        'CFBundleExecutable': APP_NAME,
        'CFBundleIconFile': 'AppIcon',
        'CFBundleIdentifier': BUNDLE_ID,
        'CFBundleInfoDictionaryVersion': '6.0',
        'CFBundleName': APP_NAME,
        'CFBundlePackageType': 'APPL',
        'CFBundleShortVersionString': '0.1.0',
        'CFBundleVersion': '1',
        'LSMinimumSystemVersion': '10.15',
        'NSHighResolutionCapable': True,
    }
    plist_path = APP_PATH / 'Contents' / 'Info.plist'
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    with plist_path.open('wb') as file:
        plistlib.dump(plist, file, sort_keys=False)


def write_launcher():
    executable_path = APP_PATH / 'Contents' / 'MacOS' / APP_NAME
    executable_path.parent.mkdir(parents=True, exist_ok=True)
    command_path = APP_PATH / 'Contents' / 'Resources' / 'run_scholardew.command'
    command_path.parent.mkdir(parents=True, exist_ok=True)
    pid_file = '${TMPDIR:-/tmp}/scholardew-valley.pid'
    command = f'''#!/bin/zsh
PID_FILE="{pid_file}"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Scholardew Valley is already running."
  exit 0
fi

echo $$ > "$PID_FILE"
trap 'rm -f "$PID_FILE"' EXIT

cd {shlex.quote(str(ROOT))} || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Python environment not found. Run setup from the Scholardew Valley repo, then try again."
  read -k 1 '?Press any key to close.'
  exit 1
fi

.venv/bin/python code/main.py
'''
    command_path.write_text(command)
    command_mode = command_path.stat().st_mode
    command_path.chmod(command_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    launcher = f'''#!/bin/zsh
APP_CONTENTS="$(cd "$(dirname "$0")/.." && pwd)"
/usr/bin/open "$APP_CONTENTS/Resources/run_scholardew.command"
'''
    executable_path.write_text(launcher)
    mode = executable_path.stat().st_mode
    executable_path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def make_app():
    if APP_PATH.exists():
        shutil.rmtree(APP_PATH)
    (APP_PATH / 'Contents' / 'Resources').mkdir(parents=True)
    write_info_plist()
    write_launcher()
    make_iconset()
    shutil.rmtree(ICONSET_PATH)
    run(['touch', str(APP_PATH)])
    return APP_PATH


def copy_app(app_path, destination_dir):
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_path = destination_dir / app_path.name
    if destination_path.exists():
        shutil.rmtree(destination_path)
    shutil.copytree(app_path, destination_path)
    run(['touch', str(destination_path)])
    return destination_path


def copy_to_desktop(app_path):
    return copy_app(app_path, Path.home().joinpath('Desktop'))


def copy_to_applications(app_path):
    return copy_app(app_path, USER_APPLICATIONS_DIR)


def pin_to_dock(app_path):
    dock_entry = subprocess.run(
        ['defaults', 'read', 'com.apple.dock', 'persistent-apps'],
        capture_output=True,
        text=True,
        check=False)
    app_path_text = str(app_path)
    if app_path_text in dock_entry.stdout:
        return False

    tile = (
        '<dict>'
        '<key>tile-data</key>'
        '<dict>'
        '<key>file-data</key>'
        '<dict>'
        '<key>_CFURLString</key>'
        f'<string>{app_path_text}</string>'
        '<key>_CFURLStringType</key>'
        '<integer>0</integer>'
        '</dict>'
        '<key>file-label</key>'
        f'<string>{APP_NAME}</string>'
        '</dict>'
        '</dict>'
    )
    run(['defaults', 'write', 'com.apple.dock', 'persistent-apps', '-array-add', tile])
    run(['killall', 'Dock'])
    return True


def main():
    parser = argparse.ArgumentParser(description='Build a clickable macOS app launcher for Scholardew Valley.')
    parser.add_argument('--desktop', action='store_true', help='Also copy the app bundle to ~/Desktop.')
    parser.add_argument('--applications', action='store_true', help='Also copy the app bundle to ~/Applications.')
    parser.add_argument('--dock', action='store_true', help='Pin the ~/Applications app bundle to the Dock.')
    args = parser.parse_args()

    if sys.platform != 'darwin':
        raise SystemExit('This launcher builder only supports macOS.')

    app_path = make_app()
    print(app_path)
    if args.desktop:
        print(copy_to_desktop(app_path))
    applications_path = None
    if args.applications or args.dock:
        applications_path = copy_to_applications(app_path)
        print(applications_path)
    if args.dock:
        pinned = pin_to_dock(applications_path)
        print('Dock icon pinned.' if pinned else 'Dock icon already pinned.')


if __name__ == '__main__':
    main()
