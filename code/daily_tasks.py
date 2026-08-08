from datetime import date
import json
import pygame

from settings import DAILY_TASKS_PATH, DAILY_TASKS_STATE_PATH, LAYERS, SCREEN_HEIGHT, SCREEN_WIDTH
from support import get_path


TASKS_PATH = DAILY_TASKS_PATH
STATE_PATH = DAILY_TASKS_STATE_PATH
DAILY_REWARD_ITEM = 'strawberry'
DAILY_REWARD_NAME = 'Strawberry'

PANEL = (244, 229, 188)
PANEL_DARK = (96, 62, 39)
PANEL_SHADOW = (45, 31, 24)
INK = (35, 25, 20)
MUTED = (92, 76, 60)
ACCENT = (152, 84, 38)
SUCCESS = (47, 111, 78)
WARNING = (155, 58, 48)


class DailyDesk(pygame.sprite.Sprite):
    def __init__(self, pos, groups):
        super().__init__(groups)
        self.image = self.make_image()
        self.rect = self.image.get_rect(center=pos)
        self.z = LAYERS['main']
        self.hitbox = self.rect.copy().inflate(-18, -22)

    def make_image(self):
        surf = pygame.Surface((88, 72), pygame.SRCALPHA)
        pygame.draw.ellipse(surf, (34, 24, 20, 80), (12, 58, 64, 10))

        pygame.draw.rect(surf, (116, 74, 44), (14, 28, 60, 30), border_radius=4)
        pygame.draw.rect(surf, (78, 50, 33), (14, 28, 60, 30), 3, border_radius=4)
        pygame.draw.rect(surf, (151, 94, 50), (10, 18, 68, 18), border_radius=5)
        pygame.draw.rect(surf, (78, 50, 33), (10, 18, 68, 18), 3, border_radius=5)

        pygame.draw.rect(surf, (226, 199, 132), (23, 12, 26, 18), border_radius=2)
        pygame.draw.line(surf, (109, 75, 48), (28, 17), (43, 17), 2)
        pygame.draw.line(surf, (109, 75, 48), (28, 22), (41, 22), 2)

        pygame.draw.rect(surf, (61, 96, 132), (54, 9, 12, 20), border_radius=2)
        pygame.draw.rect(surf, (41, 61, 86), (54, 9, 12, 20), 2, border_radius=2)
        pygame.draw.circle(surf, (242, 206, 105), (60, 9), 6)

        pygame.draw.rect(surf, (86, 54, 36), (20, 56, 8, 12))
        pygame.draw.rect(surf, (86, 54, 36), (60, 56, 8, 12))
        return surf


class DailyRewardChest(pygame.sprite.Sprite):
    def __init__(self, pos, groups, daily_tasks):
        super().__init__(groups)
        self.daily_tasks = daily_tasks
        self.opened = False
        self.closed_image = self.make_image(False)
        self.open_image = self.make_image(True)
        self.image = self.closed_image
        self.rect = self.image.get_rect(center=pos)
        self.z = LAYERS['main']

    def make_image(self, opened):
        surf = pygame.Surface((66, 58), pygame.SRCALPHA)
        pygame.draw.ellipse(surf, (34, 24, 20, 85), (9, 48, 48, 8))

        body = (81, 118, 102)
        lid = (106, 153, 129)
        trim = (47, 70, 61)
        accent = (236, 190, 91)
        glow = (228, 221, 137, 95)

        if opened:
            pygame.draw.polygon(surf, glow, [(33, 2), (61, 39), (5, 39)])
            pygame.draw.rect(surf, body, (12, 27, 42, 25), border_radius=4)
            pygame.draw.rect(surf, trim, (12, 27, 42, 25), 3, border_radius=4)
            pygame.draw.polygon(surf, lid, [(13, 27), (50, 14), (54, 27)])
            pygame.draw.line(surf, trim, (13, 27), (50, 14), 3)
        else:
            pygame.draw.rect(surf, body, (11, 23, 44, 28), border_radius=4)
            pygame.draw.rect(surf, trim, (11, 23, 44, 28), 3, border_radius=4)
            pygame.draw.rect(surf, lid, (15, 14, 36, 17), border_radius=6)
            pygame.draw.rect(surf, trim, (15, 14, 36, 17), 3, border_radius=6)

        pygame.draw.rect(surf, accent, (30, 32, 7, 9), border_radius=2)
        pygame.draw.rect(surf, accent, (13, 32, 40, 4))
        pygame.draw.line(surf, (242, 221, 154), (23, 20), (42, 20), 1)
        pygame.draw.line(surf, (242, 221, 154), (25, 38), (40, 38), 1)
        return surf

    def update(self, dt=None):
        should_open = self.daily_tasks.rewarded_today()
        if should_open == self.opened:
            return

        midbottom = self.rect.midbottom
        self.opened = should_open
        self.image = self.open_image if self.opened else self.closed_image
        self.rect = self.image.get_rect(midbottom=midbottom)


