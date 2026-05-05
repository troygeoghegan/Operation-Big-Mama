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

MENU_PDF = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "SpaceSwarm", "Images", "Menu", "Menu.pdf")

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
DEBUG_MODE = os.environ.get("MAMA_DEBUG", "0") == "1"

def trigger_vibration():
    if HAS_VIBRATOR:
        try: vibrator.vibrate(0.4)
        except Exception: pass
    if HAS_JS:
        try: js.navigator.vibrate(400)
        except Exception: pass

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
    PLAYING_PUZZLE = auto()
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
    SECRET_REWARD = auto()

TRIVIA_QUESTIONS = [
    {
        "question": "Which of these is the ultimate brunch beverage?",
        "options": ["Tap water", "Mimosas", "Warm milk", "Pickle juice"],
        "answer": 1
    },
    {
        "question": "What time is the socially acceptable hour to start eating brunch?",
        "options": ["6:00 AM", "10:00 AM to 2:00 PM", "4:00 PM", "Midnight"],
        "answer": 1
    },
    {
        "question": "What are River and McKenna's favourite colours combined?",
        "options": ["Peach", "Coral", "Light Orange", "Apricot"],
        "answer": 0
    },
    {
        "question": "What is the number of the Twins SIN's added together",
        "options": ["648345911", "985549843", "296632516", "468830127"],
        "answer": 2
    },
    {
        "question": "River and McKenna Love ______ the most.",
        "options": ["Unicorns", "Mama", "Tractors", "Drums"],
        "answer": 1
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
            "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
            "answer": 1
        }
        Do NOT prefix options with letters like "A)" or "B)". The 'answer' should be the integer index (0-3) of the correct option.
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
    0: "",
    1: "",
    2: ""
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

SOUNDS = {}
SOUND_NAMES = ("correct", "wrong", "flip", "match", "slide", "win")
_last_won_anim_time = -1.0

def _init_sounds():
    """Load all sound effects from images/sounds/. Safe to call once mixer is up."""
    global SOUNDS
    try:
        if not pygame.mixer.get_init():
            return
    except Exception:
        return
    snd_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")
    for name in SOUND_NAMES:
        path = os.path.join(snd_dir, name + ".wav")
        if os.path.exists(path):
            try:
                SOUNDS[name] = pygame.mixer.Sound(path)
            except Exception:
                SOUNDS[name] = None

def play_sound(name):
    """Play a loaded sound effect; no-op if mixer/file unavailable."""
    s = SOUNDS.get(name)
    if s is not None:
        try: s.play()
        except Exception: pass


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

_btn_text_cache = {}

def _draw_brunch_item(surf, item_type, cx, cy, scale, alpha):
    """Draws a brunch-themed sticker icon."""
    s = max(0.1, scale)
    if alpha < 1: return

    if item_type == 0:  # Croissant
        temp_surf = pygame.Surface((int(60 * s), int(40 * s)), pygame.SRCALPHA)
        body_color = (214, 156, 70)
        line_color = (139, 90, 40)
        body_rect = pygame.Rect(int(10 * s), 0, int(40 * s), int(25 * s))
        pygame.draw.arc(temp_surf, body_color, body_rect, 0, math.pi, int(12 * s))
        pygame.draw.arc(temp_surf, line_color, body_rect, 0, math.pi, int(2 * s))
        for i in range(3):
            start, end = 0.5 + i * 0.7, 0.8 + i * 0.7
            pygame.draw.arc(temp_surf, line_color, body_rect.inflate(int(-10 * s), int(-10 * s)), start, end, int(1.5 * s))
        temp_surf.set_alpha(alpha)
        surf.blit(temp_surf, (cx - 30 * s, cy - 20 * s))

    elif item_type == 1:  # Coffee Cup
        temp_surf = pygame.Surface((int(60 * s), int(60 * s)), pygame.SRCALPHA)
        tx, ty = 30 * s, 40 * s
        cup_w_top, cup_w_bot, cup_h = 30 * s, 20 * s, 25 * s
        cup_pts = [(tx - cup_w_top / 2, ty - cup_h / 2), (tx + cup_w_top / 2, ty - cup_h / 2),
                   (tx + cup_w_bot / 2, ty + cup_h / 2), (tx - cup_w_bot / 2, ty + cup_h / 2)]
        pygame.draw.polygon(temp_surf, (240, 240, 255), cup_pts)
        pygame.draw.polygon(temp_surf, COLOR_OUTLINE, cup_pts, int(2 * s))
        pygame.draw.ellipse(temp_surf, COLOR_OUTLINE, (tx - cup_w_top / 2, ty - cup_h / 2 - 3 * s, cup_w_top, 6 * s), int(2 * s))
        pygame.draw.arc(temp_surf, COLOR_OUTLINE, (tx + cup_w_top / 2 - 2 * s, ty - cup_h / 4, 12 * s, 15 * s), -math.pi / 2, math.pi / 2, int(3 * s))
        for i in range(3):
            sx = tx - 8 * s + i * 8 * s
            sy = ty - cup_h / 2 - 5 * s
            pts = [(sx + math.sin(time.time() * 4 + i) * 2 * s, sy - j * 4 * s) for j in range(4)]
            if len(pts) > 1: pygame.draw.lines(temp_surf, (200, 200, 210), False, pts, int(2 * s))
        temp_surf.set_alpha(alpha)
        surf.blit(temp_surf, (cx - 30 * s, cy - 40 * s))

    else:  # Mimosa
        temp_surf = pygame.Surface((int(40 * s), int(80 * s)), pygame.SRCALPHA)
        tx, ty = 20 * s, 25 * s
        glass_h, glass_w = 40 * s, 18 * s
        bowl_pts = [(tx - glass_w / 2, ty - glass_h / 2), (tx + glass_w / 2, ty - glass_h / 2), (tx, ty)]
        pygame.draw.polygon(temp_surf, (200, 220, 255, 70), bowl_pts)
        drink_h, drink_w = glass_h * 0.8, glass_w * 0.9
        drink_pts = [(tx - drink_w / 2, ty - glass_h / 2 + (glass_h - drink_h)),
                     (tx + drink_w / 2, ty - glass_h / 2 + (glass_h - drink_h)), (tx, ty)]
        pygame.draw.polygon(temp_surf, (255, 180, 70), drink_pts)
        for _ in range(3):
            pygame.draw.circle(temp_surf, (255, 220, 150),
                               (tx + random.uniform(-drink_w / 3, drink_w / 3), ty - random.uniform(0, drink_h * 0.7)),
                               random.uniform(1, 2) * s)
        stem_y_end = ty + 20 * s
        pygame.draw.line(temp_surf, COLOR_OUTLINE, (tx, ty), (tx, stem_y_end), int(2 * s))
        pygame.draw.ellipse(temp_surf, COLOR_OUTLINE, (tx - 12 * s, stem_y_end - 2 * s, 24 * s, 4 * s), int(2 * s))
        pygame.draw.polygon(temp_surf, COLOR_OUTLINE, bowl_pts, int(2 * s))
        temp_surf.set_alpha(alpha)
        surf.blit(temp_surf, (cx - 20 * s, cy - 40 * s))

_btn_text_cache = {}

def draw_crafted_button(screen, rect, text, font, base_color, text_outline_color=None):
    mx, my = pygame.mouse.get_pos()
    is_hover = rect.collidepoint(mx, my)
    offset = 3 if is_hover else 0
    r = rect.height // 2
    outline_col = text_outline_color if text_outline_color is not None else COLOR_OUTLINE

    # Drop shadow
    pygame.draw.rect(screen, (0, 0, 0),   (rect.x+5, rect.y+7, rect.width, rect.height), border_radius=r)
    btn = pygame.Rect(rect.x, rect.y - offset, rect.width, rect.height)
    # Body
    pygame.draw.rect(screen, base_color,   btn, border_radius=r)
    # Outline
    pygame.draw.rect(screen, COLOR_OUTLINE, btn, 4, border_radius=r)
    # Glossy gradient highlight — bright at top, fading down
    inset = 5
    sw, sh = btn.width - inset * 2, btn.height // 2
    if sw > 0 and sh > 0:
        shine_surf = pygame.Surface((btn.width, btn.height), pygame.SRCALPHA)
        # Build vertical gradient from white-90 at top to transparent
        grad = pygame.Surface((sw, sh), pygame.SRCALPHA)
        for row in range(sh):
            alpha = int(90 * (1 - row / sh) ** 1.5)
            pygame.draw.line(grad, (255, 255, 255, alpha), (0, row), (sw - 1, row))
        # Pill-shaped mask so gradient stays inside the button
        mask = pygame.Surface((btn.width, btn.height), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255),
                         (inset, inset, sw, btn.height - inset * 2),
                         border_radius=max(1, r - inset))
        shine_surf.blit(grad, (inset, inset))
        shine_surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        screen.blit(shine_surf, (btn.x, btn.y))

    lines = wrap_text(text, font, btn.width - 20)
    line_h = font.get_height()
    ty = btn.centery - (line_h * len(lines)) // 2
    for line in lines:
        cache_key = (line, id(font), outline_col)
        cached_line = _btn_text_cache.get(cache_key)
        if cached_line is None:
            o = font.render(line, True, outline_col)
            ts = font.render(line, True, COLOR_CREAM)
            tw, th = ts.get_size()
            ow = 2
            combined = pygame.Surface((tw + ow*2, th + ow*2), pygame.SRCALPHA)
            for ddx, ddy in [(-ow,0),(ow,0),(0,-ow),(0,ow),(-ow,-ow),(ow,-ow),(-ow,ow),(ow,ow)]:
                combined.blit(o, (ow + ddx, ow + ddy))
            combined.blit(ts, (ow, ow))
            _btn_text_cache[cache_key] = combined
            cached_line = combined
        screen.blit(cached_line, (btn.centerx - cached_line.get_width()//2, ty))
        ty += line_h

_soft_text_cache = {}

def draw_soft_text(screen, text, font, color, center_pos, max_width=None):
    """Cartoon outlined text: dark navy ring, then colour fill on top. Cached."""
    key = (text, id(font), color, max_width)
    cached = _soft_text_cache.get(key)
    if cached is None:
        text_surf = font.render(text, True, color)
        out_surf  = font.render(text, True, COLOR_OUTLINE)
        if max_width and text_surf.get_width() > max_width:
            sc = max_width / text_surf.get_width()
            nw, nh = max(1, int(text_surf.get_width()*sc)), max(1, int(text_surf.get_height()*sc))
            text_surf = pygame.transform.smoothscale(text_surf, (nw, nh))
            out_surf  = pygame.transform.smoothscale(out_surf,  (nw, nh))
        tw, th = text_surf.get_size()
        ow = 3
        combined = pygame.Surface((tw + ow*2, th + ow*2), pygame.SRCALPHA)
        for ddx in (-ow, 0, ow):
            for ddy in (-ow, 0, ow):
                if ddx or ddy:
                    combined.blit(out_surf, (ow + ddx, ow + ddy))
        combined.blit(text_surf, (ow, ow))
        _soft_text_cache[key] = combined
        cached = combined
    cx, cy = center_pos
    screen.blit(cached, (cx - cached.get_width()//2, cy - cached.get_height()//2))

def _draw_star(surf, x, y, r, color):
    """Simple 8-point gold star."""
    if r < 1:
        return
    pts = [(x, y-r*2), (x+r//2, y-r//2), (x+r*2, y),   (x+r//2, y+r//2),
           (x, y+r*2), (x-r//2, y+r//2), (x-r*2, y),   (x-r//2, y-r//2)]
    pygame.draw.polygon(surf, color, pts)
    pygame.draw.polygon(surf, COLOR_OUTLINE, pts, max(1, r//3))

def _draw_banner(surf, rect, color=None):
    """Hot-pink pill banner with shadow, outline, and glossy gradient highlight."""
    if color is None:
        color = COLOR_BLUSH
    r = rect.height // 2
    pygame.draw.rect(surf, COLOR_SHADOW, (rect.x+5, rect.y+7, rect.width, rect.height), border_radius=r)
    pygame.draw.rect(surf, color,        rect,                                            border_radius=r)
    pygame.draw.rect(surf, COLOR_OUTLINE, rect, 4,                                        border_radius=r)

    inset = 5
    sw, sh = rect.width - inset * 2, rect.height // 2
    if sw > 0 and sh > 0:
        shine_surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        grad = pygame.Surface((sw, sh), pygame.SRCALPHA)
        for row in range(sh):
            alpha = int(90 * (1 - row / sh) ** 1.5)
            pygame.draw.line(grad, (255, 255, 255, alpha), (0, row), (sw - 1, row))
        mask = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255),
                         (inset, inset, sw, rect.height - inset * 2),
                         border_radius=max(1, r - inset))
        shine_surf.blit(grad, (inset, inset))
        shine_surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        surf.blit(shine_surf, (rect.x, rect.y))

def _menu_button_rects():
    """Shared menu button geometry — used by both draw_menu and click handler."""
    btn_h, btn_gap = 66, 10
    btn_top = HEIGHT - 3 * btn_h - 2 * btn_gap - 70
    return [pygame.Rect(WIDTH // 2 - 148, btn_top + i * (btn_h + btn_gap), 296, btn_h) for i in range(3)]

def get_trivia_layout():
    """Return (q_rect, start_y) based on current font so banner+card+answers all fit."""
    banner_y = 70
    if font_win is None or font_ui is None:
        return pygame.Rect(10, banner_y + 80, WIDTH-20, 130), banner_y + 240
    banner_h = font_ui.get_height() + font_win.get_height() + 22
    q_top = banner_y + banner_h + 40
    q_rect = pygame.Rect(10, q_top, WIDTH-20, 130)
    return q_rect, q_rect.bottom + 40

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
                         "kind": random.choices([0, 1, 2], weights=[60, 20, 20])[0],
                         "sz": random.randint(3, 6)} for _ in range(28)]

    # ── helpers ──────────────────────────────────────────────────────────────

    def _cloud(self, surf, cx, cy, w):
        for ox, oy, rr in [(0,0,w//2),(w//3,-w//5,int(w*.38)),
                            (-w//3,-w//7,int(w*.33)),(w//2,w//9,int(w*.26)),(-w//2,w//10,int(w*.24))]:
            s = pygame.Surface((rr*2+1, rr*2+1), pygame.SRCALPHA)
            pygame.draw.circle(s, (255,255,255,230), (rr, rr), rr)
            surf.blit(s, (cx+ox-rr, cy+oy-rr))

    def _flower(self, surf, x, y, kind, sz):
        petal = [(220, 40, 80), (255, 255, 255), (200, 160, 255)][kind]
        centre = [(255, 140, 180), (255, 210, 0), (255, 240, 0)][kind]
        
        if kind == 0: # Rose
            for ang in range(0, 360, 72):
                rad = math.radians(ang)
                pygame.draw.circle(surf, petal, (int(x+math.cos(rad)*sz), int(y+math.sin(rad)*sz)), sz)
            for ang in range(36, 360, 90):
                rad = math.radians(ang)
                pygame.draw.circle(surf, centre, (int(x+math.cos(rad)*(sz*0.6)), int(y+math.sin(rad)*(sz*0.6))), max(1, int(sz*0.8)))
        elif kind == 1: # Fluffy complementary
            for ang in range(0, 360, 45):
                rad = math.radians(ang)
                pygame.draw.circle(surf, petal, (int(x+math.cos(rad)*(sz*1.2)), int(y+math.sin(rad)*(sz*1.2))), max(1, sz-1))
            pygame.draw.circle(surf, centre, (int(x), int(y)), max(1, sz))
        else: # Daisy
            for ang in range(0, 360, 30):
                rad = math.radians(ang)
                pygame.draw.circle(surf, petal, (int(x+math.cos(rad)*(sz*1.5)), int(y+math.sin(rad)*(sz*1.5))), max(1, sz//2))
            pygame.draw.circle(surf, centre, (int(x), int(y)), max(1, sz))

    # ── main draw ────────────────────────────────────────────────────────────

    def draw(self, surf, dt):
        t = time.time()
        surf.blit(self._sky, (0, 0))

        # Clouds
        for i, (bx, by, bw) in enumerate([(75,78,95),(295,55,82),(172,112,70),(380,90,62)]):
            drift = math.sin(t*0.055 + i*1.85) * 9
            self._cloud(surf, int(bx+drift), by, bw)

        # Hill layer 1 — back, lightest (simplified)
        h1 = int(HEIGHT*0.50)
        pts1 = [(0,h1+30),(WIDTH//3,h1-15),(2*WIDTH//3,h1-10),
                (WIDTH,h1+20),(WIDTH,HEIGHT),(0,HEIGHT)]
        pygame.draw.polygon(surf, COLOR_GRASS_BACK, pts1)

        # Hill layer 2 — mid (simplified)
        h2 = int(HEIGHT*0.60)
        pts2 = [(0,h2+15),(WIDTH//4,h2-40),(WIDTH//2,h2-25),(3*WIDTH//4,h2-35),
                (WIDTH,h2+10),(WIDTH,HEIGHT),(0,HEIGHT)]
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

def _build_reward_takeover(title, photo_img, info1, info2, logo_img=None):
    """Themed full-screen reward card: banner + photo + reservation info. Shared across games."""
    W, H = 400, 780
    surf = pygame.Surface((W, H), pygame.SRCALPHA)

    body = pygame.Rect(6, 8, W - 12, H - 16)
    pygame.draw.rect(surf, (*COLOR_SHADOW, 160), body.move(4, 6), border_radius=22)
    pygame.draw.rect(surf, COLOR_CREAM, body, border_radius=22)
    pygame.draw.rect(surf, COLOR_OUTLINE, body, 5, border_radius=22)

    banner_rect = pygame.Rect(body.x + 16, body.y + 18, body.width - 32, 60)
    _draw_banner(surf, banner_rect, COLOR_BLUSH)
    _draw_star(surf, banner_rect.x + 20, banner_rect.centery, 7, COLOR_YELLOW)
    _draw_star(surf, banner_rect.right - 20, banner_rect.centery, 7, COLOR_YELLOW)
    draw_soft_text(surf, title, font_win, COLOR_CREAM,
                   (banner_rect.centerx, banner_rect.centery),
                   max_width=banner_rect.width - 60)

    info_h = 160 if logo_img is not None else 120
    info_y = body.bottom - info_h
    photo_top = banner_rect.bottom + 18
    photo_area = pygame.Rect(body.x + 20, photo_top,
                             body.width - 40, info_y - photo_top - 14)

    if photo_img is not None:
        pw, ph = photo_img.get_size()
        src_aspect = pw / ph
        dst_aspect = photo_area.width / photo_area.height
        if src_aspect > dst_aspect:
            src_h = ph
            src_w = int(ph * dst_aspect)
            src_rect = pygame.Rect((pw - src_w) // 2, 0, src_w, src_h)
        else:
            src_w = pw
            src_h = int(pw / dst_aspect)
            src_rect = pygame.Rect(0, (ph - src_h) // 2, src_w, src_h)
        cropped = pygame.Surface((src_rect.width, src_rect.height), pygame.SRCALPHA)
        cropped.blit(photo_img, (0, 0), src_rect)
        scaled = pygame.transform.smoothscale(cropped, photo_area.size)

        photo_surf = pygame.Surface(photo_area.size, pygame.SRCALPHA)
        photo_surf.blit(scaled, (0, 0))
        mask = pygame.Surface(photo_area.size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255),
                         pygame.Rect(0, 0, photo_area.width, photo_area.height),
                         border_radius=16)
        photo_surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        surf.blit(photo_surf, photo_area.topleft)
    else:
        pygame.draw.rect(surf, (*COLOR_BLUSH, 40), photo_area, border_radius=16)
        draw_vector_heart(surf, photo_area.centerx, photo_area.centery,
                          photo_area.height / 80.0, COLOR_BLUSH)
    pygame.draw.rect(surf, COLOR_OUTLINE, photo_area, 4, border_radius=16)

    info_cx = body.centerx
    line1 = font_ui.render(info1, True, COLOR_OUTLINE)
    surf.blit(line1, (info_cx - line1.get_width() // 2, info_y + 24))

    if logo_img is not None:
        max_w, max_h = body.width - 80, 80
        lw, lh = logo_img.get_size()
        scale = min(max_w / lw, max_h / lh)
        scaled_logo = pygame.transform.smoothscale(logo_img,
                                                   (max(1, int(lw * scale)),
                                                    max(1, int(lh * scale))))
        logo_y = info_y + 24 + line1.get_height() + 12
        surf.blit(scaled_logo,
                  (info_cx - scaled_logo.get_width() // 2, logo_y))
    elif info2:
        line2 = font_ui.render(info2, True, COLOR_OUTLINE)
        surf.blit(line2, (info_cx - line2.get_width() // 2, info_y + 24 + line1.get_height() + 8))

    return surf


def _generate_brunch_reservation_card():
    """Mother's Day brunch reservation card: banner + salad hero photo + reservation line."""
    W, H = 480, 620
    surf = pygame.Surface((W, H), pygame.SRCALPHA)

    body = pygame.Rect(8, 10, W - 16, H - 24)
    pygame.draw.rect(surf, (*COLOR_SHADOW, 160), body.move(5, 7), border_radius=22)
    pygame.draw.rect(surf, COLOR_CREAM,  body, border_radius=22)
    pygame.draw.rect(surf, COLOR_OUTLINE, body, 5, border_radius=22)

    # Top banner
    banner_rect = pygame.Rect(body.x + 18, body.y + 22, body.width - 36, 68)
    _draw_banner(surf, banner_rect, COLOR_BLUSH)
    _draw_star(surf, banner_rect.x + 22,     banner_rect.centery, 8, COLOR_YELLOW)
    _draw_star(surf, banner_rect.right - 22, banner_rect.centery, 8, COLOR_YELLOW)
    draw_soft_text(surf, "MOTHER'S DAY BRUNCH", font_win, COLOR_CREAM,
                   (banner_rect.centerx, banner_rect.centery),
                   max_width=banner_rect.width - 70)

    # Hero photo: salad. Cropped to a square and framed with the cartoon outline.
    photo_rect = pygame.Rect(0, 0, 360, 360)
    photo_rect.center = (body.centerx, banner_rect.bottom + 30 + photo_rect.height // 2)
    try:
        img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brunch2.jpeg")
        photo = pygame.image.load(img_path).convert_alpha()
        # Centre-crop to square so the bowl stays centred
        pw, ph = photo.get_size()
        side = min(pw, ph)
        crop_rect = pygame.Rect((pw - side) // 2, (ph - side) // 2, side, side)
        sq = pygame.Surface((side, side), pygame.SRCALPHA)
        sq.blit(photo, (0, 0), crop_rect)
        scaled = pygame.transform.smoothscale(sq, (photo_rect.width, photo_rect.height))
        # Rounded mask so the photo sits nicely inside the cartoon outline
        mask = pygame.Surface((photo_rect.width, photo_rect.height), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255),
                         mask.get_rect(), border_radius=18)
        scaled.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        surf.blit(scaled, photo_rect.topleft)
    except Exception:
        # Fallback: blush placeholder if the image fails to load
        pygame.draw.rect(surf, (*COLOR_BLUSH, 60), photo_rect, border_radius=18)
    pygame.draw.rect(surf, COLOR_OUTLINE, photo_rect, 4, border_radius=18)

    # Reservation line under the photo
    info_y = photo_rect.bottom + 40
    draw_soft_text(surf, "Table for Four", font_win, COLOR_OUTLINE,
                   (body.centerx, info_y),
                   max_width=body.width - 40)
    draw_soft_text(surf, "@ 11:00 am", font_win, COLOR_BLUSH,
                   (body.centerx, info_y + 44),
                   max_width=body.width - 40)

    # Hearts at bottom
    for x in (body.centerx - 70, body.centerx, body.centerx + 70):
        draw_vector_heart(surf, x, body.bottom - 26, 0.8, COLOR_BLUSH)

    return surf


def load_images():
    imgs = []
    valid = (".png", ".jpg", ".jpeg")
    IMAGE_FOLDER = os.path.dirname(os.path.abspath(__file__))
    KIDS_FOLDER = os.path.join(IMAGE_FOLDER, "kids")
    sources = []
    if os.path.isdir(KIDS_FOLDER):
        kids = [os.path.join(KIDS_FOLDER, f) for f in os.listdir(KIDS_FOLDER)
                if f.lower().endswith(valid)]
        random.shuffle(kids)
        sources.extend(kids)
    if os.path.isdir(IMAGE_FOLDER):
        extras = sorted(f for f in os.listdir(IMAGE_FOLDER) if f.lower().endswith(valid))
        sources.extend(os.path.join(IMAGE_FOLDER, f) for f in extras)
    for path in sources:
        try:
            img = pygame.image.load(path).convert_alpha()
            w, h = img.get_size()
            side = min(w, h)
            square = pygame.Surface((side, side), pygame.SRCALPHA)
            square.blit(img, (0, 0), pygame.Rect((w - side) // 2, (h - side) // 2, side, side))
            img = pygame.transform.smoothscale(square, (SIDE-10, SIDE-10))
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

async def play_video(filepath, max_duration=None):
    """Play a video. Returns 'ended' (natural end / max_duration reached),
    'skipped' (Skip pressed), or 'menu' (Menu pressed)."""
    if not HAS_VIDEO_LIB: return "ended"
    result = "ended"
    try:
        cap = cv2.VideoCapture(filepath)
        if not cap.isOpened(): return "ended"

        audio_path = os.path.splitext(filepath)[0] + ".mp3"
        if os.path.exists(audio_path):
            pygame.mixer.music.load(audio_path)
            pygame.mixer.music.play()

        vid_clock = pygame.time.Clock()
        fps = cap.get(cv2.CAP_PROP_FPS) or 30

        start_time = time.time()
        skip_rect = pygame.Rect(WIDTH//2 + 10, HEIGHT - 60, 120, 44)
        menu_rect = pygame.Rect(WIDTH//2 - 130, HEIGHT - 60, 120, 44)
        last_surf = None

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break

            elapsed_now = time.time() - start_time
            if max_duration is not None and elapsed_now >= max_duration:
                result = "ended"
                break

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    result = "skipped"
                    break
                elif event.type == pygame.KEYDOWN:
                    result = "skipped"
                    break
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if menu_rect.collidepoint(event.pos):
                        result = "menu"
                        break
                    if skip_rect.collidepoint(event.pos):
                        result = "skipped"
                        break
            if result != "ended":
                break
            
            # Convert BGR (OpenCV) to RGB (Pygame) and rotate correctly
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = np.transpose(frame, (1, 0, 2))
            surf = pygame.surfarray.make_surface(frame)
            sw, sh = surf.get_size()
            # Cover: scale up so the video fills the window, cropping overflow
            scale_factor = max(WIDTH / sw, HEIGHT / sh)
            new_w = max(1, int(sw * scale_factor))
            new_h = max(1, int(sh * scale_factor))
            scaled = pygame.transform.smoothscale(surf, (new_w, new_h))
            last_surf = pygame.Surface((WIDTH, HEIGHT))
            last_surf.blit(scaled, ((WIDTH - new_w) // 2, (HEIGHT - new_h) // 2))
            
            screen.blit(last_surf, (0, 0))
            
            elapsed = time.time() - start_time
            if elapsed < 1.0:
                fade_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                alpha = max(0, 255 - int((elapsed / 1.0) * 255))
                fade_surf.fill((255, 255, 255, alpha))
                screen.blit(fade_surf, (0, 0))
                
            if elapsed > 1.0:
                draw_crafted_button(screen, menu_rect, "Menu", font_ui, COLOR_SAGE)
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

options = [{"text": "Brunch", "limit": None, "pairs": 6, "type": "trivia"}, {"text": "Massage", "limit": 180, "type": "puzzle"}, {"text": "Dinner", "limit": 45, "pairs": 9, "type": "memory"}]
selected_idx = None
game_state = GameState.ORIENTATION_PROMPT if IS_WEB else GameState.MENU
completed_games = set()
secret_button_appear_time = 0
secret_unlocked_seen = False
cards, first, second, wait_timer = [], None, None, 0
puzzle_tiles = []
puzzle_tile_images = []
puzzle_anim = {}
puzzle_full_image = None
puzzle_preview_start = None
puzzle_move_count = 0
hint_button_reveal_time = None
hint_popup_start = None
hint_click_count = 0
puzzle_auto_solve_used = False
PUZZLE_TILE_PX = 0
PUZZLE_BOARD_PX = 0
PUZZLE_BOARD_X = 0
PUZZLE_BOARD_Y = 0
start_time, paused_time, modal_image, modal_start_time = 0, 0, None, 0
win_animation_start_time = 0
win_particles = []
current_question_idx = 0
trivia_question_start = 0
prev_game_state_before_landscape = None
_prompt_start = None
_menu_enter_time = None
_menu_prev_state = None

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


def _draw_speech_bubble(surf, cx, cy, text, font_size, outline_col, bg_col, flip=False):
    """Draw a cute cartoon speech bubble with text. flip=True puts tail on left."""
    # Create a temporary font for the text
    bubble_font = pygame.font.SysFont(None, font_size)
    text_surf = bubble_font.render(text, True, (255, 255, 255))
    text_w, text_h = text_surf.get_size()

    # Bubble dimensions with padding
    pad_x, pad_y = 12, 8
    bubble_w = text_w + pad_x * 2
    bubble_h = text_h + pad_y * 2

    # Create bubble surface
    bubble_surf = pygame.Surface((bubble_w + 30, bubble_h + 20), pygame.SRCALPHA)

    # Draw tail (pointer)
    if flip:
        tail_pts = [(30, bubble_h), (10, bubble_h + 15), (20, bubble_h)]
    else:
        tail_pts = [(bubble_w - 30, bubble_h), (bubble_w - 10, bubble_h + 15), (bubble_w - 20, bubble_h)]

    # Filled tail and bubble
    bubble_rect = pygame.Rect(0, 0, bubble_w, bubble_h)
    pygame.draw.polygon(bubble_surf, bg_col, tail_pts)
    pygame.draw.rect(bubble_surf, bg_col, bubble_rect, border_radius=12)

    # Draw text inside bubble
    text_x = pad_x
    text_y = pad_y
    bubble_surf.blit(text_surf, (text_x, text_y))

    # Blit to main surface, positioned at center-top of bubble
    surf.blit(bubble_surf, (cx - bubble_w // 2, cy - bubble_h - 5))




def _draw_unicorn(surf, anim_t):
    """Sticker-style unicorn with recognizable horse silhouette."""
    CYCLE = 8.0
    t = anim_t % CYCLE
    OL = COLOR_OUTLINE

    GY = int(HEIGHT * 0.65)
    STOP_X = int(WIDTH * 0.28)

    if t < 2.5:
        cx = int(-80 + (STOP_X + 80) * (t / 2.5))
        walking, wink, looking = True, False, False
    elif t < 3.2:
        cx, walking, wink, looking = STOP_X, False, False, True
    elif t < 4.2:
        cx, walking, wink, looking = STOP_X, False, False, True
    elif t < 4.8:
        cx, walking, wink, looking = STOP_X, False, True, False
    else:
        cx = int(STOP_X + (WIDTH + 100 - STOP_X) * ((t - 4.8) / (CYCLE - 4.8)))
        walking, wink, looking = True, False, False

    if walking:
        bounce = int(abs(math.sin(anim_t * 8)) * 4)
    else:
        bounce = int(math.sin(anim_t * 2.5) * 2)

    WHITE  = (255, 245, 255)
    PINK   = (255, 100, 190)
    PURPLE = (180, 90, 255)
    GOLD   = (255, 212, 0)
    BLUSH  = (255, 170, 200)
    MANE_C = [PINK, PURPLE, GOLD]

    # Drop shadow on ground
    sh = pygame.Surface((58, 10), pygame.SRCALPHA)
    pygame.draw.ellipse(sh, (0, 0, 0, 45), (0, 0, 58, 10))
    surf.blit(sh, (cx - 29, GY - 3))

    # --- Tail: flowing coloured curves behind body ---
    tail_bx = cx - 26
    tail_by = GY - 38 - bounce
    for ti, tc in enumerate(MANE_C):
        wave = math.sin(anim_t * 3.2 + ti * 0.9) * 7
        pts = []
        for s in range(6):
            f = s / 5
            px = int(tail_bx - 6 - ti * 3 - f * 10 + wave * f)
            py = int(tail_by + 8 + f * 22 + ti * 4)
            pts.append((px, py))
        for j in range(len(pts) - 1):
            pygame.draw.line(surf, OL, pts[j], pts[j + 1], 6)
        for j in range(len(pts) - 1):
            pygame.draw.line(surf, tc, pts[j], pts[j + 1], 4)

    # --- Legs: four slender legs with hooves ---
    leg_anchors = [(-18, 0), (-8, 2), (10, 2), (20, 0)]
    for li, (lox, loy) in enumerate(leg_anchors):
        phase = li * math.pi * 0.6
        swing = int(math.sin(anim_t * 9 + phase) * 5) if walking else 0
        hx_l = cx + lox
        hy_top = GY - 22 - bounce + loy
        hy_bot = GY - 2
        fx = hx_l + swing
        # Leg
        pygame.draw.line(surf, OL, (hx_l, hy_top), (fx, hy_bot), 7)
        pygame.draw.line(surf, WHITE, (hx_l, hy_top), (fx, hy_bot), 5)
        # Hoof
        pygame.draw.ellipse(surf, OL, (fx - 5, hy_bot - 2, 10, 6))
        pygame.draw.ellipse(surf, BLUSH, (fx - 4, hy_bot - 1, 8, 4))

    # --- Body: horizontal oval ---
    by = GY - 42 - bounce
    body_rect = pygame.Rect(cx - 26, by, 52, 28)
    # Shadow
    pygame.draw.ellipse(surf, (0, 0, 0), (body_rect.x + 2, body_rect.y + 3,
                        body_rect.w, body_rect.h))
    pygame.draw.ellipse(surf, OL, body_rect.inflate(4, 4))
    pygame.draw.ellipse(surf, WHITE, body_rect)
    # Belly shine
    shine_r = pygame.Rect(body_rect.x + 8, body_rect.y + 4, body_rect.w - 16, 10)
    sh_s = pygame.Surface(shine_r.size, pygame.SRCALPHA)
    sh_s.fill((255, 255, 255, 60))
    surf.blit(sh_s, shine_r.topleft)

    # --- Neck: angled connection ---
    neck_base_x = cx + 22
    neck_base_y = by + 6
    head_cx = cx + 34
    head_cy = by - 16 + bounce
    neck_pts = [
        (neck_base_x - 4, neck_base_y),
        (neck_base_x + 6, neck_base_y),
        (head_cx + 3, head_cy + 14),
        (head_cx - 7, head_cy + 14),
    ]
    pygame.draw.polygon(surf, OL, [(p[0] - 1, p[1] - 1) for p in neck_pts])
    pygame.draw.polygon(surf, OL, [(p[0] + 1, p[1] + 1) for p in neck_pts])
    pygame.draw.polygon(surf, WHITE, neck_pts)

    # --- Head: slightly oval, not perfect circle ---
    hx, hy = head_cx, head_cy
    head_rect = pygame.Rect(hx - 16, hy - 14, 32, 28)
    pygame.draw.ellipse(surf, (0, 0, 0), (head_rect.x + 2, head_rect.y + 2,
                        head_rect.w, head_rect.h))
    pygame.draw.ellipse(surf, OL, head_rect.inflate(4, 4))
    pygame.draw.ellipse(surf, WHITE, head_rect)

    # --- Snout: elongated bump ---
    snout_rect = pygame.Rect(hx + 8, hy + 2, 16, 12)
    pygame.draw.ellipse(surf, OL, snout_rect.inflate(2, 2))
    pygame.draw.ellipse(surf, WHITE, snout_rect)
    pygame.draw.circle(surf, BLUSH, (hx + 16, hy + 8), 2)
    pygame.draw.circle(surf, BLUSH, (hx + 20, hy + 7), 1)
    pygame.draw.arc(surf, OL, (hx + 10, hy + 6, 10, 7), -math.pi, 0, 2)

    # --- Ear: triangular, toward back of head ---
    ear_pts = [(hx - 6, hy - 10), (hx - 12, hy - 26), (hx + 1, hy - 20)]
    pygame.draw.polygon(surf, OL, ear_pts)
    pygame.draw.polygon(surf, BLUSH, [(hx - 6, hy - 11), (hx - 11, hy - 24), (hx, hy - 19)])

    # --- Horn: golden, angled forward ---
    horn_tip = (hx + 12, hy - 28)
    horn_bl = (hx - 2, hy - 14)
    horn_br = (hx + 6, hy - 12)
    pygame.draw.polygon(surf, OL, [horn_tip, horn_bl, horn_br])
    pygame.draw.polygon(surf, GOLD, [(horn_tip[0], horn_tip[1] + 2),
                                     (horn_bl[0] + 1, horn_bl[1] - 1),
                                     (horn_br[0] - 1, horn_br[1] - 1)])
    for si in range(4):
        f = (si + 1) / 5
        sy_ = int(horn_bl[1] + (horn_tip[1] - horn_bl[1]) * f)
        sx_ = int(horn_bl[0] + (horn_tip[0] - horn_bl[0]) * f) + 1
        srx = int(horn_br[0] + (horn_tip[0] - horn_br[0]) * f) - 1
        pygame.draw.line(surf, MANE_C[si % 3], (sx_, sy_), (srx, sy_), 2)

    # --- Mane: flowing strands from head down neck ---
    mane_x = hx - 8
    mane_y = hy - 12
    for mi, mc in enumerate(MANE_C):
        wave = math.sin(anim_t * 3.0 + mi * 1.0) * 5
        pts = []
        for s in range(5):
            f = s / 4
            px = int(mane_x - mi * 3 - f * 8 + wave * f)
            py = int(mane_y + f * 24 + mi * 4)
            pts.append((px, py))
        for j in range(len(pts) - 1):
            pygame.draw.line(surf, OL, pts[j], pts[j + 1], 6)
        for j in range(len(pts) - 1):
            pygame.draw.line(surf, mc, pts[j], pts[j + 1], 4)

    # --- Eye: big and expressive ---
    ex, ey = hx + 3, hy - 3
    if wink:
        pygame.draw.arc(surf, OL, (ex - 6, ey - 2, 13, 10), 0, math.pi, 3)
    else:
        pygame.draw.circle(surf, OL, (ex, ey), 7)
        pygame.draw.circle(surf, (60, 20, 80), (ex, ey), 6)
        pygame.draw.circle(surf, OL, (ex + 1, ey + 1), 3)
        pygame.draw.circle(surf, (255, 255, 255), (ex + 2, ey - 2), 2)
        pygame.draw.circle(surf, (255, 255, 255), (ex - 1, ey + 1), 1)
    # Blush
    bl_s = pygame.Surface((12, 8), pygame.SRCALPHA)
    pygame.draw.ellipse(bl_s, (*BLUSH, 90), (0, 0, 12, 8))
    surf.blit(bl_s, (ex + 8, ey + 5))

    # Speech bubble
    if looking:
        _draw_speech_bubble(surf, cx + 80, by - 34, "hi mama", 20,
                            OL, PINK, flip=True)


def _draw_robot(surf, anim_t):
    """Cute sticker-style robot with big head and rosy cheeks."""
    CYCLE = 8.0
    t = anim_t % CYCLE
    OL = COLOR_OUTLINE

    GY = int(HEIGHT * 0.65)
    STOP_X = int(WIDTH * 0.72)

    if t < 2.5:
        cx = int(WIDTH + 70 - (WIDTH + 70 - STOP_X) * (t / 2.5))
        walking, looking = True, False
    elif t < 4.0:
        cx, walking, looking = STOP_X, False, True
    else:
        cx = int(STOP_X + (WIDTH + 70 - STOP_X) * ((t - 4.0) / (CYCLE - 4.0)))
        walking, looking = True, False

    if walking:
        bounce = int(abs(math.sin(anim_t * 8)) * 4)
    else:
        bounce = int(math.sin(anim_t * 2.5) * 2)

    BODY_C = (100, 196, 248)
    DARK_C = (70, 155, 210)
    GOLD   = (255, 212, 0)
    RED    = (236, 48, 118)
    METAL  = (200, 210, 225)
    LITE   = (170, 225, 255)
    BLUSH  = (255, 160, 190)

    # Drop shadow
    sh = pygame.Surface((50, 10), pygame.SRCALPHA)
    pygame.draw.ellipse(sh, (0, 0, 0, 45), (0, 0, 50, 10))
    surf.blit(sh, (cx - 25, GY - 3))

    # --- Legs: short chunky with round feet ---
    for lx_off in (-10, 10):
        phase = lx_off * 0.3
        swing = int(math.sin(anim_t * 9 + phase) * 4) if walking else 0
        lx = cx + lx_off + swing
        ly_top = GY - 18 - bounce
        ly_bot = GY - 2
        # Leg
        pygame.draw.rect(surf, OL, (lx - 5, ly_top, 10, ly_bot - ly_top), border_radius=3)
        pygame.draw.rect(surf, METAL, (lx - 4, ly_top + 1, 8, ly_bot - ly_top - 2), border_radius=2)
        # Round shoe
        pygame.draw.ellipse(surf, OL, (lx - 7, ly_bot - 4, 14, 8))
        pygame.draw.ellipse(surf, GOLD, (lx - 6, ly_bot - 3, 12, 6))

    # --- Body: rounded rectangle, compact ---
    by = GY - 48 - bounce
    BW, BH = 38, 30
    body_rect = pygame.Rect(cx - BW // 2, by, BW, BH)
    pygame.draw.rect(surf, (0, 0, 0), (body_rect.x + 3, body_rect.y + 3,
                     BW, BH), border_radius=8)
    pygame.draw.rect(surf, OL, body_rect.inflate(4, 4), border_radius=9)
    pygame.draw.rect(surf, BODY_C, body_rect, border_radius=8)
    # Tummy panel
    panel = pygame.Rect(cx - 10, by + 5, 20, 16)
    pygame.draw.rect(surf, OL, panel.inflate(2, 2), border_radius=4)
    pygame.draw.rect(surf, DARK_C, panel, border_radius=4)
    # Heart on tummy
    draw_vector_heart(surf, cx, by + 13, 0.35, RED)
    # Shine
    shine = pygame.Surface((BW - 10, 7), pygame.SRCALPHA)
    shine.fill((255, 255, 255, 60))
    surf.blit(shine, (body_rect.x + 5, body_rect.y + 3))

    # --- Arms: short rounded stubs that wave ---
    for side in (-1, 1):
        ax = cx + side * (BW // 2 + 2)
        ay = by + 8
        wave_ang = math.sin(anim_t * 3 + side * 2) * 0.4
        arm_len = 16
        end_x = ax + int(math.sin(wave_ang) * arm_len) * side
        end_y = ay + int(math.cos(wave_ang) * arm_len)
        # Arm
        pygame.draw.line(surf, OL, (ax, ay), (end_x, end_y), 8)
        pygame.draw.line(surf, METAL, (ax, ay), (end_x, end_y), 5)
        # Round mitten hand
        pygame.draw.circle(surf, OL, (end_x, end_y), 6)
        pygame.draw.circle(surf, LITE, (end_x, end_y), 4)

    # --- Head: big and rounded (larger than body for cuteness) ---
    HW, HH = 40, 32
    hx, hy = cx, by - 8
    head_rect = pygame.Rect(hx - HW // 2, hy - HH // 2, HW, HH)
    pygame.draw.rect(surf, (0, 0, 0), (head_rect.x + 2, head_rect.y + 2,
                     HW, HH), border_radius=10)
    pygame.draw.rect(surf, OL, head_rect.inflate(4, 4), border_radius=11)
    pygame.draw.rect(surf, BODY_C, head_rect, border_radius=10)
    # Shine on forehead
    sh_s = pygame.Surface((HW - 10, 8), pygame.SRCALPHA)
    sh_s.fill((255, 255, 255, 60))
    surf.blit(sh_s, (head_rect.x + 5, head_rect.y + 3))

    # --- Eyes: big round with sparkle highlights ---
    for ex_off in (-8, 8):
        ex = hx + ex_off
        ey = hy - 3 if looking else hy - 1
        # Eye white
        pygame.draw.circle(surf, OL, (ex, ey), 7)
        pygame.draw.circle(surf, (255, 255, 255), (ex, ey), 6)
        # Iris
        pygame.draw.circle(surf, OL, (ex, ey + 1), 4)
        pygame.draw.circle(surf, DARK_C, (ex, ey + 1), 3)
        # Sparkle
        pygame.draw.circle(surf, (255, 255, 255), (ex + 2, ey - 2), 2)
        pygame.draw.circle(surf, (255, 255, 255), (ex - 1, ey + 1), 1)

    # --- Rosy cheeks ---
    for side in (-1, 1):
        bl = pygame.Surface((12, 8), pygame.SRCALPHA)
        pygame.draw.ellipse(bl, (*BLUSH, 100), (0, 0, 12, 8))
        surf.blit(bl, (hx + side * 12 - 6, hy + 4))

    # --- Mouth: happy smile ---
    pygame.draw.arc(surf, OL, (hx - 5, hy + 6, 10, 8), -math.pi, 0, 2)

    # --- Antenna: bouncy with heart-shaped ball ---
    ant_x = hx
    ant_base = head_rect.top
    ant_top = ant_base - 14 + int(math.sin(anim_t * 4) * 3)
    pygame.draw.line(surf, OL, (ant_x, ant_base), (ant_x, ant_top + 4), 3)
    pygame.draw.line(surf, METAL, (ant_x, ant_base), (ant_x, ant_top + 4), 2)
    draw_vector_heart(surf, ant_x, ant_top, 0.3, RED)

    # --- Ear bolts (small, round) ---
    for side in (-1, 1):
        bx_ = hx + side * (HW // 2 + 2)
        by_ = hy - 1
        pygame.draw.circle(surf, OL, (bx_, by_), 4)
        pygame.draw.circle(surf, GOLD, (bx_, by_), 3)

    # Speech bubble
    if looking:
        _draw_speech_bubble(surf, cx - 55, by - 24, "I'm RivBot", 20,
                            OL, GOLD)

def _draw_rose_head(surf, cx, cy, sz, pc, cc):
    """Cartoon rose viewed from above. Built from layered scalloped polygons
    (no rotated sub-surfaces) so the silhouette is one continuous curve and
    blends with the chunky outlined art style of the menu scene.
    `pc` = primary petal colour, `cc` = bud centre colour."""
    pc_dark  = tuple(max(0, int(c * 0.62)) for c in pc)
    pc_light = tuple(min(255, int(c + (255 - c) * 0.40)) for c in pc)

    def _scalloped(r_base, r_amp, n_bumps, phase, samples=64):
        """Polygon points for a flower-shaped circle: r = base + amp·cos(n·θ - n·phase)."""
        out = []
        for i in range(samples):
            th = i * (2 * math.pi / samples)
            r  = r_base + r_amp * math.cos(n_bumps * th - n_bumps * phase)
            out.append((cx + math.cos(th) * r, cy + math.sin(th) * r))
        return out

    def _inflate_pts(pts, extra):
        """Push each point `extra` px farther from (cx,cy) — used for outline."""
        out = []
        for (px, py) in pts:
            dx, dy = px - cx, py - cy
            d = math.hypot(dx, dy) or 1
            s = (d + extra) / d
            out.append((cx + dx * s, cy + dy * s))
        return out

    # Back layer: large 5-bump scalloped rosette in darker tone, with one
    # solid outer outline (matches the cartoon style elsewhere)
    back = _scalloped(sz * 1.55, sz * 0.55, 5, -math.pi / 2)
    pygame.draw.polygon(surf, COLOR_OUTLINE, _inflate_pts(back, 2.5))
    pygame.draw.polygon(surf, pc_dark, back)

    # Middle layer: smaller rosette in primary colour, offset by half-bump
    # so its petals sit between the back petals
    mid = _scalloped(sz * 1.05, sz * 0.32, 5, -math.pi / 2 + math.pi / 5)
    pygame.draw.polygon(surf, pc, mid)

    # Inner highlight layer: smaller still, lighter tone
    inner = _scalloped(sz * 0.62, sz * 0.18, 5, -math.pi / 2)
    pygame.draw.polygon(surf, pc_light, inner)

    # Subtle dark divisions between back petals to suggest folded petals
    for i in range(5):
        valley = -math.pi / 2 + (i + 0.5) * (2 * math.pi / 5)
        x1 = cx + math.cos(valley) * (sz * 0.55)
        y1 = cy + math.sin(valley) * (sz * 0.55)
        x2 = cx + math.cos(valley) * (sz * 1.20)
        y2 = cy + math.sin(valley) * (sz * 1.20)
        pygame.draw.line(surf, pc_dark, (int(x1), int(y1)), (int(x2), int(y2)), 1)

    # Spiral bud centre
    bud_r = max(3, int(sz * 0.42))
    pygame.draw.circle(surf, COLOR_OUTLINE, (cx, cy), bud_r + 2)
    pygame.draw.circle(surf, cc, (cx, cy), bud_r + 1)
    fold = max(1, sz // 5)
    pygame.draw.circle(surf, pc, (cx + fold, cy - fold), max(2, bud_r - 1))
    pygame.draw.circle(surf, pc_light, (cx - fold // 2, cy + fold // 2), max(1, bud_r - 2))


def _draw_menu_scene(surf, t, menu_elapsed=999):
    """Mother's Day illustration: sun, unicorn, big flowers, floating hearts."""
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

    # ── Big roses (drawn first so they appear behind characters) ────────────
    #   Two-phase grow: stem rises out of the ground, then bloom unfolds.
    #   Each rose is staggered randomly AFTER the "HAPPY MAMA DAY" lockup
    #   finishes (~3.2s).
    h3y = int(HEIGHT * 0.52)
    flowers = [
        (int(WIDTH * 0.10), h3y - 28, 12, [(220,  40,  80), (130,  14,  40)]),  # Red rose
        (int(WIDTH * 0.28), h3y - 50, 14, [(255, 140, 180), (236,  48, 118)]),  # Pink rose
        (int(WIDTH * 0.50), h3y - 36, 11, [(255, 240, 230), (240, 180, 160)]),  # Cream rose
        (int(WIDTH * 0.72), h3y - 52, 15, [(255, 200,  90), (240, 130,  30)]),  # Yellow rose
        (int(WIDTH * 0.90), h3y - 26, 11, [(200, 160, 255), (140,  90, 200)]),  # Lavender rose
    ]

    FLOWER_START  = 3.2   # matches LOCKUP_DUR (STAR_START + STAR_DUR)
    FLOWER_WINDOW = 1.4   # total random stagger window
    STEM_GROW     = 0.45  # phase 1: stem rises from ground
    BLOOM_GROW    = 0.50  # phase 2: bloom unfolds at the tip

    for fx, fy, fsz, (pc, cc) in flowers:
        seed        = fx * 1000 + fy
        spawn_delay = random.Random(seed ^ 0x5EED).uniform(0, FLOWER_WINDOW)
        grow_t      = menu_elapsed - FLOWER_START - spawn_delay
        if grow_t <= 0:
            continue

        stem_len = fsz * 6
        stem_w   = max(2, fsz // 4)
        ground_y = fy + stem_len  # base of stem (where it meets the hill)

        # ── Phase 1: stem grows upward from the ground ──
        stem_p   = min(1.0, grow_t / STEM_GROW)
        cur_len  = int(stem_len * _ease_out_cubic(stem_p))
        if cur_len < 1:
            continue

        rng = random.Random(seed)
        # Build full stem+leaves to a local surface, then blit only the bottom
        # `cur_len` portion so leaves emerge naturally as the stem rises.
        side_pad = fsz + 6
        S_W = side_pad * 2
        S_H = stem_len + 2
        ssurf = pygame.Surface((S_W, S_H), pygame.SRCALPHA)
        sx = side_pad

        pygame.draw.line(ssurf, COLOR_GRASS_DARK, (sx, 0), (sx, S_H - 1), stem_w)

        num_leaves = rng.randint(2, 4)
        positions  = sorted([rng.uniform(0.2, 0.8) for _ in range(num_leaves)])
        first_side = rng.choice((-1, 1))
        for li, lf in enumerate(positions):
            ly = int(S_H * lf)
            side   = first_side if li % 2 == 0 else -first_side
            leaf_w = rng.randint(fsz, fsz + 5)
            leaf_h = rng.randint(fsz // 2 + 1, fsz // 2 + 5)
            leaf_pts = [
                (sx, ly),
                (sx + side * leaf_w, ly - leaf_h // 2),
                (sx + side * leaf_w * 3 // 4, ly + leaf_h // 2),
            ]
            pygame.draw.polygon(ssurf, COLOR_GRASS_DARK, leaf_pts)
            inner_pts = [
                (sx + side * 1, ly),
                (sx + side * (leaf_w - 1), ly - leaf_h // 2 + 1),
                (sx + side * (leaf_w * 3 // 4 - 1), ly + leaf_h // 2 - 1),
            ]
            pygame.draw.polygon(ssurf, COLOR_GRASS, inner_pts)

        src_rect = pygame.Rect(0, S_H - cur_len, S_W, cur_len)
        surf.blit(ssurf, (fx - side_pad, ground_y - cur_len), src_rect)

        # ── Phase 2: bloom unfolds at the tip of the fully-grown stem ──
        if grow_t < STEM_GROW:
            continue

        bloom_t = grow_t - STEM_GROW
        bloom_p = min(1.0, bloom_t / BLOOM_GROW)
        scale   = max(0.0, _ease_out_back(bloom_p))
        if scale <= 0.01:
            continue

        # Render rose head onto a local surface centred at (B/2, B/2).
        # The rose silhouette extends out to ~sz*2.1 + outline; size B with
        # generous margin so the silhouette is never clipped to a rectangle.
        B = int(fsz * 2.4) * 2 + 12
        bsurf = pygame.Surface((B, B), pygame.SRCALPHA)
        _draw_rose_head(bsurf, B // 2, B // 2, fsz, pc, cc)

        sw = max(1, int(B * scale))
        sh = max(1, int(B * scale))
        scaled = pygame.transform.smoothscale(bsurf, (sw, sh))

        # Post-bloom wobble: gentle rotation damping out in ~0.8s
        if bloom_p >= 1.0:
            wob_t = bloom_t - BLOOM_GROW
            if wob_t < 0.8:
                damp  = 1.0 - (wob_t / 0.8)
                angle = math.sin(wob_t * 11.0) * 6.0 * damp
                scaled = pygame.transform.rotate(scaled, angle)

        rect = scaled.get_rect(center=(fx, fy))
        surf.blit(scaled, rect)

    # ── Characters enter after title finishes animating (~3.2s) ─────────────
    CHAR_DELAY = 3.5
    if menu_elapsed > CHAR_DELAY:
        char_t = menu_elapsed - CHAR_DELAY
        _draw_unicorn(surf, char_t)
        _draw_robot(surf, char_t + 4.0)

    # ── Floating hearts rising through the sky ────────────────────────────────
    heart_cols = [COLOR_BLUSH, COLOR_YELLOW, COLOR_CREAM, (255,160,200), COLOR_BLUSH]
    for i in range(5):
        seed  = i * 1.7
        hx    = int(WIDTH * (0.12 + i * 0.19))
        cycle = (t * 0.38 + seed) % 1.0
        hy    = int(HEIGHT * 0.50 - cycle * HEIGHT * 0.40)
        alpha = int(210 * math.sin(cycle * math.pi))
        size  = 0.8 + 0.4 * math.sin(seed)
        draw_vector_heart(surf, hx, hy, size, heart_cols[i], alpha)


def _ease_out_back(t):
    """Overshoot ease-out for bouncy pop-in."""
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)

def _ease_out_cubic(t):
    return 1 - pow(1 - t, 3)

def draw_menu(screen, dt, selected_idx, completed_games):
    global _menu_enter_time, _menu_prev_state
    crafted_bg.draw(screen, dt)
    t = time.time()

    # Track menu entry for animation
    if _menu_enter_time is None or _menu_prev_state != GameState.MENU:
        _menu_enter_time = t
    _menu_prev_state = GameState.MENU
    menu_elapsed = t - _menu_enter_time

    # Full-screen Mother's Day illustration
    _draw_menu_scene(screen, t, menu_elapsed)

    # ── Title lockup: "HAPPY MAMA DAY" ──────────────────────────────────────
    #   Single centered unit that animates in together, then holds
    _fhuge    = font_huge if font_huge else font_title
    lockup_cy = int(HEIGHT * 0.26)
    cx        = WIDTH // 2

    # Row heights — Happy is scaled down, Day is full size like MAMA
    r_mama  = _fhuge.get_height()
    r_happy = int(r_mama * 0.36)
    r_day   = r_mama
    gap     = -2
    total_h = r_happy + gap + r_mama + gap + r_day

    # ── Dramatic staggered reveal ───────────────────────────────────────────
    #   Phase 1: "Happy" floats down          0.4s – 1.1s
    #   Phase 2: "MAMA" letters bounce in     1.0s – 2.2s  (each letter staggered)
    #   Phase 3: "Day ♥" fades up             2.0s – 2.6s
    #   Phase 4: Stars sparkle in             2.4s – 2.8s
    #   Phase 5: Buttons rise                 2.8s+

    HAPPY_START, HAPPY_DUR   = 0.4, 0.7
    MAMA_START,  MAMA_DUR    = 1.0, 0.5
    MAMA_STAGGER_DELAY       = 0.25
    DAY_START,   DAY_DUR     = 2.0, 0.6
    STAR_START,  STAR_DUR    = 2.8, 0.4

    # Compute screen-space positions for each row
    lockup_top = lockup_cy - total_h // 2
    y_happy = lockup_top
    y_mama  = y_happy + r_happy + gap
    y_day   = y_mama  + r_mama  + gap
    ow = 3

    # ── "Happy" — floats down from above with fade ────────────────────────────
    happy_elapsed = menu_elapsed - HAPPY_START
    happy_p = max(0.0, min(1.0, happy_elapsed / HAPPY_DUR))
    if happy_p > 0:
        happy_scale = _ease_out_back(happy_p)
        happy_alpha = min(255, int(happy_p * 2.0 * 255))
        happy_slide = int((1 - _ease_out_cubic(happy_p)) * -50)

        happy_fs = _fhuge.render("Happy", True, COLOR_CREAM)
        happy_os = _fhuge.render("Happy", True, COLOR_OUTLINE)
        hsw = max(1, int(happy_fs.get_width() * 0.40 * happy_scale))
        hsh = max(1, int(happy_fs.get_height() * 0.40 * happy_scale))
        happy_fs = pygame.transform.smoothscale(happy_fs, (hsw, hsh))
        happy_os = pygame.transform.smoothscale(happy_os, (hsw, hsh))
        hx = cx - hsw // 2
        hy = y_happy + r_happy // 2 - hsh // 2 + happy_slide
        tmp = pygame.Surface((hsw + ow*2, hsh + ow*2), pygame.SRCALPHA)
        for ddx in (-ow, 0, ow):
            for ddy in (-ow, 0, ow):
                if ddx or ddy:
                    tmp.blit(happy_os, (ow + ddx, ow + ddy))
        tmp.blit(happy_fs, (ow, ow))
        tmp.set_alpha(happy_alpha)
        screen.blit(tmp, (hx - ow, hy - ow))

    # ── "MAMA" — each letter bounces in individually ──────────────────────────
    letters      = "MAMA"
    alt_cols     = [COLOR_BLUSH, COLOR_YELLOW, COLOR_BLUSH, COLOR_YELLOW]
    letter_surfs = [_fhuge.render(l, True, c) for l, c in zip(letters, alt_cols)]
    out_surfs    = [_fhuge.render(l, True, COLOR_OUTLINE) for l in letters]
    total_lw     = sum(s.get_width() for s in letter_surfs) + 2 * (len(letters) - 1)
    lx           = cx - total_lw // 2
    mow          = 4
    all_mama_done = True
    for idx, (ls, os_) in enumerate(zip(letter_surfs, out_surfs)):
        letter_elapsed = menu_elapsed - MAMA_START - idx * MAMA_STAGGER_DELAY
        letter_p = max(0.0, min(1.0, letter_elapsed / MAMA_DUR))
        if letter_p < 1.0:
            all_mama_done = False
        if letter_p <= 0:
            lx += ls.get_width() + 2
            continue

        letter_scale = _ease_out_back(letter_p)
        letter_alpha = min(255, int(letter_p * 2.5 * 255))
        bob = int(math.sin(t * 2.8 + idx * 1.1) * 7) if letter_p >= 1.0 else 0
        drop = int((1 - _ease_out_cubic(letter_p)) * -80)

        sw = max(1, int(ls.get_width() * letter_scale))
        sh = max(1, int(ls.get_height() * letter_scale))
        ls_s = pygame.transform.smoothscale(ls, (sw, sh))
        os_s = pygame.transform.smoothscale(os_, (sw, sh))
        draw_x = lx + ls.get_width() // 2 - sw // 2
        draw_y = y_mama + bob + drop + ls.get_height() // 2 - sh // 2
        tmp = pygame.Surface((sw + mow*2, sh + mow*2), pygame.SRCALPHA)
        for ddx in (-mow, 0, mow):
            for ddy in (-mow, 0, mow):
                if ddx or ddy:
                    tmp.blit(os_s, (mow + ddx, mow + ddy))
        tmp.blit(ls_s, (mow, mow))
        tmp.set_alpha(letter_alpha)
        screen.blit(tmp, (draw_x - mow, draw_y - mow))
        lx += ls.get_width() + 2

    # ── "DAY" — full-size letters with individual bounce, like MAMA ─────────
    day_letters  = "DAY"
    day_cols     = [COLOR_YELLOW, COLOR_BLUSH, COLOR_YELLOW]
    day_surfs    = [_fhuge.render(l, True, c) for l, c in zip(day_letters, day_cols)]
    day_out      = [_fhuge.render(l, True, COLOR_OUTLINE) for l in day_letters]
    total_dw     = sum(s.get_width() for s in day_surfs) + 2 * (len(day_letters) - 1)
    dlx          = cx - total_dw // 2
    for idx, (ds, do_) in enumerate(zip(day_surfs, day_out)):
        dl_elapsed = menu_elapsed - DAY_START - idx * MAMA_STAGGER_DELAY
        dl_p = max(0.0, min(1.0, dl_elapsed / DAY_DUR))
        if dl_p <= 0:
            dlx += ds.get_width() + 2
            continue

        dl_scale = _ease_out_back(dl_p)
        dl_alpha = min(255, int(dl_p * 2.5 * 255))
        bob = int(math.sin(t * 2.8 + idx * 1.1 + 2.0) * 7) if dl_p >= 1.0 else 0
        drop = int((1 - _ease_out_cubic(dl_p)) * 40)

        dsw = max(1, int(ds.get_width() * dl_scale))
        dsh = max(1, int(ds.get_height() * dl_scale))
        ds_s = pygame.transform.smoothscale(ds, (dsw, dsh))
        do_s = pygame.transform.smoothscale(do_, (dsw, dsh))
        draw_x = dlx + ds.get_width() // 2 - dsw // 2
        draw_y = y_day + bob + drop + ds.get_height() // 2 - dsh // 2
        tmp = pygame.Surface((dsw + mow*2, dsh + mow*2), pygame.SRCALPHA)
        for ddx in (-mow, 0, mow):
            for ddy in (-mow, 0, mow):
                if ddx or ddy:
                    tmp.blit(do_s, (mow + ddx, mow + ddy))
        tmp.blit(ds_s, (mow, mow))
        tmp.set_alpha(dl_alpha)
        screen.blit(tmp, (draw_x - mow, draw_y - mow))
        dlx += ds.get_width() + 2

    # ── Stars flanking the lockup — sparkle in ────────────────────────────────
    star_elapsed = menu_elapsed - STAR_START
    star_p = max(0.0, min(1.0, star_elapsed / STAR_DUR))
    if star_p > 0:
        mama_half_w = total_lw // 2 + 20
        day_half_w  = total_dw // 2 + 20
        star_alpha = min(255, int(star_p * 255))
        star_scale_anim = _ease_out_back(star_p)
        for i, (sx, sy, sr) in enumerate([
            (cx - mama_half_w, y_happy + r_happy // 2, 7),
            (cx + mama_half_w, y_happy + r_happy // 2, 7),
            (cx - day_half_w + 14, y_day + r_day // 2, 5),
            (cx + day_half_w - 14, y_day + r_day // 2, 5),
        ]):
            pulse = 1.0 + 0.3 * math.sin(t * 2.5 + i * 1.4)
            _draw_star(screen, sx, sy, int(sr * pulse * star_scale_anim), COLOR_YELLOW)

    # ── Buttons — bubble up after full reveal ─────────────────────────────────
    LOCKUP_DUR = STAR_START + STAR_DUR  # total reveal time
    BTN_DELAY  = LOCKUP_DUR + 0.15
    BTN_DUR    = 0.45
    BTN_STAGGER = 0.15
    BTN_COLORS = [(100, 196, 248), COLOR_BLUSH, (255, 185, 0)]
    for i, (opt, rect) in enumerate(zip(options, _menu_button_rects())):
        btn_elapsed = menu_elapsed - BTN_DELAY - i * BTN_STAGGER
        btn_p = max(0.0, min(1.0, btn_elapsed / BTN_DUR))
        if btn_p <= 0:
            continue
        slide_offset = int((1 - _ease_out_back(btn_p)) * 80)
        btn_alpha = min(255, int(btn_p * 2.5 * 255))
        anim_rect = pygame.Rect(rect.x, rect.y + slide_offset, rect.width, rect.height)
        col  = COLOR_BLUSH if i == selected_idx else BTN_COLORS[i % 3]
        btn_surf = pygame.Surface((rect.width + 8, rect.height + 8), pygame.SRCALPHA)
        btn_sub_rect = pygame.Rect(4, 4, rect.width, rect.height)
        draw_crafted_button(btn_surf, btn_sub_rect, opt["text"], font_ui, col)
        btn_surf.set_alpha(btn_alpha)
        screen.blit(btn_surf, (anim_rect.x - 4, anim_rect.y - 4))
        if i in completed_games:
            # Completed-game indicator — slow pulse with a black stroke
            heart_cx = anim_rect.right - 28
            heart_cy = anim_rect.centery
            pulse = 1.0 + 0.10 * math.sin(t * 1.6 + i * 0.7)
            heart_size = 1.0 * pulse
            draw_vector_heart(screen, heart_cx, heart_cy, heart_size * 1.22, (0, 0, 0), alpha=btn_alpha)
            draw_vector_heart(screen, heart_cx, heart_cy, heart_size, COLOR_YELLOW, alpha=btn_alpha)

def init_sliding_puzzle():
    """4×4 sliding-tile puzzle. Solved = tiles 1-15 in order with the blank at position 15."""
    global puzzle_tiles, puzzle_tile_images, puzzle_anim, hint_popup_start, hint_click_count
    global puzzle_full_image, puzzle_preview_start, puzzle_move_count, hint_button_reveal_time
    global puzzle_auto_solve_used
    global PUZZLE_TILE_PX, PUZZLE_BOARD_PX, PUZZLE_BOARD_X, PUZZLE_BOARD_Y
    hint_popup_start = None
    hint_click_count = 0
    puzzle_full_image = None
    puzzle_preview_start = None
    puzzle_move_count = 0
    hint_button_reveal_time = None
    puzzle_auto_solve_used = False

    PUZZLE_TILE_PX = (WIDTH - 24) // 4
    PUZZLE_BOARD_PX = PUZZLE_TILE_PX * 4
    PUZZLE_BOARD_X = (WIDTH - PUZZLE_BOARD_PX) // 2
    avail_h = HEIGHT - GAME_TOP - GAME_BOTTOM
    PUZZLE_BOARD_Y = GAME_TOP + (avail_h - PUZZLE_BOARD_PX) // 2

    # Tile art — fixed closeup of the twins, with fallbacks
    img_dir = os.path.dirname(os.path.abspath(__file__))
    kids_dir = os.path.join(img_dir, "kids")
    src_path = None
    for preferred_path in (
        os.path.join(kids_dir, "ducks2.jpeg"),
        os.path.join(kids_dir, "ducks2.jpg"),
        os.path.join(kids_dir, "ducks2.JPG"),
        os.path.join(kids_dir, "ducks2.png"),
    ):
        if os.path.exists(preferred_path):
            src_path = preferred_path
            break
    if src_path is None and os.path.isdir(kids_dir):
        try:
            photos = [f for f in os.listdir(kids_dir)
                      if f.lower().endswith((".png", ".jpg", ".jpeg"))]
            if photos:
                src_path = os.path.join(kids_dir, random.choice(photos))
        except Exception:
            pass
    if src_path is None:
        for fallback in ("img1.jpg.jpeg", "img1.jpeg", "img1.jpg", "img1.png"):
            p = os.path.join(img_dir, fallback)
            if os.path.exists(p):
                src_path = p
                break

    puzzle_tile_images = []
    if src_path:
        try:
            full = pygame.image.load(src_path).convert_alpha()
            # Crop to square around the kids (focal point) so their faces fill the board
            w, h = full.get_size()
            zoom = 2.5
            focal_x_frac = 0.50
            focal_y_frac = 0.58
            side = max(1, int(min(w, h) / zoom))
            fx = int(w * focal_x_frac)
            fy = int(h * focal_y_frac)
            x0 = max(0, min(w - side, fx - side // 2))
            y0 = max(0, min(h - side, fy - side // 2))
            square = pygame.Surface((side, side), pygame.SRCALPHA)
            square.blit(full, (0, 0), pygame.Rect(x0, y0, side, side))
            full = pygame.transform.smoothscale(square, (PUZZLE_BOARD_PX, PUZZLE_BOARD_PX))
            puzzle_full_image = full.copy()
            puzzle_preview_start = time.time()
            for i in range(16):
                r, c = divmod(i, 4)
                slice_surf = pygame.Surface((PUZZLE_TILE_PX, PUZZLE_TILE_PX), pygame.SRCALPHA)
                slice_surf.blit(full, (0, 0),
                                pygame.Rect(c * PUZZLE_TILE_PX, r * PUZZLE_TILE_PX,
                                            PUZZLE_TILE_PX, PUZZLE_TILE_PX))
                puzzle_tile_images.append(slice_surf)
        except Exception:
            puzzle_tile_images = []

    # Shuffle via random valid moves from the solved state — guarantees solvability
    tiles = list(range(1, 16)) + [0]
    blank = 15
    last_blank = -1
    for _ in range(200):
        r, c = divmod(blank, 4)
        neighbours = []
        if r > 0: neighbours.append(blank - 4)
        if r < 3: neighbours.append(blank + 4)
        if c > 0: neighbours.append(blank - 1)
        if c < 3: neighbours.append(blank + 1)
        neighbours = [n for n in neighbours if n != last_blank] or neighbours
        pick = random.choice(neighbours)
        tiles[blank], tiles[pick] = tiles[pick], tiles[blank]
        last_blank, blank = blank, pick

    puzzle_tiles = tiles
    puzzle_anim = {}


def _puzzle_tile_rect(index):
    r, c = divmod(index, 4)
    return pygame.Rect(PUZZLE_BOARD_X + c * PUZZLE_TILE_PX,
                       PUZZLE_BOARD_Y + r * PUZZLE_TILE_PX,
                       PUZZLE_TILE_PX, PUZZLE_TILE_PX)


def _puzzle_try_move(clicked_index):
    """Swap with blank if orthogonally adjacent. Returns True on a move."""
    if puzzle_tiles[clicked_index] == 0:
        return False
    blank = puzzle_tiles.index(0)
    r1, c1 = divmod(clicked_index, 4)
    r2, c2 = divmod(blank, 4)
    if abs(r1 - r2) + abs(c1 - c2) != 1:
        return False
    tile_num = puzzle_tiles[clicked_index]
    puzzle_anim[tile_num] = [(c1 - c2) * PUZZLE_TILE_PX, (r1 - r2) * PUZZLE_TILE_PX]
    puzzle_tiles[blank], puzzle_tiles[clicked_index] = (
        puzzle_tiles[clicked_index], puzzle_tiles[blank])
    return True


def _puzzle_solved():
    return puzzle_tiles == list(range(1, 16)) + [0]


HINT_POPUP_DUR = 0.32
HINT_CARD_W = 360
HINT_CARD_H = 150

PUZZLE_PREVIEW_HOLD = 1.5
PUZZLE_PREVIEW_DISSOLVE = 0.5
PUZZLE_PREVIEW_TOTAL = PUZZLE_PREVIEW_HOLD + PUZZLE_PREVIEW_DISSOLVE

HINT_BUTTON_REVEAL_MOVES = 6
HINT_BUTTON_REVEAL_DUR = 0.45
HINT_BUTTON_W = 260
HINT_BUTTON_H = 68


def _hint_button_rect():
    r = pygame.Rect(0, 0, HINT_BUTTON_W, HINT_BUTTON_H)
    r.center = (WIDTH // 2, (PUZZLE_BOARD_Y + PUZZLE_BOARD_PX + HEIGHT) // 2)
    return r


def _hint_button_visible():
    return puzzle_move_count >= HINT_BUTTON_REVEAL_MOVES and not puzzle_auto_solve_used


def _puzzle_preview_active():
    return (puzzle_preview_start is not None
            and time.time() - puzzle_preview_start < PUZZLE_PREVIEW_TOTAL)

HINT_MESSAGES = [
    ("Just kidding!",      "Figure it out"),
    ("Still no help.",     "You got this"),
    ("Nope.",              "Back to work"),
    ("Try harder.",        "Keep trying"),
    ("Are you serious?",   "Stop clicking"),
    ("This is sad now.",   "Help yourself"),
    ("Bless your heart.",  "Good luck"),
    ("OK fine.",           "Take 75% off"),
]


def _hint_card_rect():
    r = pygame.Rect(0, 0, HINT_CARD_W, HINT_CARD_H)
    r.center = (WIDTH // 2, HEIGHT - GAME_BOTTOM - 10 - HINT_CARD_H // 2)
    return r


def _hint_dismiss_rect():
    r = pygame.Rect(0, 0, 210, 46)
    card = _hint_card_rect()
    r.center = (card.centerx, card.bottom - 38)
    return r


def _hint_current_texts():
    idx = max(0, min(hint_click_count - 1, len(HINT_MESSAGES) - 1))
    return HINT_MESSAGES[idx]


def _draw_hint_popup(screen):
    """Escalating 'Just kidding' pop-up — gets sassier each click."""
    t = max(0.0, time.time() - hint_popup_start)
    if t < HINT_POPUP_DUR:
        p = t / HINT_POPUP_DUR
        s = 1.70158
        scale = 1 + ((p - 1) ** 3) * (s + 1) + ((p - 1) ** 2) * s
    else:
        scale = 1.0
    scale = max(0.05, scale)

    base = _hint_card_rect()
    card_w = max(1, int(base.width * scale))
    card_h = max(1, int(base.height * scale))
    card_rect = pygame.Rect(0, 0, card_w, card_h)
    card_rect.center = base.center

    pygame.draw.rect(screen, (0, 0, 0), card_rect.move(4, 6), border_radius=18)
    pygame.draw.rect(screen, COLOR_CREAM, card_rect, border_radius=18)
    pygame.draw.rect(screen, COLOR_OUTLINE, card_rect, 4, border_radius=18)

    title_text, button_text = _hint_current_texts()

    if scale > 0.55:
        alpha = int(min(1.0, (scale - 0.55) / 0.45) * 255)
        # Shrink font if title is too wide for the card
        title_font = font_title
        title = title_font.render(title_text, True, COLOR_OUTLINE)
        if title.get_width() > card_rect.width - 30:
            title_font = font_win
            title = title_font.render(title_text, True, COLOR_OUTLINE)
        title.set_alpha(alpha)
        screen.blit(title, title.get_rect(center=(card_rect.centerx, card_rect.top + 40)))

    if scale >= 0.99:
        draw_crafted_button(screen, _hint_dismiss_rect(), button_text, font_ui, COLOR_BLUSH)


def draw_playing_puzzle(screen, dt, limit, elapsed_time):
    crafted_bg.draw(screen, dt)

    elapsed_time = max(0.0, elapsed_time)
    if limit:
        remaining = max(0, limit - elapsed_time)
        bar_w = int((remaining / limit) * (WIDTH - 40))
        pygame.draw.rect(screen, COLOR_OUTLINE, (20, 18, WIDTH-40, 16), border_radius=8)
        pygame.draw.rect(screen, (200, 220, 255), (22, 20, WIDTH-44, 12), border_radius=6)
        pygame.draw.rect(screen, COLOR_OUTLINE, (20, 18, WIDTH-40, 16), 3, border_radius=8)
        if bar_w > 0:
            if remaining < 10:
                pulse = abs(math.sin(time.time() * 4)) * 0.3
                bar_color = (255, int(80 + pulse * 100), 60)
            elif remaining < 30:
                bar_color = (255, 200, 0)
            else:
                bar_color = COLOR_YELLOW
            pygame.draw.rect(screen, bar_color, (22, 20, max(0, bar_w-4), 12), border_radius=6)

    # Header banner
    header_lines = wrap_text("Faces that only a Mama knows", font_win, WIDTH - 60)
    th = font_win.get_height()
    banner_h = th * len(header_lines) + 22
    banner_y = 55
    _draw_banner(screen, pygame.Rect(10, banner_y, WIDTH - 20, banner_h))
    _draw_star(screen, 24,          banner_y + banner_h // 2, 7, COLOR_YELLOW)
    _draw_star(screen, WIDTH - 24,  banner_y + banner_h // 2, 7, COLOR_YELLOW)
    ty = banner_y + 11
    for line in header_lines:
        draw_soft_text(screen, line, font_win, COLOR_CREAM, (WIDTH // 2, ty + th // 2))
        ty += th

    # Board backdrop with drop shadow
    board_rect = pygame.Rect(PUZZLE_BOARD_X - 6, PUZZLE_BOARD_Y - 6,
                             PUZZLE_BOARD_PX + 12, PUZZLE_BOARD_PX + 12)
    pygame.draw.rect(screen, (0, 0, 0), board_rect.move(4, 6), border_radius=14)
    pygame.draw.rect(screen, COLOR_GROUND, board_rect, border_radius=14)
    pygame.draw.rect(screen, COLOR_OUTLINE, board_rect, 3, border_radius=14)

    # Ease slides toward 0
    for n in list(puzzle_anim.keys()):
        dx, dy = puzzle_anim[n]
        decay = min(1.0, 14 * dt)
        dx -= dx * decay
        dy -= dy * decay
        if abs(dx) < 0.5 and abs(dy) < 0.5:
            del puzzle_anim[n]
        else:
            puzzle_anim[n] = [dx, dy]

    for i in range(16):
        n = puzzle_tiles[i]
        if n == 0:
            continue
        base = _puzzle_tile_rect(i)
        ox, oy = puzzle_anim.get(n, (0, 0))
        tile_rect = base.move(int(ox), int(oy))
        inner = tile_rect.inflate(-4, -4)

        pygame.draw.rect(screen, (0, 0, 0), inner.move(2, 3), border_radius=10)
        pygame.draw.rect(screen, COLOR_CREAM, inner, border_radius=10)

        if puzzle_tile_images:
            slice_surf = puzzle_tile_images[n - 1]
            if slice_surf.get_size() != (inner.width, inner.height):
                slice_surf = pygame.transform.smoothscale(slice_surf, (inner.width, inner.height))
            screen.blit(slice_surf, inner.topleft)

        pygame.draw.rect(screen, COLOR_OUTLINE, inner, 3, border_radius=10)

    if _puzzle_preview_active() and puzzle_full_image is not None:
        t = time.time() - puzzle_preview_start
        if t < PUZZLE_PREVIEW_HOLD:
            alpha = 255
        else:
            p = (t - PUZZLE_PREVIEW_HOLD) / PUZZLE_PREVIEW_DISSOLVE
            alpha = int(255 * (1 - p))
        overlay = puzzle_full_image.copy()
        overlay.set_alpha(max(0, min(255, alpha)))
        screen.blit(overlay, (PUZZLE_BOARD_X, PUZZLE_BOARD_Y))

    auto_rect = pygame.Rect(WIDTH // 2 - 55, HEIGHT - GAME_BOTTOM + 5, 110, 38)
    draw_crafted_button(screen, auto_rect, "Auto Win", font_ui, COLOR_BLUSH)

    if _hint_button_visible():
        base = _hint_button_rect()
        if hint_button_reveal_time is not None:
            reveal_t = time.time() - hint_button_reveal_time
            if reveal_t < HINT_BUTTON_REVEAL_DUR:
                p = reveal_t / HINT_BUTTON_REVEAL_DUR
                s = 1.70158
                scale = 1 + ((p - 1) ** 3) * (s + 1) + ((p - 1) ** 2) * s
            else:
                scale = 1.0
        else:
            scale = 1.0
        scale = max(0.05, scale)
        anim_rect = pygame.Rect(0, 0,
                                max(1, int(base.width * scale)),
                                max(1, int(base.height * scale)))
        anim_rect.center = base.center
        draw_crafted_button(screen, anim_rect, "HINT", font_ui, COLOR_YELLOW)

    if hint_popup_start is not None:
        _draw_hint_popup(screen)


def draw_playing(screen, dt, limit, elapsed_time, cards):
    crafted_bg.draw(screen, dt)

    if limit:
        remaining = max(0, limit - elapsed_time)
        bar_w = int((remaining / limit) * (WIDTH - 40))
        pygame.draw.rect(screen, COLOR_OUTLINE, (20, 18, WIDTH-40, 16), border_radius=8)
        pygame.draw.rect(screen, (200, 220, 255), (22, 20, WIDTH-44, 12), border_radius=6)
        pygame.draw.rect(screen, COLOR_OUTLINE, (20, 18, WIDTH-40, 16), 3, border_radius=8)
        if bar_w > 0:
            if remaining < 10:
                pulse = abs(math.sin(time.time() * 4)) * 0.3
                bar_color = (255, int(80 + pulse * 100), 60)
            elif remaining < 30:
                bar_color = (255, 200, 0)
            else:
                bar_color = COLOR_YELLOW
            pygame.draw.rect(screen, bar_color, (22, 20, max(0,bar_w-4), 12), border_radius=6)

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

def _draw_trivia_banner_to(surf, banner_y):
    """Banner + stars + headline text, drawn to `surf` with the banner's top
    at `banner_y`. Used by both the static and animated paths."""
    eyebrow_h  = font_ui.get_height()
    headline_h = font_win.get_height()
    banner_h   = eyebrow_h + headline_h + 22
    _draw_banner(surf, pygame.Rect(10, banner_y, WIDTH-20, banner_h))
    _draw_star(surf, 24,        banner_y + banner_h // 2, 7, COLOR_YELLOW)
    _draw_star(surf, WIDTH-24,  banner_y + banner_h // 2, 7, COLOR_YELLOW)
    draw_soft_text(surf, "Who wants to eat like a", font_ui, COLOR_CREAM,
                   (WIDTH // 2, banner_y + 11 + eyebrow_h // 2))
    draw_soft_text(surf, "MA-MILLIONAIRE", font_win, COLOR_CREAM,
                   (WIDTH // 2, banner_y + 11 + eyebrow_h + headline_h // 2),
                   max_width=WIDTH - 48)


def _draw_trivia_card_to(surf, rect, question_text):
    """Cream question card with shadow + outline + wrapped question text."""
    pygame.draw.rect(surf, (0, 0, 0),     (rect.x+4, rect.y+5, rect.width, rect.height), border_radius=14)
    pygame.draw.rect(surf, COLOR_GROUND,  rect, border_radius=14)
    pygame.draw.rect(surf, COLOR_OUTLINE, rect, 3, border_radius=14)
    lines = wrap_text(question_text, font_ui, rect.width - 28)
    line_h = font_ui.get_height()
    qy = rect.centery - (line_h * len(lines)) // 2
    for line in lines:
        q_txt = font_ui.render(line, True, COLOR_OUTLINE)
        surf.blit(q_txt, (rect.centerx - q_txt.get_width() // 2, qy))
        qy += line_h


def draw_trivia(screen, dt, question_idx):
    crafted_bg.draw(screen, dt)

    q_rect, start_y = get_trivia_layout()

    eyebrow_h  = font_ui.get_height()
    headline_h = font_win.get_height()
    banner_h   = eyebrow_h + headline_h + 22
    banner_y   = 70

    # Hero intro on Q0 (entry from menu / TRY AGAIN restart).
    # Subsequent questions skip the banner-reveal portion (1.30s) so only the
    # question card + answer buttons + auto-win re-animate as a round transition.
    INTRO_TOTAL = 2.55
    intro_t = time.time() - trivia_question_start
    if question_idx > 0:
        intro_t += 1.30

    def phase(start, dur):
        return max(0.0, min(1.0, (intro_t - start) / dur))

    # ── Title banner — staged hero reveal ───────────────────────────────────
    if intro_t >= 1.30:
        _draw_trivia_banner_to(screen, banner_y)
    else:
        # 1) Banner shape drops from far above, fades in
        bp = phase(0.00, 0.55)
        slide = int((1 - _ease_out_cubic(bp)) * -240)
        b_alpha = min(255, int(bp * 2.0 * 255))
        bs = pygame.Surface((WIDTH, banner_h + 24), pygame.SRCALPHA)
        _draw_banner(bs, pygame.Rect(10, 12, WIDTH - 20, banner_h))
        bs.set_alpha(b_alpha)
        screen.blit(bs, (0, banner_y - 12 + slide))

        # 2) Eyebrow "Who wants to eat like a" fades up
        ep = phase(0.45, 0.40)
        if ep > 0:
            lift = int((1 - _ease_out_cubic(ep)) * 12)
            es = pygame.Surface((WIDTH, eyebrow_h + 8), pygame.SRCALPHA)
            draw_soft_text(es, "Who wants to eat like a", font_ui, COLOR_CREAM,
                           (WIDTH // 2, (eyebrow_h + 8) // 2))
            es.set_alpha(min(255, int(ep * 255)))
            target_cy = banner_y + 11 + eyebrow_h // 2 + lift
            screen.blit(es, es.get_rect(center=(WIDTH // 2, target_cy)))

        # 3) MA-MILLIONAIRE punches in with overshoot scale
        hp = phase(0.75, 0.50)
        if hp > 0:
            scale = max(0.05, 1.6 - 0.6 * _ease_out_back(hp))
            h_alpha = min(255, int(hp * 1.6 * 255))
            hs = pygame.Surface((WIDTH, headline_h + 16), pygame.SRCALPHA)
            draw_soft_text(hs, "MA-MILLIONAIRE", font_win, COLOR_CREAM,
                           (WIDTH // 2, (headline_h + 16) // 2),
                           max_width=WIDTH - 48)
            sw = max(1, int(hs.get_width() * scale))
            sh = max(1, int(hs.get_height() * scale))
            scaled = pygame.transform.smoothscale(hs, (sw, sh))
            scaled.set_alpha(h_alpha)
            target_cy = banner_y + 11 + eyebrow_h + headline_h // 2
            screen.blit(scaled, scaled.get_rect(center=(WIDTH // 2, target_cy)))

        # 4) Stars sparkle in with overshoot
        sp = phase(0.90, 0.40)
        if sp > 0:
            ss = max(0.05, _ease_out_back(sp))
            star_r = max(1, int(7 * ss))
            _draw_star(screen, 24,       banner_y + banner_h // 2, star_r, COLOR_YELLOW)
            _draw_star(screen, WIDTH-24, banner_y + banner_h // 2, star_r, COLOR_YELLOW)

    if question_idx >= len(TRIVIA_QUESTIONS):
        return

    q_data = TRIVIA_QUESTIONS[question_idx]

    # ── Question card — pop in with bouncy scale ────────────────────────────
    cp = phase(1.40, 0.50)
    if cp >= 1.0:
        _draw_trivia_card_to(screen, q_rect, q_data["question"])
    elif cp > 0:
        scale = max(0.05, _ease_out_back(cp))
        alpha = min(255, int(cp * 2.5 * 255))
        ts = pygame.Surface((q_rect.width + 20, q_rect.height + 20), pygame.SRCALPHA)
        local_q = pygame.Rect(10, 10, q_rect.width, q_rect.height)
        _draw_trivia_card_to(ts, local_q, q_data["question"])
        sw = max(1, int(ts.get_width() * scale))
        sh = max(1, int(ts.get_height() * scale))
        scaled = pygame.transform.smoothscale(ts, (sw, sh))
        scaled.set_alpha(alpha)
        screen.blit(scaled, scaled.get_rect(center=q_rect.center))

    # ── Answer buttons — slide up from below + pop in, staggered ────────────
    OPT_COLORS = [(100, 196, 248), COLOR_BLUSH, (100, 196, 248), COLOR_BLUSH]
    mx, my = pygame.mouse.get_pos()
    for i, opt in enumerate(q_data["options"]):
        opt_rect = pygame.Rect(WIDTH//2 - 185, start_y + i*82, 370, 66)
        col = COLOR_YELLOW if opt_rect.collidepoint(mx, my) else OPT_COLORS[i]
        bp_i = phase(1.65 + i * 0.10, 0.40)
        if bp_i <= 0:
            continue
        if bp_i >= 1.0:
            draw_crafted_button(screen, opt_rect, opt, font_ui, col)
        else:
            slide = int((1 - _ease_out_back(bp_i)) * 90)
            alpha = min(255, int(bp_i * 2.5 * 255))
            ts = pygame.Surface((opt_rect.width + 20, opt_rect.height + 20), pygame.SRCALPHA)
            draw_crafted_button(ts, pygame.Rect(10, 10, opt_rect.width, opt_rect.height),
                                opt, font_ui, col)
            ts.set_alpha(alpha)
            screen.blit(ts, (opt_rect.x - 10, opt_rect.y - 10 + slide))

    # ── Auto-win button — fades in last ─────────────────────────────────────
    auto_rect = pygame.Rect(WIDTH // 2 - 55, HEIGHT - GAME_BOTTOM + 5, 110, 38)
    ap = phase(2.20, 0.35)
    if ap >= 1.0:
        draw_crafted_button(screen, auto_rect, "Auto Win", font_ui, COLOR_BLUSH)
    elif ap > 0:
        alpha = min(255, int(ap * 255))
        ts = pygame.Surface((auto_rect.width + 20, auto_rect.height + 20), pygame.SRCALPHA)
        draw_crafted_button(ts, pygame.Rect(10, 10, auto_rect.width, auto_rect.height),
                            "Auto Win", font_ui, COLOR_BLUSH)
        ts.set_alpha(alpha)
        screen.blit(ts, (auto_rect.x - 10, auto_rect.y - 10))

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
                   (WIDTH//2, HEIGHT//2 - 60), WIDTH - 30)

    # Secret Gift button — glowing gold, centered
    glow = 0.5 + 0.5 * math.sin(time.time() * 3)
    glow_color = (255, int(200 + 55 * glow), 0)
    secret_gift_rect = pygame.Rect(WIDTH//2 - 100, HEIGHT//2 - 5, 200, 62)
    draw_crafted_button(screen, secret_gift_rect, "Secret Gift", font_ui, glow_color)
    # Sparkle stars flanking the button
    for s in range(4):
        angle = time.time() * 2.5 + s * (math.pi * 2 / 4)
        sx = secret_gift_rect.centerx + int(math.cos(angle) * (secret_gift_rect.width // 2 + 18))
        sy = secret_gift_rect.centery + int(math.sin(angle) * (secret_gift_rect.height // 2 + 12))
        star_s = max(2, int(4 + 3 * math.sin(time.time() * 5 + s)))
        _draw_star(screen, sx, sy, star_s, COLOR_YELLOW)

    menu_button_rect = pygame.Rect(WIDTH//2 - 168, HEIGHT - 105, 150, 62)
    draw_crafted_button(screen, menu_button_rect, "MENU", font_ui, (100, 196, 248))

    exit_button_rect = pygame.Rect(WIDTH//2 + 18, HEIGHT - 105, 150, 62)
    draw_crafted_button(screen, exit_button_rect, "EXIT", font_ui, COLOR_BLUSH)

    return menu_button_rect, exit_button_rect, secret_gift_rect

def draw_secret_reward(screen, dt, win_animation_start_time, win_particles):
    crafted_bg.draw(screen, dt)

    # Celebratory gold particles
    for p in win_particles:
        p["y"] -= p["speed"] * dt
        if p["y"] < -50: p["y"] = HEIGHT + 50
        sway = math.sin(time.time() * 2 + p["seed"]) * 30
        _draw_star(screen, int(p["x"] + sway), int(p["y"]),
                   int(p["size"] * 4), p["color"])

    elapsed = time.time() - win_animation_start_time
    progress = min(1.0, elapsed / 1.2)
    eased = 1 - (1 - progress) ** 3

    # Large heart at the top
    hx, hy = WIDTH // 2, int(50 + 15 * (1 - eased))
    hs = eased * 2.5
    if hs > 0.1:
        draw_vector_heart(screen, hx, hy, hs, COLOR_BLUSH)

    # "SECRET REWARD UNLOCKED!"
    if progress > 0.2:
        a = min(255, int((progress - 0.2) / 0.25 * 255))
        txt = font_win.render("SECRET REWARD UNLOCKED!", True, COLOR_YELLOW)
        txt.set_alpha(a)
        screen.blit(txt, (WIDTH // 2 - txt.get_width() // 2, 95))

    # "PHOTOSHOOT" big title
    if progress > 0.45:
        a = min(255, int((progress - 0.45) / 0.25 * 255))
        title = font_title.render("PHOTOSHOOT", True, COLOR_BLUSH)
        title.set_alpha(a)
        screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 135))

    # "with ANNIE" and description
    if progress > 0.65:
        a = min(255, int((progress - 0.65) / 0.25 * 255))
        sub = font_win.render("with ANNIE", True, COLOR_OUTLINE)
        sub.set_alpha(a)
        screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 240))

        desc1 = font_ui.render("A prepaid photoshoot with your", True, COLOR_OUTLINE)
        desc1.set_alpha(a)
        screen.blit(desc1, (WIDTH // 2 - desc1.get_width() // 2, 290))

        desc2 = font_ui.render("favourite photographer!", True, COLOR_OUTLINE)
        desc2.set_alpha(a)
        screen.blit(desc2, (WIDTH // 2 - desc2.get_width() // 2, 318))

    menu_button_rect = None
    if progress >= 1.0:
        menu_button_rect = pygame.Rect(WIDTH // 2 - 75, HEIGHT - 80, 150, 55)
        draw_crafted_button(screen, menu_button_rect, "MENU", font_ui, (100, 196, 248))

    return menu_button_rect

def draw_trivia_correct(screen, dt, start_time, question_idx, heart_pos, items):
    draw_trivia(screen, dt, question_idx)
    elapsed = time.time() - start_time

    for i, item_type in enumerate(items):
        offset_x = (i - 1) * 50
        delay = i * 0.15
        t = max(0, elapsed - delay)
        if t <= 0:
            continue
        hy = heart_pos[1] - t * 200
        alpha = max(0, 255 - int(t * 255))
        size = 1.5 + t * 0.5
        _draw_brunch_item(screen, item_type, heart_pos[0] + offset_x, hy, size, alpha)

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
    btn_label = "LET'S EAT" if (game_state_val == GameState.WON and selected_idx == 0) else "GOOD JOB!"

    menu_button_rect = None
    save_button_rect = None
    
    if game_state_val == GameState.WON and current_img is not None:
        global _last_won_anim_time
        if win_animation_start_time != _last_won_anim_time:
            play_sound("win")
            _last_won_anim_time = win_animation_start_time
        crafted_bg.draw(screen, dt)

        for p in win_particles:
            p["y"] -= p["speed"] * dt
            if p["y"] < -50: p["y"] = HEIGHT + 50
            sway = math.sin(time.time()*2 + p["seed"]) * 30
            draw_vector_heart(screen, p["x"] + sway, p["y"], p["size"], p["color"], 150)

        win_elapsed = time.time() - win_animation_start_time

        # wrap the reward message so it never overflows the 450px canvas
        if msg.strip():
            msg_lines = wrap_text(msg, font_win, WIDTH - 30)
            line_h = font_win.get_height()
            msg_block_h = line_h * len(msg_lines)
            img_top = msg_block_h + 20
        else:
            msg_lines = []
            line_h = font_win.get_height()
            msg_block_h = 0
            img_top = 10

        avail_h = HEIGHT - img_top - 80
        base_scale = min(1.0, avail_h / current_img.get_height(), (WIDTH - 20) / current_img.get_width())
        base_w, base_h = int(current_img.get_width() * base_scale), int(current_img.get_height() * base_scale)
        base_x = WIDTH // 2 - base_w // 2
        base_y = img_top + (avail_h - base_h) // 2 if msg_block_h == 0 else img_top

        DINNER_ANIM_TOTAL = 1.55
        if selected_idx == 2 and win_elapsed < DINNER_ANIM_TOTAL:
            # ── Dinner: piece-by-piece staged reveal (banner → photo → info) ──
            # Slice the pre-built 400×780 card into 3 horizontal sections
            full_w, full_h = current_img.get_size()
            BANNER_END = int(full_h * (100 / 780))   # ≈ 100 in original coords
            PHOTO_END  = int(full_h * (608 / 780))   # ≈ 608

            sec_w = base_w
            banner_h_s = int(BANNER_END * base_scale)
            photo_h_s  = int((PHOTO_END - BANNER_END) * base_scale)
            info_h_s   = base_h - banner_h_s - photo_h_s

            def _phase(start, dur):
                return max(0.0, min(1.0, (win_elapsed - start) / dur))

            # 1) Banner — drops from far above with fade
            bp = _phase(0.00, 0.55)
            if bp > 0:
                slide = int((1 - _ease_out_cubic(bp)) * -300)
                alpha = min(255, int(bp * 2.0 * 255))
                banner_orig = current_img.subsurface((0, 0, full_w, BANNER_END))
                scaled_banner = pygame.transform.smoothscale(banner_orig, (sec_w, banner_h_s))
                scaled_banner.set_alpha(alpha)
                screen.blit(scaled_banner, (base_x, base_y + slide))

            # 2) Photo — pops in with overshoot scale + fade
            pp = _phase(0.45, 0.55)
            if pp > 0:
                scale_p = max(0.05, _ease_out_back(pp))
                alpha = min(255, int(pp * 1.8 * 255))
                photo_orig = current_img.subsurface((0, BANNER_END, full_w, PHOTO_END - BANNER_END))
                tw = max(1, int(sec_w * scale_p))
                th = max(1, int(photo_h_s * scale_p))
                scaled_photo = pygame.transform.smoothscale(photo_orig, (tw, th))
                scaled_photo.set_alpha(alpha)
                photo_cy = base_y + banner_h_s + photo_h_s // 2
                screen.blit(scaled_photo, scaled_photo.get_rect(center=(base_x + sec_w // 2, photo_cy)))

            # 3) Info — fades in with slide up
            ip = _phase(0.90, 0.55)
            if ip > 0:
                lift = int((1 - _ease_out_cubic(ip)) * 30)
                alpha = min(255, int(ip * 1.5 * 255))
                info_orig = current_img.subsurface((0, PHOTO_END, full_w, full_h - PHOTO_END))
                scaled_info = pygame.transform.smoothscale(info_orig, (sec_w, info_h_s))
                scaled_info.set_alpha(alpha)
                info_y_target = base_y + banner_h_s + photo_h_s
                screen.blit(scaled_info, (base_x, info_y_target + lift))

            progress = win_elapsed / DINNER_ANIM_TOTAL
        else:
            # Existing scale-up animation for brunch/massage (and dinner post-anim)
            progress = min(1.0, win_elapsed / 0.7)
            eased_progress = 1 - (1 - progress) ** 4
            curr_w, curr_h = int(base_w * eased_progress), int(base_h * eased_progress)
            if curr_w > 0 and curr_h > 0:
                pad = 0 if msg_block_h == 0 else 15
                img_x = WIDTH // 2 - curr_w // 2
                if msg_block_h == 0:
                    img_y = img_top + (avail_h - curr_h) // 2
                else:
                    img_y = img_top + (base_h - curr_h) // 2
                if pad > 0:
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
            draw_crafted_button(screen, menu_button_rect, btn_label, font_ui, COLOR_BLUSH, text_outline_color=(0, 0, 0))
    else:
        crafted_bg.draw(screen, dt)
        for p in win_particles:
            p["y"] -= p["speed"] * dt
            if p["y"] < -50: p["y"] = HEIGHT + 50
            sway = math.sin(time.time()*2 + p["seed"]) * 30
            draw_vector_heart(screen, p["x"] + sway, p["y"], p["size"], p["color"], 150)
        draw_vector_heart(screen, WIDTH//2, HEIGHT//2 - 60, 6.0, COLOR_BLUSH)
        draw_soft_text(screen, msg, font_win, COLOR_CREAM, (WIDTH//2, HEIGHT//2 + 40), max_width=WIDTH - 40)

        show_retry = (selected_idx is not None
                      and 0 <= selected_idx < len(options)
                      and options[selected_idx].get("type") in ("trivia", "memory"))
        if show_retry:
            # Brunch (trivia) & Dinner (memory) failure: offer TRY AGAIN + MENU.
            # Handler at MOUSEBUTTONDOWN restarts the appropriate game type when
            # save_button_rect is clicked.
            save_button_rect = pygame.Rect(WIDTH//2 - 120, HEIGHT//2 + 100, 240, 52)
            draw_crafted_button(screen, save_button_rect, "TRY AGAIN, MAMA!", font_ui, COLOR_BLUSH)
            menu_button_rect = pygame.Rect(WIDTH//2 - 80, HEIGHT//2 + 168, 160, 44)
            draw_crafted_button(screen, menu_button_rect, "MENU", font_ui, COLOR_SAGE)
        else:
            menu_button_rect = pygame.Rect(WIDTH//2 - 80, HEIGHT//2 + 100, 160, 50)
            draw_crafted_button(screen, menu_button_rect, "GOOD JOB!", font_ui, COLOR_BLUSH, text_outline_color=(0, 0, 0))

    return menu_button_rect, save_button_rect

async def main():
    global game_state, selected_idx, cards, first, second, wait_timer, start_time, paused_time, modal_image, modal_start_time, win_animation_start_time, win_particles, scroll_y, completed_games, current_question_idx, trivia_question_start
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
        except Exception:
            pass
        while True:
            await asyncio.sleep(1)

async def _main():
    global game_state, selected_idx, cards, first, second, wait_timer, start_time, paused_time, modal_image, modal_start_time, win_animation_start_time, win_particles, scroll_y, completed_games, current_question_idx, landscape_ready_start, prev_game_state_before_landscape, trivia_question_start, secret_button_appear_time, secret_unlocked_seen, hint_popup_start, hint_click_count, puzzle_preview_start, puzzle_full_image, puzzle_move_count, hint_button_reveal_time, puzzle_auto_solve_used
    global screen, clock, crafted_bg, game_images, reward_images, menu_images, nodo_image, nodo_video_path, massage_video_path, pdf_surface, pdf_surface_height, font_title, font_win, font_ui, font_huge

    pygame.display.init()
    pygame.font.init()
    try:
        pygame.mixer.init()
    except Exception:
        pass
    _init_sounds()
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
    brunch_hero = None
    nola_logo = None
    massage_hero = None
    sereno_logo = None
    dinner_hero = None
    try:
        img_dir = os.path.dirname(os.path.abspath(__file__))
        root_path = os.path.dirname(img_dir)
        for fname in ("brunch2.jpeg", "brunch2.jpg", "Amal-Pancakes.jpg", "Amal-Pancakes.jpeg", "Amal-Pancakes.png"):
            p = os.path.join(img_dir, fname)
            if os.path.exists(p):
                brunch_hero = pygame.image.load(p).convert_alpha()
                break
        for fname in ("nola.webp", "NOLA.webp", "NOLA.png", "nola.png", "nola-logo.png", "NOLA-logo.png", "NOLA.jpg", "nola.jpg"):
            p = os.path.join(img_dir, fname)
            if os.path.exists(p):
                nola_logo = pygame.image.load(p).convert_alpha()
                break
        for fname in ("therapeute.jpg", "gettyimages-1590247404-170667a.jpg", "massage-hero.jpg", "massage-hero.png"):
            p = os.path.join(img_dir, fname)
            if os.path.exists(p):
                massage_hero = pygame.image.load(p).convert_alpha()
                break
        for fname in ("Sereno-logo.png", "sereno-logo.png", "Sereno.png", "sereno.png"):
            p = os.path.join(img_dir, fname)
            if os.path.exists(p):
                sereno_logo = pygame.image.load(p).convert_alpha()
                _black = pygame.Surface(sereno_logo.get_size(), pygame.SRCALPHA)
                _black.fill((0, 0, 0, 255))
                sereno_logo.blit(_black, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                break
        for fname in ("nodo.jpg", "nodo.jpeg", "nodo.png", "dinner.jpg"):
            p = os.path.join(img_dir, fname)
            if os.path.exists(p):
                dinner_hero = pygame.image.load(p).convert_alpha()
                break
        files = {1: "massage.jpg.jpeg", 2: "dinner.jpg"}
        space_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "SpaceSwarm")
        for idx, fname in files.items():
            path = os.path.join(space_path, fname)
            if os.path.exists(path):
                reward_images[idx] = pygame.image.load(path).convert_alpha()
            else:
                path = os.path.join(space_path, "Images", fname)
                if os.path.exists(path):
                    reward_images[idx] = pygame.image.load(path).convert_alpha()
    except Exception: pass

    menu_images = []
    try:
        menu_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "SpaceSwarm", "Images", "Menu")
        if os.path.exists(menu_dir):
            for i in range(7):
                for ext in [".jpg", ".png", ".jpeg"]:
                    fpath = os.path.join(menu_dir, f"Menu-Images-{i}{ext}")
                    if os.path.exists(fpath):
                        img = pygame.image.load(fpath).convert_alpha()
                        scale = (WIDTH - 100) / img.get_width()
                        menu_images.append(pygame.transform.smoothscale(img, (int(WIDTH - 100), int(img.get_height() * scale))))
                        break
    except Exception: pass

    nodo_image = None
    nodo_logo = None
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
        for fname in ["NODO-logo.png", "nodo-logo.png", "NODO Octagon-LeslievilleWHITE.png"]:
            npath = os.path.join(current_dir, fname)
            if os.path.exists(npath):
                nodo_logo = pygame.image.load(npath).convert_alpha()
                _black = pygame.Surface(nodo_logo.get_size(), pygame.SRCALPHA)
                _black.fill((0, 0, 0, 255))
                nodo_logo.blit(_black, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                break
    except Exception: pass

    nodo_video_path = None
    try:
        root_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "SpaceSwarm")
        video_dir = os.path.join(root_path, "Video")
        if not os.path.exists(video_dir):
            video_dir = os.path.join(root_path, "video")
        if os.path.exists(video_dir):
            for fname in ["NODO.mp4", "nodo.mp4", "NODO.mov", "nodo.mov"]:
                fpath = os.path.join(video_dir, fname)
                if os.path.exists(fpath):
                    nodo_video_path = fpath
                    break
    except Exception: pass

    massage_video_path = None
    try:
        if nodo_video_path and os.path.exists(os.path.dirname(nodo_video_path)):
            _vdir = os.path.dirname(nodo_video_path)
        elif 'video_dir' in dir() and os.path.exists(video_dir):
            _vdir = video_dir
        else:
            _vdir = None
        if _vdir:
            for fname in ["MASSAGE.mp4", "massage.mp4", "Massage.mp4", "MASSAGE.mov"]:
                if os.path.exists(os.path.join(_vdir, fname)):
                    massage_video_path = os.path.join(_vdir, fname)
                    break
    except Exception: pass

    _curr_dir  = os.path.dirname(os.path.abspath(__file__))
    _parent_dir = os.path.dirname(_curr_dir)

    # Fredoka One → titles and win-screen text (bubbly, rounded)
    fredoka = None
    for fname in ["FredokaOne-Regular.ttf", "Fredoka-Bold.ttf", "Fredoka-SemiBold.ttf", "Fredoka_One.ttf", "fredoka_one.ttf"]:
        p = os.path.join(_curr_dir, fname)
        if os.path.exists(p):
            try: fredoka = p; break
            except Exception: pass

    # Titan One → buttons and UI text (chunky, bold)
    titan = None
    for fname in ["TitanOne-Regular.ttf", "Titan_One.ttf", "titan_one.ttf"]:
        p = os.path.join(_curr_dir, fname)
        if os.path.exists(p):
            try: titan = p; break
            except Exception: pass

    try:
        font_title = pygame.font.Font(fredoka, 54) if fredoka else pygame.font.SysFont(None, 52)
        font_win   = pygame.font.Font(fredoka, 40) if fredoka else pygame.font.SysFont(None, 40)
        font_huge  = pygame.font.Font(titan,   92) if titan   else pygame.font.SysFont(None, 88)
    except Exception:
        font_title = pygame.font.SysFont(None, 52)
        font_win   = pygame.font.SysFont(None, 40)
        font_huge  = pygame.font.SysFont(None, 88)

    try:
        font_ui = pygame.font.Font(titan, 22) if titan else pygame.font.SysFont(None, 24)
    except Exception:
        font_ui = pygame.font.SysFont(None, 24)

    try:
        reward_images[0] = _build_reward_takeover(
            "MOTHER'S DAY BRUNCH", brunch_hero,
            "Reso for 4 @ 11AM",
            "NOLA Toronto",
            logo_img=nola_logo)
        reward_images[1] = _build_reward_takeover(
            "MOTHER'S DAY MASSAGE", massage_hero,
            "1:45PM",
            "Spa Sereno",
            logo_img=sereno_logo)
        reward_images[2] = _build_reward_takeover(
            "MOTHER'S DAY DINNER", dinner_hero,
            "FamJam eats @ 6:15pm",
            "NODO Leslieville",
            logo_img=nodo_logo)
    except Exception:
        if 0 not in reward_images and brunch_hero is None:
            try: reward_images[0] = _generate_brunch_reservation_card()
            except Exception: pass

    scroll_y = 0
    nodo_start_time = 0
    transition_start_time = 0
    transition_particles = []
    running = True
    menu_button_rect = None
    save_button_rect = None
    exit_button_rect = None
    secret_gift_rect = None
    pdf_scroll_y = 0
    pdf_close_rect = None
    correct_anim_start = 0
    correct_anim_pos = (WIDTH // 2, HEIGHT // 2)
    correct_anim_items = []
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

        elif game_state == GameState.PLAYING_PUZZLE:
            limit = options[selected_idx]["limit"]
            elapsed = (time.time() - start_time) - paused_time
            draw_playing_puzzle(screen, dt, limit, elapsed)
            if limit and (limit - elapsed) <= 0:
                game_state = GameState.GAMEOVER
            elif not puzzle_anim and _puzzle_solved():
                completed_games.add(selected_idx)
                game_state = GameState.TRANSITION_TO_REWARD
                transition_start_time = time.time()
                transition_particles = []

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
                        play_sound("match")
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
                if selected_idx == 2:  # Dinner uses the NODO video reward flow
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
                else:  # Brunch & Massage — cut straight to the reward card
                    game_state = GameState.WON
                    scroll_y = 0
                    win_animation_start_time = time.time()
                    win_particles = [{"x": random.randint(0, WIDTH), "y": random.randint(0, HEIGHT),
                                      "size": random.uniform(1.0, 3.0), "speed": random.uniform(100, 200),
                                      "seed": random.random(), "color": random.choice([COLOR_SOFT_PINK, COLOR_ROSE_GOLD, COLOR_CREAM])} for _ in range(40)]

        elif game_state == GameState.PLAY_VIDEO_REWARD:
            if IS_WEB:
                await play_video_web("https://troygeoghegan.github.io/Operation-Big-Mama/nodo.mp4")
                game_state = GameState.WON
                scroll_y = 0
                win_animation_start_time = time.time()
                win_particles = [{"x": random.randint(0, WIDTH), "y": random.randint(0, HEIGHT),
                                  "size": random.uniform(1.0, 3.0), "speed": random.uniform(100, 200),
                                  "seed": random.random(), "color": random.choice([COLOR_SOFT_PINK, COLOR_ROSE_GOLD, COLOR_CREAM])} for _ in range(40)]
            else:
                skipped = await play_video(nodo_video_path)
                if skipped and selected_idx == 2:
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
            menu_button_rect, exit_button_rect, secret_gift_rect = draw_final_message(screen, dt, transition_particles)

        elif game_state == GameState.SECRET_REWARD:
            menu_button_rect = draw_secret_reward(screen, dt, win_animation_start_time, win_particles)

        elif game_state == GameState.TRIVIA_CORRECT:
            if draw_trivia_correct(screen, dt, correct_anim_start, current_question_idx, correct_anim_pos, correct_anim_items):
                current_question_idx += 1
                if current_question_idx >= len(TRIVIA_QUESTIONS):
                    completed_games.add(selected_idx)
                    game_state = GameState.TRANSITION_TO_REWARD
                    transition_start_time = time.time()
                    transition_particles = []
                else:
                    game_state = GameState.PLAYING_TRIVIA
                    trivia_question_start = time.time()

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
                    for i, btn_rect in enumerate(_menu_button_rects()):
                        if btn_rect.collidepoint(mx, my):
                            selected_idx = i
                            if options[selected_idx].get("type") == "trivia":
                                if pending_trivia_questions:
                                    TRIVIA_QUESTIONS[:] = pending_trivia_questions
                                game_state = GameState.PLAYING_TRIVIA
                                current_question_idx = 0
                                trivia_question_start = time.time()
                            elif options[selected_idx].get("type") == "puzzle":
                                init_sliding_puzzle()
                                game_state = GameState.PLAYING_PUZZLE
                                start_time = time.time() + PUZZLE_PREVIEW_TOTAL
                                paused_time = 0
                            else:
                                cards, game_state, start_time, paused_time = create_board(game_images, options[selected_idx]["pairs"]), GameState.PLAYING, time.time(), 0
                elif game_state == GameState.PLAYING_TRIVIA:
                    if pygame.Rect(WIDTH // 2 - 55, HEIGHT - GAME_BOTTOM + 5, 110, 38).collidepoint(mx, my):
                        current_question_idx = len(TRIVIA_QUESTIONS)
                        completed_games.add(selected_idx)
                        game_state = GameState.TRANSITION_TO_REWARD
                        transition_start_time = time.time()
                        transition_particles = []
                    else:
                        q_data = TRIVIA_QUESTIONS[current_question_idx]
                        _, start_y = get_trivia_layout()
                        for i in range(4):
                            opt_rect = pygame.Rect(WIDTH//2 - 185, start_y + i*82, 370, 66)
                            if opt_rect.collidepoint(mx, my):
                                if i == q_data["answer"]:
                                    correct_anim_start = time.time()
                                    correct_anim_pos = opt_rect.center
                                    correct_anim_items = [random.randint(0, 2) for _ in range(3)]
                                    game_state = GameState.TRIVIA_CORRECT
                                    play_sound("correct")
                                else:
                                    game_state = GameState.TRIVIA_FAIL_FADE
                                    transition_start_time = time.time()
                                    trigger_vibration()
                                    play_sound("wrong")
                elif game_state == GameState.PLAYING_PUZZLE and not _puzzle_preview_active():
                    popup_up = hint_popup_start is not None
                    if popup_up and time.time() - hint_popup_start >= HINT_POPUP_DUR and _hint_dismiss_rect().collidepoint(mx, my):
                        # On the LAST hint (after 8+ clicks), the dismiss button
                        # actually solves the puzzle to 75% — leaves 3 moves.
                        if hint_click_count >= len(HINT_MESSAGES) and not puzzle_auto_solve_used:
                            for i in range(12):
                                puzzle_tiles[i] = i + 1
                            puzzle_tiles[12] = 0
                            puzzle_tiles[13] = 13
                            puzzle_tiles[14] = 14
                            puzzle_tiles[15] = 15
                            puzzle_anim.clear()
                            puzzle_auto_solve_used = True
                        hint_popup_start = None
                    elif pygame.Rect(WIDTH // 2 - 55, HEIGHT - GAME_BOTTOM + 5, 110, 38).collidepoint(mx, my):
                        for i in range(15):
                            puzzle_tiles[i] = i + 1
                        puzzle_tiles[15] = 0
                        puzzle_anim.clear()
                        completed_games.add(selected_idx)
                        game_state = GameState.TRANSITION_TO_REWARD
                        transition_start_time = time.time()
                        transition_particles = []
                    elif not popup_up and _hint_button_visible() and _hint_button_rect().collidepoint(mx, my):
                        hint_popup_start = time.time()
                        hint_click_count += 1
                    else:
                        for i in range(16):
                            if _puzzle_tile_rect(i).collidepoint(mx, my):
                                if _puzzle_try_move(i):
                                    puzzle_move_count += 1
                                    play_sound("slide")
                                    if puzzle_move_count == HINT_BUTTON_REVEAL_MOVES and hint_button_reveal_time is None:
                                        hint_button_reveal_time = time.time()
                                break
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
                            play_sound("flip")
                            if not first: first = card
                            elif not second: second, wait_timer = card, 0.7
                elif game_state == GameState.SECRET_REWARD:
                    if menu_button_rect and menu_button_rect.collidepoint(mx, my):
                        game_state = GameState.MENU
                        selected_idx = None
                        menu_button_rect = None
                elif game_state == GameState.PDF_VIEWER:
                    if pdf_close_rect and pdf_close_rect.collidepoint(mx, my):
                        game_state = GameState.MENU
                        selected_idx = None
                elif game_state in [GameState.WON, GameState.GAMEOVER, GameState.FINAL_MESSAGE]:
                    if game_state == GameState.WON and time.time() - win_animation_start_time < 0.5:
                        continue
                    if menu_button_rect and menu_button_rect.collidepoint(mx, my):
                        if game_state == GameState.WON and len(completed_games) == len(options):
                            game_state = GameState.FINAL_MESSAGE
                            transition_start_time = time.time()
                            transition_particles = []
                        else:
                            game_state = GameState.MENU
                            selected_idx = None
                        menu_button_rect = None
                        save_button_rect = None
                    elif game_state == GameState.FINAL_MESSAGE and secret_gift_rect and secret_gift_rect.collidepoint(mx, my):
                        game_state = GameState.SECRET_REWARD
                        win_animation_start_time = time.time()
                        win_particles = [{"x": random.randint(0, WIDTH), "y": random.randint(0, HEIGHT),
                                          "size": random.uniform(1.5, 4.0), "speed": random.uniform(80, 180),
                                          "seed": random.random(), "color": random.choice([COLOR_YELLOW, COLOR_BLUSH, COLOR_CREAM])} for _ in range(60)]
                        menu_button_rect = None
                        secret_gift_rect = None
                    elif game_state == GameState.GAMEOVER and save_button_rect and save_button_rect.collidepoint(mx, my):
                        if options[selected_idx].get("type") == "trivia":
                            if pending_trivia_questions:
                                TRIVIA_QUESTIONS[:] = pending_trivia_questions
                            game_state = GameState.PLAYING_TRIVIA
                            current_question_idx = 0
                            trivia_question_start = time.time()
                        elif options[selected_idx].get("type") == "puzzle":
                            init_sliding_puzzle()
                            game_state = GameState.PLAYING_PUZZLE
                            start_time = time.time()
                            paused_time = 0
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