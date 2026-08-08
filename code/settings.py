import os
from pathlib import Path

from pygame.math import Vector2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_NAME = os.environ.get('KNOWLEDGE_GAME_APP_NAME', 'Scholardew Valley')
WINDOW_TITLE = APP_NAME


def project_path_from_env(name, default):
    configured = os.environ.get(name)
    path = Path(configured).expanduser() if configured else Path(default).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


USER_DATA_DIR = project_path_from_env('KNOWLEDGE_GAME_DATA_DIR', PROJECT_ROOT / 'data' / 'user')
ENV_PATH = project_path_from_env('KNOWLEDGE_GAME_ENV_PATH', PROJECT_ROOT / '.env')
NOTEBOOK_PATH = project_path_from_env('KNOWLEDGE_GAME_NOTEBOOK_PATH', USER_DATA_DIR / 'notebook.md')
NOTEBOOK_TITLE = os.environ.get('KNOWLEDGE_GAME_NOTEBOOK_TITLE', 'Player Notebook')
NOTEBOOK_HEADING = os.environ.get('KNOWLEDGE_GAME_NOTEBOOK_HEADING', 'Player Profile')
DAILY_TASKS_PATH = project_path_from_env('KNOWLEDGE_GAME_TASKS_PATH', USER_DATA_DIR / 'daily-tasks.md')
KNOWLEDGE_STATE_PATH = project_path_from_env('KNOWLEDGE_GAME_KNOWLEDGE_STATE_PATH', USER_DATA_DIR / 'knowledge_state.json')
DAILY_TASKS_STATE_PATH = project_path_from_env('KNOWLEDGE_GAME_DAILY_TASKS_STATE_PATH', USER_DATA_DIR / 'daily_tasks_state.json')

FPS = 60

# screen
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 768
TILE_SIZE = 64

# overlay position
OVERLAY_POSITIONS = {
    'tool': (40, SCREEN_HEIGHT - 15),
    'seed': (70, SCREEN_HEIGHT - 5)
}

PLAYER_TOOL_OFFSET = {
    'left': Vector2(-50, 40),
    'right': Vector2(50, 40),
    'up': Vector2(0, -10),
    'down': Vector2(0, 50)
}

LAYERS = {
    'water': 0,
    'ground': 1,
    'soil': 2,
    'soil water': 3,
    'rain floor': 4,
    'house bottom': 5,
    'ground plant': 6,
    'main': 7,
    'house top': 8,
    'fruit': 9,
    'rain drops': 10
}

APPLE_POS = {
    'Small': [(18, 17), (30, 37), (12, 50), (30, 45), (20, 30), (30, 10)],
    'Large': [(30, 24), (60, 65), (50, 50), (16, 40), (45, 50), (42, 70)]
}

GROW_SPEED = {
    'corn': 1,
    'tomato': 0.7
}

SALE_PRICES = {
    'wood': 4,
    'apple': 2,
    'corn': 10,
    'tomato': 20,
}

PURCHASE_PRICES = {
    'corn': 4,
    'tomato': 5
}
