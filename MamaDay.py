import pygame
import random
import os
import time
import math

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
    max_r = int(17 * size) + 2
    for t in range(0, 628, 15):
        t_rad = t / 100
        hx = 16 * math.sin(t_rad)**3
        hy = -(13 * math.cos(t_rad) - 5 * math.cos(2*t_rad) - 2 * math.cos(3*t_rad) - math.cos(4*t_rad))
        points.append((max_r + hx * size, max_r + hy * size))
    temp_surf = pygame.Surface((max_r * 2, max_r * 2), pygame.SRCALPHA)
    pygame.draw.polygon(temp_surf, (*color, alpha), points)
    surf.blit(temp_surf, (x - max_r, y - max_r))

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
    base_path = os.path.dirname(os.path.abspath(__file__))
    IMAGE_FOLDER = os.path.join(base_path, "images")
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
    heart_colors = [
        COLOR_ROSE_GOLD, COLOR_SOFT_PINK, COLOR_DEEP_CHERRY,
        (255, 182, 193), (221, 160, 221), (231, 188, 187)
    ]
    color_idx = 0
    while len(imgs) < 9:
        surf = pygame.Surface((SIDE-10, SIDE-10), pygame.SRCALPHA)
        color = heart_colors[color_idx % len(heart_colors)]
        draw_vector_heart(surf, (SIDE-10)//2, (SIDE-10)//2, (SIDE-10)/40.0, color)
        imgs.append(surf)
        color_idx += 1
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
start_time, paused_time, modal_image, modal_start_time = 0, 0, None, 0

try:
    font_win = pygame.font.SysFont("georgia", 50, italic=True)
    font_ui = pygame.font.SysFont("verdana", 22)
except:
    font_win = pygame.font.SysFont("arial", 46, bold=True)
    font_ui = pygame.font.SysFont("arial", 22)

# --- Main Loop ---
running = True
while running:
    dt = clock.tick(60) / 1000
    
    if game_state == "MENU":
        romantic_bg.draw(screen, dt)
        title = font_win.render("Mom's Memory Challenge", True, COLOR_DEEP_CHERRY)
        screen.blit(title, (WIDTH//2 - title.get_width()//2, 50))
        for i, opt in enumerate(options):
            rect = pygame.Rect(WIDTH//2 - 160, 150 + i*65, 320, 50)
            pygame.draw.rect(screen, COLOR_SOFT_PINK if i == selected_idx else COLOR_CREAM, rect, border_radius=10)
            pygame.draw.rect(screen, COLOR_DEEP_CHERRY, rect, 2, border_radius=10)
            txt = font_ui.render(opt["text"], True, COLOR_DEEP_CHERRY)
            screen.blit(txt, (rect.centerx - txt.get_width()//2, rect.centery - txt.get_height()//2))
        
        start_btn = pygame.Rect(WIDTH//2 - 70, 360, 140, 50)
        pygame.draw.rect(screen, COLOR_DEEP_CHERRY, start_btn, border_radius=25)
        btn_txt = font_ui.render("START", True, COLOR_CREAM)
        screen.blit(btn_txt, (start_btn.centerx - btn_txt.get_width()//2, start_btn.centery - btn_txt.get_height()//2))

    elif game_state in ["PLAYING", "MODAL"]:
        romantic_bg.draw(screen, dt)
        
        # Timer
        limit = options[selected_idx]["limit"]
        if limit and game_state == "PLAYING":
            elapsed = (time.time() - start_time) - paused_time
            remaining = max(0, limit - elapsed)
            bar_h = int((remaining / limit) * (HEIGHT - 40))
            pygame.draw.rect(screen, COLOR_DEEP_CHERRY, (20, 20, 20, HEIGHT - 40), 2)
            pygame.draw.rect(screen, (220, 50, 50), (22, 20 + (HEIGHT - 40 - bar_h), 16, bar_h))
            if remaining <= 0: game_state = "GAMEOVER"

        # Match Logic
        if game_state == "PLAYING" and first and second and wait_timer > 0:
            wait_timer -= dt
            if wait_timer <= 0:
                if first["image"] == second["image"]:
                    first["matched"] = second["matched"] = True
                    modal_image, modal_start_time, game_state = first["image"], time.time(), "MODAL"
                else:
                    first["flipped"] = second["flipped"] = False
                first = second = None

        # Draw Tiles with Flip Animation
        for card in cards:
            if card["matched"]: continue
            
            # Smooth flip logic
            target = 1.0 if card["flipped"] or card["matched"] else 0.0
            if card["flip_proc"] != target:
                card["flip_proc"] += (target - card["flip_proc"]) * 10 * dt
                if abs(card["flip_proc"] - target) < 0.01: card["flip_proc"] = target

            # Calculate flip width (the "3D" effect)
            flip_w = abs(math.cos(card["flip_proc"] * math.pi))
            draw_rect = pygame.Rect(0, 0, int(CARD_W * flip_w), CARD_H)
            draw_rect.center = card["rect"].center

            if card["flip_proc"] > 0.5: # Front Side
                pygame.draw.rect(screen, COLOR_CREAM, draw_rect, border_radius=8)
                if flip_w > 0.1:
                    scaled_img = pygame.transform.scale(card["image"], (int((SIDE-10)*flip_w), SIDE-10))
                    screen.blit(scaled_img, (draw_rect.centerx - scaled_img.get_width()//2, draw_rect.centery - scaled_img.get_height()//2))
            else: # Back Side
                pygame.draw.rect(screen, COLOR_CARD_BACK, draw_rect, border_radius=8)
                beat = (1.1 + math.sin(time.time()*3 + card["seed"]*10)*0.1) * flip_w
                draw_vector_heart(screen, draw_rect.centerx, draw_rect.centery, beat, COLOR_CREAM, 180)

        # Full Screen Fade Effect
        if game_state == "MODAL":
            m_elapsed = time.time() - modal_start_time
            if m_elapsed < 2.0:
                progress = m_elapsed / 2.0
                size_val = SIDE + (progress * (HEIGHT - SIDE - 20))
                alpha = max(0, 255 - int(progress * 255))
                scaled = pygame.transform.smoothscale(modal_image, (int(size_val), int(size_val)))
                scaled.set_alpha(alpha)
                screen.blit(scaled, scaled.get_rect(center=(WIDTH//2, HEIGHT//2)))
            else:
                paused_time += 2.0
                game_state = "PLAYING"
                if all(c["matched"] for c in cards): game_state = "WIN"

    elif game_state in ["WIN", "GAMEOVER"]:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((255, 255, 255, 180))
        screen.blit(overlay, (0,0))
        msg = REWARDS[selected_idx] if game_state == "WIN" else "Time Ran Out!"
        txt = font_win.render(msg, True, COLOR_DEEP_CHERRY)
        screen.blit(txt, (WIDTH//2 - txt.get_width()//2, HEIGHT//2 - 40))
        retry = pygame.Rect(WIDTH//2 - 80, HEIGHT//2 + 60, 160, 50)
        pygame.draw.rect(screen, COLOR_DEEP_CHERRY, retry, border_radius=25)
        btn_txt = font_ui.render("MENU", True, COLOR_CREAM)
        screen.blit(btn_txt, (retry.centerx - btn_txt.get_width()//2, retry.centery - btn_txt.get_height()//2))

    for event in pygame.event.get():
        if event.type == pygame.QUIT: running = False
        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = pygame.mouse.get_pos()
            if game_state == "MENU":
                for i in range(3):
                    if pygame.Rect(WIDTH//2 - 160, 150 + i*65, 320, 50).collidepoint(mx, my): selected_idx = i
                if pygame.Rect(WIDTH//2 - 70, 360, 140, 50).collidepoint(mx, my):
                    cards, game_state, start_time, paused_time = create_board(game_images), "PLAYING", time.time(), 0
            elif game_state == "PLAYING" and wait_timer <= 0:
                for card in cards:
                    if card["rect"].collidepoint(mx, my) and not card["flipped"] and not card["matched"]:
                        card["flipped"] = True
                        if not first: first = card
                        elif not second: second, wait_timer = card, 0.7
            elif game_state in ["WIN", "GAMEOVER"]:
                if retry.collidepoint(mx, my): game_state = "MENU"

    pygame.display.flip()
pygame.quit()