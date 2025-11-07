import sys
from time import sleep
import pygame
from bullet import Bullet
from alien import Alien
from alien_bullet import AlienBullet
import random

def check_keydown_events(event,ai_settings, screen, ship, bullets):

			if event.key == pygame.K_RIGHT:
				ship.moving_right = True
			
			elif event.key == pygame.K_LEFT:
				ship.moving_left = True

			elif event.key == pygame.K_SPACE:
				fire_bullet(ai_settings, screen, ship, bullets)
			elif event.key == pygame.K_q:
				sys.exit()
			elif event.key == pygame.K_t:
				ai_settings.bullet_width = 70

def check_keyup_events(event,ai_settings, screen, ship, bullets):

			if event.key == pygame.K_RIGHT:
					ship.moving_right = False
			elif event.key == pygame.K_LEFT:
					ship.moving_left = False	


def check_events(ai_settings,screen, stats, sb, play_button, ship, aliens, bullets, alien_bullets):

	for event in pygame.event.get():
		if event.type == pygame.QUIT:
			sys.exit()
		elif event.type == pygame.KEYDOWN:
			check_keydown_events(event, ai_settings, screen, ship, bullets)
				
		elif event.type == pygame.KEYUP:	
			check_keyup_events (event,ai_settings, screen, ship, bullets)
		elif event.type == pygame.MOUSEBUTTONDOWN:
			mouse_x, mouse_y = pygame.mouse.get_pos()
			check_play_button(ai_settings, screen, stats, sb, play_button, ship, aliens, bullets, alien_bullets, mouse_x, mouse_y)

def check_play_button(ai_settings, screen, stats, sb, play_button, ship, aliens, bullets, alien_bullets, mouse_x, mouse_y):
	"""Start a new game when the player clicks Play."""
	button_clicked = play_button.rect.collidepoint(mouse_x, mouse_y)
	if button_clicked and not stats.game_active:
		#Reset the game settings.
		ai_settings.initialize_dynamic_settings()
		#Hide the mouse cursor.
		pygame.mouse.set_visible(False)
		#Reset the game statistics.
		stats.reset_stats()
		stats.game_active = True

		#Reset the scoreboard images.
		sb.prep_score()
		sb.prep_high_score()
		sb.prep_level()
		sb.prep_ships()

		#Empty the list of aliens and bullets.
		aliens.empty()
		bullets.empty()
		alien_bullets.empty()

		#Create a new fleet and center the ship.
		create_fleet(ai_settings, screen, ship, aliens)
		ship.center_ship()

def update_screen(ai_settings, screen, stats, sb, ship, aliens, bullets, alien_bullets, play_button):
	"""Update images on the screen and flip to the new screen."""
	screen.fill(ai_settings.bg_color)

	for bullet in bullets.sprites():
		bullet.draw_bullet()
	
	for alien_bullet in alien_bullets.sprites():
		alien_bullet.draw_bullet()

	ship.blitme()
	aliens.draw(screen)
	#alien.blitme()

	#Draw the score information.
	sb.show_score()

	#Draw the play button if the game is inactive.
	if not stats.game_active:
		play_button.draw_button()

	#Make the most recently drawn screen visible.	
	pygame.display.flip()

def update_bullets(ai_settings, screen, stats, sb, ship, aliens, bullets, alien_bullets):
	"""Update position of bullets and delete old bullets"""

	#update bullet position
	bullets.update()

	#Deleting old bullets

	for bullet in bullets.copy():
		if bullet.rect.bottom <= 0:
			bullets.remove(bullet)

	check_bullet_alien_collisions(ai_settings, screen, stats, sb, ship, aliens, bullets, alien_bullets)
		

def check_bullet_alien_collisions(ai_settings, screen, stats, sb, ship, aliens, bullets, alien_bullets):
	#Check for any bullets that have hit aliens.
	#If so, get rid of the bullet and the alien.
	collisions = pygame.sprite.groupcollide(bullets, aliens, True, True)

	if collisions:
		for aliens_hit in collisions.values():
			stats.score += ai_settings.alien_points * len(aliens_hit)
			sb.prep_score()
		check_high_scores(stats, sb)

	if len(aliens)== 0:
		#If entire fleet is destroyed, start a new level.
		bullets.empty()
		alien_bullets.empty()  # Clear alien bullets when level advances
		ai_settings.increase_speed()

		#Increase Level
		stats.level += 1
		sb.prep_level()

		create_fleet(ai_settings, screen, ship, aliens)
	


def fire_bullet(ai_settings, screen, ship, bullets):
	"""Fire limited bullets"""
	#Create a new bullet and add it to the bullets group.
	if len(bullets) < ai_settings.bullets_allowed:
		new_bullet = Bullet(ai_settings, screen, ship)
		bullets.add(new_bullet)

def get_number_aliens_x(ai_settings, alien_width):
	"""Determine the number of aliens that fit in a row."""
	available_space_x = ai_settings.screen_width -2 * alien_width
	number_aliens_x = int (available_space_x / (2 * alien_width))
	return number_aliens_x

def get_number_rows(ai_settings, ship_height, alien_height):
	"""Determine the number of rows of alien that fit on screen."""
	available_space_y = (ai_settings.screen_height-(3 * alien_height) - ship_height)
	number_rows = int (available_space_y / (2 * alien_height))
	return number_rows

