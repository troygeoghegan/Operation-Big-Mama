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

WIDTH, HEIGHT = 412, 860
screen = None
clock = None

pdf_surface = None
pdf_surface_height = 0

# ── Art-direction palette ─────────────────────────────────────────────────
COLOR_SKY_TOP    = (95,  196, 248)   # bright blue sky top
COLOR_SKY_BOT    = (138, 218, 255)   # lighter blue sky bottom
COLOR_GRASS_BACK = (148, 220, 108)   # back hill — lightest green
COLOR_GRASS      = (100, 190, 65)    # mid hill
COLOR_GRASS_DARK = (62,  152, 38)    # front hill — darkest green
COLOR_GROUND     = (255, 245, 212)   # warm cream/peach flat ground
COLOR_OUTLINE    = (22,  10,  52)    # very dark navy outline (text + borders)
COLOR_YELLOW     = (255, 212, 0)     # gold — stars, highlights

# Legacy names kept so nothing else breaks
COLOR_PAPER_BG  = COLOR_GROUND
COLOR_BLUSH     = (236, 48,  118)    # hot pink — banners, card backs
COLOR_SAGE      = (100, 196, 248)    # sky-blue accent
COLOR_TEXT      = COLOR_OUTLINE      # dark text for dark-on-light rendering
COLOR_CREAM     = (255, 255, 255)    # pure white
COLOR_CARD_BACK = COLOR_BLUSH
COLOR_SHADOW    = (168, 28,  84)     # deep-pink drop shadow

