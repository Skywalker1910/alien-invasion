import sys
import pygame
from settings import settings
from game_stats import GameStats
from scoreboard import Scoreboard
from button import Button
from ship import Ship
from alien import Alien
import game_funtions as gf 
from pygame.sprite import Group

def run_game():

	pygame.init()
	ai_settings = settings()
	screen=pygame.display.set_mode((ai_settings.screen_width, ai_settings.screen_height))
	pygame.display.set_caption("ALIEN INVASION")

	#Make the play button.
	play_button = Button(ai_settings, screen, "Play")

	# Create an instance to store game statistics and create a scoreboard.
	stats = GameStats(ai_settings)
	sb = Scoreboard(ai_settings, screen, stats)

	# Make a ship, a group of bullets and group of aliens.
	ship = Ship(ai_settings,screen)
	alien = Alien (ai_settings, screen)
	bullets = Group()
	aliens = Group()
	alien_bullets = Group()  # Group for alien bullets
	
	
	#Creating a fleet of aliens
	gf.create_fleet(ai_settings, screen, ship, aliens)
		
	while True:
		
		gf.check_events(ai_settings, screen, stats, sb, play_button, ship, aliens, bullets, alien_bullets)
		if stats.game_active:
			ship.update()
			gf.update_bullets(ai_settings, screen, stats, sb, ship, aliens, bullets)
			gf.update_aliens(ai_settings, screen, stats, sb, ship, aliens, bullets, alien_bullets)
			gf.update_alien_bullets(ai_settings, screen, stats, sb, ship, alien_bullets, aliens, bullets)
		
		gf.update_screen(ai_settings, screen, stats, sb, ship, aliens, bullets, alien_bullets, play_button)
		#alien.blitme()

run_game()