def create_alien(ai_settings, screen, aliens, alien_number, row_number):
	"""Create an alien and place it in row."""
	alien = Alien(ai_settings, screen)
	alien_width = alien.rect.width
	alien.x = alien_width + 2 * alien_width * alien_number
	alien.rect.x = alien.x
	alien.rect.y = alien.rect.height + 2 * alien.rect.height * row_number
	aliens.add(alien)

def create_fleet(ai_settings, screen, ship, aliens):
	"""Create a full fleet of aliens"""
	alien = Alien(ai_settings, screen)
	alien_width = alien.rect.width
	available_space_x = ai_settings.screen_width - 2 * alien_width
	#number_alien_x = int (available_space_x /(2 * alien_width))
	number_alien_x = get_number_aliens_x(ai_settings, alien.rect.width)
	number_rows = get_number_rows(ai_settings, ship.rect.height, alien.rect.height)

	for row_number in range(number_rows):
		for alien_number in range(number_alien_x):
			create_alien(ai_settings, screen, aliens, alien_number, row_number)
		
def check_fleet_edges(ai_settings, aliens):
	"""Respond appropriately if any alien have reached an edge."""
	for alien in aliens.sprites():
		if alien.check_edges():
			change_fleet_direction(ai_settings, aliens)
			break

def change_fleet_direction(ai_settings, aliens):
	"""Drop the entire fleet and change the fleet's direction."""
	for alien in aliens.sprites():
		alien.rect.y += ai_settings.fleet_drop_speed
	ai_settings.fleet_direction *= -1	


def ship_hit(ai_settings, screen, stats, sb, ship, aliens, bullets):
	"""Respond to ship being hit by alien."""
	if stats.ships_left > 0:
		#Decrement ships_left
		stats.ships_left -= 1

		#Update scoreboard
		sb.prep_ships()

		#Empty the list of aliens and bullets.
		if aliens is not None:
			aliens.empty()
		if bullets is not None:
			bullets.empty()

		#Create a new fleet and center the ship.
		if aliens is not None:
			create_fleet(ai_settings, screen, ship, aliens)
		ship.center_ship()

		#pause
		sleep(0.5)

	else:
		stats.game_active = False
		pygame.mouse.set_visible(True)

def check_aliens_bottom(ai_settings, screen, stats, sb, ship, aliens, bullets):
	"""Check if any aliens have reaches the bottom of the screen."""
	screen_rect = screen.get_rect()
	for alien in aliens.sprites():
		if alien.rect.bottom >= screen_rect.bottom:
			#Treat this the same as if the ship got hit.
			ship_hit(ai_settings, screen, stats, sb, ship, aliens, bullets)
			break


def update_aliens(ai_settings, screen, stats, sb, ship, aliens, bullets, alien_bullets):
	"""Check if the fleet is at an edge, and then update the position of all aliens in the fleet."""
	check_fleet_edges(ai_settings, aliens)
	aliens.update()

	# Make aliens shoot randomly
	aliens_shoot(ai_settings, screen, aliens, alien_bullets)

	#Look for alien-ship collision
	if pygame.sprite.spritecollideany(ship, aliens):
		ship_hit(ai_settings, screen, stats, sb, ship, aliens, bullets)

	#Look for aliens hitting the bottom of the screen.
	check_aliens_bottom(ai_settings, screen, stats, sb, ship, aliens, bullets)


def check_high_scores(stats, sb):
	"""Check to see if there's a new high score."""
	if stats.score > stats.high_score:
		stats.high_score = stats.score
		sb.prep_high_score()

def alien_fire_bullet(ai_settings, screen, alien, alien_bullets):
	"""Create an alien bullet and add it to the alien bullets group."""
	new_bullet = AlienBullet(ai_settings, screen, alien)
	alien_bullets.add(new_bullet)

def update_alien_bullets(ai_settings, screen, stats, sb, ship, alien_bullets, aliens, bullets):
	"""Update position of alien bullets and check for collisions with ship."""
	alien_bullets.update()
	
	# Remove alien bullets that have disappeared off the bottom of the screen
	for bullet in alien_bullets.copy():
		if bullet.rect.top >= ai_settings.screen_height:
			alien_bullets.remove(bullet)
	
	# Check for player bullets hitting alien bullets (bullets destroy each other)
	bullet_collisions = pygame.sprite.groupcollide(bullets, alien_bullets, True, True)
	
	# Check for alien bullet hitting ship
	if pygame.sprite.spritecollideany(ship, alien_bullets):
		ship_hit(ai_settings, screen, stats, sb, ship, aliens, bullets)
		# Remove all alien bullets after ship is hit
		alien_bullets.empty()

def aliens_shoot(ai_settings, screen, aliens, alien_bullets):
	"""Strategically select aliens to shoot - only front row aliens and limit total bullets."""
	# Don't shoot if we already have max bullets on screen
	if len(alien_bullets) >= ai_settings.max_alien_bullets:
		return
	
	# Get front-row aliens (bottommost aliens in each column)
	front_row_aliens = get_front_row_aliens(aliens)
	
	# Only allow shooting from front row and with very low probability
	for alien in front_row_aliens:
		if random.random() < ai_settings.alien_shooting_frequency:
			alien_fire_bullet(ai_settings, screen, alien, alien_bullets)
			break  # Only one alien shoots per frame maximum

def get_front_row_aliens(aliens):
	"""Get the bottommost alien in each column (front row)."""
	front_row = {}
	
	# Group aliens by x position (column)
	for alien in aliens.sprites():
		x_pos = alien.rect.centerx
		if x_pos not in front_row or alien.rect.bottom > front_row[x_pos].rect.bottom:
			front_row[x_pos] = alien
	
	return list(front_row.values())