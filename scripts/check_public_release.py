from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTENSIONS = {
    '.env',
    '.example',
    '.gitignore',
    '.md',
    '.py',
    '.txt',
}
DENY_PATTERNS = (
    re.compile(r'/Users/lili'),
    re.compile(r'\bLili\b'),
    re.compile(r'\blili\b'),
    re.compile(r'Path\.home\(\)\s*/\s*[\'"]Desktop[\'"]'),
    re.compile(r'OPENAI_API_KEY=sk-[A-Za-z0-9_-]{12,}'),
    re.compile(r'sk-proj-[A-Za-z0-9_-]{12,}'),
)
IGNORED_DIRS = {'.git', '.venv', '__pycache__'}
IGNORED_FILES = {'.env', 'check_public_release.py'}


def iter_text_files():
    for path in ROOT.rglob('*'):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.name in IGNORED_FILES:
            continue
        if not path.is_file():
            continue
        if path.suffix in TEXT_EXTENSIONS or path.name in {'README', 'LICENSE'}:
            yield path


def scan_public_text():
    errors = []
    for path in iter_text_files():
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        for pattern in DENY_PATTERNS:
            if pattern.search(text):
                errors.append(f'{path.relative_to(ROOT)} matches {pattern.pattern}')
    return errors


def check_gitignore():
    gitignore = (ROOT / '.gitignore').read_text()
    required = ['/.env', '/.venv', '/data/user/*', '!/data/user/.gitkeep', '*.pdf']
    return [f'.gitignore missing {item}' for item in required if item not in gitignore]


def check_missions():
    sys.path.insert(0, str(ROOT / 'code'))
    from knowledge import MISSIONS

    errors = []
    if len(MISSIONS) != 3:
        errors.append(f'public starter set should expose exactly 3 missions, found {len(MISSIONS)}')

    keys = [mission.key for mission in MISSIONS]
    reward_items = [mission.reward_item for mission in MISSIONS]
    for values, label in ((keys, 'mission key'), (reward_items, 'reward item')):
        duplicates = sorted({item for item in values if values.count(item) > 1})
        if duplicates:
            errors.append(f'duplicate {label}: {", ".join(duplicates)}')

    for mission in MISSIONS:
        if len(mission.key_facts) < mission.required_hits:
            errors.append(f'{mission.key} requires more hits than it has facts')
        if mission.questions:
            conceptual = sum(1 for question in mission.questions if question.category == 'Conceptual')
            methods = sum(1 for question in mission.questions if question.category == 'Methods')
            if len(mission.questions) != 10 or conceptual != 5 or methods != 5:
                errors.append(f'{mission.key} should have 5 conceptual and 5 methods questions')
    return errors


def main():
    errors = []
    errors.extend(scan_public_text())
    errors.extend(check_gitignore())
    errors.extend(check_missions())
    if errors:
        for error in errors:
            print(f'FAIL: {error}')
        raise SystemExit(1)

    print('Public release checks passed.')


if __name__ == '__main__':
    main()