COLOR_SOFT_PINK = COLOR_BLUSH
COLOR_ROSE_GOLD = COLOR_YELLOW

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
    offset = 3 if is_hover else 0
    r = rect.height // 2

    # Drop shadow
    pygame.draw.rect(screen, (0, 0, 0),   (rect.x+5, rect.y+7, rect.width, rect.height), border_radius=r)
    btn = pygame.Rect(rect.x, rect.y - offset, rect.width, rect.height)
    # Body
    pygame.draw.rect(screen, base_color,   btn, border_radius=r)
    # Outline
    pygame.draw.rect(screen, COLOR_OUTLINE, btn, 4, border_radius=r)
    # Vertical gradient: light top → transparent bottom
    grad_w = max(1, btn.width - 8)
    grad_h = max(1, btn.height)
    grad = pygame.Surface((grad_w, grad_h), pygame.SRCALPHA)
    for gy in range(grad_h):
        t_g = gy / grad_h
        # top half brightens, bottom half darkens
        if t_g < 0.45:
            a = int(110 * (1 - t_g / 0.45))
            grad.fill((255, 255, 255, a), (0, gy, grad_w, 1))
        else:
            a = int(60 * ((t_g - 0.45) / 0.55))
            grad.fill((0, 0, 0, a), (0, gy, grad_w, 1))
    screen.blit(grad, (btn.x + 4, btn.y))

    lines = wrap_text(text, font, btn.width - 20)
    line_h = font.get_height()
    ty = btn.centery - (line_h * len(lines)) // 2
    for line in lines:
        o = font.render(line, True, COLOR_OUTLINE)
        for ddx, ddy in [(-2,0),(2,0),(0,-2),(0,2),(-2,-2),(2,-2),(-2,2),(2,2)]:
            screen.blit(o, (btn.centerx - o.get_width()//2 + ddx, ty + ddy))
        ts = font.render(line, True, COLOR_CREAM)
        screen.blit(ts, (btn.centerx - ts.get_width()//2, ty))
        ty += line_h

def draw_soft_text(screen, text, font, color, center_pos, max_width=None):
    """Cartoon outlined text: dark navy ring, then colour fill on top."""
    text_surf = font.render(text, True, color)
    out_surf  = font.render(text, True, COLOR_OUTLINE)
    if max_width and text_surf.get_width() > max_width:
        sc = max_width / text_surf.get_width()
        nw, nh = max(1, int(text_surf.get_width()*sc)), max(1, int(text_surf.get_height()*sc))
        text_surf = pygame.transform.smoothscale(text_surf, (nw, nh))
        out_surf  = pygame.transform.smoothscale(out_surf,  (nw, nh))
    cx, cy = center_pos
    tw, th = text_surf.get_size()
    ow = 3
    for ddx in (-ow, 0, ow):
        for ddy in (-ow, 0, ow):
            if ddx or ddy:
                screen.blit(out_surf, (cx - tw//2 + ddx, cy - th//2 + ddy))
    screen.blit(text_surf, (cx - tw//2, cy - th//2))

def _draw_star(surf, x, y, r, color):
    """Simple 8-point gold star."""
    if r < 1:
        return
    pts = [(x, y-r*2), (x+r//2, y-r//2), (x+r*2, y),   (x+r//2, y+r//2),
           (x, y+r*2), (x-r//2, y+r//2), (x-r*2, y),   (x-r//2, y-r//2)]
    pygame.draw.polygon(surf, color, pts)
    pygame.draw.polygon(surf, COLOR_OUTLINE, pts, max(1, r//3))

def _draw_banner(surf, rect, color=None):
    """Hot-pink pill banner with shadow, outline, and shine strip."""
    if color is None:
        color = COLOR_BLUSH
    r = rect.height // 2
    pygame.draw.rect(surf, COLOR_SHADOW, (rect.x+5, rect.y+7, rect.width, rect.height), border_radius=r)
    pygame.draw.rect(surf, color,        rect,                                            border_radius=r)
    pygame.draw.rect(surf, COLOR_OUTLINE, rect, 4,                                        border_radius=r)
    shine = pygame.Surface((max(1, rect.width-24), max(1, rect.height//3)), pygame.SRCALPHA)
    shine.fill((255, 255, 255, 65))
    surf.blit(shine, (rect.x+12, rect.y+8))

def get_trivia_layout():
    """Return (q_rect, start_y) based on current font so banner+card+answers all fit."""
    if font_win is None:
        return pygame.Rect(10, 80, WIDTH-20, 110), 215
    lines = wrap_text("Who Wants to Win a Nap?", font_win, WIDTH-48)
    banner_h = font_win.get_height() * len(lines) + 22
    q_top = banner_h + 10
    q_rect = pygame.Rect(10, q_top, WIDTH-20, 110)
    return q_rect, q_rect.bottom + 12

class CraftedBackground:
    def __init__(self):
        # Pre-bake sky gradient
        self._sky = pygame.Surface((WIDTH, HEIGHT))
        sky_h = int(HEIGHT * 0.63)
        for y in range(sky_h):
            t = y / max(1, sky_h - 1)
            r = int(COLOR_SKY_TOP[0]*(1-t) + COLOR_SKY_BOT[0]*t)
            g = int(COLOR_SKY_TOP[1]*(1-t) + COLOR_SKY_BOT[1]*t)
            b = int(COLOR_SKY_TOP[2]*(1-t) + COLOR_SKY_BOT[2]*t)
            pygame.draw.line(self._sky, (r, g, b), (0, y), (WIDTH, y))
        self._sky.fill(COLOR_GROUND, (0, sky_h, WIDTH, HEIGHT - sky_h))

        # Stars in sky only
        self.stars = [{"x": random.uniform(12, WIDTH-12),
                       "y": random.uniform(18, HEIGHT*0.46),
                       "size": random.uniform(2, 5),
                       "phase": random.uniform(0, 6.28)} for _ in range(22)]

        # Floating hearts (rise through sky area)
        self.particles = [{"x": random.uniform(0, WIDTH),
                           "y": random.uniform(0, HEIGHT*0.58),
                           "size": random.uniform(0.6, 1.5),
                           "speed": random.uniform(20, 52),
                           "seed": random.random(),
                           "color": random.choice([COLOR_BLUSH, COLOR_YELLOW,
                                                   (255,255,255), (255,130,175)])}
                          for _ in range(18)]

        # Flowers along front hill (fixed x, y derived each frame from hill curve)
        self.flowers = [{"x": random.uniform(10, WIDTH-10),
                         "kind": random.randint(0, 2),
                         "sz": random.randint(3, 6)} for _ in range(28)]

    # ── helpers ──────────────────────────────────────────────────────────────

    def _cloud(self, surf, cx, cy, w):
        for ox, oy, rr in [(0,0,w//2),(w//3,-w//5,int(w*.38)),
                            (-w//3,-w//7,int(w*.33)),(w//2,w//9,int(w*.26)),(-w//2,w//10,int(w*.24))]:
            s = pygame.Surface((rr*2+1, rr*2+1), pygame.SRCALPHA)
            pygame.draw.circle(s, (255,255,255,230), (rr, rr), rr)
            surf.blit(s, (cx+ox-rr, cy+oy-rr))

    def _flower(self, surf, x, y, kind, sz):
        petal = [(255,140,180),(255,255,255),(255,222,80)][kind]
        centre= [(255,220,0), (255,210,0),(255,160,20)][kind]
        for ang in range(0, 360, 60):
            rad = math.radians(ang)
            pygame.draw.circle(surf, petal,
                               (int(x+math.cos(rad)*(sz+1)), int(y+math.sin(rad)*(sz+1))), sz)
        pygame.draw.circle(surf, centre, (int(x), int(y)), max(1, sz-1))

    # ── main draw ────────────────────────────────────────────────────────────

    def draw(self, surf, dt):
        t = time.time()
        surf.blit(self._sky, (0, 0))

        # Clouds
        for i, (bx, by, bw) in enumerate([(75,78,95),(295,55,82),(172,112,70),(380,90,62)]):
            drift = math.sin(t*0.055 + i*1.85) * 9
            self._cloud(surf, int(bx+drift), by, bw)

        # Hill layer 1 — back, lightest
        h1 = int(HEIGHT*0.50)
        pts1 = [(0,h1+50),(WIDTH//7,h1-18),(2*WIDTH//7,h1+32),(3*WIDTH//7,h1-42),
                (4*WIDTH//7,h1+18),(5*WIDTH//7,h1-28),(6*WIDTH//7,h1+28),
                (WIDTH,h1+8),(WIDTH,HEIGHT),(0,HEIGHT)]
        pygame.draw.polygon(surf, COLOR_GRASS_BACK, pts1)

        # Hill layer 2 — mid
        h2 = int(HEIGHT*0.60)
        pts2 = [(0,h2+22),(WIDTH//5,h2-52),(2*WIDTH//5,h2+14),(WIDTH//2,h2-44),
                (3*WIDTH//5,h2+18),(4*WIDTH//5,h2-48),(WIDTH,h2+10),
                (WIDTH,HEIGHT),(0,HEIGHT)]
        pygame.draw.polygon(surf, COLOR_GRASS, pts2)

        # Cream ground strip — fills all the way to bottom
        gy = int(HEIGHT*0.78)
        pygame.draw.rect(surf, COLOR_GROUND, (0, gy, WIDTH, HEIGHT))

        # Hill layer 3 — front, darkest (sits on cream)
        h3 = int(HEIGHT*0.72)
        pts3 = [(0,h3+14),(WIDTH//4,h3-48),(WIDTH//2,h3+6),
                (3*WIDTH//4,h3-46),(WIDTH,h3+16),(WIDTH,HEIGHT),(0,HEIGHT)]
        pygame.draw.polygon(surf, COLOR_GRASS_DARK, pts3)

        # Flowers on front hill
        for fl in self.flowers:
            fy = h3 - 18 + int(math.sin(fl["x"]*0.055)*28)
            self._flower(surf, fl["x"], fy, fl["kind"], fl["sz"])

        # Twinkling gold stars
        for star in self.stars:
            tw = 0.5 + 0.5*math.sin(t*2.1 + star["phase"])
            r = max(1, int(star["size"]*tw))
            _draw_star(surf, int(star["x"]), int(star["y"]), r, COLOR_YELLOW)

        # Floating hearts
        for p in self.particles:
            p["y"] -= p["speed"] * dt
            if p["y"] < -20:
                p["y"] = HEIGHT * 0.60
            sway = math.sin(t*0.5 + p["seed"]*5) * 13
            draw_vector_heart(surf, int(p["x"]+sway), int(p["y"]),
                              p["size"], p["color"], 195)

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
    """Fullscreen autoplay video with NODO logo and skip button."""
    if not IS_WEB:
        return
    try:
        LOGO_URL = "https://troygeoghegan.github.io/Operation-Big-Mama/nodo_logo.png"
        done_js  = "document.getElementById('_nodo_wrap').setAttribute('data-done','1')"

        wrap = js.document.createElement("div")
        wrap.id = "_nodo_wrap"
        wrap.setAttribute("data-done", "0")
        wrap.style.cssText = ("position:fixed;top:0;left:0;width:100%;height:100%;"
                              "z-index:9999;background:#000;")

        # Video — autoplay (browser honours this after prior user interaction)
        v = js.document.createElement("video")
        v.id = "_nodo_vid"
        v.setAttribute("autoplay",        "")
        v.setAttribute("playsinline",     "")
        v.setAttribute("webkit-playsinline", "")
        v.setAttribute("onended", done_js)
        v.setAttribute("onerror", done_js)
        v.style.cssText = "width:100%;height:100%;object-fit:cover;"
        v.src = url
        wrap.appendChild(v)

        # NODO logo — centred, lower-third
        logo = js.document.createElement("img")
        logo.src = LOGO_URL
        logo.style.cssText = ("position:absolute;bottom:100px;left:50%;"
                              "transform:translateX(-50%);width:140px;"
                              "opacity:0.85;pointer-events:none;z-index:10001;")
        wrap.appendChild(logo)

        # Skip button — visible immediately, bottom centre
        skip = js.document.createElement("button")
        skip.id = "_nodo_skip"
        skip.textContent = "Skip"
        skip.style.cssText = ("position:absolute;bottom:36px;left:50%;"
                              "transform:translateX(-50%);padding:10px 40px;"
                              "background:rgba(235,196,196,0.92);color:rgb(94,80,80);"
                              "border:none;border-radius:24px;font-size:17px;"
                              "font-weight:bold;cursor:pointer;z-index:10002;")
        skip.setAttribute("onclick",      done_js + ";document.getElementById('_nodo_vid').pause()")
        skip.setAttribute("ontouchstart", done_js + ";document.getElementById('_nodo_vid').pause()")
        wrap.appendChild(skip)

        js.document.body.appendChild(wrap)
        while wrap.getAttribute("data-done") != "1":
            await asyncio.sleep(0.1)
        js.document.body.removeChild(wrap)
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
        iframe.setAttribute("loading", "eager")
        iframe.style.cssText = ("width:100vw;height:100vh;border:none;"
                                "max-width:100%;overflow-y:auto;-webkit-overflow-scrolling:touch;")
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
_prompt_start = None

font_title = None
font_win = None
font_ui = None
font_huge = None    # extra-large Fredoka for MAMA hero word

def draw_orientation_prompt(screen, dt):
    """Portrait welcome screen. Returns True when 'Let's Go' is tapped."""
    global _prompt_start
    if _prompt_start is None:
        _prompt_start = time.time()

    crafted_bg.draw(screen, dt)
    cx, cy = WIDTH // 2, HEIGHT // 2
    t       = time.time()
    elapsed = t - _prompt_start

    # ── Rising hearts (behind text) ──────────────────────────────────────────
    for i in range(7):
        seed  = i * 1.3
        speed = 30 + i * 8
        cycle = (t * speed * 0.01 + seed) % 1.0
        hx    = cx + math.sin(seed * 2.4 + t * 0.4) * (60 + i * 18)
        hy    = HEIGHT - cycle * (HEIGHT + 80)
        size  = 1.2 + math.sin(seed) * 0.6
        alpha = int(180 * math.sin(cycle * math.pi))
        color = [COLOR_BLUSH, COLOR_SAGE, COLOR_CARD_BACK][i % 3]
        draw_vector_heart(screen, hx, hy, size, color, alpha)

    msg_font  = font_ui if font_ui else pygame.font.SysFont(None, 28)
    title_cy  = cy - 50
    sub_cy    = cy + 30

    # ── Continuous-stroke handwriting reveal: "Hey Mama!" ────────────────────
    FULL_TITLE     = "Hey Mama!"
    WRITE_DURATION = 1.7   # seconds to write the full title

    title_surf  = font_title.render(FULL_TITLE, True, COLOR_CREAM)
    shadow_surf = font_title.render(FULL_TITLE, True, COLOR_OUTLINE)
    title_w, title_h = title_surf.get_size()

    # Smooth eased progress + subtle rhythm wobble (slight decel at
    # letter-lift points, faster across long strokes)
    raw_p       = min(1.0, elapsed / WRITE_DURATION)
    eased       = raw_p * raw_p * (3 - 2 * raw_p)          # smoothstep
    rhythm      = 0.025 * math.sin(raw_p * 9 * math.pi)    # ~1 micro-pause per letter
    reveal_frac = max(0.0, min(1.0, eased + rhythm))
    reveal_px   = int(title_w * reveal_frac)
    title_done  = raw_p >= 1.0

    title_x = cx - title_w // 2
    ty      = title_cy - title_h // 2

    # Clip-reveal: expose pre-rendered text surface from left to right
    screen.set_clip(pygame.Rect(title_x + 2, ty + 2, reveal_px, title_h))
    screen.blit(shadow_surf, (title_x + 2, ty + 2))
    screen.set_clip(pygame.Rect(title_x, ty, reveal_px, title_h))
    screen.blit(title_surf,  (title_x, ty))
    screen.set_clip(None)

    # Pen nib — glowing ink dot leading the stroke
    if not title_done and reveal_px > 0:
        nib_x = title_x + reveal_px
        nib_y = title_cy
        nib   = pygame.Surface((22, 22), pygame.SRCALPHA)
        pygame.draw.circle(nib, (*COLOR_BLUSH,   80),  (11, 11), 10)   # outer aura
        pygame.draw.circle(nib, (*COLOR_BLUSH,  160),  (11, 11),  6)   # ink body
        pygame.draw.circle(nib, (*COLOR_OUTLINE, 220), (11, 11),  3)   # nib tip
        pygame.draw.circle(nib, (255, 255, 255,  180), ( 9,  9),  2)   # wet gloss
        screen.blit(nib, (nib_x - 11, nib_y - 11))

    # Flourish underline draws itself after title finishes
    if title_done:
        fl_age  = elapsed - WRITE_DURATION
        fl_prog = min(1.0, fl_age / 0.38)
        fl_len  = int(title_w * 0.70 * fl_prog)
        fl_x    = cx - int(title_w * 0.70) // 2
        fl_y    = ty + title_h - 3
        if fl_len > 2:
            fl_surf = pygame.Surface((fl_len, 3), pygame.SRCALPHA)
            for px in range(fl_len):
                fade = math.sin(px / fl_len * math.pi)
                a    = int(85 * fade)
                fl_surf.set_at((px, 0), (*COLOR_CREAM,  a))
                fl_surf.set_at((px, 1), (*COLOR_BLUSH,  int(a * 0.75)))
                fl_surf.set_at((px, 2), (*COLOR_CREAM,  int(a * 0.3)))
            screen.blit(fl_surf, (fl_x, fl_y))

    # ── Word swell: "a little something just for you 🌸" ─────────────────────
    SUBTITLE    = "a little something just for you  \U0001f338"
    WORD_DELAY  = 0.20
    WORD_SWELL  = 0.22
    words       = SUBTITLE.split(" ")

    title_finish = WRITE_DURATION + 0.32   # brief pause after flourish
    sub_elapsed  = elapsed - title_finish

    full_sub_w = msg_font.render(SUBTITLE, True, COLOR_CREAM).get_width()
    draw_x     = cx - full_sub_w // 2
    sub_y_top  = sub_cy - msg_font.get_height() // 2
    cursor_x   = draw_x
    space_w    = msg_font.render(" ", True, COLOR_CREAM).get_width()

    for wi, word in enumerate(words):
        age = sub_elapsed - wi * WORD_DELAY
        if age < 0:
            break
        word_surf = msg_font.render(word, True, COLOR_CREAM)
        ww, wh    = word_surf.get_size()
        if age < WORD_SWELL:
            p     = age / WORD_SWELL
            scale = p * (2 - p) * (1 + 0.28 * math.sin(p * math.pi))
            sw    = max(1, int(ww * scale))
            sh_h  = max(1, int(wh * scale))
            wx    = cursor_x + (ww - sw) // 2
            wy    = sub_y_top + (wh - sh_h) // 2
            sh_sc = pygame.transform.smoothscale(msg_font.render(word, True, COLOR_OUTLINE), (sw, sh_h))
            sc    = pygame.transform.smoothscale(word_surf, (sw, sh_h))
            screen.blit(sh_sc, (wx + 2, wy + 2))
            screen.blit(sc,    (wx,     wy))
        else:
            sh_surf = msg_font.render(word, True, COLOR_OUTLINE)
            screen.blit(sh_surf,  (cursor_x + 2, sub_y_top + 2))
            screen.blit(word_surf, (cursor_x,     sub_y_top))
        cursor_x += ww + space_w

    # ── Button — bubble swell pop-in ─────────────────────────────────────────
    last_word_done = title_finish + (len(words) - 1) * WORD_DELAY + WORD_SWELL
    btn_w, btn_h   = 220, 54
    btn_cx         = cx
    btn_mid_y      = HEIGHT - 103

    swell_t   = elapsed - last_word_done
    p_btn     = min(1.0, max(0.0, swell_t / 0.45))
    btn_scale = p_btn * (2 - p_btn) * (1 + 0.22 * math.sin(p_btn * math.pi)) if swell_t >= 0 else 0.0

    btn_rect = pygame.Rect(btn_cx - btn_w // 2, btn_mid_y - btn_h // 2, btn_w, btn_h)

    if btn_scale > 0.01:
        sw = max(1, int(btn_w * btn_scale))
        sh = max(1, int(btn_h * btn_scale))
        btn_surf = pygame.Surface((btn_w, btn_h), pygame.SRCALPHA)
        draw_crafted_button(btn_surf, pygame.Rect(0, 0, btn_w, btn_h),
                            "Let's Go!", msg_font, COLOR_BLUSH)
        scaled_btn = pygame.transform.smoothscale(btn_surf, (sw, sh))
        screen.blit(scaled_btn, (btn_cx - sw // 2, btn_mid_y - sh // 2))

    for event in pygame.event.get(pygame.MOUSEBUTTONDOWN):
        if btn_rect.collidepoint(event.pos):
            _prompt_start = None
            return True
    for event in pygame.event.get(pygame.FINGERDOWN):
        fx, fy = int(event.x * WIDTH), int(event.y * HEIGHT)
        if btn_rect.collidepoint(fx, fy):
            _prompt_start = None
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


def _render_scaled_outlined(surf, text, font, scale, color, cx, cy):
    """Render `text` in `font` scaled to `scale` fraction, with dark outline."""
    ts = font.render(text, True, color)
    os_ = font.render(text, True, COLOR_OUTLINE)
    nw = max(1, int(ts.get_width() * scale))
    nh = max(1, int(ts.get_height() * scale))
    ts  = pygame.transform.smoothscale(ts,  (nw, nh))
    os_ = pygame.transform.smoothscale(os_, (nw, nh))
    ow = 3
    for ddx in (-ow, 0, ow):
        for ddy in (-ow, 0, ow):
            if ddx or ddy:
                surf.blit(os_, (cx - nw//2 + ddx, cy - nh//2 + ddy))
    surf.blit(ts, (cx - nw//2, cy - nh//2))

def _draw_menu_scene(surf, t):
    """Mother's Day illustration: sun, rainbow, big flowers, floating hearts."""
    # ── Sun top-right ────────────────────────────────────────────────────────
    sun_x, sun_y, sun_r = int(WIDTH * 0.82), 72, 36
    for ang in range(0, 360, 30):
        rad = math.radians(ang + t * 15)
        rlen = sun_r + 16 + int(math.sin(t * 2.5 + ang) * 4)
        x1 = int(sun_x + math.cos(rad) * (sun_r + 5))
        y1 = int(sun_y + math.sin(rad) * (sun_r + 5))
        x2 = int(sun_x + math.cos(rad) * rlen)
        y2 = int(sun_y + math.sin(rad) * rlen)
        pygame.draw.line(surf, COLOR_OUTLINE, (x1, y1), (x2, y2), 3)
        pygame.draw.line(surf, COLOR_YELLOW,  (x1, y1), (x2, y2), 2)
    pygame.draw.circle(surf, COLOR_OUTLINE, (sun_x, sun_y), sun_r + 3)
    pygame.draw.circle(surf, COLOR_YELLOW,  (sun_x, sun_y), sun_r)
    pygame.draw.circle(surf, (255, 245, 150), (sun_x - 10, sun_y - 10), sun_r // 3)

    # ── Rainbow — thick bubbly bands drawn as circle chains ─────────────────
    r_cols  = [(255,80,80),(255,160,0),(255,230,0),(80,200,80),(80,140,255),(180,80,255)]
    arc_cx  = int(WIDTH * 0.38)
    arc_cy  = int(HEIGHT * 0.60)
    band_r  = 10          # radius of each circle in the chain
    spacing = 7           # degrees between circles
    for ri, rc in enumerate(r_cols):
        rr = 82 + ri * (band_r * 2 + 3)
        # dark outline ring first
        for ang in range(10, 171, spacing):
            rad = math.radians(ang)
            cx2 = int(arc_cx + math.cos(rad) * rr)
            cy2 = int(arc_cy - math.sin(rad) * rr)
            pygame.draw.circle(surf, COLOR_OUTLINE, (cx2, cy2), band_r + 2)
        # colour fill on top
        for ang in range(10, 171, spacing):
            rad = math.radians(ang)
            cx2 = int(arc_cx + math.cos(rad) * rr)
            cy2 = int(arc_cy - math.sin(rad) * rr)
            pygame.draw.circle(surf, rc, (cx2, cy2), band_r)
            # shine dot top-left
            pygame.draw.circle(surf, (255,255,255),
                               (cx2 - band_r//3, cy2 - band_r//3),
                               max(1, band_r // 3))

    # ── Big foreground flowers ────────────────────────────────────────────────
    h3y = int(HEIGHT * 0.72)
    flowers = [
        (int(WIDTH * 0.10), h3y - 28, 11, [(255,120,170),(255,240,0)]),
        (int(WIDTH * 0.28), h3y - 50, 13, [(255,255,255),(255,210,0)]),
        (int(WIDTH * 0.50), h3y - 36, 10, [(255,190,80), (255,130,0)]),
        (int(WIDTH * 0.72), h3y - 52, 14, [(255,120,170),(255,240,0)]),
        (int(WIDTH * 0.90), h3y - 26, 10, [(255,255,255),(255,210,0)]),
    ]
    for fx, fy, fsz, (pc, cc) in flowers:
        pygame.draw.line(surf, COLOR_GRASS_DARK, (fx, fy), (fx, fy + fsz * 3),
                         max(2, fsz // 4))
        for ang in range(0, 360, 45):
            rad = math.radians(ang)
            pygame.draw.circle(surf, COLOR_OUTLINE,
                               (int(fx + math.cos(rad) * (fsz+2)),
                                int(fy + math.sin(rad) * (fsz+2))), fsz+1)
            pygame.draw.circle(surf, pc,
                               (int(fx + math.cos(rad) * (fsz+1)),
                                int(fy + math.sin(rad) * (fsz+1))), fsz)
        pygame.draw.circle(surf, COLOR_OUTLINE, (fx, fy), fsz // 2 + 2)
        pygame.draw.circle(surf, cc,            (fx, fy), fsz // 2)

    # ── Floating hearts rising through the sky ────────────────────────────────
    heart_cols = [COLOR_BLUSH, COLOR_YELLOW, COLOR_CREAM, (255,160,200), COLOR_BLUSH]
    for i in range(5):
        seed  = i * 1.7
        hx    = int(WIDTH * (0.12 + i * 0.19))
        cycle = (t * 0.38 + seed) % 1.0
        hy    = int(HEIGHT * 0.58 - cycle * HEIGHT * 0.48)
        alpha = int(210 * math.sin(cycle * math.pi))
        size  = 0.8 + 0.4 * math.sin(seed)
        draw_vector_heart(surf, hx, hy, size, heart_cols[i], alpha)


def draw_menu(screen, dt, selected_idx, completed_games):
    crafted_bg.draw(screen, dt)
    t = time.time()

    # Full-screen Mother's Day illustration
    _draw_menu_scene(screen, t)

    # ── Title lockup: "Happy" / "MAMA" / "Day ♥" ─────────────────────────────
    #   Small word → HUGE hero word → small word  (like the reference)
    _fhuge    = font_huge if font_huge else font_title
    lockup_cy = int(HEIGHT * 0.26)
    cx        = WIDTH // 2

    # Row heights — happy/day are _fhuge scaled down
    r_mama  = _fhuge.get_height()
    r_happy = int(r_mama * 0.40)
    r_day   = int(r_mama * 0.38)
    gap     = 4
    total_h = r_happy + gap + r_mama + gap + r_day

    y_happy = lockup_cy - total_h // 2
    y_mama  = y_happy + r_happy + gap
    y_day   = y_mama  + r_mama  + gap

    # ── "Happy" — same font as MAMA but scaled down to ~40% ─────────────────
    _render_scaled_outlined(screen, "Happy", _fhuge, 0.40, COLOR_CREAM,
                            cx, y_happy + r_happy // 2)

    # ── "MAMA" — each letter individually, bouncing + alternating pink/gold ──
    letters      = "MAMA"
    alt_cols     = [COLOR_BLUSH, COLOR_YELLOW, COLOR_BLUSH, COLOR_YELLOW]
    letter_surfs = [_fhuge.render(l, True, c) for l, c in zip(letters, alt_cols)]
    out_surfs    = [_fhuge.render(l, True, COLOR_OUTLINE) for l in letters]
    total_lw     = sum(s.get_width() for s in letter_surfs) + 2 * (len(letters) - 1)
    lx           = cx - total_lw // 2
    ow            = 4   # outline width
    for idx, (ls, os_) in enumerate(zip(letter_surfs, out_surfs)):
        bob  = int(math.sin(t * 2.8 + idx * 1.1) * 7)
        ly   = y_mama + bob
        lw   = ls.get_width()
        lh   = ls.get_height()
        # Dark outline — 8 directions
        for ddx in (-ow, 0, ow):
            for ddy in (-ow, 0, ow):
                if ddx or ddy:
                    screen.blit(os_, (lx + ddx, ly + ddy))
        screen.blit(ls, (lx, ly))
        # Shine spot top-left of each letter
        shine_s = pygame.Surface((max(1, lw // 3), max(1, lh // 5)), pygame.SRCALPHA)
        shine_s.fill((255, 255, 255, 80))
        screen.blit(shine_s, (lx + lw // 6, ly + lh // 8))
        lx += lw + 2

    # ── "Day ♥" — same font as MAMA scaled to ~38%, gold ────────────────────
    _render_scaled_outlined(screen, "Day  \u2665", _fhuge, 0.38, COLOR_YELLOW,
                            cx, y_day + r_day // 2)

    # Pulsing stars beside the lockup
    for i, (sx, sy, sr) in enumerate([
        (cx - 162, y_happy + r_happy // 2, 7),
        (cx + 162, y_happy + r_happy // 2, 7),
        (cx - 148, y_day   + r_day   // 2, 5),
        (cx + 148, y_day   + r_day   // 2, 5),
    ]):
        pulse = 1.0 + 0.3 * math.sin(t * 2.5 + i * 1.4)
        _draw_star(screen, sx, sy, int(sr * pulse), COLOR_YELLOW)

    # ── Buttons pinned to bottom ──────────────────────────────────────────────
    BTN_COLORS = [(100, 196, 248), COLOR_BLUSH, (255, 185, 0)]
    btn_h   = 66
    btn_gap = 10
    btn_top = HEIGHT - 3 * btn_h - 2 * btn_gap - 70
    for i, opt in enumerate(options):
        rect = pygame.Rect(WIDTH // 2 - 148, btn_top + i * (btn_h + btn_gap), 296, btn_h)
        col  = COLOR_BLUSH if i == selected_idx else BTN_COLORS[i % 3]
        draw_crafted_button(screen, rect, opt["text"], font_ui, col)
        if i in completed_games:
            draw_vector_heart(screen, rect.right - 28, rect.centery, 1.0, COLOR_YELLOW)

def draw_playing(screen, dt, limit, elapsed_time, cards):
    crafted_bg.draw(screen, dt)

    if limit:
        remaining = max(0, limit - elapsed_time)
        bar_w = int((remaining / limit) * (WIDTH - 40))
        pygame.draw.rect(screen, COLOR_OUTLINE, (20, 18, WIDTH-40, 16), border_radius=8)
        pygame.draw.rect(screen, (200, 220, 255), (22, 20, WIDTH-44, 12), border_radius=6)
        pygame.draw.rect(screen, COLOR_OUTLINE, (20, 18, WIDTH-40, 16), 3, border_radius=8)
        if bar_w > 0:
            pygame.draw.rect(screen, COLOR_YELLOW, (22, 20, max(0,bar_w-4), 12), border_radius=6)

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
        pygame.draw.rect(screen, (0, 0, 0), shadow_rect, border_radius=12)

        if card["flip_proc"] > 0.5:
            pygame.draw.rect(screen, COLOR_GROUND, draw_rect, border_radius=12)
            pygame.draw.rect(screen, COLOR_OUTLINE, draw_rect, 3, border_radius=12)
            if flip_w > 0.1:
                scaled_img = pygame.transform.scale(card["image"], (int((SIDE-10)*flip_w), SIDE-10))
                screen.blit(scaled_img, (draw_rect.centerx - scaled_img.get_width()//2, draw_rect.centery - scaled_img.get_height()//2))
        else:
            pygame.draw.rect(screen, COLOR_CARD_BACK, draw_rect, border_radius=12)
            pygame.draw.rect(screen, COLOR_OUTLINE,   draw_rect, 3, border_radius=12)
            ss = max(2, draw_rect.width // 7)
            _draw_star(screen, draw_rect.centerx, draw_rect.centery, ss, COLOR_YELLOW)

    auto_rect = pygame.Rect(WIDTH // 2 - 55, HEIGHT - GAME_BOTTOM + 5, 110, 38)
    draw_crafted_button(screen, auto_rect, "Auto Win", font_ui, COLOR_BLUSH)

def draw_trivia(screen, dt, question_idx):
    crafted_bg.draw(screen, dt)

    q_rect, start_y = get_trivia_layout()

    # ── Title banner ─────────────────────────────────────────────────────────
    title_lines = wrap_text("Who Wants to Win a Nap?", font_win, WIDTH - 48)
    th = font_win.get_height()
    banner_h = th * len(title_lines) + 22
    _draw_banner(screen, pygame.Rect(10, 6, WIDTH-20, banner_h))
    _draw_star(screen, 24,        6+banner_h//2, 7, COLOR_YELLOW)
    _draw_star(screen, WIDTH-24,  6+banner_h//2, 7, COLOR_YELLOW)
    ty = 6 + 11
    for line in title_lines:
        draw_soft_text(screen, line, font_win, COLOR_CREAM, (WIDTH//2, ty + th//2))
        ty += th

    if question_idx >= len(TRIVIA_QUESTIONS):
        return

    q_data = TRIVIA_QUESTIONS[question_idx]

    # ── Question card ─────────────────────────────────────────────────────────
    pygame.draw.rect(screen, (0, 0, 0),      (q_rect.x+4, q_rect.y+5, q_rect.width, q_rect.height), border_radius=14)
    pygame.draw.rect(screen, COLOR_GROUND,    q_rect, border_radius=14)
    pygame.draw.rect(screen, COLOR_OUTLINE,   q_rect, 3, border_radius=14)

    q_lines = wrap_text(q_data["question"], font_ui, q_rect.width - 28)
    line_h  = font_ui.get_height()
    qy = q_rect.centery - (line_h * len(q_lines)) // 2
    for line in q_lines:
        q_txt = font_ui.render(line, True, COLOR_OUTLINE)
        screen.blit(q_txt, (q_rect.centerx - q_txt.get_width()//2, qy))
        qy += line_h

    # ── Answer buttons (alternating blue / pink) ──────────────────────────────
    OPT_COLORS = [(100, 196, 248), COLOR_BLUSH, (100, 196, 248), COLOR_BLUSH]
    mx, my = pygame.mouse.get_pos()
    for i, opt in enumerate(q_data["options"]):
        opt_rect = pygame.Rect(WIDTH//2 - 185, start_y + i*82, 370, 66)
        col = COLOR_BLUSH if opt_rect.collidepoint(mx, my) else OPT_COLORS[i]
        draw_crafted_button(screen, opt_rect, opt, font_ui, col)

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
    crafted_bg.draw(screen, dt)
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
    pygame.draw.rect(gift_surf, COLOR_BLUSH,   body_rect, border_radius=8)
    pygame.draw.rect(gift_surf, COLOR_OUTLINE, body_rect, 3, border_radius=8)

    ribbon_w = 14
    pygame.draw.rect(gift_surf, COLOR_SAGE, (cx - ribbon_w // 2, by, ribbon_w, box_h))
    pygame.draw.rect(gift_surf, COLOR_SAGE, (bx, by + box_h // 2 - ribbon_w // 2, box_w, ribbon_w))

    if is_open:
        open_progress = min(1.0, (elapsed - shake_phase) / 0.4)
        lid_y = by - lid_h - int(open_progress * 55)
    else:
        lid_y = by - lid_h

    lid_rect = pygame.Rect(bx - 4, lid_y, box_w + 8, lid_h)
    pygame.draw.rect(gift_surf, COLOR_BLUSH,   lid_rect, border_radius=8)
    pygame.draw.rect(gift_surf, COLOR_OUTLINE, lid_rect, 3, border_radius=8)

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
        base_txt = font_win.render("Good Job!", True, COLOR_CREAM)
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
    
    draw_soft_text(screen, "Happy Mother's Day!", font_title, COLOR_CREAM,
                   (WIDTH//2, HEIGHT//2 - 40), WIDTH - 30)

    menu_button_rect = pygame.Rect(WIDTH//2 - 168, HEIGHT - 105, 150, 62)
    draw_crafted_button(screen, menu_button_rect, "MENU", font_ui, (100, 196, 248))

    exit_button_rect = pygame.Rect(WIDTH//2 + 18, HEIGHT - 105, 150, 62)
    draw_crafted_button(screen, exit_button_rect, "EXIT", font_ui, COLOR_BLUSH)
    
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
    global screen, clock, crafted_bg, game_images, reward_images, menu_images, nodo_image, nodo_video_path, massage_video_path, pdf_surface, pdf_surface_height, font_title, font_win, font_ui, font_huge

    pygame.display.init()
    pygame.font.init()
    if not IS_WEB:
        try:
            pygame.mixer.init()
        except Exception:
            pass
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()

    if IS_WEB:
        try:
            style = js.document.createElement("style")
            style.textContent = (
                "body{margin:0;padding:0;background:#0a0520;"
                "display:flex;justify-content:center;align-items:center;"
                "width:100vw;height:100vh;overflow:hidden;}"
                "canvas{display:block;width:100vw;height:100vh;"
                "object-fit:contain;touch-action:none;}"
            )
            js.document.head.appendChild(style)
            vm = js.document.querySelector("meta[name='viewport']")
            if not vm:
                vm = js.document.createElement("meta")
                vm.name = "viewport"
                vm.content = "width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no"
                js.document.head.appendChild(vm)
        except Exception:
            pass

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

    _curr_dir  = os.path.dirname(os.path.abspath(__file__))
    _parent_dir = os.path.dirname(_curr_dir)

    # Fredoka One → titles and win-screen text (bubbly, rounded)
    fredoka = None
    for fname in ["FredokaOne-Regular.ttf", "Fredoka_One.ttf", "fredoka_one.ttf"]:
        p = os.path.join(_curr_dir, fname)
        if os.path.exists(p):
            try: fredoka = p; break
            except: pass

    # Titan One → buttons and UI text (chunky, bold)
    titan = None
    for fname in ["TitanOne-Regular.ttf", "Titan_One.ttf", "titan_one.ttf"]:
        p = os.path.join(_curr_dir, fname)
        if os.path.exists(p):
            try: titan = p; break
            except: pass

    try:
        font_title = pygame.font.Font(fredoka, 54) if fredoka else pygame.font.SysFont(None, 52)
        font_win   = pygame.font.Font(fredoka, 40) if fredoka else pygame.font.SysFont(None, 40)
        font_huge  = pygame.font.Font(titan,   92) if titan   else pygame.font.SysFont(None, 88)
    except:
        font_title = pygame.font.SysFont(None, 52)
        font_win   = pygame.font.SysFont(None, 40)
        font_huge  = pygame.font.SysFont(None, 88)

    try:
        font_ui = pygame.font.Font(titan, 22) if titan else pygame.font.SysFont(None, 24)
    except:
        font_ui = pygame.font.SysFont(None, 24)

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
                    btn_top = HEIGHT - 3 * 66 - 2 * 10 - 70
                    for i in range(3):
                        if pygame.Rect(WIDTH//2 - 148, btn_top + i * 76, 296, 66).collidepoint(mx, my):
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
                    _, start_y = get_trivia_layout()
                    for i in range(4):
                        opt_rect = pygame.Rect(WIDTH//2 - 185, start_y + i*82, 370, 66)
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