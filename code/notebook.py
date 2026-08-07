import pygame

from settings import NOTEBOOK_HEADING, NOTEBOOK_PATH, NOTEBOOK_TITLE, SCREEN_HEIGHT, SCREEN_WIDTH
from support import get_path


PANEL = (244, 229, 188)
PANEL_DARK = (96, 62, 39)
PANEL_SHADOW = (45, 31, 24)
INK = (35, 25, 20)
MUTED = (92, 76, 60)
ACCENT = (152, 84, 38)
SUCCESS = (47, 111, 78)
WARNING = (155, 58, 48)

NOTEBOOK_TEMPLATE = f"""# {NOTEBOOK_HEADING}

## Key Facts
"""


class PlayerNotebook:
    def __init__(self):
        self.display_surface = pygame.display.get_surface()
        self.font = pygame.font.Font(get_path('../font/LycheeSoda.ttf'), 30)
        self.small_font = pygame.font.Font(get_path('../font/LycheeSoda.ttf'), 22)
        self.tiny_font = pygame.font.Font(get_path('../font/LycheeSoda.ttf'), 18)
        self.micro_font = pygame.font.Font(get_path('../font/LycheeSoda.ttf'), 15)
        self.active = False
        self.entry = ''
        self.message = ''
        self.scroll = 0
        self.facts = []
        self.ensure_file()
        self.load_facts()

    def ensure_file(self):
        if not NOTEBOOK_PATH.exists():
            NOTEBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
            NOTEBOOK_PATH.write_text(NOTEBOOK_TEMPLATE)

        self.repair_file_structure()

    def repair_file_structure(self):
        try:
            text = NOTEBOOK_PATH.read_text()
        except OSError:
            return

        if '## Key Facts' in text:
            return

        lines = text.splitlines()
        title = f'# {NOTEBOOK_HEADING}'
        facts = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('# '):
                title = stripped
            elif stripped.startswith('- '):
                facts.append(stripped)

        rebuilt = [title, '', '## Key Facts', '', *facts]

        NOTEBOOK_PATH.write_text('\n'.join(rebuilt).rstrip() + '\n')

    def load_facts(self):
        try:
            text = NOTEBOOK_PATH.read_text()
        except OSError:
            self.facts = []
            self.message = 'Notebook file could not be read.'
            return

        facts = []
        in_key_facts = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped == '## Key Facts':
                in_key_facts = True
                continue
            if in_key_facts and stripped.startswith('## '):
                break
            if in_key_facts and stripped.startswith('- '):
                facts.append(stripped[2:].strip())

        self.facts = facts

    def append_fact(self, fact, quiet=False):
        cleaned = self.clean_fact(fact)
        if not cleaned:
            return False

        try:
            text = NOTEBOOK_PATH.read_text() if NOTEBOOK_PATH.exists() else NOTEBOOK_TEMPLATE
        except OSError:
            if not quiet:
                self.message = 'Notebook file could not be read.'
            return False

        if self.fact_exists(cleaned, text):
            if not quiet:
                self.message = 'Already recorded.'
            return False

        lines = text.splitlines()
        if '## Key Facts' not in lines:
            if lines and lines[-1].strip():
                lines.append('')
            lines.extend(['## Key Facts', ''])

        header_index = lines.index('## Key Facts')
        insert_at = len(lines)
        for index in range(header_index + 1, len(lines)):
            if lines[index].startswith('## '):
                insert_at = index
                break

        while insert_at > header_index + 1 and not lines[insert_at - 1].strip():
            insert_at -= 1

        if insert_at > 0 and lines[insert_at - 1].strip() and insert_at == len(lines):
            lines.append('')
            insert_at = len(lines) - 1

        lines.insert(insert_at, f'- {cleaned}')
        if insert_at + 1 < len(lines) and lines[insert_at + 1].startswith('## '):
            lines.insert(insert_at + 1, '')
        try:
            NOTEBOOK_PATH.write_text('\n'.join(lines).rstrip() + '\n')
        except OSError:
            if not quiet:
                self.message = 'Notebook file could not be saved.'
            return False

        if not quiet:
            self.message = 'Recorded.'
        return True

    def clean_fact(self, fact):
        cleaned = ' '.join(fact.strip().lstrip('-').strip().split())
        if cleaned and cleaned[-1] not in '.!?':
            cleaned += '.'
        return cleaned

    def fact_exists(self, fact, text):
        target = self.normalize_fact(fact)
        for line in text.splitlines():
            if line.strip().startswith('- ') and self.normalize_fact(line.strip()[2:]) == target:
                return True
        return False

    def normalize_fact(self, fact):
        return fact.strip().rstrip('.!?').lower()

    def toggle(self):
        self.active = not self.active
        self.entry = ''
        self.message = ''
        if self.active:
            self.load_facts()
            self.scroll = max(0, len(self.facts) - 9)

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return self.active

        if event.key == pygame.K_n and not self.active:
            self.toggle()
            return True

        if not self.active:
            return False

        if event.key == pygame.K_ESCAPE:
            self.active = False
            self.entry = ''
            return True
        if event.key == pygame.K_RETURN:
            if self.append_fact(self.entry):
                self.entry = ''
                self.load_facts()
                self.scroll = max(0, len(self.facts) - 9)
            return True
        if event.key == pygame.K_BACKSPACE:
            self.entry = self.entry[:-1]
            return True
        if event.key == pygame.K_UP:
            self.scroll = max(0, self.scroll - 1)
            return True
        if event.key == pygame.K_DOWN:
            self.scroll = min(max(0, len(self.facts) - 1), self.scroll + 1)
            return True
        if event.key == pygame.K_TAB:
            self.entry += '    '
            return True
        typed = getattr(event, 'unicode', '')
        if typed and typed.isprintable() and len(self.entry) < 180:
            self.entry += typed
            return True

        return True

    def display_prompt(self):
        help_surf = self.tiny_font.render('N notebook', False, INK)
        help_rect = help_surf.get_rect(topright=(SCREEN_WIDTH - 14, 14)).inflate(16, 8)
        pygame.draw.rect(self.display_surface, (238, 213, 164), help_rect, border_radius=5)
        self.display_surface.blit(help_surf, (help_rect.left + 8, help_rect.top + 4))

    def display(self):
        if not self.active:
            return

        self.load_facts()
        shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 110))
        self.display_surface.blit(shade, (0, 0))

        panel = pygame.Rect(132, 76, SCREEN_WIDTH - 264, SCREEN_HEIGHT - 152)
        pygame.draw.rect(self.display_surface, PANEL_SHADOW, panel.move(6, 7), border_radius=8)
        pygame.draw.rect(self.display_surface, PANEL, panel, border_radius=8)
        pygame.draw.rect(self.display_surface, PANEL_DARK, panel, 4, border_radius=8)

        title = self.font.render(NOTEBOOK_TITLE, False, INK)
        self.display_surface.blit(title, (panel.left + 24, panel.top + 18))
        path_surf = self.tiny_font.render(str(NOTEBOOK_PATH), False, MUTED)
        self.display_surface.blit(path_surf, (panel.left + 24, panel.top + 54))

        facts_rect = pygame.Rect(panel.left + 24, panel.top + 88, panel.width - 48, 330)
        pygame.draw.rect(self.display_surface, (248, 233, 196), facts_rect, border_radius=6)
        pygame.draw.rect(self.display_surface, PANEL_DARK, facts_rect, 2, border_radius=6)

        header = self.small_font.render('Key Facts', False, INK)
        self.display_surface.blit(header, (facts_rect.left + 16, facts_rect.top + 12))

        y = facts_rect.top + 48
        visible = self.visible_facts(facts_rect.height - 62)
        for fact in self.facts[self.scroll:self.scroll + visible]:
            y = self.draw_wrapped(f'- {fact}', self.tiny_font, INK, facts_rect.left + 16, y, facts_rect.width - 32)
            y += 2

        if len(self.facts) > visible:
            count = self.tiny_font.render(f'{min(self.scroll + visible, len(self.facts))}/{len(self.facts)}', False, MUTED)
            self.display_surface.blit(count, (facts_rect.right - count.get_width() - 14, facts_rect.bottom - 26))

        input_rect = pygame.Rect(panel.left + 24, facts_rect.bottom + 18, panel.width - 48, 96)
        pygame.draw.rect(self.display_surface, (255, 247, 221), input_rect, border_radius=6)
        pygame.draw.rect(self.display_surface, PANEL_DARK, input_rect, 2, border_radius=6)
        label = self.small_font.render('New Fact', False, INK)
        self.display_surface.blit(label, (input_rect.left + 14, input_rect.top + 10))
        text = self.entry if self.entry else 'write a durable fact...'
        color = INK if self.entry else MUTED
        self.draw_wrapped(text, self.small_font, color, input_rect.left + 14, input_rect.top + 42, input_rect.width - 28)

        if self.message:
            msg = self.tiny_font.render(self.message, False, SUCCESS if self.message == 'Recorded.' else WARNING)
            self.display_surface.blit(msg, (panel.left + 24, panel.bottom - 44))

        footer = self.tiny_font.render('Enter save | Up/Down scroll | Esc close', False, MUTED)
        self.display_surface.blit(footer, (panel.right - footer.get_width() - 24, panel.bottom - 44))

    def visible_facts(self, height):
        return max(1, height // (self.tiny_font.get_height() + 10))

    def draw_wrapped(self, text, font, color, x, y, width):
        for line in self.wrap_text(text, font, width):
            surf = font.render(line, False, color)
            self.display_surface.blit(surf, (x, y))
            y += surf.get_height() + 4
        return y

    def wrap_text(self, text, font, width):
        lines = []
        for paragraph in text.split('\n'):
            words = paragraph.split(' ')
            current = ''
            for word in words:
                candidate = word if not current else current + ' ' + word
                if font.size(candidate)[0] <= width:
                    current = candidate
                else:
                    if current:
                        lines.append(current)
                    current = word
            if current:
                lines.append(current)
        return lines
