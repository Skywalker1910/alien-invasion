import pygame
from pygame.sprite import Sprite
import random

class AlienBullet(Sprite):
    """A class to manage bullets fired by aliens"""

    def __init__(self, ai_settings, screen, alien):
        """Create an alien bullet object at the alien's current position"""
        super().__init__()
        self.screen = screen

        self.rect = pygame.Rect(0, 0, ai_settings.alien_bullet_width, ai_settings.alien_bullet_height)
        
        self.rect.centerx = alien.rect.centerx
        self.rect.bottom = alien.rect.bottom
        
        # Store bullet's position as a decimal value
        self.y = float(self.rect.y)

        self.color = ai_settings.alien_bullet_color
        self.speed_factor = ai_settings.alien_bullet_speed_factor

    def update(self):
        """Move bullet down the screen."""
        # Update decimal position of the bullet
        self.y += self.speed_factor
        # Update the rect position
        self.rect.y = self.y

    def draw_bullet(self):
        """Draw the bullet to the screen"""
        pygame.draw.rect(self.screen, self.color, self.rect)