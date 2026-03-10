import pygame
import random
import os
import time
import math
import asyncio  # Required for web compatibility

# --- Reward Configuration ---
REWARDS = {
    0: "A Dinner Date at the Fanciest Place in Town!",
    1: "A Special Night at the Keg Mansion!",
    2: "A Royal Feast at Burger King!"
}

# --- Configuration & Romantic Palette ---
pygame.init()
WIDTH, HEIGHT = 998, 448 
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()

COLOR_BG_GRADIENT = (255, 240, 245) 
COLOR_ROSE_GOLD = (231, 188, 187)
COLOR_DEEP_CHERRY = (120, 0, 20)
COLOR_CREAM = (255, 253, 245)
COLOR_SOFT_PINK = (255, 215, 225)
COLOR_CARD_BACK = (255, 140, 180)

TIMER_BAR_WIDTH = 60 
ROWS, COLS = 3, 6 
PADDING = 12

MAX_SIDE_H = (HEIGHT - (PADDING * (ROWS + 1))) // ROWS
MAX_SIDE_W = (WIDTH - TIMER_BAR_WIDTH - (PADDING * (COLS + 1))) // COLS
SIDE = min(MAX_SIDE_H, MAX_SIDE_W)
CARD_W = CARD_H = SIDE

# --- Vector Graphic Helpers ---
def draw_vector_heart(surf, x, y, size, color, alpha=255):
    points = []
    for t in range(0, 628, 15):
        t_rad = t / 100
        hx = 16 * math.sin(t_rad)**3
        hy = -(13 * math.cos(t_rad) - 5 * math.cos(2*t_rad) - 2 * math.cos(3*t_rad) - math.cos(4*t_rad))
        points.append((x + hx * size, y + hy * size))
    temp_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    pygame.draw.polygon(temp_surf, (*color, alpha), points)
    surf.blit(temp_surf, (0, 0))

class RomanticBackground:
    def __init__(self):
        self.particles = [{"x": random.randint(0, WIDTH), "y": random.randint(0, HEIGHT), 
                           "size": random.uniform(0.5, 2.5), "speed": random.uniform(20, 50), 
                           "seed": random.random()} for _ in range(12)]
    def draw(self, surf, dt):
        surf.fill(COLOR_BG_GRADIENT)
        for p in self.particles:
            p["y"] -= p["speed"] * dt
            if p["y"] < -50: p["y"] = HEIGHT + 50
            sway = math.sin(time.time() + p["seed"]) * 20
            draw_vector_heart(surf, p["x"] + sway, p["y"], p["size"], COLOR_ROSE_GOLD, 80)