class DailyTasks:
    def __init__(self, player):
        self.display_surface = pygame.display.get_surface()
        self.player = player
        self.font = pygame.font.Font(get_path('../font/LycheeSoda.ttf'), 30)
        self.small_font = pygame.font.Font(get_path('../font/LycheeSoda.ttf'), 22)
        self.tiny_font = pygame.font.Font(get_path('../font/LycheeSoda.ttf'), 18)
        self.active = False
        self.entry = ''
        self.message = ''
        self.index = 0
        self.scroll = 0
        self.tasks = []
        self.ensure_player_state()
        self.load_reward_state()
        self.ensure_file()
        self.load_tasks()

    def today_heading(self):
        return f'## {date.today().isoformat()}'

    def today_key(self):
        return date.today().isoformat()

    def ensure_player_state(self):
        if not hasattr(self.player, 'strength'):
            self.player.strength = 0
        if not hasattr(self.player, 'daily_reward_inventory'):
            self.player.daily_reward_inventory = {}
        if not hasattr(self.player, 'daily_task_reward_dates'):
            self.player.daily_task_reward_dates = set()

    def load_reward_state(self):
        if not STATE_PATH.exists():
            return

        try:
            data = json.loads(STATE_PATH.read_text())
        except (OSError, json.JSONDecodeError):
            self.message = 'Task reward log could not be loaded.'
            return

        self.player.strength = int(data.get('strength', self.player.strength))
        rewards = data.get('daily_reward_inventory')
        if rewards is None:
            rewards = {}
            legacy_chests = int(data.get('daily_chests', 0))
            if legacy_chests:
                rewards[DAILY_REWARD_ITEM] = legacy_chests
        self.player.daily_reward_inventory = rewards
        self.player.daily_task_reward_dates = set(
            data.get('daily_task_reward_dates', self.player.daily_task_reward_dates))

    def save_reward_state(self):
        data = {
            'strength': self.player.strength,
            'daily_reward_inventory': self.player.daily_reward_inventory,
            'daily_task_reward_dates': sorted(self.player.daily_task_reward_dates),
        }
        try:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STATE_PATH.write_text(json.dumps(data, indent=2) + '\n')
        except OSError:
            self.message = 'Task reward log could not be saved.'

    def ensure_file(self):
        if not TASKS_PATH.exists():
            TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)
            TASKS_PATH.write_text('# Daily Tasks\n\n')
        self.ensure_today_section()

    def ensure_today_section(self):
        try:
            text = TASKS_PATH.read_text()
        except OSError:
            self.message = 'Task file could not be read.'
            return

        lines = text.rstrip().splitlines()
        if not lines:
            lines = ['# Daily Tasks']
        carried_tasks = self.carried_tasks_for_today(lines)
        heading = self.today_heading()
        start, end = self.section_bounds(lines, heading)

        if start is not None:
            existing_tasks = self.tasks_between(lines, start + 1, end)
            if existing_tasks or not carried_tasks:
                return
            task_lines = [self.task_line(task) for task in carried_tasks]
            lines = lines[:start + 1] + task_lines + lines[end:]
        else:
            if lines[-1].strip():
                lines.append('')
            lines.extend([heading, *[self.task_line(task) for task in carried_tasks]])

        try:
            TASKS_PATH.write_text('\n'.join(lines).rstrip() + '\n')
        except OSError:
            self.message = 'Task file could not be saved.'

    def section_bounds(self, lines, heading):
        try:
            start = lines.index(heading)
        except ValueError:
            return None, None

        end = len(lines)
        for index in range(start + 1, len(lines)):
            if lines[index].startswith('## '):
                end = index
                break
        return start, end

    def parse_task_line(self, line):
        stripped = line.strip()
        if not stripped.startswith('- [') or len(stripped) < 5:
            return None

        marker = stripped[3].lower()
        if marker not in (' ', 'x'):
            return None

        text = stripped[5:].strip()
        if not text:
            return None

        return {'done': marker == 'x', 'text': text}

    def task_line(self, task):
        return f'- [{"x" if task["done"] else " "}] {task["text"]}'

    def tasks_between(self, lines, start, end):
        tasks = []
        for line in lines[start:end]:
            task = self.parse_task_line(line)
            if task:
                tasks.append(task)
        return tasks

    def carried_tasks_for_today(self, lines):
        today = date.today()
        latest_tasks = []
        headings = [
            (index, line.strip())
            for index, line in enumerate(lines)
            if line.strip().startswith('## ')
        ]

        for heading_index, (start, heading) in enumerate(headings):
            try:
                heading_date = date.fromisoformat(heading[3:].strip())
            except ValueError:
                continue
            if heading_date >= today:
                continue

            end = headings[heading_index + 1][0] if heading_index + 1 < len(headings) else len(lines)
            tasks = self.tasks_between(lines, start + 1, end)
            if tasks:
                latest_tasks = tasks

        carried = []
        seen = set()
        for task in latest_tasks:
            text = task['text']
            if text in seen:
                continue
            seen.add(text)
            carried.append({'done': False, 'text': text})
        return carried

    def load_tasks(self):
        self.ensure_today_section()
        try:
            lines = TASKS_PATH.read_text().splitlines()
        except OSError:
            self.tasks = []
            self.message = 'Task file could not be read.'
            return

        tasks = []
        in_today = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('## '):
                in_today = stripped == self.today_heading()
                continue
            if in_today and stripped.startswith('- ['):
                task = self.parse_task_line(stripped)
                if task:
                    tasks.append(task)

        self.tasks = tasks
        if self.tasks:
            self.index = max(0, min(self.index, len(self.tasks) - 1))
        else:
            self.index = 0
        self.scroll = max(0, min(self.scroll, max(0, len(self.tasks) - 1)))

    def write_tasks(self):
        self.ensure_today_section()
        try:
            lines = TASKS_PATH.read_text().splitlines()
        except OSError:
            self.message = 'Task file could not be read.'
            return False

        heading = self.today_heading()
        try:
            start = lines.index(heading)
        except ValueError:
            lines.extend(['', heading])
            start = len(lines) - 1

        end = len(lines)
        for index in range(start + 1, len(lines)):
            if lines[index].startswith('## '):
                end = index
                break

        task_lines = [self.task_line(task) for task in self.tasks]
        new_section = [heading, *task_lines]
        if end < len(lines):
            new_section.append('')
        rebuilt = lines[:start] + new_section + lines[end:]

        try:
            TASKS_PATH.write_text('\n'.join(rebuilt).rstrip() + '\n')
        except OSError:
            self.message = 'Task file could not be saved.'
            return False
        return True

    def open(self):
        self.active = True
        self.entry = ''
        self.message = ''
        self.load_tasks()
        self.maybe_award_completion()
        self.scroll = max(0, min(self.index, max(0, len(self.tasks) - 7)))

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return self.active

        if not self.active:
            return False

        if event.key == pygame.K_ESCAPE:
            self.active = False
            self.entry = ''
            return True
        if event.key == pygame.K_RETURN:
            self.add_task()
            return True
        if event.key == pygame.K_BACKSPACE:
            self.entry = self.entry[:-1]
            return True
        if event.key == pygame.K_UP:
            self.move_selection(-1)
            return True
        if event.key == pygame.K_DOWN:
            self.move_selection(1)
            return True
        if event.key == pygame.K_SPACE and not self.entry:
            self.toggle_selected()
            return True
        if event.key == pygame.K_DELETE and not self.entry:
            self.delete_selected()
            return True
        if event.key == pygame.K_TAB:
            self.entry += '    '
            return True

        typed = getattr(event, 'unicode', '')
        if typed and typed.isprintable() and len(self.entry) < 140:
            self.entry += typed
            return True

        return True

    def add_task(self):
        cleaned = ' '.join(self.entry.strip().lstrip('-').strip().split())
        if not cleaned:
            self.message = 'Type a task first.'
            return

        self.tasks.append({'done': False, 'text': cleaned})
        self.index = len(self.tasks) - 1
        if self.write_tasks():
            self.entry = ''
            self.message = 'Task added.'
            self.load_tasks()
            self.scroll = max(0, len(self.tasks) - 7)

    def move_selection(self, step):
        if not self.tasks:
            return
        self.index = (self.index + step) % len(self.tasks)
        if self.index < self.scroll:
            self.scroll = self.index
        visible = self.visible_count()
        if self.index >= self.scroll + visible:
            self.scroll = self.index - visible + 1

    def toggle_selected(self):
        if not self.tasks:
            self.message = 'No tasks yet.'
            return
        self.tasks[self.index]['done'] = not self.tasks[self.index]['done']
        if self.write_tasks():
            self.message = 'Task updated.'
            self.load_tasks()
            self.maybe_award_completion()

    def delete_selected(self):
        if not self.tasks:
            self.message = 'No tasks yet.'
            return
        del self.tasks[self.index]
        self.index = max(0, min(self.index, len(self.tasks) - 1))
        if self.write_tasks():
            self.message = 'Task deleted.'
            self.load_tasks()

    def today_completed(self):
        return bool(self.tasks) and all(task['done'] for task in self.tasks)

    def rewarded_today(self):
        return self.today_key() in self.player.daily_task_reward_dates

    def maybe_award_completion(self):
        if not self.today_completed() or self.rewarded_today():
            return False

        self.player.daily_task_reward_dates.add(self.today_key())
        self.player.daily_reward_inventory[DAILY_REWARD_ITEM] = (
            self.player.daily_reward_inventory.get(DAILY_REWARD_ITEM, 0) + 1
        )
        self.player.strength += 1
        self.save_reward_state()
        self.message = f'Earned {DAILY_REWARD_NAME} item and +1 Strength.'
        return True

    def reward_count(self):
        return self.player.daily_reward_inventory.get(DAILY_REWARD_ITEM, 0)

    def visible_count(self):
        return 5

    def wrap_text(self, text, font, max_width, max_lines=None):
        words = text.split()
        lines = []
        current = ''

        for word in words:
            if font.size(word)[0] > max_width:
                if current:
                    lines.append(current)
                    current = ''
                lines.extend(self.break_long_word(word, font, max_width))
                continue

            candidate = word if not current else f'{current} {word}'
            if font.size(candidate)[0] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word

        if current:
            lines.append(current)

        if max_lines and len(lines) > max_lines:
            lines = lines[:max_lines]
            while lines[-1] and font.size(lines[-1] + '...')[0] > max_width:
                lines[-1] = lines[-1][:-1].rstrip()
            lines[-1] = lines[-1] + '...'

        return lines or ['']

    def break_long_word(self, word, font, max_width):
        parts = []
        current = ''
        for char in word:
            candidate = current + char
            if current and font.size(candidate)[0] > max_width:
                parts.append(current)
                current = char
            else:
                current = candidate
        if current:
            parts.append(current)
        return parts

    def display_prompt(self):
        status = f'{DAILY_REWARD_NAME} claimed' if self.rewarded_today() else 'Desk'
        help_surf = self.tiny_font.render(f'T tasks | {status}', False, INK)
        help_rect = help_surf.get_rect(topright=(SCREEN_WIDTH - 14, 46)).inflate(16, 8)
        pygame.draw.rect(self.display_surface, (238, 213, 164), help_rect, border_radius=5)
        self.display_surface.blit(help_surf, (help_rect.left + 8, help_rect.top + 4))

    def display(self):
        if not self.active:
            return

        self.load_tasks()
        self.maybe_award_completion()
        shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 110))
        self.display_surface.blit(shade, (0, 0))

        panel = pygame.Rect(150, 88, SCREEN_WIDTH - 300, SCREEN_HEIGHT - 176)
        pygame.draw.rect(self.display_surface, PANEL_SHADOW, panel.move(6, 7), border_radius=8)
        pygame.draw.rect(self.display_surface, PANEL, panel, border_radius=8)
        pygame.draw.rect(self.display_surface, PANEL_DARK, panel, 4, border_radius=8)

        title = self.font.render('Daily Desk', False, INK)
        self.display_surface.blit(title, (panel.left + 24, panel.top + 18))
        date_surf = self.tiny_font.render(f'Today: {date.today().isoformat()}', False, MUTED)
        self.display_surface.blit(date_surf, (panel.left + 24, panel.top + 54))
        stats = self.tiny_font.render(
            f'Strength {self.player.strength} | Strawberries {self.reward_count()}',
            False,
            SUCCESS if self.rewarded_today() else MUTED)
        self.display_surface.blit(stats, (panel.left + 230, panel.top + 54))

        list_rect = pygame.Rect(panel.left + 24, panel.top + 86, panel.width - 48, 288)
        pygame.draw.rect(self.display_surface, (248, 233, 196), list_rect, border_radius=6)
        pygame.draw.rect(self.display_surface, PANEL_DARK, list_rect, 2, border_radius=6)

        if not self.tasks:
            empty = self.small_font.render('No tasks for today.', False, MUTED)
            self.display_surface.blit(empty, (list_rect.left + 16, list_rect.top + 20))
        else:
            y = list_rect.top + 12
            visible = self.visible_count()
            for visible_i, task in enumerate(self.tasks[self.scroll:self.scroll + visible], start=self.scroll):
                row = pygame.Rect(list_rect.left + 10, y, list_rect.width - 20, 50)
                selected = visible_i == self.index
                color = (238, 219, 174) if selected else (248, 233, 196)
                pygame.draw.rect(self.display_surface, color, row, border_radius=4)
                if selected:
                    pygame.draw.rect(self.display_surface, ACCENT, row, 2, border_radius=4)
                marker = '[x]' if task['done'] else '[ ]'
                text_color = SUCCESS if task['done'] else INK
                marker_surf = self.small_font.render(marker, False, text_color)
                self.display_surface.blit(marker_surf, (row.left + 10, row.top + 6))

                text_x = row.left + 54
                text_width = row.right - text_x - 10
                lines = self.wrap_text(task['text'], self.tiny_font, text_width, max_lines=2)
                line_y = row.top + 6
                for line in lines:
                    task_surf = self.tiny_font.render(line, False, text_color)
                    self.display_surface.blit(task_surf, (text_x, line_y))
                    line_y += task_surf.get_height() + 1
                y += 54

        input_rect = pygame.Rect(panel.left + 24, list_rect.bottom + 18, panel.width - 48, 44)
        pygame.draw.rect(self.display_surface, (255, 247, 221), input_rect, border_radius=5)
        pygame.draw.rect(self.display_surface, PANEL_DARK, input_rect, 2, border_radius=5)
        input_text = self.entry if self.entry else 'type a task, then press Enter...'
        input_color = INK if self.entry else MUTED
        input_surf = self.small_font.render(input_text, False, input_color)
        self.display_surface.blit(input_surf, (input_rect.left + 12, input_rect.top + 11))

        if self.message:
            msg_surf = self.tiny_font.render(self.message, False, ACCENT)
            self.display_surface.blit(msg_surf, (panel.left + 24, input_rect.bottom + 12))
        elif self.rewarded_today():
            msg_surf = self.tiny_font.render(f'Today complete: {DAILY_REWARD_NAME} stored in chest.', False, SUCCESS)
            self.display_surface.blit(msg_surf, (panel.left + 24, input_rect.bottom + 12))

        footer = 'Up/Down select | Space done | Delete remove | Enter add | Esc close'
        footer_surf = self.tiny_font.render(footer, False, MUTED)
        self.display_surface.blit(footer_surf, (panel.left + 24, panel.bottom - 36))
