from pathlib import Path
import argparse
import plistlib
import shutil
import subprocess
import sys
from urllib.parse import unquote


APP_NAME = 'Scholardew Valley'
BUNDLE_ID = 'com.bethyini.scholardewvalley'
ROOT = Path(__file__).resolve().parents[1]
SOURCE_ICON = ROOT / 'graphics' / 'ui' / 'app_icon.png'
DIST_DIR = ROOT / 'dist'
BUILD_DIR = ROOT / 'build' / 'pyinstaller'
APP_PATH = DIST_DIR / f'{APP_NAME}.app'
ICONSET_PATH = BUILD_DIR / 'AppIcon.iconset'
ICNS_PATH = BUILD_DIR / 'AppIcon.icns'
HOOKS_DIR = BUILD_DIR / 'hooks'
USER_APPLICATIONS_DIR = Path.home().joinpath('Applications')
APP_SUPPORT_DIR = Path.home().joinpath('Library', 'Application Support', APP_NAME)
DOCK_PLIST = Path.home().joinpath('Library', 'Preferences', 'com.apple.dock.plist')


def run(command):
    subprocess.run(command, check=True)


def make_iconset():
    if not SOURCE_ICON.exists():
        raise SystemExit(f'Missing source icon: {SOURCE_ICON}')

    if ICONSET_PATH.exists():
        shutil.rmtree(ICONSET_PATH)
    ICONSET_PATH.mkdir(parents=True, exist_ok=True)

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

    run(['iconutil', '-c', 'icns', str(ICONSET_PATH), '-o', str(ICNS_PATH)])


def write_pyinstaller_hooks():
    HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    (HOOKS_DIR / 'hook-notebook.py').write_text(
        "# Scholardew has a local notebook.py module; do not apply Jupyter's notebook hook.\n")


def app_info_plist_path(app_path):
    return app_path / 'Contents' / 'Info.plist'


def patch_info_plist(app_path):
    plist_path = app_info_plist_path(app_path)
    with plist_path.open('rb') as file:
        plist = plistlib.load(file)
    plist.update({
        'CFBundleDisplayName': APP_NAME,
        'CFBundleIdentifier': BUNDLE_ID,
        'CFBundleName': APP_NAME,
        'LSMinimumSystemVersion': '10.15',
        'NSHighResolutionCapable': True,
    })
    with plist_path.open('wb') as file:
        plistlib.dump(plist, file, sort_keys=False)


def pyinstaller_available():
    result = subprocess.run(
        [sys.executable, '-m', 'PyInstaller', '--version'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False)
    return result.returncode == 0


def add_data_arg(source, destination):
    return f'{source}:{destination}'


def make_app():
    if sys.platform != 'darwin':
        raise SystemExit('This launcher builder only supports macOS.')
    if not pyinstaller_available():
        raise SystemExit('Missing PyInstaller. Install it with: python -m pip install pyinstaller')

    if APP_PATH.exists():
        shutil.rmtree(APP_PATH)
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    make_iconset()
    write_pyinstaller_hooks()
    command = [
        sys.executable,
        '-m',
        'PyInstaller',
        '--noconfirm',
        '--windowed',
        '--name',
        APP_NAME,
        '--icon',
        str(ICNS_PATH),
        '--distpath',
        str(DIST_DIR),
        '--workpath',
        str(BUILD_DIR),
        '--specpath',
        str(BUILD_DIR),
        '--additional-hooks-dir',
        str(HOOKS_DIR),
        '--add-data',
        add_data_arg(ROOT / 'audio', 'audio'),
        '--add-data',
        add_data_arg(ROOT / 'data' / 'Tilesets', 'data/Tilesets'),
        '--add-data',
        add_data_arg(ROOT / 'data' / 'map.tmx', 'data'),
        '--add-data',
        add_data_arg(ROOT / 'font', 'font'),
        '--add-data',
        add_data_arg(ROOT / 'graphics', 'graphics'),
        str(ROOT / 'code' / 'main.py'),
    ]
    run([str(item) for item in command])
    patch_info_plist(APP_PATH)
    seed_app_support_data()
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


def seed_app_support_data():
    source = ROOT / 'data' / 'user'
    destination = APP_SUPPORT_DIR / 'data' / 'user'
    if destination.exists() or not source.exists():
        return None
    shutil.copytree(source, destination)
    return destination


def dock_item_label(item):
    return item.get('tile-data', {}).get('file-label', '')


def dock_item_url(item):
    return item.get('tile-data', {}).get('file-data', {}).get('_CFURLString', '')


def dock_url_path(url):
    if url.startswith('file://'):
        return unquote(url[len('file://'):]).rstrip('/')
    return unquote(url).rstrip('/')


def is_stale_python_launcher(item):
    path = dock_url_path(dock_item_url(item))
    return (
        dock_item_label(item) == 'Python'
        and path.endswith('/Python.app')
        and '/CommandLineTools/Library/Frameworks/Python3.framework/' in path
    )


def is_scholardew_entry(item):
    path = dock_url_path(dock_item_url(item))
    return dock_item_label(item) == APP_NAME or path.endswith(f'/{APP_NAME}.app')


def prune_stale_dock_entries(app_path):
    if not DOCK_PLIST.exists():
        return False, False

    with DOCK_PLIST.open('rb') as file:
        dock = plistlib.load(file)

    target_path = str(app_path.resolve()).rstrip('/')
    filtered_apps = []
    changed = False
    has_target = False

    for item in dock.get('persistent-apps', []):
        path = dock_url_path(dock_item_url(item))
        if is_stale_python_launcher(item):
            changed = True
            continue
        if is_scholardew_entry(item):
            if path == target_path and not has_target:
                filtered_apps.append(item)
                has_target = True
            else:
                changed = True
            continue
        filtered_apps.append(item)

    if changed:
        dock['persistent-apps'] = filtered_apps
        with DOCK_PLIST.open('wb') as file:
            plistlib.dump(dock, file, sort_keys=False)

    return has_target, changed


def pin_to_dock(app_path):
    has_target, changed = prune_stale_dock_entries(app_path)
    if has_target:
        if changed:
            run(['killall', 'Dock'])
        return False

    dock_entry = subprocess.run(
        ['defaults', 'read', 'com.apple.dock', 'persistent-apps'],
        capture_output=True,
        text=True,
        check=False)
    app_path_text = str(app_path)
    app_uri = app_path.resolve().as_uri()
    if app_path_text in dock_entry.stdout or app_uri in dock_entry.stdout or APP_NAME in dock_entry.stdout:
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
    parser = argparse.ArgumentParser(description='Build a native macOS app bundle for Scholardew Valley.')
    parser.add_argument('--desktop', action='store_true', help='Also copy the app bundle to ~/Desktop.')
    parser.add_argument('--applications', action='store_true', help='Also copy the app bundle to ~/Applications.')
    parser.add_argument('--dock', action='store_true', help='Pin the ~/Applications app bundle to the Dock.')
    args = parser.parse_args()

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
