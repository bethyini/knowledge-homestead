from dataclasses import dataclass
import json
import os
import re
import urllib.error
import urllib.request

from settings import APP_VERSION, DEFAULT_UPDATE_CHECK_URL, UPDATE_CHECK_TIMEOUT


FALSE_VALUES = {'0', 'false', 'no', 'off'}
TRUE_VALUES = {'1', 'true', 'yes', 'on'}


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    title: str
    message: str
    url: str


def update_checks_enabled():
    value = os.environ.get('SCHOLARDEW_UPDATE_CHECK', '1').strip().lower()
    if value in FALSE_VALUES:
        return False
    if os.environ.get('SCHOLARDEW_DISABLE_UPDATE_CHECK', '').strip().lower() in TRUE_VALUES:
        return False
    return True


def version_tuple(version):
    parts = [int(part) for part in re.findall(r'\d+', str(version))]
    if not parts:
        return ()
    return tuple((parts + [0, 0, 0])[:3])


def is_newer_version(candidate, current=APP_VERSION):
    candidate_parts = version_tuple(candidate)
    current_parts = version_tuple(current)
    return bool(candidate_parts and current_parts and candidate_parts > current_parts)


def read_latest_update():
    if not update_checks_enabled():
        return None

    url = os.environ.get('SCHOLARDEW_UPDATE_URL', DEFAULT_UPDATE_CHECK_URL).strip()
    if not url:
        return None

    request = urllib.request.Request(url, headers={'User-Agent': f'Scholardew Valley/{APP_VERSION}'})
    try:
        with urllib.request.urlopen(request, timeout=UPDATE_CHECK_TIMEOUT) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    version = str(payload.get('version', '')).strip().lstrip('v')
    if not is_newer_version(version):
        return None

    title = str(payload.get('title') or f'Scholardew Valley v{version}').strip()
    message = str(payload.get('message') or 'A new version is available.').strip()
    update_url = str(payload.get('url') or payload.get('download_url') or '').strip()
    if not update_url:
        update_url = 'https://github.com/bethyini/scholardew-valley'

    return UpdateInfo(
        version=version,
        title=title[:90],
        message=message[:280],
        url=update_url)
