import pygame
import random
import os
import time
import math
import asyncio
from enum import Enum, auto
import json
import threading
import io

try:
    import fitz  # pymupdf
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

MENU_PDF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Menu", "Menu.pdf")

try:
    from plyer import vibrator
    HAS_VIBRATOR = True
except ImportError:
    HAS_VIBRATOR = False

try:
    import js
    HAS_JS = True
except ImportError:
    HAS_JS = False

IS_WEB = HAS_JS

def trigger_vibration():
    if HAS_VIBRATOR:
        try: vibrator.vibrate(0.4)
        except: pass
    if HAS_JS:
        try: js.navigator.vibrate(400)
        except: pass

try:
    from google import genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

HAS_VIDEO_LIB = False
if not IS_WEB:
    try:
        cv2 = __import__("cv2")
        np = __import__("numpy")
        HAS_VIDEO_LIB = True
    except ImportError:
        pass

class GameState(Enum):
    ORIENTATION_PROMPT = auto()
    LANDSCAPE_READY = auto()
    MENU = auto()
    PLAYING = auto()
    PLAYING_TRIVIA = auto()
    MODAL = auto()
    GAMEOVER = auto()
    TRANSITION_TO_REWARD = auto()
    PLAY_VIDEO_REWARD = auto()
    NODO_REVEAL = auto()
    WON = auto()
    FINAL_MESSAGE = auto()
    PDF_VIEWER = auto()
    TRIVIA_CORRECT = auto()
    TRIVIA_FAIL_FADE = auto()

TRIVIA_QUESTIONS = [
    {
        "question": "For 5 MINUTES: Which of these is the most essential component of a good nap?",
        "options": ["A) A loud alarm clock", "B) A cozy blanket", "C) Bright sunlight", "D) A strong cup of coffee"],
        "answer": 1
    },
    {
        "question": "For 10 MINUTES: What is the optimal length for a 'power nap'?",
        "options": ["A) 5 minutes", "B) 10-20 minutes", "C) 2 hours", "D) 4 hours"],
        "answer": 1
    },
    {
        "question": "For 15 MINUTES: What is the best place to take a nap?",
        "options": ["A) On a bed of nails", "B) In the kitchen", "C) A comfy couch or bed", "D) While standing up"],
        "answer": 2
    },
    {
        "question": "For 30 MINUTES: If someone interrupts a nap, the correct response is:",
        "options": ["A) Thank them", "B) Give them a chore", "C) Apologize", "D) Go back to sleep"],
        "answer": 3
    },
    {
        "question": "For 1 HOUR: Who is the most deserving of a peaceful nap right now?",
        "options": ["A) The neighbors", "B) The dog", "C) Mom", "D) The TV"],
        "answer": 2
    }
]

dynamic_trivia_loaded = False
pending_trivia_questions = None

