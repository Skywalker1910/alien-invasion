class settings():
	
	def __init__(self):
		"""Initialize the game's settings."""
		# Screen settings        
		self.screen_width = 1200
		self.screen_height = 800
		self.bg_color = (230, 230, 230)
		
		#self.ship_speed_factor =1.5

		#Bullet settings
		#self.bullet_speed_factor = 1
		self.bullet_width = 3
		self.bullet_height= 15
		self.bullet_color = 230,0,0
		self.bullets_allowed = 3

		#Alien bullet settings
		self.alien_bullet_width = 3
		self.alien_bullet_height = 10
		self.alien_bullet_color = (255, 0, 0)
		self.alien_bullet_speed_factor = 2
		self.alien_shooting_frequency = 0.001  # Much lower probability per frame
		self.max_alien_bullets = 3  # Limit total alien bullets on screen

		#Alien settings
		#self.alien_speed_factor = 1
		self.fleet_drop_speed = 10
		#fleet_direction of 1 represents right; -1 represents left.
		#self.fleet_direction = 1

		#ship settings
		#self.ship_speed_factor = 1.5
		self.ship_limit = 3

		#How quickly the game speeds up
		self.speedup_scale = 1.1
		#How quickly the alien point values increase
		self.score_scale = 1.5

		self.initialize_dynamic_settings()

	def initialize_dynamic_settings(self):
		"""Initialize settings that change throughout the game."""
		self.ship_speed_factor = 1.5
		self.bullet_speed_factor = 3
		self.alien_speed_factor = 1

		#fleet direction of 1 represent right; -1 represents left
		self.fleet_direction = 1

		#scoring
		self.alien_points = 50
		
		# Reset alien shooting frequency to base level
		self.alien_shooting_frequency = 0.001

	def increase_speed(self):
		"""Increase speed settings."""
		self.ship_speed_factor *= self.speedup_scale
		self.bullet_speed_factor *= self.speedup_scale
		self.alien_speed_factor *= self.speedup_scale

		self.alien_points = int(self.alien_points * self.score_scale)
		
		# Slightly increase alien shooting frequency each level (but keep it reasonable)
		self.alien_shooting_frequency = min(self.alien_shooting_frequency * 1.2, 0.005)
		