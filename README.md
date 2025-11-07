# Alien Invasion Game

A classic 2D space shooter game built with Python and Pygame.

## Description

Alien Invasion is a side-scrolling space shooter where the player controls a ship to defend against waves of descending aliens. The game features progressive difficulty, scoring system, and multiple lives.

## Features

- **Player Controls**: Move ship left/right with arrow keys, shoot with spacebar
- **Enemy Waves**: Aliens move in formation and drop down when hitting screen edges
- **Scoring System**: Points for destroying aliens, with high score tracking
- **Progressive Difficulty**: Game speed increases with each level
- **Lives System**: Player has 3 ships/lives per game
- **Alien Shooting**: Aliens fire back at the player (recently added)

## Recent Enhancements

- ✅ **Alien Shooting Mechanics**: Aliens now shoot projectiles that the player must avoid
- 🔄 **In Progress**: Additional alien types and power-ups
- 📋 **Planned**: Boss aliens, enhanced difficulty scaling, sound effects

## Installation

1. Make sure you have Python installed
2. Install Pygame: `pip install pygame`
3. Clone or download this repository
4. Run the game: `python alien_invasion.py`

## Controls

- **Arrow Keys**: Move ship left and right
- **Spacebar**: Fire bullets
- **Q**: Quit game
- **Mouse**: Click "Play" button to start/restart

## Game Files

- `alien_invasion.py` - Main game loop and initialization
- `settings.py` - Game configuration and settings
- `ship.py` - Player ship class
- `alien.py` - Enemy alien class
- `bullet.py` - Player bullet class
- `alien_bullet.py` - Alien bullet class
- `game_funtions.py` - Core game logic and functions
- `game_stats.py` - Game statistics tracking
- `scoreboard.py` - Score display and UI
- `button.py` - Menu button implementation

## Development

This project uses Git for version control. See commit history for development progress and feature additions.

## License

This project is for educational purposes.