def fetch_gemini_trivia():
    global pending_trivia_questions, dynamic_trivia_loaded
    
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not HAS_GEMINI or not api_key:
        return

    try:
        client = genai.Client(api_key=api_key)
        
        prompt = """
        Generate 5 fun, heartwarming, and humorous multiple-choice trivia questions about moms, Mother's Day, and parenting.
        Respond ONLY with a valid JSON array of objects. Do not include markdown formatting or backticks.
        Each object must have exactly this structure:
        {
            "question": "The question text?",
            "options": ["A) Option 1", "B) Option 2", "C) Option 3", "D) Option 4"],
            "answer": 1
        }
        The 'answer' should be the integer index (0-3) of the correct option.
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        
        raw_json = response.text.replace("```json", "").replace("```", "").strip()
            
        new_questions = json.loads(raw_json)
        if len(new_questions) > 0:
            pending_trivia_questions = new_questions
            dynamic_trivia_loaded = True
    except Exception as e:
        print(f"Failed to fetch dynamic trivia: {e}")

try:
    threading.Thread(target=fetch_gemini_trivia, daemon=True).start()
except Exception:
    pass

REWARDS = {
    0: "Enjoy a well-deserved nap!",
    1: "You've earned a relaxing massage!",
    2: "A delicious dinner is waiting for you!"
}

WIDTH, HEIGHT = 450, 800
screen = None
clock = None

pdf_surface = None
pdf_surface_height = 0

COLOR_PAPER_BG = (250, 246, 240)
COLOR_BLUSH = (235, 196, 196)
COLOR_SAGE = (200, 185, 220)
COLOR_TEXT = (94, 80, 80)
COLOR_CREAM = (255, 252, 248)
COLOR_CARD_BACK = (226, 172, 166)
COLOR_SHADOW = (220, 210, 205)

COLOR_SOFT_PINK = COLOR_BLUSH
COLOR_ROSE_GOLD = COLOR_SAGE

GAME_TOP = 55          # horizontal timer bar + gap
GAME_BOTTOM = 50       # auto-win button zone
ROWS, COLS = 6, 3      # worst-case grid (used for SIDE calculation)
PADDING = 10

MAX_SIDE_H = (HEIGHT - GAME_TOP - GAME_BOTTOM - PADDING * (ROWS + 1)) // ROWS
MAX_SIDE_W = (WIDTH - PADDING * (COLS + 1)) // COLS
SIDE = min(MAX_SIDE_H, MAX_SIDE_W)
CARD_W = CARD_H = SIDE

def wrap_text(text, font, max_width):
    words = text.split(' ')
    lines, current = [], ''
    for word in words:
        test = (current + ' ' + word).strip()
        if font.size(test)[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]

def draw_vector_heart(surf, x, y, size, color, alpha=255):
    points = []
    max_r = int(17 * size) + 2
    for t in range(0, 628, 15):
        t_rad = t / 100
        hx = 16 * math.sin(t_rad)**3
        hy = -(13 * math.cos(t_rad) - 5 * math.cos(2*t_rad) - 2 * math.cos(3*t_rad) - math.cos(4*t_rad))
        points.append((max_r + hx * size, max_r + hy * size))
    temp_surf = pygame.Surface((max_r * 2, max_r * 2), pygame.SRCALPHA)
    rgb_color = (color[0], color[1], color[2], alpha)
    pygame.draw.polygon(temp_surf, rgb_color, points)
    surf.blit(temp_surf, (x - max_r, y - max_r))

def draw_crafted_button(screen, rect, text, font, base_color):
    mx, my = pygame.mouse.get_pos()
    is_hover = rect.collidepoint(mx, my)
    offset = 2 if is_hover else 0

    pygame.draw.rect(screen, COLOR_SHADOW, (rect.x + 3, rect.y + 5, rect.width, rect.height), border_radius=6)

    btn_rect = pygame.Rect(rect.x, rect.y - offset, rect.width, rect.height)
    pygame.draw.rect(screen, base_color, btn_rect, border_radius=6)
    pygame.draw.rect(screen, COLOR_CREAM, btn_rect.inflate(-8, -8), width=1, border_radius=4)
    
    lines = wrap_text(text, font, btn_rect.width - 16)
    line_h = font.get_height()
    y = btn_rect.centery - (line_h * len(lines)) // 2
    for line in lines:
        text_surf = font.render(line, True, COLOR_TEXT)
        screen.blit(text_surf, (btn_rect.centerx - text_surf.get_width() // 2, y))
        y += line_h

def draw_soft_text(screen, text, font, color, center_pos):
    shadow = font.render(text, True, COLOR_SHADOW)
    screen.blit(shadow, (center_pos[0] - shadow.get_width()//2 + 2, center_pos[1] - shadow.get_height()//2 + 2))
    text_surf = font.render(text, True, color)
    screen.blit(text_surf, (center_pos[0] - text_surf.get_width()//2, center_pos[1] - text_surf.get_height()//2))

class CraftedBackground:
    def __init__(self):
        self.paper = pygame.Surface((WIDTH, HEIGHT))
        self.paper.fill(COLOR_PAPER_BG)
        for _ in range(3000):
            x, y = random.randint(0, WIDTH), random.randint(0, HEIGHT)
            c = random.choice([(240, 235, 230), (255, 252, 248)])
            self.paper.set_at((x, y), c)
        self.particles = [{"x": random.randint(0, WIDTH), "y": random.randint(0, HEIGHT),
                           "size": random.uniform(0.5, 1.5), "speed": random.uniform(10, 25),
                           "seed": random.random(), "color": random.choice([COLOR_BLUSH, COLOR_SAGE, COLOR_CREAM]),
                           "heart": i % 2 == 0} for i, _ in enumerate(range(25))]

    def draw(self, surf, dt):
        surf.blit(self.paper, (0, 0))
        for p in self.particles:
            p["y"] -= p["speed"] * dt
            if p["y"] < -20: p["y"] = HEIGHT + 20
            sway = math.sin(time.time()*0.5 + p["seed"]*5) * 15
            px, py = int(p["x"] + sway), int(p["y"])
            if p["heart"]:
                draw_vector_heart(surf, px, py, p["size"], p["color"])
            else:
                pygame.draw.circle(surf, p["color"], (px, py), int(p["size"] * 10))

def load_images():
    imgs = []
    IMAGE_FOLDER = os.path.dirname(os.path.abspath(__file__))
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
        (235, 196, 196), (226, 172, 166), (200, 185, 220),
        (245, 230, 210), (210, 180, 180), (215, 200, 230)
    ]
    color_idx = 0
    while len(imgs) < 9:
        surf = pygame.Surface((SIDE-10, SIDE-10), pygame.SRCALPHA)
        color = heart_colors[color_idx % len(heart_colors)]
        draw_vector_heart(surf, (SIDE-10)//2, (SIDE-10)//2, (SIDE-10)/40.0, color)
        imgs.append(surf)
        color_idx += 1
    return imgs

def create_board(images, num_pairs=9):
    deck = images[:num_pairs] * 2
    random.shuffle(deck)
    cards = []

    # Portrait layout: always 3 columns
    if selected_idx == 1:   # Massage: 6 pairs → 3×4
        rows, cols = 4, 3
    else:                   # Dinner: 9 pairs → 3×6
        rows, cols = 6, 3

    grid_w = (cols * CARD_W) + ((cols - 1) * PADDING)
    grid_h = (rows * CARD_H) + ((rows - 1) * PADDING)
    available_h = HEIGHT - GAME_TOP - GAME_BOTTOM
    start_x = (WIDTH - grid_w) // 2
    start_y = GAME_TOP + (available_h - grid_h) // 2
    for i in range(rows * cols):
        col, row = i % cols, i // cols
        cards.append({
            "rect": pygame.Rect(start_x + (col * (CARD_W + PADDING)), start_y + (row * (CARD_H + PADDING)), CARD_W, CARD_H),
            "image": deck.pop(), "flipped": False, "matched": False, "flip_proc": 0.0, "seed": random.random()
        })
    return cards

async def play_video_web(url):
    """Fullscreen HTML5 video over the canvas. Tap anywhere or wait for end."""
    if not IS_WEB:
        return
    try:
        v = js.document.createElement("video")
        v.setAttribute("playsinline", "")
        v.setAttribute("webkit-playsinline", "")
        v.setAttribute("data-done", "0")
        v.setAttribute("onended",     "this.setAttribute('data-done','1')")
        v.setAttribute("onclick",     "this.setAttribute('data-done','1');this.pause()")
        v.setAttribute("ontouchstart","this.setAttribute('data-done','1');this.pause()")
        v.setAttribute("onerror",     "this.setAttribute('data-done','1')")
        v.style.cssText = ("position:fixed;top:0;left:0;width:100%;height:100%;"
                           "z-index:9999;background:#000;object-fit:contain;")
        v.src = url
        js.document.body.appendChild(v)
        v.play()
        while v.getAttribute("data-done") != "1":
            await asyncio.sleep(0.1)
        js.document.body.removeChild(v)
    except Exception as e:
        print("video error:", e)

async def show_online_menu():
    """Full-screen iframe of the restaurant website with a Back button overlay."""
    if not IS_WEB:
        return
    try:
        wrap = js.document.createElement("div")
        wrap.setAttribute("data-done", "0")
        wrap.style.cssText = ("position:fixed;top:0;left:0;width:100%;height:100%;"
                              "z-index:9998;background:#fff;")

        iframe = js.document.createElement("iframe")
        iframe.src = "https://nodoleslieville.ca"
        iframe.style.cssText = "width:100%;height:100%;border:none;"
        wrap.appendChild(iframe)

        btn = js.document.createElement("button")
        btn.textContent = "Back to Menu"
        btn.style.cssText = ("position:fixed;top:12px;right:12px;z-index:10000;"
                             "padding:10px 18px;background:rgb(235,196,196);"
                             "color:rgb(94,80,80);border:none;border-radius:8px;"
                             "font-size:15px;font-weight:bold;cursor:pointer;")
        btn.setAttribute("onclick", "document.getElementById('_menu_wrap').setAttribute('data-done','1')")
        wrap.id = "_menu_wrap"
        wrap.appendChild(btn)

        js.document.body.appendChild(wrap)
        while wrap.getAttribute("data-done") != "1":
            await asyncio.sleep(0.2)
        js.document.body.removeChild(wrap)
    except Exception as e:
        print("menu error:", e)

async def play_video(filepath):
    if not HAS_VIDEO_LIB: return False
    skipped = False
    try:
        cap = cv2.VideoCapture(filepath)
        if not cap.isOpened(): return False
        
        audio_path = os.path.splitext(filepath)[0] + ".mp3"
        if os.path.exists(audio_path):
            pygame.mixer.music.load(audio_path)
            pygame.mixer.music.play()
            
        vid_clock = pygame.time.Clock()
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        
        start_time = time.time()
        skip_rect = pygame.Rect(WIDTH - 120, 20, 100, 40)
        last_surf = None
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break
            
            skip_pressed = False
            for event in pygame.event.get():
                if event.type == pygame.QUIT or event.type == pygame.KEYDOWN:
                    skip_pressed = True
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if skip_rect.collidepoint(event.pos):
                        skip_pressed = True
            
            if skip_pressed:
                skipped = True
                break
            
            # Convert BGR (OpenCV) to RGB (Pygame) and rotate correctly
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = np.transpose(frame, (1, 0, 2))
            surf = pygame.surfarray.make_surface(frame)
            last_surf = pygame.transform.scale(surf, (WIDTH, HEIGHT))
            
            screen.blit(last_surf, (0, 0))
            
            elapsed = time.time() - start_time
            if elapsed < 1.0:
                fade_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                alpha = max(0, 255 - int((elapsed / 1.0) * 255))
                fade_surf.fill((255, 255, 255, alpha))
                screen.blit(fade_surf, (0, 0))
                
            if elapsed > 1.0:
                draw_crafted_button(screen, skip_rect, "Skip", font_ui, COLOR_BLUSH)
                
            pygame.display.flip()
            vid_clock.tick(fps)
            await asyncio.sleep(0)
            
        cap.release()
        pygame.mixer.music.stop()
        
        if last_surf is not None:
            fade_start = time.time()
            while time.time() - fade_start < 0.4:
                vid_clock.tick(60)
                elapsed = time.time() - fade_start
                alpha = min(255, int((elapsed / 0.4) * 255))
                fade_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                fade_surf.fill((255, 255, 255, alpha))
                screen.blit(last_surf, (0, 0))
                screen.blit(fade_surf, (0, 0))
                pygame.display.flip()
                pygame.event.pump()
                await asyncio.sleep(0)

            pygame.event.clear()
            
        return skipped
    except Exception as e:
        print(f"Video Error: {e}")
        return False

crafted_bg = None
game_images = []

reward_images = {}

menu_images = []

nodo_image = None

nodo_video_path = None

massage_video_path = None

landscape_ready_start = 0.0

options = [{"text": "Nap Time", "limit": None, "pairs": 6, "type": "trivia"}, {"text": "Massage", "limit": 120, "pairs": 6, "type": "memory"}, {"text": "Dinner", "limit": 45, "pairs": 9, "type": "memory"}]
selected_idx = None
game_state = GameState.ORIENTATION_PROMPT if IS_WEB else GameState.MENU
completed_games = set()
cards, first, second, wait_timer = [], None, None, 0
start_time, paused_time, modal_image, modal_start_time = 0, 0, None, 0
win_animation_start_time = 0
win_particles = []
current_question_idx = 0
prev_game_state_before_landscape = None

font_title = None
font_win = None
font_ui = None

def draw_orientation_prompt(screen, dt):
    """Portrait welcome screen. Returns True when 'Let's Go' is tapped."""
    crafted_bg.draw(screen, dt)
    cx, cy = WIDTH // 2, HEIGHT // 2
    t = time.time()

    # Floating heart accent — large, centre-screen
    bob = math.sin(t * 1.6) * 8
    draw_vector_heart(screen, cx, cy - 40 + bob, 4.5, COLOR_BLUSH, 120)
    draw_vector_heart(screen, cx, cy - 40 + bob, 3.2, COLOR_CARD_BACK, 80)

    # Title
    if font_title:
        draw_soft_text(screen, "Hey Mama!", font_title, COLOR_TEXT, (cx, 110))

    # Sub-title
    msg_font = font_ui if font_ui else pygame.font.SysFont(None, 28)
    draw_soft_text(screen, "A little something just for you  🌸", msg_font, COLOR_CARD_BACK, (cx, 168))

    # "Let's Go" button
    btn_w, btn_h = 220, 54
    btn_rect = pygame.Rect(cx - btn_w // 2, HEIGHT - 140, btn_w, btn_h)
    draw_crafted_button(screen, btn_rect, "Let's Go  🌸", msg_font, COLOR_BLUSH)

    for event in pygame.event.get(pygame.MOUSEBUTTONDOWN):
        if btn_rect.collidepoint(event.pos):
            return True
    for event in pygame.event.get(pygame.FINGERDOWN):
        fx, fy = int(event.x * WIDTH), int(event.y * HEIGHT)
        if btn_rect.collidepoint(fx, fy):
            return True
    return False


def draw_thumbs_up(surf, cx, cy, scale):
    """Draw a thumbs-up icon centred at (cx, cy), scaled by `scale`."""
    s = scale
    bc = COLOR_BLUSH
    dc = COLOR_CARD_BACK   # darker outline/detail
    gc = COLOR_ROSE_GOLD   # highlight accent

    # Fist body (rounded rectangle below thumb)
    fist_w, fist_h = int(52*s), int(44*s)
    fist_rect = pygame.Rect(cx - fist_w//2, cy - fist_h//4, fist_w, fist_h)
    pygame.draw.rect(surf, bc,  fist_rect, border_radius=int(10*s))
    pygame.draw.rect(surf, dc,  fist_rect, int(2*s), border_radius=int(10*s))

    # Knuckle lines
    for i in range(1, 4):
        kx = fist_rect.left + int(fist_w * i / 4)
        pygame.draw.line(surf, dc,
                         (kx, fist_rect.top + int(4*s)),
                         (kx, fist_rect.top + int(14*s)), max(1, int(1.5*s)))

    # Thumb (polygon pointing upward-left)
    tx, ty = cx - int(14*s), cy - int(8*s)
    thumb = [
        (tx,              ty),
        (tx - int(18*s),  ty - int(38*s)),
        (tx - int(8*s),   ty - int(52*s)),
        (tx + int(10*s),  ty - int(42*s)),
        (tx + int(16*s),  ty - int(18*s)),
        (tx + int(16*s),  ty),
    ]
    pygame.draw.polygon(surf, bc, thumb)
    pygame.draw.polygon(surf, dc, thumb, max(1, int(2*s)))

    # Nail highlight
    nail = [
        (tx - int(12*s),  ty - int(38*s)),
        (tx - int(4*s),   ty - int(50*s)),
        (tx + int(8*s),   ty - int(42*s)),
        (tx + int(4*s),   ty - int(32*s)),
    ]
    pygame.draw.polygon(surf, gc, nail)
    pygame.draw.polygon(surf, dc, nail, max(1, int(1*s)))


def draw_landscape_ready(screen, dt, elapsed):
    """Winking face shown when phone is rotated to landscape. Auto-dismissed on return to portrait."""
    crafted_bg.draw(screen, dt)
    cx, cy = WIDTH // 2, HEIGHT // 2
    t = time.time()

    # Entry scale-in (0 → 0.5 s)
    entry = min(1.0, elapsed / 0.45)
    if entry < 0.7:
        scale = entry / 0.7 * 1.12
    else:
        scale = 1.12 - (entry - 0.7) / 0.3 * 0.12
    scale = max(0.01, scale)

    face_r = int(90 * scale)
    fy_off = int((1.0 - scale) * 60)   # slides down as it grows in
    face_cx, face_cy = cx, cy - 30 + fy_off

    # Head
    pygame.draw.circle(screen, COLOR_BLUSH,    (face_cx, face_cy), face_r)
    pygame.draw.circle(screen, COLOR_CARD_BACK,(face_cx, face_cy), face_r, max(1, int(3*scale)))

    # Cheek blush
    for _, sign in [(-1, -1), (1, 1)]:
        bs = pygame.Surface((int(42*scale), int(20*scale)), pygame.SRCALPHA)
        pygame.draw.ellipse(bs, (*COLOR_BLUSH, 130), bs.get_rect())
        screen.blit(bs, (face_cx + sign * int(52*scale) - bs.get_width()//2,
                         face_cy + int(18*scale) - bs.get_height()//2))

    # Eyes — wink cycle: blinks at ~2.5 s intervals for 0.25 s
    wink_cycle = t % 2.8
    is_winking = wink_cycle < 0.25 or (wink_cycle > 1.4 and wink_cycle < 1.65)
    eye_y = face_cy - int(22 * scale)
    for ex, do_wink in [(face_cx - int(28*scale), False),
                        (face_cx + int(28*scale), is_winking)]:
        if do_wink:
            # Closed wink: ∩ arc
            ew = int(22 * scale)
            pygame.draw.arc(screen, COLOR_TEXT,
                            pygame.Rect(ex - ew//2, eye_y - ew//4, ew, ew//2),
                            0, math.pi, max(2, int(3*scale)))
        else:
            er = max(1, int(8 * scale))
            pygame.draw.circle(screen, COLOR_TEXT,  (ex, eye_y), er)
            pygame.draw.circle(screen, COLOR_CREAM, (ex - max(1,int(2*scale)), eye_y - max(1,int(2*scale))), max(1, int(3*scale)))

    # Smile
    sm_w, sm_h = int(56*scale), int(32*scale)
    pygame.draw.arc(screen, COLOR_TEXT,
                    pygame.Rect(face_cx - sm_w//2, face_cy - sm_h//4, sm_w, sm_h),
                    math.pi, 2*math.pi, max(2, int(3*scale)))

    # Text
    msg_font = font_ui if font_ui else pygame.font.SysFont(None, 26)
    if entry > 0.6:
        alpha = int(min(255, (entry - 0.6) / 0.4 * 255))
        for txt, col, yo in [("Oops! I work best upright 😄", COLOR_TEXT, cy + 90),
                              ("Flip me back to play  🌸",     COLOR_CARD_BACK, cy + 120)]:
            s = msg_font.render(txt, True, col)
            s.set_alpha(alpha)
            screen.blit(s, (cx - s.get_width()//2, yo))


def draw_menu(screen, dt, selected_idx, completed_games):
    crafted_bg.draw(screen, dt)
    draw_soft_text(screen, "Happy Mama Day", font_title, COLOR_TEXT, (WIDTH//2, 60))
    
    for i, opt in enumerate(options):
        rect = pygame.Rect(WIDTH//2 - 160, HEIGHT//2 - 110 + i*90, 320, 60)
        
        base_color = COLOR_BLUSH if i == selected_idx else COLOR_CREAM
        draw_crafted_button(screen, rect, opt["text"], font_ui, base_color)
        
        if i in completed_games:
            draw_vector_heart(screen, rect.right - 25, rect.centery, 0.9, COLOR_BLUSH)

def draw_playing(screen, dt, limit, elapsed_time, cards):
    crafted_bg.draw(screen, dt)

    if limit:
        remaining = max(0, limit - elapsed_time)
        bar_w = int((remaining / limit) * (WIDTH - 40))
        pygame.draw.rect(screen, COLOR_SHADOW, (20, 18, WIDTH - 40, 14), border_radius=7)
        pygame.draw.rect(screen, COLOR_TEXT,   (20, 18, WIDTH - 40, 14), 2, border_radius=7)
        if bar_w > 0:
            pygame.draw.rect(screen, COLOR_SAGE, (22, 20, bar_w - 4, 10), border_radius=5)

    for card in cards:
        if card["matched"]: continue
        
        target = 1.0 if card["flipped"] or card["matched"] else 0.0
        if card["flip_proc"] != target:
            card["flip_proc"] += (target - card["flip_proc"]) * 10 * dt
            if abs(card["flip_proc"] - target) < 0.01: card["flip_proc"] = target

        flip_w = abs(math.cos(card["flip_proc"] * math.pi))
        draw_rect = pygame.Rect(0, 0, int(CARD_W * flip_w), CARD_H)
        draw_rect.center = card["rect"].center
        
        shadow_rect = draw_rect.copy()
        shadow_rect.y += 4
        pygame.draw.rect(screen, COLOR_SHADOW, shadow_rect, border_radius=8)

        if card["flip_proc"] > 0.5:
            pygame.draw.rect(screen, COLOR_CREAM, draw_rect, border_radius=8)
            pygame.draw.rect(screen, COLOR_SHADOW, draw_rect, 1, border_radius=8)
            if flip_w > 0.1:
                scaled_img = pygame.transform.scale(card["image"], (int((SIDE-10)*flip_w), SIDE-10))
                screen.blit(scaled_img, (draw_rect.centerx - scaled_img.get_width()//2, draw_rect.centery - scaled_img.get_height()//2))
        else:
            pygame.draw.rect(screen, COLOR_CARD_BACK, draw_rect, border_radius=8)
            pygame.draw.rect(screen, COLOR_CREAM, draw_rect.inflate(-10, -10), 1, border_radius=4)

    auto_rect = pygame.Rect(WIDTH // 2 - 55, HEIGHT - GAME_BOTTOM + 5, 110, 38)
    draw_crafted_button(screen, auto_rect, "Auto Win", font_ui, COLOR_BLUSH)

def draw_trivia(screen, dt, question_idx):
    crafted_bg.draw(screen, dt)
    draw_soft_text(screen, "Who Wants to Win a Nap?", font_win, COLOR_TEXT, (WIDTH//2, 55))
    
    if question_idx >= len(TRIVIA_QUESTIONS):
        return
        
    q_data = TRIVIA_QUESTIONS[question_idx]
    
    q_rect = pygame.Rect(10, 75, WIDTH - 20, 115)
    pygame.draw.rect(screen, COLOR_SHADOW, (q_rect.x + 4, q_rect.y + 6, q_rect.width, q_rect.height), border_radius=10)
    pygame.draw.rect(screen, COLOR_CREAM, q_rect, border_radius=10)
    pygame.draw.rect(screen, COLOR_BLUSH, q_rect, 2, border_radius=10)

    q_lines = wrap_text(q_data["question"], font_ui, q_rect.width - 30)
    line_h = font_ui.get_height()
    y = q_rect.centery - (line_h * len(q_lines)) // 2
    for line in q_lines:
        q_txt = font_ui.render(line, True, COLOR_TEXT)
        screen.blit(q_txt, (q_rect.centerx - q_txt.get_width() // 2, y))
        y += line_h

    start_y = 215
    mx, my = pygame.mouse.get_pos()
    for i, opt in enumerate(q_data["options"]):
        opt_rect = pygame.Rect(WIDTH // 2 - 190, start_y + i * 90, 380, 72)
        is_hover = opt_rect.collidepoint(mx, my)
        color_base = COLOR_SAGE if is_hover else COLOR_CREAM
        draw_crafted_button(screen, opt_rect, opt, font_ui, color_base)

def draw_modal(screen, modal_image, modal_start_time):
    m_elapsed = time.time() - modal_start_time
    if m_elapsed < 2.0:
        progress = m_elapsed / 2.0
        size_val = SIDE + (progress * (HEIGHT - SIDE - 20))
        alpha = max(0, 255 - int(progress * 255))
        scaled = pygame.transform.smoothscale(modal_image, (int(size_val), int(size_val)))
        scaled.set_alpha(alpha)
        screen.blit(scaled, scaled.get_rect(center=(WIDTH//2, HEIGHT//2)))
        return False
    return True

def draw_nodo_reveal(screen, nodo_start_time, nodo_image):
    screen.fill(COLOR_PAPER_BG)
    nodo_elapsed = time.time() - nodo_start_time
    alpha = 0
    if nodo_elapsed < 0.5:
        alpha = int((nodo_elapsed / 0.5) * 255)
    elif nodo_elapsed < 1.5:
        alpha = 255
    elif nodo_elapsed < 2.0:
        alpha = int((1.0 - (nodo_elapsed - 1.5) / 0.5) * 255)
    else:
        return True
    
    if nodo_image is not None:
        nodo_image.set_alpha(alpha)
        r = nodo_image.get_rect(center=(WIDTH//2, HEIGHT//2))
        screen.blit(nodo_image, r)
    return False

def draw_transition_to_reward(screen, dt, transition_start_time, transition_particles):
    screen.fill(COLOR_PAPER_BG)
    elapsed = time.time() - transition_start_time
    
    shake_phase = 0.6
    spurt_phase = 1.8
    
    cam_x = random.randint(-12, 12) if shake_phase < elapsed < shake_phase + 0.2 else 0
    cam_y = random.randint(-12, 12) if shake_phase < elapsed < shake_phase + 0.2 else 0

    shake_x = math.sin(elapsed * 60) * 4 if elapsed < shake_phase else 0
    shake_y = math.cos(elapsed * 50) * 2 if elapsed < shake_phase else 0

    box_w, box_h, lid_h = 110, 80, 30
    box_base_x = int(WIDTH // 2 - box_w // 2 + shake_x)
    box_base_y = int(HEIGHT // 2 + shake_y)
    bx = box_base_x + cam_x
    by = box_base_y + cam_y
    cx = bx + box_w // 2

    is_open = elapsed > shake_phase

    gift_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

    shadow = pygame.Surface((box_w + 20, 16), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (*COLOR_SHADOW, 120), shadow.get_rect())
    gift_surf.blit(shadow, (bx - 10, by + box_h + 2))

    if not is_open:
        pulse = abs(math.sin(elapsed * 8))
        for i in range(3, 0, -1):
            r = int((60 + pulse * 20) * (i / 3.0))
            pygame.draw.circle(gift_surf, (*COLOR_BLUSH, int(35 / i)), (cx, by + box_h // 2), r)

    body_rect = pygame.Rect(bx, by, box_w, box_h)
    pygame.draw.rect(gift_surf, COLOR_BLUSH, body_rect, border_radius=6)
    pygame.draw.rect(gift_surf, COLOR_SHADOW, body_rect, 2, border_radius=6)

    ribbon_w = 14
    pygame.draw.rect(gift_surf, COLOR_SAGE, (cx - ribbon_w // 2, by, ribbon_w, box_h))
    pygame.draw.rect(gift_surf, COLOR_SAGE, (bx, by + box_h // 2 - ribbon_w // 2, box_w, ribbon_w))

    if is_open:
        open_progress = min(1.0, (elapsed - shake_phase) / 0.4)
        lid_y = by - lid_h - int(open_progress * 55)
    else:
        lid_y = by - lid_h

    lid_rect = pygame.Rect(bx - 4, lid_y, box_w + 8, lid_h)
    pygame.draw.rect(gift_surf, COLOR_BLUSH, lid_rect, border_radius=6)
    pygame.draw.rect(gift_surf, COLOR_SHADOW, lid_rect, 2, border_radius=6)

    pygame.draw.rect(gift_surf, COLOR_SAGE, (cx - ribbon_w // 2, lid_y, ribbon_w, lid_h))

    bow_cx, bow_cy = cx, lid_y - 2
    loop_w, loop_h = 20, 14
    pygame.draw.ellipse(gift_surf, COLOR_SAGE, (bow_cx - loop_w - 4, bow_cy - loop_h, loop_w, loop_h * 2))
    pygame.draw.ellipse(gift_surf, COLOR_SHADOW, (bow_cx - loop_w - 4, bow_cy - loop_h, loop_w, loop_h * 2), 2)
    pygame.draw.ellipse(gift_surf, COLOR_SAGE, (bow_cx + 4, bow_cy - loop_h, loop_w, loop_h * 2))
    pygame.draw.ellipse(gift_surf, COLOR_SHADOW, (bow_cx + 4, bow_cy - loop_h, loop_w, loop_h * 2), 2)
    pygame.draw.circle(gift_surf, COLOR_SAGE, (bow_cx, bow_cy), 7)
    pygame.draw.circle(gift_surf, COLOR_SHADOW, (bow_cx, bow_cy), 7, 2)

    if is_open and len(transition_particles) < 150 and elapsed < spurt_phase:
        for _ in range(3):
            transition_particles.append({
                "x": cx + random.uniform(-12, 12), "y": by + 10,
                "vx": random.uniform(-150, 150), "vy": random.uniform(-120, -420),
                "size": 0.4, "target_size": random.uniform(0.8, 2.5),
                "color": random.choice([COLOR_BLUSH, COLOR_SAGE, COLOR_CREAM]),
                "growth": random.uniform(2.0, 5.0)
            })

    if elapsed > spurt_phase:
        gift_surf.set_alpha(max(0, 255 - int((elapsed - spurt_phase) * 510)))

    screen.blit(gift_surf, (0, 0))

    for p in transition_particles:
        if p["size"] < p["target_size"]: p["size"] += p["growth"] * dt
        p["x"] += p.get("vx", 0) * dt
        p["y"] += p.get("vy", 0) * dt
        if "vy" in p: p["vy"] += 500 * dt 
        draw_vector_heart(screen, p["x"] + cam_x, p["y"] + cam_y, p["size"], p["color"], 220)

    if shake_phase < elapsed < shake_phase + 0.25:
        flash_alpha = int(200 * (1.0 - (elapsed - shake_phase) / 0.25))
        flash_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        flash_surf.fill((255, 255, 255, flash_alpha))
        screen.blit(flash_surf, (0, 0))

    if elapsed > spurt_phase:
        text_elapsed = elapsed - spurt_phase
        scale = min(1.0, text_elapsed * 2) + 0.1 * math.sin(text_elapsed * 10)
        base_txt = font_win.render("Good Job!", True, COLOR_TEXT)
        if scale > 0:
            new_w, new_h = int(base_txt.get_width() * scale), int(base_txt.get_height() * scale)
            txt = pygame.transform.smoothscale(base_txt, (max(1, new_w), max(1, new_h)))
            screen.blit(txt, (WIDTH//2 - new_w//2, HEIGHT//2 - new_h//2 - 60))
            
    if elapsed > 4.5:
        return True
    return False

def draw_final_message(screen, dt, transition_particles):
    crafted_bg.draw(screen, dt)
    if len(transition_particles) < 50:
        transition_particles.append({
            "x": random.randint(0, WIDTH), "y": random.randint(0, HEIGHT),
            "size": 0.1, "target_size": random.uniform(1.0, 3.0),
                "color": random.choice([COLOR_BLUSH, COLOR_SAGE, COLOR_CREAM]),
            "growth": random.uniform(2.0, 5.0)
        })
    for p in transition_particles:
        if p["size"] < p["target_size"]: p["size"] += p["growth"] * dt
        draw_vector_heart(screen, p["x"], p["y"], p["size"], p["color"], 180)
    
    draw_soft_text(screen, "Happy Mother's Day!", font_title, COLOR_TEXT, (WIDTH//2, HEIGHT//2 - 40))
    
    menu_button_rect = pygame.Rect(WIDTH//2 - 180, HEIGHT - 100, 160, 60)
    draw_crafted_button(screen, menu_button_rect, "MENU", font_ui, COLOR_CREAM)

    exit_button_rect = pygame.Rect(WIDTH//2 + 20, HEIGHT - 100, 160, 60)
    draw_crafted_button(screen, exit_button_rect, "EXIT", font_ui, COLOR_CREAM)
    
    return menu_button_rect, exit_button_rect

def draw_trivia_correct(screen, dt, start_time, question_idx, heart_pos):
    draw_trivia(screen, dt, question_idx)
    elapsed = time.time() - start_time

    for i in range(3):
        offset_x = (i - 1) * 40
        delay = i * 0.15
        t = max(0, elapsed - delay)
        if t <= 0:
            continue
        hy = heart_pos[1] - t * 180
        alpha = max(0, 255 - int(t * 220))
        size = 0.8 + t * 0.6
        draw_vector_heart(screen, heart_pos[0] + offset_x, hy, size, COLOR_BLUSH, alpha)

    return elapsed > 1.2

def draw_trivia_fail_fade(screen, dt, start_time, question_idx):
    elapsed = time.time() - start_time
    
    temp_surf = pygame.Surface((WIDTH, HEIGHT))
    draw_trivia(temp_surf, dt, question_idx)
    
    shake_x, shake_y = 0, 0
    if elapsed < 0.4:
        shake_x = random.randint(-15, 15)
        shake_y = random.randint(-15, 15)
        flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        flash.fill((255, 100, 100, 120))
        temp_surf.blit(flash, (0, 0))
        
    screen.fill(COLOR_PAPER_BG)
    screen.blit(temp_surf, (shake_x, shake_y))
    
    if elapsed > 0.4:
        fade_alpha = min(255, int((elapsed - 0.4) / 0.4 * 255))
        fade_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        fade_surf.fill((*COLOR_PAPER_BG, fade_alpha))
        screen.blit(fade_surf, (0, 0))
        
    return elapsed > 0.8

def draw_pdf_viewer(screen, pdf_surf, surf_h, scroll_y):
    screen.fill((20, 20, 20))
    if pdf_surf:
        screen.blit(pdf_surf, (0, -scroll_y))
    else:
        msg = font_ui.render("Menu PDF could not be loaded.", True, (220, 220, 220))
        screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2))

    if surf_h > HEIGHT:
        bar_h = max(30, int(HEIGHT * HEIGHT / surf_h))
        bar_y = int(scroll_y * (HEIGHT - bar_h) / max(1, surf_h - HEIGHT))
        pygame.draw.rect(screen, (60, 60, 60), (WIDTH - 8, 0, 8, HEIGHT))
        pygame.draw.rect(screen, (180, 180, 180), (WIDTH - 8, bar_y, 8, bar_h))

    close_rect = pygame.Rect(WIDTH - 120, 10, 110, 36)
    draw_crafted_button(screen, close_rect, "Close Menu", font_ui, COLOR_BLUSH)
    return close_rect

def draw_won_gameover(screen, dt, game_state_val, selected_idx, win_animation_start_time, win_particles, scroll_y, menu_images):
    msg = REWARDS[selected_idx] if game_state_val == GameState.WON else "Better luck next time!"
    current_img = reward_images.get(selected_idx)
    
    menu_button_rect = None
    save_button_rect = None
    
    if game_state_val == GameState.WON and (current_img is not None or (selected_idx == 2 and len(menu_images) > 0)):
        if selected_idx == 2:
            screen.fill(COLOR_PAPER_BG)

        for p in win_particles:
            p["y"] -= p["speed"] * dt
            if p["y"] < -50: p["y"] = HEIGHT + 50
            sway = math.sin(time.time()*2 + p["seed"]) * 30
            draw_vector_heart(screen, p["x"] + sway, p["y"], p["size"], p["color"], 150)

        win_elapsed = time.time() - win_animation_start_time
        progress = min(1.0, win_elapsed / 0.7)
        eased_progress = 1 - (1 - progress) ** 4

        if selected_idx == 2:
            y_pos = 20 - scroll_y
            for img in menu_images:
                screen.blit(img, (50, y_pos))
                y_pos += img.get_height() + 20
            
            menu_button_rect = pygame.Rect(WIDTH - 120, HEIGHT - 60, 100, 40)
            draw_crafted_button(screen, menu_button_rect, "Menu", font_ui, COLOR_BLUSH)
        else:
            # wrap the reward message so it never overflows the 450px canvas
            msg_lines = wrap_text(msg, font_win, WIDTH - 30)
            line_h = font_win.get_height()
            msg_block_h = line_h * len(msg_lines)
            img_top = msg_block_h + 20

            avail_h = HEIGHT - img_top - 80
            base_scale = min(1.0, avail_h / current_img.get_height(), (WIDTH - 40) / current_img.get_width())
            base_w, base_h = int(current_img.get_width() * base_scale), int(current_img.get_height() * base_scale)
            curr_w, curr_h = int(base_w * eased_progress), int(base_h * eased_progress)

            if curr_w > 0 and curr_h > 0:
                pad = 15
                img_x = WIDTH//2 - curr_w//2
                img_y = img_top + (base_h - curr_h)//2
                pygame.draw.rect(screen, (255, 255, 255), (img_x - pad, img_y - pad, curr_w + pad*2, curr_h + pad*2))
                scaled_img = pygame.transform.smoothscale(current_img, (curr_w, curr_h))
                screen.blit(scaled_img, (img_x, img_y))

            if progress >= 1.0:
                msg_y = 10
                for line in msg_lines:
                    shadow = font_win.render(line, True, COLOR_SHADOW)
                    screen.blit(shadow, (WIDTH//2 - shadow.get_width()//2 + 2, msg_y + 2))
                    line_surf = font_win.render(line, True, COLOR_TEXT)
                    screen.blit(line_surf, (WIDTH//2 - line_surf.get_width()//2, msg_y))
                    msg_y += line_h

                menu_button_rect = pygame.Rect(WIDTH//2 - 100, HEIGHT - 60, 200, 40)
                btn_label = "Booked for 2pm" if selected_idx == 1 else "Momma's Menu"
                draw_crafted_button(screen, menu_button_rect, btn_label, font_ui, COLOR_BLUSH)
    else:
        txt = font_win.render(msg, True, COLOR_TEXT)
        screen.blit(txt, (WIDTH//2 - txt.get_width()//2, HEIGHT//2 - 40))
        menu_button_rect = pygame.Rect(WIDTH//2 - 80, HEIGHT//2 + 60, 160, 50)
        draw_crafted_button(screen, menu_button_rect, "MENU", font_ui, COLOR_BLUSH)

    return menu_button_rect, save_button_rect

async def main():
    global game_state, selected_idx, cards, first, second, wait_timer, start_time, paused_time, modal_image, modal_start_time, win_animation_start_time, win_particles, scroll_y, completed_games, current_question_idx
    try:
        await _main()
    except Exception:
        import traceback
        err = traceback.format_exc()
        print("CRASH:", err)
        try:
            pygame.init()
            s = pygame.display.set_mode((998, 448))
            s.fill((20, 20, 20))
            f = pygame.font.SysFont(None, 22)
            lines = err.strip().split('\n')
            for i, line in enumerate(lines[-12:]):
                surf = f.render(line[:90], True, (255, 80, 80))
                s.blit(surf, (10, 10 + i * 24))
            pygame.display.flip()
        except:
            pass
        while True:
            await asyncio.sleep(1)

async def _main():
    global game_state, selected_idx, cards, first, second, wait_timer, start_time, paused_time, modal_image, modal_start_time, win_animation_start_time, win_particles, scroll_y, completed_games, current_question_idx, landscape_ready_start, prev_game_state_before_landscape
    global screen, clock, crafted_bg, game_images, reward_images, menu_images, nodo_image, nodo_video_path, massage_video_path, pdf_surface, pdf_surface_height, font_title, font_win, font_ui

    pygame.display.init()
    pygame.font.init()
    if not IS_WEB:
        try:
            pygame.mixer.init()
        except Exception:
            pass
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()

    pdf_surface = None
    pdf_surface_height = 0
    if HAS_FITZ and os.path.exists(MENU_PDF):
        try:
            doc = fitz.open(MENU_PDF)
            pages = []
            for page in doc:
                zoom = WIDTH / page.rect.width
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                pages.append(pygame.image.load(io.BytesIO(pix.tobytes("png"))).convert())
            doc.close()
            if pages:
                pdf_surface_height = sum(s.get_height() for s in pages)
                pdf_surface = pygame.Surface((WIDTH, pdf_surface_height))
                y = 0
                for s in pages:
                    pdf_surface.blit(s, (0, y))
                    y += s.get_height()
        except Exception as e:
            print(f"ERROR: Could not load menu PDF: {e}")

    crafted_bg = CraftedBackground()
    game_images = load_images()

    reward_images = {}
    try:
        root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        files = {0: "nap.jpg", 1: "massage.jpg", 2: "dinner.jpg"}
        for idx, fname in files.items():
            path = os.path.join(root_path, fname)
            if os.path.exists(path):
                reward_images[idx] = pygame.image.load(path).convert_alpha()
    except: pass

    menu_images = []
    try:
        menu_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "menu")
        if os.path.exists(menu_dir):
            for i in range(7):
                for ext in [".jpg", ".png", ".jpeg"]:
                    fpath = os.path.join(menu_dir, f"Menu-Images-{i}{ext}")
                    if os.path.exists(fpath):
                        img = pygame.image.load(fpath).convert_alpha()
                        scale = (WIDTH - 100) / img.get_width()
                        menu_images.append(pygame.transform.smoothscale(img, (int(WIDTH - 100), int(img.get_height() * scale))))
                        break
    except: pass

    nodo_image = None
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        for fname in ["NODO.avif", "NODO.png", "nodo.avif", "nodo.png"]:
            npath = os.path.join(current_dir, fname)
            if os.path.exists(npath):
                nodo_image = pygame.image.load(npath).convert_alpha()
                scale = min(WIDTH / nodo_image.get_width(), HEIGHT / nodo_image.get_height()) * 0.8
                if scale < 1:
                    nodo_image = pygame.transform.smoothscale(nodo_image, (int(nodo_image.get_width() * scale), int(nodo_image.get_height() * scale)))
                break
    except: pass

    nodo_video_path = None
    try:
        root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        video_dir = os.path.join(root_path, "Video")
        if not os.path.exists(video_dir):
            video_dir = os.path.join(root_path, "video")
        if os.path.exists(video_dir):
            for fname in ["NODO.mp4", "nodo.mp4", "NODO.mov", "nodo.mov"]:
                fpath = os.path.join(video_dir, fname)
                if os.path.exists(fpath):
                    nodo_video_path = fpath
                    break
    except: pass

    massage_video_path = None
    try:
        if os.path.exists(video_dir):
            for fname in ["MASSAGE.mp4", "massage.mp4", "Massage.mp4", "MASSAGE.mov"]:
                if os.path.exists(os.path.join(video_dir, fname)):
                    massage_video_path = os.path.join(video_dir, fname)
                    break
    except: pass

    _curr_dir = os.path.dirname(os.path.abspath(__file__))
    _parent_dir = os.path.dirname(_curr_dir)

    amatemora_paths = [
        os.path.join(_curr_dir, "Amatemora.ttf"), os.path.join(_curr_dir, "Amatemora.otf"),
        os.path.join(_curr_dir, "amatemora.ttf"), os.path.join(_curr_dir, "amatemora.otf"),
        os.path.join(_parent_dir, "Amatemora.ttf"), os.path.join(_parent_dir, "Amatemora.otf"),
        os.path.join(_parent_dir, "amatemora.ttf"), os.path.join(_parent_dir, "amatemora.otf"),
    ]

    font_title, font_win = None, None
    for path in amatemora_paths:
        if os.path.exists(path):
            try:
                font_title = pygame.font.Font(path, 86)
                font_win = pygame.font.Font(path, 64)
                break
            except:
                pass

    if not font_title:
        font_title = pygame.font.SysFont(None, 76)
        font_win = pygame.font.SysFont(None, 54)

    melon_paths = [
        os.path.join(_curr_dir, "Melon Pop.ttf"),
        os.path.join(_parent_dir, "Melon Pop.ttf"),
    ]
    font_ui = None
    for path in melon_paths:
        if os.path.exists(path):
            try:
                font_ui = pygame.font.Font(path, 22)
                break
            except:
                pass
    if not font_ui:
        font_ui = pygame.font.SysFont(None, 22)

    scroll_y = 0
    nodo_start_time = 0
    transition_start_time = 0
    transition_particles = []
    running = True
    menu_button_rect = None
    save_button_rect = None
    exit_button_rect = None
    pdf_scroll_y = 0
    pdf_close_rect = None
    correct_anim_start = 0
    correct_anim_pos = (WIDTH // 2, HEIGHT // 2)
    while running:
        dt = clock.tick(60) / 1000

        # --- landscape interrupt: winking face whenever phone is sideways ---
        if IS_WEB:
            try:
                _in_landscape = js.window.innerWidth > js.window.innerHeight
            except Exception:
                _in_landscape = False
            if _in_landscape and game_state != GameState.LANDSCAPE_READY:
                prev_game_state_before_landscape = game_state
                landscape_ready_start = time.time()
                game_state = GameState.LANDSCAPE_READY
            elif not _in_landscape and game_state == GameState.LANDSCAPE_READY:
                game_state = prev_game_state_before_landscape or GameState.ORIENTATION_PROMPT

        if game_state == GameState.ORIENTATION_PROMPT:
            if draw_orientation_prompt(screen, dt):
                game_state = GameState.MENU

        elif game_state == GameState.LANDSCAPE_READY:
            elapsed = time.time() - landscape_ready_start
            draw_landscape_ready(screen, dt, elapsed)

        elif game_state == GameState.MENU:
            draw_menu(screen, dt, selected_idx, completed_games)
            
        elif game_state == GameState.PLAYING_TRIVIA:
            draw_trivia(screen, dt, current_question_idx)

        elif game_state in [GameState.PLAYING, GameState.MODAL]:
            limit = options[selected_idx]["limit"]
            elapsed = (time.time() - start_time) - paused_time if game_state == GameState.PLAYING else 0
            
            draw_playing(screen, dt, limit, elapsed, cards)
            
            if limit and game_state == GameState.PLAYING:
                remaining = max(0, limit - elapsed)
                if remaining <= 0: game_state = GameState.GAMEOVER

            if game_state == GameState.PLAYING and first and second and wait_timer > 0:
                wait_timer -= dt
                if wait_timer <= 0:
                    if first["image"] == second["image"]:
                        first["matched"] = second["matched"] = True
                        modal_image, modal_start_time, game_state = first["image"], time.time(), GameState.MODAL
                    else:
                        first["flipped"] = second["flipped"] = False
                    first = second = None

            if game_state == GameState.MODAL:
                if draw_modal(screen, modal_image, modal_start_time):
                    paused_time += 2.0
                    game_state = GameState.PLAYING
                    if all(c["matched"] for c in cards):
                        completed_games.add(selected_idx)
                        game_state = GameState.TRANSITION_TO_REWARD
                        transition_start_time = time.time()
                        transition_particles = []

        elif game_state == GameState.NODO_REVEAL:
            if draw_nodo_reveal(screen, nodo_start_time, nodo_image):
                game_state = GameState.WON
                scroll_y = 0
                win_animation_start_time = time.time()
                win_particles = [{"x": random.randint(0, WIDTH), "y": random.randint(0, HEIGHT), 
                                  "size": random.uniform(1.0, 3.0), "speed": random.uniform(100, 200), 
                                  "seed": random.random(), "color": random.choice([COLOR_SOFT_PINK, COLOR_ROSE_GOLD, COLOR_CREAM])} for _ in range(40)]

        elif game_state == GameState.TRANSITION_TO_REWARD:
            if draw_transition_to_reward(screen, dt, transition_start_time, transition_particles):
                if selected_idx in [1, 2]:  # Massage & Dinner both use the video reward flow
                    if IS_WEB or (nodo_video_path and HAS_VIDEO_LIB):
                        game_state = GameState.PLAY_VIDEO_REWARD
                    elif nodo_image is not None:
                        game_state = GameState.NODO_REVEAL
                        nodo_start_time = time.time()
                    else:
                        game_state = GameState.WON
                        scroll_y = 0
                        win_animation_start_time = time.time()
                        win_particles = [{"x": random.randint(0, WIDTH), "y": random.randint(0, HEIGHT),
                                          "size": random.uniform(1.0, 3.0), "speed": random.uniform(100, 200),
                                          "seed": random.random(), "color": random.choice([COLOR_SOFT_PINK, COLOR_ROSE_GOLD, COLOR_CREAM])} for _ in range(40)]
                else:  # Nap
                    game_state = GameState.MENU
                    selected_idx = None

        elif game_state == GameState.PLAY_VIDEO_REWARD:
            if IS_WEB:
                await play_video_web("https://troygeoghegan.github.io/Operation-Big-Mama/nodo.mp4")
                if selected_idx == 2:  # dinner → show the live restaurant menu, then return
                    await show_online_menu()
                    game_state = GameState.MENU
                    selected_idx = None
                else:
                    game_state = GameState.WON
                    scroll_y = 0
                    win_animation_start_time = time.time()
                    win_particles = [{"x": random.randint(0, WIDTH), "y": random.randint(0, HEIGHT),
                                      "size": random.uniform(1.0, 3.0), "speed": random.uniform(100, 200),
                                      "seed": random.random(), "color": random.choice([COLOR_SOFT_PINK, COLOR_ROSE_GOLD, COLOR_CREAM])} for _ in range(40)]
            else:
                skipped = await play_video(nodo_video_path)
                if skipped:
                    game_state = GameState.PDF_VIEWER
                    pdf_scroll_y = 0
                elif nodo_image is not None:
                    game_state = GameState.NODO_REVEAL
                    nodo_start_time = time.time()
                else:
                    game_state = GameState.WON
                    scroll_y = 0
                    win_animation_start_time = time.time()
                    win_particles = [{"x": random.randint(0, WIDTH), "y": random.randint(0, HEIGHT),
                                      "size": random.uniform(1.0, 3.0), "speed": random.uniform(100, 200),
                                      "seed": random.random(), "color": random.choice([COLOR_SOFT_PINK, COLOR_ROSE_GOLD, COLOR_CREAM])} for _ in range(40)]

        elif game_state == GameState.PDF_VIEWER:
            pdf_close_rect = draw_pdf_viewer(screen, pdf_surface, pdf_surface_height, pdf_scroll_y)

        elif game_state == GameState.FINAL_MESSAGE:
            menu_button_rect, exit_button_rect = draw_final_message(screen, dt, transition_particles)
            
        elif game_state == GameState.TRIVIA_CORRECT:
            if draw_trivia_correct(screen, dt, correct_anim_start, current_question_idx, correct_anim_pos):
                current_question_idx += 1
                if current_question_idx >= len(TRIVIA_QUESTIONS):
                    completed_games.add(selected_idx)
                    game_state = GameState.TRANSITION_TO_REWARD
                    transition_start_time = time.time()
                    transition_particles = []
                else:
                    game_state = GameState.PLAYING_TRIVIA

        elif game_state == GameState.TRIVIA_FAIL_FADE:
            if draw_trivia_fail_fade(screen, dt, transition_start_time, current_question_idx):
                game_state = GameState.GAMEOVER

        elif game_state == GameState.WON or game_state == GameState.GAMEOVER:
            menu_button_rect, save_button_rect = draw_won_gameover(screen, dt, game_state, selected_idx, win_animation_start_time, win_particles, scroll_y, menu_images)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and game_state == GameState.PDF_VIEWER:
                if event.key in (pygame.K_DOWN, pygame.K_RIGHT):
                    pdf_scroll_y = min(max(0, pdf_surface_height - HEIGHT), pdf_scroll_y + 80)
                elif event.key in (pygame.K_UP, pygame.K_LEFT):
                    pdf_scroll_y = max(0, pdf_scroll_y - 80)
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = pygame.mouse.get_pos()
                if game_state == GameState.MENU:
                    for i in range(3):
                        if pygame.Rect(WIDTH//2 - 160, HEIGHT//2 - 110 + i*90, 320, 60).collidepoint(mx, my):
                            selected_idx = i
                            if options[selected_idx].get("type") == "trivia":
                                if pending_trivia_questions:
                                    TRIVIA_QUESTIONS[:] = pending_trivia_questions
                                game_state = GameState.PLAYING_TRIVIA
                                current_question_idx = 0
                            else:
                                cards, game_state, start_time, paused_time = create_board(game_images, options[selected_idx]["pairs"]), GameState.PLAYING, time.time(), 0
                elif game_state == GameState.PLAYING_TRIVIA:
                    q_data = TRIVIA_QUESTIONS[current_question_idx]
                    start_y = 215
                    for i in range(4):
                        opt_rect = pygame.Rect(WIDTH // 2 - 190, start_y + i * 90, 380, 72)
                        if opt_rect.collidepoint(mx, my):
                            if i == q_data["answer"]:
                                correct_anim_start = time.time()
                                correct_anim_pos = opt_rect.center
                                game_state = GameState.TRIVIA_CORRECT
                            else:
                                game_state = GameState.TRIVIA_FAIL_FADE
                                transition_start_time = time.time()
                                trigger_vibration()
                elif game_state == GameState.PLAYING and wait_timer <= 0:
                    if pygame.Rect(WIDTH // 2 - 55, HEIGHT - GAME_BOTTOM + 5, 110, 38).collidepoint(mx, my):
                        for c in cards: c["matched"] = True
                        completed_games.add(selected_idx)
                        game_state = GameState.TRANSITION_TO_REWARD
                        transition_start_time = time.time()
                        transition_particles = []

                    for card in cards:
                        if card["rect"].collidepoint(mx, my) and not card["flipped"] and not card["matched"]:
                            card["flipped"] = True
                            if not first: first = card
                            elif not second: second, wait_timer = card, 0.7
                elif game_state == GameState.PDF_VIEWER:
                    if pdf_close_rect and pdf_close_rect.collidepoint(mx, my):
                        game_state = GameState.MENU
                        selected_idx = None
                elif game_state in [GameState.WON, GameState.GAMEOVER, GameState.FINAL_MESSAGE]:
                    if game_state == GameState.WON and time.time() - win_animation_start_time < 0.5:
                        continue
                    if menu_button_rect and menu_button_rect.collidepoint(mx, my):
                        if game_state == GameState.WON:
                            if len(completed_games) == len(options):
                                game_state = GameState.FINAL_MESSAGE
                                transition_start_time = time.time()
                                transition_particles = []
                            else:
                                game_state = GameState.MENU
                                selected_idx = None
                        else:
                            game_state = GameState.MENU
                            selected_idx = None
                        menu_button_rect = None
                        save_button_rect = None
                    elif game_state == GameState.GAMEOVER and save_button_rect and save_button_rect.collidepoint(mx, my):
                        if options[selected_idx].get("type") == "trivia":
                            if pending_trivia_questions:
                                TRIVIA_QUESTIONS[:] = pending_trivia_questions
                            game_state = GameState.PLAYING_TRIVIA
                            current_question_idx = 0
                        else:
                            cards, game_state, start_time, paused_time = create_board(game_images, options[selected_idx]["pairs"]), GameState.PLAYING, time.time(), 0
                        menu_button_rect = None
                        save_button_rect = None
                    elif game_state == GameState.FINAL_MESSAGE and exit_button_rect and exit_button_rect.collidepoint(mx, my):
                        running = False
            if event.type == pygame.MOUSEWHEEL:
                if game_state == GameState.PDF_VIEWER:
                    pdf_scroll_y -= event.y * 40
                    pdf_scroll_y = max(0, min(pdf_scroll_y, max(0, pdf_surface_height - HEIGHT)))
                elif game_state == GameState.WON and selected_idx == 2:
                    scroll_y -= event.y * 30
                    content_h = sum(img.get_height() + 20 for img in menu_images) + 20
                    scroll_y = max(0, min(scroll_y, max(0, content_h - HEIGHT)))

        pygame.display.flip()
        await asyncio.sleep(0)

asyncio.run(main())