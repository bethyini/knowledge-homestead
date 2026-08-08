import pygame
import sys
import time
from settings import *
from level import Level


class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption(WINDOW_TITLE)
        self.set_app_icon()
        self.clock = pygame.time.Clock()
        self.level = Level()

    def set_app_icon(self):
        icon_path = PROJECT_ROOT / 'graphics' / 'ui' / 'app_icon.png'
        if not icon_path.exists():
            return
        try:
            pygame.display.set_icon(pygame.image.load(str(icon_path)).convert_alpha())
        except pygame.error:
            pass

    def run(self):
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                self.level.handle_event(event)

            dt = self.clock.tick(FPS) / 1000
            self.level.run(dt)
            pygame.display.update()


if __name__ == '__main__':
    game = Game()
    game.run()