def load_images():
    imgs = []
    IMAGE_FOLDER = "images"
    if os.path.exists(IMAGE_FOLDER):
        valid = (".png", ".jpg", ".jpeg")
        files = [f for f in os.listdir(IMAGE_FOLDER) if f.lower().endswith(valid)]
        files.sort()
        for f in files:
            try:
                img = pygame.image.load(os.path.join(IMAGE_FOLDER, f)).convert_alpha()
                img = pygame.transform.smoothscale(img, (SIDE-10, SIDE-10))
                imgs.append(img)
                if len(imgs) == 9: break
            except: continue
    while len(imgs) < 9:
        surf = pygame.Surface((SIDE-10, SIDE-10), pygame.SRCALPHA)
        pygame.draw.circle(surf, (200, 100, 150), (SIDE//2-5, SIDE//2-5), SIDE//3)
        imgs.append(surf)
    return imgs

def create_board(images):
    deck = images * 2
    random.shuffle(deck)
    cards = []
    grid_w = (COLS * CARD_W) + ((COLS - 1) * PADDING)
    grid_h = (ROWS * CARD_H) + ((ROWS - 1) * PADDING)
    start_x = TIMER_BAR_WIDTH + (WIDTH - TIMER_BAR_WIDTH - grid_w) // 2
    start_y = (HEIGHT - grid_h) // 2
    for i in range(ROWS * COLS):
        col, row = i % COLS, i // COLS
        cards.append({
            "rect": pygame.Rect(start_x + (col * (CARD_W + PADDING)), start_y + (row * (CARD_H + PADDING)), CARD_W, CARD_H),
            "image": deck.pop(), "flipped": False, "matched": False, "flip_proc": 0.0, "seed": random.random()
        })
    return cards

# --- State ---
romantic_bg = RomanticBackground()
game_images = load_images()
options = [{"text": "Fancy Place: 30s", "limit": 30}, {"text": "Keg Mansion: 45s", "limit": 45}, {"text": "Burger King", "limit": None}]
selected_idx, game_state = 0, "MENU"
cards, first, second, wait_timer = [], None, None, 0
start_time, paused_time = 0, 0

# Fonts (Web-safe fallbacks)
try:
    font_win = pygame.font.SysFont("georgia", 50, italic=True)
    font_ui = pygame.font.SysFont("verdana", 22)
except:
    font_win = pygame.font.SysFont("arial", 46, bold=True)
    font_ui = pygame.font.SysFont("arial", 22)

# --- Main Game Loop (Web Optimized) ---
async def main():
    global game_state, selected_idx, cards, first, second, wait_timer, start_time, paused_time
    
    running = True
    while running:
        dt = clock.tick(60) / 1000
        
        if game_state == "MENU":
            romantic_bg.draw(screen, dt)
            title = font_win.render("Mom's Memory Challenge", True, COLOR_DEEP_CHERRY)
            screen.blit(title, (WIDTH//2 - title.get_width()//2, 50))
            
            # Draw options
            for i, opt in enumerate(options):
                rect = pygame.Rect(WIDTH//2 - 160, 150 + i*65, 320, 50)
                pygame.draw.rect(screen, COLOR_SOFT_PINK if i == selected_idx else COLOR_CREAM, rect, border_radius=10)
                pygame.draw.rect(screen, COLOR_DEEP_CHERRY, rect, 2, border_radius=10)
                txt = font_ui.render(opt["text"], True, COLOR_DEEP_CHERRY)
                screen.blit(txt, (rect.centerx - txt.get_width()//2, rect.centery - txt.get_height()//2))
            
            # Draw START Button (Fixed)
            start_btn = pygame.Rect(WIDTH//2 - 70, 360, 140, 50)
            pygame.draw.rect(screen, COLOR_DEEP_CHERRY, start_btn, border_radius=25)
            start_txt = font_ui.render("START", True, COLOR_CREAM)
            screen.blit(start_txt, (start_btn.centerx - start_txt.get_width()//2, start_btn.centery - start_txt.get_height()//2))

        elif game_state == "PLAYING":
            romantic_bg.draw(screen, dt)
            # Add logic for playing state here...
            
        elif game_state == "WON" or game_state == "GAMEOVER":
            # Show end screen rewards
            msg = REWARDS[selected_idx] if game_state == "WON" else "Better luck next time!"
            txt = font_win.render(msg, True, COLOR_DEEP_CHERRY)
            screen.blit(txt, (WIDTH//2 - txt.get_width()//2, HEIGHT//2 - 40))
            
            retry = pygame.Rect(WIDTH//2 - 80, HEIGHT//2 + 60, 160, 50)
            pygame.draw.rect(screen, COLOR_DEEP_CHERRY, retry, border_radius=25)
            btn_txt = font_ui.render("MENU", True, COLOR_CREAM)
            screen.blit(btn_txt, (retry.centerx - btn_txt.get_width()//2, retry.centery - btn_txt.get_height()//2))

        # --- Event Handling ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = pygame.mouse.get_pos()
                if game_state == "MENU":
                    for i in range(3):
                        if pygame.Rect(WIDTH//2 - 160, 150 + i*65, 320, 50).collidepoint(mx, my): 
                            selected_idx = i
                    if pygame.Rect(WIDTH//2 - 70, 360, 140, 50).collidepoint(mx, my):
                        cards, game_state, start_time = create_board(game_images), "PLAYING", time.time()
                elif game_state in ["WON", "GAMEOVER"]:
                    if pygame.Rect(WIDTH//2 - 80, HEIGHT//2 + 60, 160, 50).collidepoint(mx, my):
                        game_state = "MENU"

        pygame.display.flip()
        await asyncio.sleep(0)  # Yield control back to the browser

# Execute the entry point
asyncio.run(main())