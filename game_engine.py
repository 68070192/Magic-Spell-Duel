"""
Module: game_engine.py
Description: ลูปการทำงานหลักของเกม (Main Game Loop & Application Engine)
             ทำหน้าที่ประสานงานระหว่างระบบComputer Vision (MediaPipe Hands & Face),
             การตรวจจับท่าทางและลายเส้น, ตรรกะการต่อสู้ (Combat Logic), 
             ระบบแสดงผลกราฟิก (VFX & HUD), ระบบเสียง และการจัดการสเตทการแข่งขัน (Match State Machine)
"""

import os
import time
import math
import random
import cv2
import numpy as np
import mediapipe as mp

import config as cfg
from gesture_recognizer import GestureRecognizer
from unistroke import UnistrokeRecognizer
from spell_system import SpellConfig, PlayerCombatState
from ui_renderer import UIRenderer
from sound_manager import SoundManager
from resource_helper import get_resource_path, get_base_dir


# ==============================================================================
# 1. ระบบติดตามคอมโบท่าร่าย และยูทิลิตีกราฟิกหน้าเมนู
# ==============================================================================

class ChantSequenceTracker:
    """ระบบตรวจจับลำดับท่าร่ายต่อเนื่องเพื่อปลดล็อกสกิลพิเศษ พร้อมระบบ Timeout"""

    def __init__(self, sequence=None, timeout=4.0):
        if sequence is None:
            sequence = ["FIST", "PEACE", "OPEN_HAND"]
        self.sequence = sequence
        self.current_step = 0
        self.last_step_time = 0.0
        self.timeout = timeout

    def reset(self):
        self.current_step = 0
        self.last_step_time = 0.0

    def update(self, gesture, current_time):
        if self.current_step > 0 and (current_time - self.last_step_time) > self.timeout:
            self.reset()

        target = self.sequence[self.current_step]
        if gesture == target:
            self.current_step += 1
            self.last_step_time = current_time
            if self.current_step >= len(self.sequence):
                self.reset()
                return True
            return False

        return False


def load_title_logo():
    """โหลดภาพโลโก้ไตเติลผ่าน ResourceHelper รองรับทั้งสภาพแวดล้อม Python และ .exe"""
    candidates = [
        get_resource_path("assets/images/title_logo.png"),
        get_resource_path("assets/images/title_logo.jpg"),
        get_resource_path("assets/title_logo.png"),
        get_resource_path("assets/title_logo.jpg"),
        get_resource_path("title_logo.png"),
        get_resource_path("title_logo.jpg"),
        os.path.join(get_base_dir(), "assets", "images", "title_logo.png"),
        os.path.join(get_base_dir(), "assets", "title_logo.png"),
    ]
    for path in candidates:
        if os.path.exists(path):
            img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
            if img is not None:
                return img
    return None


def draw_magic_title_graphic(frame, logo_img, center_x, top_y=55, target_width=800):
    """เรนเดอร์ภาพโลโก้ไตเติลเกมลงบนเฟรมพร้อมการจัดสเกลอัตราส่วนภาพ"""
    if logo_img is None:
        return False

    orig_h, orig_w = logo_img.shape[:2]
    aspect_ratio = orig_h / orig_w
    target_height = int(target_width * aspect_ratio)

    resized = cv2.resize(logo_img, (target_width, target_height), interpolation=cv2.INTER_AREA)

    x1 = center_x - target_width // 2
    y1 = top_y
    x2 = x1 + target_width
    y2 = y1 + target_height

    if x1 < 0 or y1 < 0 or x2 > frame.shape[1] or y2 > frame.shape[0]:
        return False

    roi = frame[y1:y2, x1:x2]

    if resized.shape[2] == 4:
        alpha = resized[:, :, 3].astype(np.float32) / 255.0
        alpha = np.expand_dims(alpha, axis=2)
        bgr = resized[:, :, :3].astype(np.float32)
        blended = (1.0 - alpha) * roi.astype(np.float32) + alpha * bgr
        frame[y1:y2, x1:x2] = np.clip(blended, 0, 255).astype(np.uint8)
    else:
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        alpha = np.clip(gray.astype(np.float32) / 190.0, 0.0, 1.0)
        alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
        alpha = np.expand_dims(alpha, axis=2)

        bgr = resized.astype(np.float32)
        blended = (1.0 - alpha) * roi.astype(np.float32) + alpha * bgr
        frame[y1:y2, x1:x2] = np.clip(blended, 0, 255).astype(np.uint8)

    return True


emoji_sprites_cache = {}

def get_emoji_sprite(emoji_char, size=46):
    """สร้างหรือดึงภาพสไปรต์อีโมจิจากแคชเพื่อใช้เป็นภาพแนะนำท่าทางบนหน้าจอ"""
    cache_key = (emoji_char, size)
    if cache_key in emoji_sprites_cache:
        return emoji_sprites_cache[cache_key]

    try:
        from PIL import Image, ImageDraw, ImageFont

        scratch_sz = int(size * 4)
        img = Image.new("RGBA", (scratch_sz, scratch_sz), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        font = None
        font_candidates = [
            "seguiemj.ttf",
            "C:\\Windows\\Fonts\\seguiemj.ttf",
            "Apple Color Emoji.ttf",
            "NotoColorEmoji.ttf",
            "segoeui.ttf",
            "arial.ttf"
        ]
        font_sz = int(size * 0.95)
        for fpath in font_candidates:
            try:
                font = ImageFont.truetype(fpath, font_sz)
                break
            except Exception:
                continue

        if font is not None:
            cx, cy = scratch_sz // 2, scratch_sz // 2
            try:
                draw.text((cx, cy), emoji_char, font=font, anchor="mm", embedded_color=True)
            except Exception:
                try:
                    draw.text((cx, cy), emoji_char, font=font, anchor="mm")
                except Exception:
                    draw.text((cx - size // 2, cy - size // 2), emoji_char, font=font, fill=(255, 220, 100, 255))

        bbox = img.getbbox()
        if bbox:
            cropped = img.crop(bbox)
            w_c, h_c = cropped.size
            scale = min(size / w_c, size / h_c)
            new_w = max(1, int(w_c * scale))
            new_h = max(1, int(h_c * scale))
            cropped = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)

            final_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            ox = (size - new_w) // 2
            oy = (size - new_h) // 2
            final_img.paste(cropped, (ox, oy))
            img = final_img
        else:
            img = img.resize((size, size))

        np_arr = np.array(img)
        bgr = cv2.cvtColor(np_arr[:, :, :3], cv2.COLOR_RGB2BGR)
        alpha = np_arr[:, :, 3]
        sprite = np.dstack([bgr, alpha])
        emoji_sprites_cache[cache_key] = sprite
        return sprite
    except Exception:
        return None


def overlay_sprite(frame, sprite, x, y):
    """วาดภาพสไปรต์แบบโปร่งแสง (Alpha Blending) ลงบนตำแหน่งที่กำหนด"""
    if sprite is None:
        return
    sh, sw = sprite.shape[:2]
    fh, fw = frame.shape[:2]

    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(fw, x + sw), min(fh, y + sh)
    if x1 >= x2 or y1 >= y2:
        return

    sx1 = x1 - x
    sy1 = y1 - y
    sx2 = sx1 + (x2 - x1)
    sy2 = sy1 + (y2 - y1)

    sub_sprite = sprite[sy1:sy2, sx1:sx2]
    alpha = (sub_sprite[:, :, 3].astype(np.float32) / 255.0)[:, :, np.newaxis]
    bgr = sub_sprite[:, :, :3].astype(np.float32)
    roi = frame[y1:y2, x1:x2].astype(np.float32)

    blended = roi * (1.0 - alpha) + bgr * alpha
    frame[y1:y2, x1:x2] = np.clip(blended, 0, 255).astype(np.uint8)


def draw_title_gesture_prompt(frame, center_x, base_y=518):
    """วาดกล่องคำแนะนำท่าทางเริ่มต้นเกมในหน้า Title Screen"""
    box_w = 78
    box_h = 60
    gap = 42
    emoji_sz = 44

    peace_sprite = get_emoji_sprite("✌️", size=emoji_sz)
    thumb_sprite = get_emoji_sprite("👍", size=emoji_sz)

    b1_cx = center_x - gap - box_w // 2
    b1_x1 = b1_cx - box_w // 2
    b1_y1 = base_y - box_h // 2
    cv2.rectangle(frame, (b1_x1, b1_y1), (b1_x1 + box_w, b1_y1 + box_h), (20, 24, 22), -1)
    cv2.rectangle(frame, (b1_x1, b1_y1), (b1_x1 + box_w, b1_y1 + box_h), (80, 255, 120), 2, cv2.LINE_AA)
    if peace_sprite is not None:
        overlay_sprite(frame, peace_sprite, b1_cx - emoji_sz // 2, base_y - emoji_sz // 2)

    or_txt = "OR"
    or_sz = cv2.getTextSize(or_txt, cv2.FONT_HERSHEY_DUPLEX, 0.65, 2)[0]
    cv2.putText(frame, or_txt, (center_x - or_sz[0] // 2 + 1, base_y + or_sz[1] // 2 + 1), cv2.FONT_HERSHEY_DUPLEX, 0.65, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(frame, or_txt, (center_x - or_sz[0] // 2, base_y + or_sz[1] // 2), cv2.FONT_HERSHEY_DUPLEX, 0.65, (0, 215, 255), 2, cv2.LINE_AA)

    b2_cx = center_x + gap + box_w // 2
    b2_x1 = b2_cx - box_w // 2
    b2_y1 = base_y - box_h // 2
    cv2.rectangle(frame, (b2_x1, b2_y1), (b2_x1 + box_w, b2_y1 + box_h), (20, 24, 22), -1)
    cv2.rectangle(frame, (b2_x1, b2_y1), (b2_x1 + box_w, b2_y1 + box_h), (80, 255, 120), 2, cv2.LINE_AA)
    if thumb_sprite is not None:
        overlay_sprite(frame, thumb_sprite, b2_cx - emoji_sz // 2, base_y - emoji_sz // 2)

    hint_main = "BOTH PLAYERS HOLD GESTURE TO START"
    hm_size = cv2.getTextSize(hint_main, cv2.FONT_HERSHEY_SIMPLEX, 0.68, 2)[0]
    cv2.putText(frame, hint_main, (center_x - hm_size[0] // 2 + 1, base_y + 55), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(frame, hint_main, (center_x - hm_size[0] // 2, base_y + 54), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (80, 255, 120), 2, cv2.LINE_AA)

    hint_key = "( press SPACE to Start | 'F' for Fullscreen )"
    hk_size = cv2.getTextSize(hint_key, cv2.FONT_HERSHEY_SIMPLEX, 0.50, 1)[0]
    cv2.putText(frame, hint_key, (center_x - hk_size[0] // 2, base_y + 82), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (180, 180, 180), 1, cv2.LINE_AA)


def draw_match_over_rematch_prompt(frame, center_x, base_y=428):
    """วาดกล่องคำแนะนำท่าทางขอแข่งใหม่ในหน้า Match Over"""
    emoji_sz = 34
    thumb_sprite = get_emoji_sprite("👍", size=emoji_sz)

    t_left = "BOTH PLAYERS HOLD"
    t_right = "TO REMATCH"

    s_left = cv2.getTextSize(t_left, cv2.FONT_HERSHEY_SIMPLEX, 0.70, 2)[0]
    s_right = cv2.getTextSize(t_right, cv2.FONT_HERSHEY_SIMPLEX, 0.70, 2)[0]

    badge_w = 58
    badge_h = 46
    gap = 14

    total_w = s_left[0] + gap + badge_w + gap + s_right[0]
    start_x = center_x - total_w // 2

    tx1 = start_x
    ty = base_y + s_left[1] // 2
    cv2.putText(frame, t_left, (tx1 + 1, ty + 1), cv2.FONT_HERSHEY_SIMPLEX, 0.70, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(frame, t_left, (tx1, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.70, (80, 255, 120), 2, cv2.LINE_AA)

    bx1 = tx1 + s_left[0] + gap
    by1 = base_y - badge_h // 2
    cv2.rectangle(frame, (bx1, by1), (bx1 + badge_w, by1 + badge_h), (20, 24, 22), -1)
    cv2.rectangle(frame, (bx1, by1), (bx1 + badge_w, by1 + badge_h), (80, 255, 120), 2, cv2.LINE_AA)

    if thumb_sprite is not None:
        sw = thumb_sprite.shape[1]
        sh = thumb_sprite.shape[0]
        pos_x = bx1 + (badge_w - sw) // 2
        pos_y = by1 + (badge_h - sh) // 2
        overlay_sprite(frame, thumb_sprite, pos_x, pos_y)

    tx2 = bx1 + badge_w + gap
    cv2.putText(frame, t_right, (tx2 + 1, ty + 1), cv2.FONT_HERSHEY_SIMPLEX, 0.70, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(frame, t_right, (tx2, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.70, (80, 255, 120), 2, cv2.LINE_AA)

    hint_k = "( press 'R' to Rematch | 'F' for Fullscreen )"
    sk = cv2.getTextSize(hint_k, cv2.FONT_HERSHEY_SIMPLEX, 0.50, 1)[0]
    cv2.putText(frame, hint_k, (center_x - sk[0] // 2, base_y + 44), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (180, 180, 180), 1, cv2.LINE_AA)


# ==============================================================================
# 2. ระบบติดตามลำตัว กระสุนเวทมนตร์ และการวาดเส้นกลางอากาศ
# ==============================================================================

class TorsoTracker:
    """ระบบคำนวณตำแหน่งและขอบเขตลำตัวผู้เล่น (Torso Hitbox) แบบลดการสั่นไหว (Smoothing)"""

    def __init__(self, is_p1):
        self.is_p1 = is_p1
        self.current_box = None
        self.last_seen_time = 0.0
        default_x = 200 if is_p1 else (cfg.FRAME_WIDTH - 200)
        self.smooth_center_x = float(default_x)
        self.smooth_chest_y = 360.0

    def update(self, detected_chest_pt, hand_wrist_y, dt):
        now = time.time()
        if detected_chest_pt is not None:
            raw_cx, raw_cy = detected_chest_pt
            self.smooth_center_x = 0.35 * raw_cx + 0.65 * self.smooth_center_x
            self.smooth_chest_y = 0.35 * raw_cy + 0.65 * self.smooth_chest_y
            self.last_seen_time = now
        else:
            if (now - self.last_seen_time) < 1.2:
                if hand_wrist_y is not None and hand_wrist_y > 420:
                    target_duck_y = min(530.0, self.smooth_chest_y + 20.0 * dt)
                    self.smooth_chest_y = 0.2 * target_duck_y + 0.8 * self.smooth_chest_y
            else:
                stand_y = 360.0
                self.smooth_chest_y = 0.05 * stand_y + 0.95 * self.smooth_chest_y

        cx = int(self.smooth_center_x)
        cy = int(self.smooth_chest_y)

        x1 = max(0, cx - cfg.TORSO_WIDTH // 2)
        x2 = min(cfg.FRAME_WIDTH, cx + cfg.TORSO_WIDTH // 2)
        y1 = max(0, cy - cfg.TORSO_HEIGHT // 2)
        y2 = min(cfg.FRAME_HEIGHT, cy + cfg.TORSO_HEIGHT // 2)

        self.current_box = (x1, y1, x2, y2)
        return self.current_box


class Projectile:
    """เอนทิตีกระสุนเวทมนตร์ ควบคุมเวกเตอร์ความเร็ว ทิศทาง และการปะทะ"""

    def __init__(self, spell_name, spell_cfg, start_pt, target_pt, owner_tag):
        self.spell_name = spell_name
        self.damage = spell_cfg["damage"]
        self.color = spell_cfg["color"]
        self.speed = spell_cfg["speed"]
        self.radius = spell_cfg["radius"]
        self.pierces_shield = spell_cfg["pierces_shield"]
        self.owner = owner_tag
        self.active = True
        self.hit_entities = set()

        if start_pt is None:
            start_pt = (200, 360) if owner_tag == "P1" else (cfg.FRAME_WIDTH - 200, 360)
        if target_pt is None:
            target_pt = (cfg.FRAME_WIDTH, start_pt[1]) if owner_tag == "P1" else (0, start_pt[1])

        self.x = float(start_pt[0])
        self.y = float(start_pt[1])
        self.trail_positions = []

        dx = float(target_pt[0] - start_pt[0])
        dy = float(target_pt[1] - start_pt[1])
        dist = math.hypot(dx, dy)
        if dist > 0:
            self.vx = (dx / dist) * self.speed
            self.vy = (dy / dist) * self.speed
        else:
            self.vx = self.speed if owner_tag == "P1" else -self.speed
            self.vy = 0.0

    def update(self, dt):
        self.trail_positions.append((int(self.x), int(self.y)))
        if len(self.trail_positions) > 10:
            self.trail_positions.pop(0)

        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.x < -180 or self.x > cfg.FRAME_WIDTH + 180 or self.y < -180 or self.y > cfg.FRAME_HEIGHT + 180:
            self.active = False


class AirDrawSession:
    """ระบบตรวจจับการวาดเส้นกลางอากาศของผู้เล่น พร้อมการกรองสัญญาณสั่นไหว"""

    def __init__(self):
        self.raw_points = []
        self.smoothed_pt = None
        self.prev_tip = None
        self.speed = 20.0
        self.is_drawing = False
        self.still_timer_start = None
        self.non_draw_timer_start = None
        self.alpha = 0.75
        self.can_start_new_draw = True

    def update(self, tip_px, gesture_key, dt, tag="P1", sound_engine=None):
        now = time.time()
        result_shape = None

        if gesture_key == "AIR_DRAW":
            if not self.can_start_new_draw:
                if sound_engine:
                    sound_engine.stop_draw_sound(tag)
                return None

            self.non_draw_timer_start = None
            self.is_drawing = True
            px, py = tip_px

            if self.smoothed_pt is None:
                self.smoothed_pt = (float(px), float(py))
                self.prev_tip = (float(px), float(py))
            else:
                sx = self.alpha * px + (1.0 - self.alpha) * self.smoothed_pt[0]
                sy = self.alpha * py + (1.0 - self.alpha) * self.smoothed_pt[1]
                self.smoothed_pt = (sx, sy)

            current_pt = (int(self.smoothed_pt[0]), int(self.smoothed_pt[1]))

            if self.prev_tip is not None:
                frame_dist = math.hypot(self.smoothed_pt[0] - self.prev_tip[0], self.smoothed_pt[1] - self.prev_tip[1])
            else:
                frame_dist = 10.0
            self.prev_tip = (self.smoothed_pt[0], self.smoothed_pt[1])

            self.speed = 0.4 * frame_dist + 0.6 * self.speed

            if len(self.raw_points) == 0:
                self.raw_points.append(current_pt)
            else:
                last_pt = self.raw_points[-1]
                dist_from_last = math.hypot(current_pt[0] - last_pt[0], current_pt[1] - last_pt[1])
                if dist_from_last >= 4.0:
                    self.raw_points.append(current_pt)

            if self.speed >= 3.0:
                self.still_timer_start = None
                if sound_engine:
                    sound_engine.start_draw_sound(tag)
            else:
                if sound_engine:
                    sound_engine.stop_draw_sound(tag)

                if self.still_timer_start is None:
                    self.still_timer_start = now
                elif (now - self.still_timer_start) >= max(0.55, cfg.STILL_TIMEOUT):
                    result_shape = self._finish()
        else:
            self.can_start_new_draw = True
            if sound_engine:
                sound_engine.stop_draw_sound(tag)

            if self.is_drawing:
                if gesture_key in ["OPEN_HAND", "RECHARGE", "PEACE", "FIST", "THREE_FINGERS", "THUMBS_UP", "OK_SIGN"]:
                    result_shape = self._finish()
                else:
                    if self.non_draw_timer_start is None:
                        self.non_draw_timer_start = now
                    elif (now - self.non_draw_timer_start) >= max(0.35, cfg.FLICKER_TOLERANCE):
                        result_shape = self._finish()

        return result_shape

    def _finish(self):
        pts = list(self.raw_points)
        self.raw_points = []
        self.smoothed_pt = None
        self.prev_tip = None
        self.speed = 20.0
        self.is_drawing = False
        self.still_timer_start = None
        self.non_draw_timer_start = None
        self.can_start_new_draw = False
        return pts if len(pts) >= 12 else None

    def reset(self, tag, sound_engine=None):
        self.raw_points.clear()
        self.smoothed_pt = None
        self.prev_tip = None
        self.speed = 20.0
        self.is_drawing = False
        self.still_timer_start = None
        self.non_draw_timer_start = None
        self.can_start_new_draw = True
        if sound_engine:
            sound_engine.stop_draw_sound(tag)


# ==============================================================================
# 3. ระบบสั่นหน้าจอ คิวเสียงพากย์ และ Arcade HUD
# ==============================================================================

shake_timer = 0.0
shake_intensity = 0.0

def trigger_screen_shake(intensity=14.0, duration=0.22):
    global shake_timer, shake_intensity
    shake_intensity = max(shake_intensity, intensity)
    shake_timer = max(shake_timer, duration)

def apply_screen_shake(frame, dt):
    global shake_timer, shake_intensity
    if shake_timer > 0.0:
        shake_timer -= dt
        current_strength = shake_intensity * (shake_timer / max(0.01, shake_timer + dt))
        offset_x = random.uniform(-current_strength, current_strength)
        offset_y = random.uniform(-current_strength, current_strength)

        M = np.float32([[1, 0, offset_x], [0, 1, offset_y]])
        shaken = cv2.warpAffine(frame, M, (cfg.FRAME_WIDTH, cfg.FRAME_HEIGHT), borderMode=cv2.BORDER_REPLICATE)
        return shaken
    return frame


announcer_queue = []

def schedule_announcer(key, delay=0.6, volume_scale=1.15):
    play_time = time.time() + delay
    announcer_queue.append((play_time, key, volume_scale))

def update_announcer_queue(sound_engine, current_time):
    for item in list(announcer_queue):
        play_time, key, volume_scale = item
        if current_time >= play_time:
            sound_engine.play_announcer(key, volume_scale=volume_scale)
            if item in announcer_queue:
                announcer_queue.remove(item)


def draw_diamond(frame, cx, cy, radius, is_active, active_color):
    pts_outer = np.array([
        [cx, cy - radius],
        [cx + radius, cy],
        [cx, cy + radius],
        [cx - radius, cy]
    ], np.int32)

    if is_active:
        pts_glow = np.array([
            [cx, cy - radius - 3],
            [cx + radius + 3, cy],
            [cx, cy + radius + 3],
            [cx - radius - 3, cy]
        ], np.int32)
        cv2.polylines(frame, [pts_glow], True, active_color, 2, cv2.LINE_AA)
        cv2.fillPoly(frame, [pts_outer], active_color)
        cv2.polylines(frame, [pts_outer], True, (255, 255, 255), 2, cv2.LINE_AA)

        in_r = max(2, radius - 5)
        pts_inner = np.array([
            [cx, cy - in_r],
            [cx + in_r, cy],
            [cx, cy + in_r],
            [cx - in_r, cy]
        ], np.int32)
        cv2.fillPoly(frame, [pts_inner], (255, 255, 255))
    else:
        cv2.fillPoly(frame, [pts_outer], (32, 32, 36))
        cv2.polylines(frame, [pts_outer], True, (80, 80, 85), 2, cv2.LINE_AA)


def draw_arcade_hud(frame, p1_state, p2_state, p1_wins, p2_wins, now):
    """เรนเดอร์แถบสถานะการต่อสู้ (Arcade HUD: HP, Mana, Round Wins) ของผู้เล่นทั้งสองฝั่ง"""
    w, h = cfg.FRAME_WIDTH, cfg.FRAME_HEIGHT

    # ฝั่ง PLAYER 1 (ซ้าย)
    p1_badge_x1, p1_badge_y1 = 20, 16
    p1_badge_x2, p1_badge_y2 = 85, 76
    cv2.rectangle(frame, (p1_badge_x1, p1_badge_y1), (p1_badge_x2, p1_badge_y2), (20, 20, 24), -1)
    cv2.rectangle(frame, (p1_badge_x1, p1_badge_y1), (p1_badge_x2, p1_badge_y2), cfg.COLOR_P1, 2, cv2.LINE_AA)
    cv2.rectangle(frame, (p1_badge_x1 + 3, p1_badge_y1 + 3), (p1_badge_x2 - 3, p1_badge_y2 - 3), (120, 120, 0), 1, cv2.LINE_AA)
    cv2.putText(frame, "P1", (p1_badge_x1 + 10, p1_badge_y1 + 42), cv2.FONT_HERSHEY_DUPLEX, 1.25, cfg.COLOR_P1, 3, cv2.LINE_AA)

    hp1_x, hp1_y, hp1_w, hp1_h = 95, 18, 330, 26
    cv2.rectangle(frame, (hp1_x, hp1_y), (hp1_x + hp1_w, hp1_y + hp1_h), (25, 25, 25), -1)
    fill_hp1 = int(hp1_w * max(0.0, min(1.0, p1_state.hp / 100.0)))
    hp1_color = (0, 220, 80) if p1_state.hp > 45 else ((0, 180, 255) if p1_state.hp > 25 else (30, 30, 230))
    if fill_hp1 > 0:
        cv2.rectangle(frame, (hp1_x, hp1_y), (hp1_x + fill_hp1, hp1_y + hp1_h), hp1_color, -1)
    cv2.rectangle(frame, (hp1_x, hp1_y), (hp1_x + hp1_w, hp1_y + hp1_h), (70, 70, 70), 2, cv2.LINE_AA)

    hp1_txt = f"{int(p1_state.hp)} / 100 HP"
    cv2.putText(frame, hp1_txt, (hp1_x + 10, hp1_y + 19), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(frame, hp1_txt, (hp1_x + 10, hp1_y + 19), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 2, cv2.LINE_AA)

    mp1_x, mp1_y, mp1_w, mp1_h = 95, 48, 290, 16
    cv2.rectangle(frame, (mp1_x, mp1_y), (mp1_x + mp1_w, hp1_y + 46), (20, 20, 20), -1)
    fill_mp1 = int(mp1_w * max(0.0, min(1.0, p1_state.mana / 100.0)))
    if fill_mp1 > 0:
        cv2.rectangle(frame, (mp1_x, mp1_y), (mp1_x + fill_mp1, mp1_y + mp1_h), (240, 160, 0), -1)
    cv2.rectangle(frame, (mp1_x, mp1_y), (mp1_x + mp1_w, hp1_y + 46), (60, 60, 60), 1, cv2.LINE_AA)

    mp1_txt = f"MANA {int(p1_state.mana)}"
    cv2.putText(frame, mp1_txt, (mp1_x + 8, mp1_y + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 2, cv2.LINE_AA)
    cv2.putText(frame, mp1_txt, (mp1_x + 8, mp1_y + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)

    pod1_x, pod1_y, pod1_w, pod1_h = 95, 70, 150, 28
    cv2.rectangle(frame, (pod1_x, pod1_y), (pod1_x + pod1_w, pod1_y + pod1_h), (18, 18, 22), -1)
    cv2.rectangle(frame, (pod1_x, pod1_y), (pod1_x + pod1_w, pod1_y + pod1_h), (255, 255, 0), 1, cv2.LINE_AA)
    cv2.putText(frame, "WINS", (pod1_x + 8, pod1_y + 19), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)

    for r in range(2):
        gx = pod1_x + 75 + r * 38
        gy = pod1_y + 14
        draw_diamond(frame, gx, gy, radius=9, is_active=(r < p1_wins), active_color=(0, 215, 255))

    # ฝั่ง PLAYER 2 (ขวา)
    p2_badge_x1, p2_badge_y1 = w - 85, 16
    p2_badge_x2, p2_badge_y2 = w - 20, 76
    cv2.rectangle(frame, (p2_badge_x1, p2_badge_y1), (p2_badge_x2, p2_badge_y2), (24, 20, 20), -1)
    cv2.rectangle(frame, (p2_badge_x1, p2_badge_y1), (p2_badge_x2, p2_badge_y2), (0, 140, 255), 2, cv2.LINE_AA)
    cv2.rectangle(frame, (p2_badge_x1 + 3, p2_badge_y1 + 3), (p2_badge_x2 - 3, p2_badge_y2 - 3), (0, 60, 140), 1, cv2.LINE_AA)
    cv2.putText(frame, "P2", (p2_badge_x1 + 10, p2_badge_y1 + 42), cv2.FONT_HERSHEY_DUPLEX, 1.25, (0, 140, 255), 3, cv2.LINE_AA)

    hp2_w, hp2_h = 330, 26
    hp2_x, hp2_y = w - 95 - hp2_w, 18
    cv2.rectangle(frame, (hp2_x, hp2_y), (hp2_x + hp2_w, hp2_y + hp2_h), (25, 25, 25), -1)
    fill_hp2 = int(hp2_w * max(0.0, min(1.0, p2_state.hp / 100.0)))
    hp2_color = (0, 220, 80) if p2_state.hp > 45 else ((0, 180, 255) if p2_state.hp > 25 else (30, 30, 230))
    if fill_hp2 > 0:
        cv2.rectangle(frame, (hp2_x + (hp2_w - fill_hp2), hp2_y), (hp2_x + hp2_w, hp2_y + hp2_h), hp2_color, -1)
    cv2.rectangle(frame, (hp2_x, hp2_y), (hp2_x + hp2_w, hp2_y + hp2_h), (70, 70, 70), 2, cv2.LINE_AA)

    hp2_txt = f"{int(p2_state.hp)} / 100 HP"
    cv2.putText(frame, hp2_txt, (hp2_x + hp2_w - 145, hp2_y + 19), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(frame, hp2_txt, (hp2_x + hp2_w - 145, hp2_y + 19), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 2, cv2.LINE_AA)

    mp2_w, mp2_h = 290, 16
    mp2_x, mp2_y = w - 95 - mp2_w, 48
    cv2.rectangle(frame, (mp2_x, mp2_y), (mp2_x + mp2_w, hp2_y + 46), (20, 20, 20), -1)
    fill_mp2 = int(mp2_w * max(0.0, min(1.0, p2_state.mana / 100.0)))
    if fill_mp2 > 0:
        cv2.rectangle(frame, (mp2_x + (mp2_w - fill_mp2), mp2_y), (mp2_x + mp2_w, hp2_y + 46), (240, 160, 0), -1)
    cv2.rectangle(frame, (mp2_x, mp2_y), (mp2_x + mp2_w, hp2_y + 46), (60, 60, 60), 1, cv2.LINE_AA)

    mp2_txt = f"MANA {int(p2_state.mana)}"
    cv2.putText(frame, mp2_txt, (mp2_x + 10, mp2_y + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 2, cv2.LINE_AA)
    cv2.putText(frame, mp2_txt, (mp2_x + 10, mp2_y + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)

    pod2_w, pod2_h = 150, 28
    pod2_x = w - 95 - pod2_w
    pod2_y = 70
    cv2.rectangle(frame, (pod2_x, pod2_y), (pod2_x + pod2_w, pod2_y + pod2_h), (18, 18, 22), -1)
    cv2.rectangle(frame, (pod2_x, pod2_y), (pod2_x + pod2_w, pod2_y + pod2_h), (0, 140, 255), 1, cv2.LINE_AA)
    cv2.putText(frame, "WINS", (pod2_x + pod2_w - 48, pod2_y + 19), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)

    for r in range(2):
        gx = pod2_x + 30 + r * 38
        gy = pod2_y + 14
        draw_diamond(frame, gx, gy, radius=9, is_active=(r < p2_wins), active_color=(0, 140, 255))


# ==============================================================================
# 4. การกำหนดค่ากล้อง โมเดล AI และตัวแปรระบบ
# ==============================================================================

cap = cv2.VideoCapture(cfg.CAMERA_INDEX, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.FRAME_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.FRAME_HEIGHT)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

WINDOW_NAME = "Magic Spell Duel - Arcade Arena"
cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
is_fullscreen = True

# ระบบประมวลผล MediaPipe
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=cfg.MAX_NUM_HANDS,
    min_detection_confidence=cfg.HAND_MIN_DETECTION_CONF,
    min_tracking_confidence=cfg.HAND_MIN_TRACKING_CONF
)
mp_face = mp.solutions.face_detection.FaceDetection(
    model_selection=1, 
    min_detection_confidence=cfg.FACE_MIN_DETECTION_CONF
)

# โมดูลระบบย่อย
gesture_engine = GestureRecognizer()
unistroke_engine = UnistrokeRecognizer()
ui_engine = UIRenderer(cfg.FRAME_WIDTH, cfg.FRAME_HEIGHT)
sound_engine = SoundManager(master_volume=0.9)

p1_chant_tracker = ChantSequenceTracker(timeout=4.0)
p2_chant_tracker = ChantSequenceTracker(timeout=4.0)

title_logo_img = load_title_logo()
sound_engine.play_bgm(track="title", loop=True, volume_scale=0.45)

p1_state = PlayerCombatState(is_p1=True)
p2_state = PlayerCombatState(is_p1=False)

p1_draw = AirDrawSession()
p2_draw = AirDrawSession()

p1_torso_tracker = TorsoTracker(is_p1=True)
p2_torso_tracker = TorsoTracker(is_p1=False)

projectiles = []
damage_popups = []

p1_round_wins = 0
p2_round_wins = 0
current_round = 1

match_state = "TITLE"  # สถานะ: TITLE, COUNTDOWN, BATTLE, ROUND_OVER, MATCH_OVER
title_ready_hold_duration = 0.0

p1_last_title_ready_time = 0.0
p2_last_title_ready_time = 0.0
p1_last_rematch_ready_time = 0.0
p2_last_rematch_ready_time = 0.0

countdown_timer = cfg.COUNTDOWN_DURATION
last_beep_second = -1
announcer_round_called = False

round_over_timer = 0.0
round_winner_text = ""
match_winner_text = ""

rematch_hold_duration = 0.0

p1_recharge_hold_timer = 0.0
p2_recharge_hold_timer = 0.0

ko_slowmo_timer = 0.0
ko_flash_alpha = 0.0

# ตัวแปรจัดการ Throttling และตรวจวัดประสิทธิภาพ
frame_counter = 0
cached_face_results = None

prev_time = time.time()
fps = 0.0


def start_new_round(reset_match=False):
    """รีเซ็ตสถานะตัวละคร อนุภาค และระบบเสียงเพื่อเริ่มรอบการแข่งขันใหม่"""
    global current_round, p1_round_wins, p2_round_wins, match_state, countdown_timer, last_beep_second
    global round_over_timer, round_winner_text, match_winner_text, rematch_hold_duration
    global ko_slowmo_timer, ko_flash_alpha, shake_timer, shake_intensity, announcer_round_called
    global p1_last_title_ready_time, p2_last_title_ready_time, p1_last_rematch_ready_time, p2_last_rematch_ready_time
    global p1_recharge_hold_timer, p2_recharge_hold_timer, frame_counter, cached_face_results

    announcer_queue.clear()

    if reset_match:
        p1_round_wins = 0
        p2_round_wins = 0
        current_round = 1
        sound_engine.play_bgm(track="battle", loop=True, volume_scale=0.45)

    p1_state.hp = 100.0
    p1_state.mana = 100.0
    p1_state.state = "IDLE"
    p1_state.pending_spell = None
    p1_state.charging_spell = None
    p1_state.charge_timer = 0.0
    p1_state.cast_origin = None
    p1_state.cast_target = None
    p1_state.shield_active = False
    p1_state.shield_timer = 0.0
    p1_state.is_recharging = False
    p1_state.cooldowns.clear()
    p1_state.recognized_start_time = None
    p1_state.cast_history.clear()
    p1_state.hollow_purple_unlocked = False
    p1_state.infinity_barrier_active = False

    p2_state.hp = 100.0
    p2_state.mana = 100.0
    p2_state.state = "IDLE"
    p2_state.pending_spell = None
    p2_state.charging_spell = None
    p2_state.charge_timer = 0.0
    p2_state.cast_origin = None
    p2_state.cast_target = None
    p2_state.shield_active = False
    p2_state.shield_timer = 0.0
    p2_state.is_recharging = False
    p2_state.cooldowns.clear()
    p2_state.recognized_start_time = None
    p2_state.cast_history.clear()
    p2_state.hollow_purple_unlocked = False
    p2_state.infinity_barrier_active = False

    p1_chant_tracker.reset()
    p2_chant_tracker.reset()

    p1_draw.reset("P1", sound_engine)
    p2_draw.reset("P2", sound_engine)

    projectiles.clear()
    damage_popups.clear()
    ui_engine.particles.clear()
    ui_engine.ember_sparks.clear()
    ui_engine.inward_embers.clear()
    ui_engine.rock_shards.clear()
    ui_engine.rising_hearts.clear()
    ui_engine.electric_particles.clear()
    ui_engine.smoke_puffs.clear()
    ui_engine.sprite_bursts.clear()
    ui_engine.mana_particles.clear()
    ui_engine.shockwaves.clear()
    ui_engine.awakened_banners.clear()

    sound_engine.stop_charge_sound("P1")
    sound_engine.stop_charge_sound("P2")
    sound_engine.set_shield_loop_sound("P1", False)
    sound_engine.set_shield_loop_sound("P2", False)
    sound_engine.set_recharge_sound("P1", False)
    sound_engine.set_recharge_sound("P2", False)

    match_state = "COUNTDOWN"
    countdown_timer = cfg.COUNTDOWN_DURATION
    last_beep_second = -1
    announcer_round_called = False
    rematch_hold_duration = 0.0
    p1_last_title_ready_time = 0.0
    p2_last_title_ready_time = 0.0
    p1_last_rematch_ready_time = 0.0
    p2_last_rematch_ready_time = 0.0
    p1_recharge_hold_timer = 0.0
    p2_recharge_hold_timer = 0.0
    ko_slowmo_timer = 0.0
    ko_flash_alpha = 0.0
    shake_timer = 0.0
    shake_intensity = 0.0
    frame_counter = 0
    cached_face_results = None


# ==============================================================================
# 5. ลูปการทำงานหลักของเกม (Main Application Loop)
# ==============================================================================

print("[System] Magic Spell Duel - Engine Initialized Successfully")

while cap.isOpened():
    success, frame = cap.read()
    if not success:
        continue

    now = time.time()
    raw_dt = now - prev_time
    prev_time = now
    if raw_dt > 0:
        fps = 0.9 * fps + 0.1 * (1.0 / raw_dt)

    # จัดการสโลว์โมชันเมื่อเกิดการ K.O.
    if ko_slowmo_timer > 0.0:
        ko_slowmo_timer -= raw_dt
        effective_dt = raw_dt * cfg.KO_SLOWMO_TIMESCALE
    else:
        effective_dt = raw_dt

    dt = effective_dt
    update_announcer_queue(sound_engine, now)

    h, w, _ = frame.shape
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # AI Downscale: ย่อภาพเหลือ 640x360 เฉพาะตอนส่งให้ AI เพื่อเพิ่ม FPS บนฮาร์ดแวร์สเปกต่ำ
    ai_frame = cv2.resize(rgb_frame, (640, 360), interpolation=cv2.INTER_LINEAR)
    hand_results = hands.process(ai_frame)

    # Face Throttling: ประมวลผลใบหน้าทุกๆ 3 เฟรมเพื่อลดภาระ CPU
    frame_counter += 1
    if frame_counter % 3 == 0 or cached_face_results is None:
        cached_face_results = mp_face.process(ai_frame)
    face_results = cached_face_results

    center_x = w // 2

    if match_state != "TITLE":
        cv2.line(frame, (center_x, 0), (center_x, h), cfg.COLOR_DIVIDER, 1)

    if match_state == "BATTLE":
        p1_state.update(dt)
        p2_state.update(dt)

    if not p1_state.is_recharging and not p2_state.is_recharging:
        ui_engine.mana_particles.clear()

    ui_engine.update_vfx(dt)

    # ตรวจจับและแยกแยะมือระหว่าง P1 (ซ้าย) และ P2 (ขวา)
    p1_cands = []
    p2_cands = []
    if hand_results.multi_hand_landmarks:
        for hl in hand_results.multi_hand_landmarks:
            if hl.landmark[mp_hands.HandLandmark.WRIST].x < 0.5:
                p1_cands.append(hl)
            else:
                p2_cands.append(hl)

    active_hands = {}
    if p1_cands:
        active_hands["P1"] = max(p1_cands, key=lambda hl: hl.landmark[mp_hands.HandLandmark.WRIST].x)
    if p2_cands:
        active_hands["P2"] = min(p2_cands, key=lambda hl: hl.landmark[mp_hands.HandLandmark.WRIST].x)

    if "P1" not in active_hands:
        sound_engine.stop_charge_sound("P1")
        sound_engine.stop_draw_sound("P1")
        sound_engine.set_recharge_sound("P1", False)
        p1_state.is_recharging = False
        p1_recharge_hold_timer = 0.0
    if "P2" not in active_hands:
        sound_engine.stop_charge_sound("P2")
        sound_engine.stop_draw_sound("P2")
        sound_engine.set_recharge_sound("P2", False)
        p2_state.is_recharging = False
        p2_recharge_hold_timer = 0.0

    # ตรวจจับใบหน้าและอัปเดตกล่องลำตัว (Torso Box)
    p1_best_face = None
    p2_best_face = None
    max_p1_area = 0.0
    max_p2_area = 0.0

    if face_results and face_results.detections:
        for detection in face_results.detections:
            bbox = detection.location_data.relative_bounding_box
            area = bbox.width * bbox.height
            face_cx = int((bbox.xmin + bbox.width / 2.0) * w)
            face_cy = int((bbox.ymin + bbox.height / 2.0) * h)

            if face_cx < center_x:
                if area > max_p1_area:
                    max_p1_area = area
                    p1_best_face = (face_cx, face_cy + cfg.CHEST_OFFSET_Y)
            else:
                if area > max_p2_area:
                    max_p2_area = area
                    p2_best_face = (face_cx, face_cy + cfg.CHEST_OFFSET_Y)

    p1_wrist_y = active_hands["P1"].landmark[mp_hands.HandLandmark.WRIST].y * h if "P1" in active_hands else None
    p2_wrist_y = active_hands["P2"].landmark[mp_hands.HandLandmark.WRIST].y * h if "P2" in active_hands else None

    p1_torso_box = p1_torso_tracker.update(p1_best_face, p1_wrist_y, dt)
    p2_torso_box = p2_torso_tracker.update(p2_best_face, p2_wrist_y, dt)

    if match_state != "TITLE":
        ui_engine.draw_soul_core(frame, p1_torso_box, p1_state.shield_active, now)
        ui_engine.draw_soul_core(frame, p2_torso_box, p2_state.shield_active, now)

    # ตรรกะการร่ายคาถา ท่าทางมือ และการเล็งเป้า
    p1_state.infinity_barrier_active = False
    p2_state.infinity_barrier_active = False

    players = [
        ("P1", p1_state, p1_draw, cfg.COLOR_P1, True, p1_torso_box, p1_chant_tracker),
        ("P2", p2_state, p2_draw, cfg.COLOR_P2, False, p2_torso_box, p2_chant_tracker)
    ]

    p1_hand_center = None
    p2_hand_center = None

    for tag, p_state, p_draw, theme_color, is_p1, torso_box, chant_tracker in players:
        if tag in active_hands:
            hl = active_hands[tag]
            fingers = gesture_engine.get_finger_status(hl)
            g_key, g_name = gesture_engine.classify_gesture(fingers, hand_landmarks=hl)

            mcp_lm = hl.landmark[mp_hands.HandLandmark.MIDDLE_FINGER_MCP]
            hand_center_px = (int(mcp_lm.x * w), int(mcp_lm.y * h))
            tip_lm = hl.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
            tip_px = (int(tip_lm.x * w), int(tip_lm.y * h))
            wrist_lm = hl.landmark[mp_hands.HandLandmark.WRIST]
            wrist_px = (int(wrist_lm.x * w), int(wrist_lm.y * h))

            if is_p1:
                p1_hand_center = hand_center_px
                if g_key in ["THUMBS_UP", "PEACE"]:
                    p1_last_title_ready_time = now
                if g_key == "THUMBS_UP":
                    p1_last_rematch_ready_time = now
            else:
                p2_hand_center = hand_center_px
                if g_key in ["THUMBS_UP", "PEACE"]:
                    p2_last_title_ready_time = now
                if g_key == "THUMBS_UP":
                    p2_last_rematch_ready_time = now

            if match_state == "BATTLE":
                # บาเรีย Infinity ป้องกันการโจมตี
                if p_state.hollow_purple_unlocked and p_state.state != "CHARGING":
                    is_two_up = (fingers[1] and fingers[2] and not fingers[3] and not fingers[4])
                    if is_two_up:
                        mid_tip_lm = hl.landmark[mp_hands.HandLandmark.MIDDLE_FINGER_TIP]
                        tip_dist = math.hypot(tip_lm.x - mid_tip_lm.x, tip_lm.y - mid_tip_lm.y)
                        palm_size = math.hypot(mcp_lm.x - wrist_lm.x, mcp_lm.y - wrist_lm.y)
                        rel_dist = tip_dist / max(0.001, palm_size)

                        if rel_dist < 0.20:
                            p_state.infinity_barrier_active = True
                            ui_engine.draw_infinity_barrier(frame, torso_box, now)

                # ตรวจสอบคอมโบท่าร่ายเพื่อปลดล็อกสกิลขั้นสูง
                if not p_state.hollow_purple_unlocked:
                    all_cast = p_state.has_cast_all_basic_spells()
                    hp_low = (p_state.hp < 50.0)
                    mana_ready = (p_state.mana >= 40.0)

                    if all_cast and hp_low and mana_ready:
                        chant_completed = chant_tracker.update(g_key, now)
                        if chant_completed:
                            p_state.hollow_purple_unlocked = True
                            sound_engine.play_sfx("chant_awakened", volume_scale=1.3)
                            trigger_screen_shake(intensity=14.0, duration=0.30)
                            awk_cx = wrist_px[0]
                            awk_cy = max(110, wrist_px[1] - 110)
                            ui_engine.spawn_awakened_banner(awk_cx, awk_cy, text="★ AWAKENED! (∞)", is_dual=False, duration=3.0)

                # การฟื้นฟูมานาแบบชาร์จพลัง
                is_recharge_gesture = (g_key == "RECHARGE")
                can_recharge = (
                    p_state.state == "IDLE" and 
                    not p_state.shield_active and 
                    not getattr(p_state, 'infinity_barrier_active', False)
                )

                if is_p1:
                    if can_recharge and is_recharge_gesture:
                        p1_recharge_hold_timer += dt
                        p_state.is_recharging = (p1_recharge_hold_timer >= 0.20)
                    else:
                        p1_recharge_hold_timer = 0.0
                        p_state.is_recharging = False
                else:
                    if can_recharge and is_recharge_gesture:
                        p2_recharge_hold_timer += dt
                        p_state.is_recharging = (p2_recharge_hold_timer >= 0.20)
                    else:
                        p2_recharge_hold_timer = 0.0
                        p_state.is_recharging = False

                sound_engine.set_recharge_sound(tag, p_state.is_recharging)

                if p_state.is_recharging:
                    ui_engine.spawn_mana_recharge_fx(hand_center_px[0], hand_center_px[1], count=3)
                    ui_engine.draw_mana_recharge(frame, hand_center_px[0], hand_center_px[1], now)

                # อัปเดตการวาดเส้นและการจำแนกสัญลักษณ์
                if p_state.state in ["IDLE", "RECOGNIZED"] and not p_state.infinity_barrier_active:
                    drawn_stroke = p_draw.update(tip_px, g_key, dt, tag=tag, sound_engine=sound_engine)

                    if p_state.state == "RECOGNIZED" and len(p_draw.raw_points) >= 3:
                        p_state.state = "IDLE"
                        p_state.pending_spell = None
                        p_state.recognized_start_time = None

                    if drawn_stroke:
                        shape, spell, score = unistroke_engine.recognize(drawn_stroke)
                        if spell != "None" and score >= 0.65:
                            success, reason = p_state.on_shape_recognized(spell, current_time=now)
                            if success:
                                sound_engine.play_sfx("spell_ready", volume_scale=0.9)
                                p_state.recognized_start_time = now
                            else:
                                sound_engine.play_sfx("no_mana", volume_scale=0.8)
                                if reason.startswith("COOLDOWN"):
                                    cd_val = reason.split(":")[1]
                                    damage_popups.append((f"COOLDOWN! ({cd_val}s)", wrist_px[0] - 60, wrist_px[1] - 80, (0, 0, 255), now + 1.2))
                                elif reason == "NO_MANA":
                                    damage_popups.append(("NO MANA!", wrist_px[0] - 40, wrist_px[1] - 80, (0, 165, 255), now + 1.2))
                        elif shape == "Uncertain" or (spell != "None" and score < 0.65):
                            damage_popups.append(("Uncertain", wrist_px[0], wrist_px[1] - 80, (0, 165, 255), now + 1.0))
                else:
                    sound_engine.stop_draw_sound(tag)

                start_ray, end_ray = gesture_engine.calculate_aiming_ray(hl, w, h, is_player_1=is_p1)

                if p_state.state == "CHARGING":
                    if hasattr(p_state, 'update_aim'):
                        p_state.update_aim(start_ray, end_ray)
                    else:
                        p_state.cast_origin = start_ray
                        p_state.cast_target = end_ray

                    charge_cfg = SpellConfig.SPELLS.get(p_state.charging_spell, {})
                    if charge_cfg.get("damage", 0) > 0:
                        ray_color = charge_cfg["color"]
                        cv2.line(frame, start_ray, end_ray, ray_color, 4, cv2.LINE_AA)
                        cv2.circle(frame, start_ray, 5, (255, 255, 255), -1)
                        cv2.circle(frame, end_ray, 8, ray_color, -1)

                prev_status = p_state.state
                triggered, status = p_state.try_trigger_spell(g_key, start_ray, end_ray)
                if triggered and prev_status != "CHARGING":
                    sound_engine.stop_draw_sound(tag)
                    sound_engine.start_charge_sound(tag, p_state.charging_spell)
                elif not triggered and status in ["COOLDOWN", "NO_MANA"]:
                    sound_engine.play_sfx("no_mana", volume_scale=0.8)
                    warn_txt = "COOLDOWN!" if status == "COOLDOWN" else "NO MANA!"
                    damage_popups.append((warn_txt, wrist_px[0] - 40, wrist_px[1] - 80, (0, 0, 255), now + 1.0))
                    p_state.state = "IDLE"
                    p_state.pending_spell = None
                    p_state.recognized_start_time = None

                # ยกเลิกการร่ายเมื่อเอามือลงหรือกำหมัด
                if p_state.state == "RECOGNIZED":
                    if not hasattr(p_state, 'recognized_start_time') or p_state.recognized_start_time is None:
                        p_state.recognized_start_time = now

                    elapsed = now - p_state.recognized_start_time
                    hand_dropped = (wrist_px[1] > (h * 0.90))
                    is_fist_cancel = (g_key == "FIST" and p_state.pending_spell != "Magic Shield" and elapsed > 0.65)

                    if hand_dropped or is_fist_cancel or elapsed >= cfg.SPELL_CALLOUT_DURATION:
                        p_state.state = "IDLE"
                        p_state.pending_spell = None
                        p_state.recognized_start_time = None
                        damage_popups.append(("CANCELLED", wrist_px[0] - 40, wrist_px[1] - 80, (160, 160, 160), now + 0.8))
                    else:
                        cd_until = p_state.cooldowns.get(p_state.pending_spell, 0.0)
                        rem_cd = max(0.0, cd_until - now)
                        ui_engine.draw_spell_ready_callout(frame, p_state.pending_spell, wrist_px, is_p1, now, rem_cd=rem_cd)
            else:
                p_draw.reset(tag, sound_engine)

        # การแสดงผลโล่ป้องกัน
        sound_engine.set_shield_loop_sound(tag, p_state.shield_active and match_state == "BATTLE")

        hand_c = p1_hand_center if is_p1 else p2_hand_center
        if hand_c is None:
            tx1, ty1, tx2, ty2 = torso_box
            hand_c = ((tx1 + tx2) // 2, (ty1 + ty2) // 2)

        if p_state.shield_active and match_state == "BATTLE":
            ui_engine.draw_magic_shield(frame, hand_c[0], hand_c[1], now, radius=cfg.SHIELD_RADIUS, rem_duration=p_state.shield_timer)

        # แอนิเมชันและการปล่อยสกิลเมื่อชาร์จเสร็จ
        if p_state.state == "CHARGING" and match_state == "BATTLE":
            ratio, remaining = p_state.get_charging_progress()
            ox, oy = p_state.cast_origin if p_state.cast_origin is not None else (center_x // 2, h // 2)
            spell_name = p_state.charging_spell

            sound_engine.ensure_charge_sound(tag, spell_name)

            if spell_name == "Fireball":
                ui_engine.draw_fireball_charging(frame, ox, oy, ratio, remaining, now)
            elif spell_name == "Magic Shield":
                ui_engine.draw_shield_charging(frame, ox, oy, ratio, remaining, now)
            elif spell_name == "Lightning Strike":
                ui_engine.draw_lightning_charging(frame, ox, oy, ratio, remaining, now)
            elif spell_name == "Terra Boulder":
                ui_engine.draw_terra_charging(frame, ox, oy, ratio, remaining, now)
            elif spell_name == "Healing Light":
                ui_engine.draw_healing_charging(frame, ox, oy, ratio, remaining, now)
            elif spell_name == "Hollow Purple":
                ui_engine.draw_hollow_purple_charging(frame, ox, oy, ratio, remaining, now)
            else:
                ui_engine.draw_generic_charging(frame, spell_name, ox, oy, ratio, remaining, now)

            if ratio >= 1.0:
                sound_engine.stop_charge_sound(tag)
                sound_engine.play_sfx(f"cast_{spell_name}", volume_scale=1.4)

                opp_torso = p2_torso_box if is_p1 else p1_torso_box
                default_target = ((opp_torso[0] + opp_torso[2]) // 2, (opp_torso[1] + opp_torso[3]) // 2)

                spawn_origin = p_state.cast_origin if p_state.cast_origin is not None else (ox, oy)
                spawn_target = getattr(p_state, 'cast_target', None)
                if spawn_target is None:
                    spawn_target = getattr(p_state, 'aim_target', None)
                if spawn_target is None:
                    spawn_target = default_target

                spell_name, s_cfg = p_state.finish_cast()
                if s_cfg["damage"] > 0:
                    proj = Projectile(spell_name, s_cfg, spawn_origin, spawn_target, tag)
                    projectiles.append(proj)
                elif spell_name == "Healing Light":
                    tx1, ty1, tx2, ty2 = torso_box
                    torso_cx = (tx1 + tx2) // 2
                    torso_cy = (ty1 + ty2) // 2

                    p_state.hp = min(100.0, p_state.hp + 25.0)
                    damage_popups.append(("+25 HP", torso_cx - 40, torso_cy - 60, (50, 255, 50), now + 1.6))
                    ui_engine.spawn_healing_fx(ox, oy, torso_cx, torso_cy)

                elif spell_name == "Magic Shield":
                    damage_popups.append(("SHIELD ON!", ox, oy - 30, (255, 220, 0), now + 1.5))
                    ui_engine.spawn_impact_fx(ox, oy, (255, 220, 0), count=20)
                    sound_engine.set_shield_loop_sound(tag, True)

        # การวาดเส้นแสงตามรอยนิ้วมือ
        pts = p_draw.raw_points
        if len(pts) > 1 and match_state == "BATTLE":
            is_confirming = (p_draw.still_timer_start is not None) and ((now - p_draw.still_timer_start) >= cfg.CONFIRM_HOLD_DELAY)
            trail_outer_color = (0, 215, 255) if is_confirming else theme_color
            trail_inner_color = (255, 255, 255)

            for i in range(1, len(pts)):
                cv2.line(frame, pts[i - 1], pts[i], trail_outer_color, 6, cv2.LINE_AA)
                cv2.line(frame, pts[i - 1], pts[i], trail_inner_color, 2, cv2.LINE_AA)

            tip_x, tip_y = pts[-1]
            if is_confirming:
                confirm_duration = max(0.001, cfg.STILL_TIMEOUT - cfg.CONFIRM_HOLD_DELAY)
                progress = min(1.0, (now - p_draw.still_timer_start - cfg.CONFIRM_HOLD_DELAY) / confirm_duration)
                ring_angle = int(360 * progress)
                cv2.ellipse(frame, (tip_x, tip_y), (18, 18), 0, -90, -90 + ring_angle, (0, 215, 255), 3, cv2.LINE_AA)
                cv2.circle(frame, (tip_x, tip_y), 5, (255, 255, 255), -1)
            else:
                cv2.circle(frame, (tip_x, tip_y), 7, (255, 255, 255), -1)
                cv2.circle(frame, (tip_x, tip_y), 11, theme_color, 2)

        if match_state != "TITLE":
            ui_engine.draw_spell_icons(frame, p_state, is_p1, now)

    # ฟิสิกส์การเคลื่อนที่ของกระสุนและการตรวจสอบการชน (Hit Detection)
    for proj in list(projectiles):
        if not proj.active:
            projectiles.remove(proj)
            continue

        proj.update(dt)

        if proj.spell_name == "Fireball":
            ui_engine.draw_fireball_projectile(frame, proj.x, proj.y, proj.vx, proj.vy, size=240)
        elif proj.spell_name == "Lightning Strike":
            ui_engine.draw_lightning_projectile(frame, proj.x, proj.y, proj.vx, proj.vy, size=260)
        elif proj.spell_name == "Terra Boulder":
            ui_engine.draw_terra_projectile(frame, proj.x, proj.y, proj.vx, proj.vy, now, size=125)
        elif proj.spell_name == "Hollow Purple":
            ui_engine.draw_hollow_purple_projectile(frame, proj.x, proj.y, proj.vx, proj.vy, now, size=180)
        else:
            for idx, (tx, ty) in enumerate(proj.trail_positions):
                fade_alpha = (idx + 1) / len(proj.trail_positions)
                trail_r = max(2, int(proj.radius * fade_alpha * 0.7))
                cv2.circle(frame, (tx, ty), trail_r, proj.color, -1, cv2.LINE_AA)

            if np.random.rand() > 0.4:
                ui_engine.spawn_trail_particle(int(proj.x), int(proj.y), proj.color)

            px, py = int(proj.x), int(proj.y)
            cv2.circle(frame, (px, py), proj.radius + 4, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(frame, (px, py), proj.radius, proj.color, -1, cv2.LINE_AA)

        px, py = int(proj.x), int(proj.y)

        if proj.owner == "P1":
            def_tag = "P2"
            def_state = p2_state
            def_torso = p2_torso_box
            def_hand = p2_hand_center if p2_hand_center else ((def_torso[0] + def_torso[2]) // 2, (def_torso[1] + def_torso[3]) // 2)
            popup_side = -50
        else:
            def_tag = "P1"
            def_state = p1_state
            def_torso = p1_torso_box
            def_hand = p1_hand_center if p1_hand_center else ((def_torso[0] + def_torso[2]) // 2, (def_torso[1] + def_torso[3]) // 2)
            popup_side = 50

        is_def_infinity = (
            (def_state.state == "CHARGING" and def_state.charging_spell == "Hollow Purple") or
            getattr(def_state, 'infinity_barrier_active', False)
        )

        # การปะทะกับโล่ป้องกัน (Shield Collision)
        hit_shield = False
        if def_state.shield_active:
            dist_to_shield = math.hypot(px - def_hand[0], py - def_hand[1])
            if dist_to_shield <= (cfg.SHIELD_RADIUS + proj.radius):
                hit_shield = True
                
                if is_def_infinity and proj.spell_name != "Hollow Purple":
                    proj.active = False
                    damage_popups.append(("INFINITY!", px + popup_side, py, (255, 220, 255), now + 1.2))
                    sound_engine.play_sfx("shield_block", volume_scale=1.0)
                    ui_engine.spawn_impact_fx(px, py, (240, 80, 230), count=16)
                    continue

                if proj.spell_name != "Hollow Purple":
                    proj.active = False

                if proj.pierces_shield:
                    if def_tag not in proj.hit_entities:
                        proj.hit_entities.add(def_tag)
                        def_state.shield_active = False
                        def_state.shield_timer = 0.0
                        sound_engine.set_shield_loop_sound(def_tag, False)

                        if proj.spell_name != "Hollow Purple":
                            trigger_screen_shake(intensity=cfg.SHAKE_SHIELD_BREAK_INTENSITY, duration=cfg.SHAKE_SHIELD_BREAK_DURATION)
                            sound_engine.play_sfx("shield_broken", volume_scale=1.2)
                            ui_engine.spawn_shield_broken_fx(def_hand[0], def_hand[1])

                        prev_hp = def_state.hp
                        def_state.hp = max(0.0, def_state.hp - proj.damage)
                        dmg_txt = "OBLITERATED! -999" if proj.damage >= 999 else f"SHIELD BROKEN! -{int(proj.damage)}"
                        damage_popups.append((dmg_txt, px + popup_side, py, (220, 20, 220) if proj.damage >= 999 else (0, 0, 255), now + 1.8))

                        if proj.spell_name == "Terra Boulder":
                            ui_engine.spawn_terra_impact(px, py, pierced_shield=True)

                        if prev_hp > 0.0 and def_state.hp <= 0.0:
                            ko_slowmo_timer = cfg.KO_SLOWMO_DURATION
                            ko_flash_alpha = cfg.KO_FLASH_ALPHA
                            trigger_screen_shake(intensity=cfg.SHAKE_KO_INTENSITY + 10.0, duration=cfg.SHAKE_KO_DURATION)
                else:
                    trigger_screen_shake(intensity=cfg.SHAKE_SHIELD_BLOCK_INTENSITY, duration=cfg.SHAKE_SHIELD_BLOCK_DURATION)
                    sound_engine.play_sfx("shield_block", volume_scale=1.0)
                    damage_popups.append(("BLOCKED!", px + popup_side, py, (255, 220, 0), now + 1.5))
                    ui_engine.spawn_shield_block_fx(px, py)
                    if proj.spell_name == "Fireball":
                        ui_engine.spawn_fireball_impact(px, py)
                    elif proj.spell_name == "Lightning Strike":
                        ui_engine.spawn_lightning_impact(px, py)

        # การปะทะกับลำตัวผู้เล่น (Body Collision)
        if (not hit_shield or proj.spell_name == "Hollow Purple") and proj.active:
            tx1, ty1, tx2, ty2 = def_torso
            closest_x = max(tx1, min(px, tx2))
            closest_y = max(ty1, min(py, ty2))
            dist_to_torso = math.hypot(px - closest_x, py - closest_y)

            if dist_to_torso <= (proj.radius + 20):
                if is_def_infinity and proj.spell_name != "Hollow Purple":
                    proj.active = False
                    damage_popups.append(("INFINITY!", px + popup_side, py, (255, 220, 255), now + 1.2))
                    sound_engine.play_sfx("shield_block", volume_scale=1.0)
                    ui_engine.spawn_impact_fx(px, py, (240, 80, 230), count=18)
                    continue

                if def_tag not in proj.hit_entities:
                    proj.hit_entities.add(def_tag)
                    
                    if proj.spell_name != "Hollow Purple":
                        proj.active = False

                    prev_hp = def_state.hp
                    def_state.hp = max(0.0, def_state.hp - proj.damage)

                    if proj.spell_name != "Hollow Purple":
                        sound_engine.play_sfx(f"hit_{proj.spell_name}", volume_scale=1.2)
                        if proj.spell_name == "Lightning Strike":
                            trigger_screen_shake(intensity=cfg.SHAKE_LIGHTNING_INTENSITY, duration=cfg.SHAKE_LIGHTNING_DURATION)
                        elif proj.spell_name == "Terra Boulder":
                            trigger_screen_shake(intensity=cfg.SHAKE_TERRA_INTENSITY, duration=cfg.SHAKE_TERRA_DURATION)
                        elif proj.spell_name == "Fireball":
                            trigger_screen_shake(intensity=cfg.SHAKE_FIREBALL_INTENSITY, duration=cfg.SHAKE_FIREBALL_DURATION)

                    hit_txt = "-999 K.O.!" if proj.damage >= 999 else f"-{int(proj.damage)}"
                    hit_col = (230, 20, 220) if proj.damage >= 999 else (0, 0, 255)
                    damage_popups.append((hit_txt, px + popup_side, py, hit_col, now + 1.8))

                    if proj.spell_name == "Fireball":
                        ui_engine.spawn_fireball_impact(px, py)
                    elif proj.spell_name == "Lightning Strike":
                        ui_engine.spawn_lightning_impact(px, py)
                    elif proj.spell_name == "Terra Boulder":
                        ui_engine.spawn_terra_impact(px, py, pierced_shield=False)
                    elif proj.spell_name != "Hollow Purple":
                        ui_engine.spawn_impact_fx(px, py, proj.color, count=28)

                    is_match_point = False
                    if proj.owner == "P1" and (p1_round_wins + 1) >= cfg.MAX_ROUND_WINS:
                        is_match_point = True
                    elif proj.owner == "P2" and (p2_round_wins + 1) >= cfg.MAX_ROUND_WINS:
                        is_match_point = True

                    if prev_hp > 0.0 and def_state.hp <= 0.0:
                        ko_slowmo_timer = cfg.KO_SLOWMO_DURATION
                        ko_flash_alpha = cfg.KO_FLASH_ALPHA
                        trigger_screen_shake(intensity=cfg.SHAKE_KO_INTENSITY, duration=cfg.SHAKE_KO_DURATION)
                        if not is_match_point:
                            schedule_announcer("announcer_ko", delay=cfg.ANNOUNCER_KO_DELAY)

    if match_state != "TITLE":
        ui_engine.draw_vfx(frame)
        draw_arcade_hud(frame, p1_state, p2_state, p1_round_wins, p2_round_wins, now)

    for pop in list(damage_popups):
        txt, px, py, p_color, expire = pop
        if now < expire:
            cv2.putText(frame, txt, (px, py), cv2.FONT_HERSHEY_SIMPLEX, 0.75, p_color, 2, cv2.LINE_AA)
        else:
            damage_popups.remove(pop)

    # ตรวจสอบการตัดสินผลแพ้ชนะในแต่ละรอบ
    if match_state == "BATTLE":
        if p1_state.hp <= 0 or p2_state.hp <= 0:
            if p1_state.hp <= 0:
                p2_round_wins += 1
                round_winner_text = "PLAYER 2 WINS THE ROUND!"
            else:
                p1_round_wins += 1
                round_winner_text = "PLAYER 1 WINS THE ROUND!"

            sound_engine.stop_charge_sound("P1")
            sound_engine.stop_charge_sound("P2")
            sound_engine.stop_draw_sound("P1")
            sound_engine.stop_draw_sound("P2")
            sound_engine.set_shield_loop_sound("P1", False)
            sound_engine.set_shield_loop_sound("P2", False)

            if p1_round_wins >= cfg.MAX_ROUND_WINS:
                match_state = "MATCH_OVER"
                match_winner_text = "PLAYER 1 IS THE CHAMPION!"
                sound_engine.play_bgm(track="victory", loop=True, volume_scale=0.55)
                announcer_queue[:] = [item for item in announcer_queue if item[1] != "announcer_ko"]
                schedule_announcer("announcer_p1_win", delay=cfg.ANNOUNCER_WIN_DELAY)
            elif p2_round_wins >= cfg.MAX_ROUND_WINS:
                match_state = "MATCH_OVER"
                match_winner_text = "PLAYER 2 IS THE CHAMPION!"
                sound_engine.play_bgm(track="victory", loop=True, volume_scale=0.55)
                announcer_queue[:] = [item for item in announcer_queue if item[1] != "announcer_ko"]
                schedule_announcer("announcer_p2_win", delay=cfg.ANNOUNCER_WIN_DELAY)
            else:
                match_state = "ROUND_OVER"
                round_over_timer = cfg.ROUND_OVER_DELAY
                sound_engine.play_sfx("spell_ready", volume_scale=1.0)

    # การเรนเดอร์ตามสเตทแมชชีน (State Machine Rendering)
    if match_state == "TITLE":
        title_overlay = frame.copy()
        cv2.rectangle(title_overlay, (0, 0), (w, h), (8, 8, 14), -1)
        cv2.addWeighted(title_overlay, 0.45, frame, 0.55, 0, frame)

        rendered_logo = draw_magic_title_graphic(frame, title_logo_img, center_x, top_y=55, target_width=800)

        if not rendered_logo:
            t1 = "MAGIC SPELL DUEL"
            s1 = cv2.getTextSize(t1, cv2.FONT_HERSHEY_DUPLEX, 2.2, 5)[0]
            cv2.putText(frame, t1, (center_x - s1[0] // 2 + 4, 254), cv2.FONT_HERSHEY_DUPLEX, 2.2, (0, 0, 0), 10, cv2.LINE_AA)
            cv2.putText(frame, t1, (center_x - s1[0] // 2, 250), cv2.FONT_HERSHEY_DUPLEX, 2.2, (0, 230, 255), 4, cv2.LINE_AA)

            t2 = "ARCADE MOTION BATTLE"
            s2 = cv2.getTextSize(t2, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)[0]
            line_len = 120
            cv2.line(frame, (center_x - s2[0] // 2 - line_len - 15, 315), (center_x - s2[0] // 2 - 15, 315), (0, 215, 255), 2, cv2.LINE_AA)
            cv2.line(frame, (center_x + s2[0] // 2 + 15, 315), (center_x + s2[0] // 2 + line_len + 15, 315), (0, 215, 255), 2, cv2.LINE_AA)
            cv2.putText(frame, t2, (center_x - s2[0] // 2, 322), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (230, 230, 230), 2, cv2.LINE_AA)

        draw_title_gesture_prompt(frame, center_x, base_y=518)

        p1_title_active = (now - p1_last_title_ready_time) < 0.35
        p2_title_active = (now - p2_last_title_ready_time) < 0.35

        if p1_title_active and p1_hand_center is not None:
            cv2.circle(frame, p1_hand_center, 24, (255, 255, 0), 3, cv2.LINE_AA)
            cv2.putText(frame, "P1 READY", (p1_hand_center[0] - 44, p1_hand_center[1] - 34),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.60, (255, 255, 0), 2, cv2.LINE_AA)

        if p2_title_active and p2_hand_center is not None:
            cv2.circle(frame, p2_hand_center, 24, (0, 140, 255), 3, cv2.LINE_AA)
            cv2.putText(frame, "P2 READY", (p2_hand_center[0] - 44, p2_hand_center[1] - 34),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 140, 255), 2, cv2.LINE_AA)

        both_ready_now = (p1_title_active and p2_title_active)
        if both_ready_now:
            title_ready_hold_duration += raw_dt
        else:
            title_ready_hold_duration = max(0.0, title_ready_hold_duration - raw_dt * 1.5)

        prog = min(1.0, title_ready_hold_duration / cfg.TITLE_READY_TARGET)
        ring_angle = int(360 * prog)

        if title_ready_hold_duration > 0.0:
            if p1_hand_center is not None:
                cv2.ellipse(frame, p1_hand_center, (35, 35), 0, -90, -90 + ring_angle, (0, 255, 0), 5, cv2.LINE_AA)
                cv2.putText(frame, f"{int(prog * 100)}%", (p1_hand_center[0] - 22, p1_hand_center[1] + 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

            if p2_hand_center is not None:
                cv2.ellipse(frame, p2_hand_center, (35, 35), 0, -90, -90 + ring_angle, (0, 255, 0), 5, cv2.LINE_AA)
                cv2.putText(frame, f"{int(prog * 100)}%", (p2_hand_center[0] - 22, p2_hand_center[1] + 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

        if title_ready_hold_duration >= cfg.TITLE_READY_TARGET:
            sound_engine.play_sfx("spell_ready", volume_scale=1.0)
            start_new_round(reset_match=True)

    elif match_state == "COUNTDOWN":
        countdown_timer -= dt
        display_txt = ""
        txt_color = (0, 255, 255)
        txt_scale = 2.5

        if countdown_timer > 2.6:
            display_txt = f"ROUND {current_round}" if current_round <= 2 else "FINAL ROUND!"
            txt_scale = 1.8
            txt_color = (255, 255, 255)

            if not announcer_round_called:
                announcer_round_called = True
                if current_round == 1:
                    schedule_announcer("announcer_round1", delay=cfg.ANNOUNCER_ROUND_DELAY)
                elif current_round == 2:
                    schedule_announcer("announcer_round2", delay=cfg.ANNOUNCER_ROUND_DELAY)
                else:
                    schedule_announcer("announcer_round_final", delay=cfg.ANNOUNCER_ROUND_DELAY)

        elif countdown_timer > 1.8:
            display_txt = "3"
            if last_beep_second != 3:
                sound_engine.play_sfx("spell_ready", volume_scale=0.85)
                last_beep_second = 3
        elif countdown_timer > 1.0:
            display_txt = "2"
            if last_beep_second != 2:
                sound_engine.play_sfx("spell_ready", volume_scale=0.9)
                last_beep_second = 2
        elif countdown_timer > 0.2:
            display_txt = "1"
            if last_beep_second != 1:
                sound_engine.play_sfx("spell_ready", volume_scale=0.95)
                last_beep_second = 1
        else:
            display_txt = "DUEL!"
            txt_color = (0, 140, 255)
            txt_scale = 3.2
            if last_beep_second != 0:
                last_beep_second = 0
                schedule_announcer("announcer_duel", delay=cfg.ANNOUNCER_DUEL_DELAY)
                sound_engine.play_sfx("cast_Fireball", volume_scale=1.0)

        if countdown_timer <= -0.4:
            match_state = "BATTLE"

        t_size = cv2.getTextSize(display_txt, cv2.FONT_HERSHEY_DUPLEX, txt_scale, 5)[0]
        tx = center_x - t_size[0] // 2
        ty = (h // 2) + t_size[1] // 2 - 20
        cv2.putText(frame, display_txt, (tx + 3, ty + 3), cv2.FONT_HERSHEY_DUPLEX, txt_scale, (0, 0, 0), 8, cv2.LINE_AA)
        cv2.putText(frame, display_txt, (tx, ty), cv2.FONT_HERSHEY_DUPLEX, txt_scale, txt_color, 4, cv2.LINE_AA)

    elif match_state == "ROUND_OVER":
        round_over_timer -= dt
        overlay = frame.copy()
        cv2.rectangle(overlay, (center_x - 360, 290), (center_x + 360, 410), (15, 15, 15), -1)
        cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

        cv2.rectangle(frame, (center_x - 360, 290), (center_x + 360, 410), (0, 215, 255), 3)
        t_size = cv2.getTextSize(round_winner_text, cv2.FONT_HERSHEY_SIMPLEX, 1.05, 3)[0]
        cv2.putText(frame, round_winner_text, (center_x - t_size[0] // 2, 360), cv2.FONT_HERSHEY_SIMPLEX, 1.05, (0, 255, 255), 3, cv2.LINE_AA)

        if round_over_timer <= 0:
            current_round += 1
            start_new_round(reset_match=False)

    elif match_state == "MATCH_OVER":
        box_x1, box_y1 = center_x - 440, 190
        box_x2, box_y2 = center_x + 440, 500

        glass_overlay = frame.copy()
        cv2.rectangle(glass_overlay, (box_x1, box_y1), (box_x2, box_y2), (10, 10, 15), -1)
        cv2.addWeighted(glass_overlay, 0.58, frame, 0.42, 0, frame)

        cv2.rectangle(frame, (box_x1, box_y1), (box_x2, box_y2), (0, 215, 255), 3, cv2.LINE_AA)
        cv2.rectangle(frame, (box_x1 + 4, box_y1 + 4), (box_x2 - 4, box_y2 - 4), (255, 255, 255), 1, cv2.LINE_AA)

        t_size = cv2.getTextSize(match_winner_text, cv2.FONT_HERSHEY_DUPLEX, 1.25, 3)[0]
        cv2.putText(frame, match_winner_text, (center_x - t_size[0] // 2 + 2, 282), cv2.FONT_HERSHEY_DUPLEX, 1.25, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(frame, match_winner_text, (center_x - t_size[0] // 2, 280), cv2.FONT_HERSHEY_DUPLEX, 1.25, (0, 255, 255), 3, cv2.LINE_AA)

        score_text = f"FINAL SCORE:  {p1_round_wins}  -  {p2_round_wins}"
        st_size = cv2.getTextSize(score_text, cv2.FONT_HERSHEY_SIMPLEX, 0.95, 2)[0]
        cv2.putText(frame, score_text, (center_x - st_size[0] // 2 + 1, 341), cv2.FONT_HERSHEY_SIMPLEX, 0.95, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, score_text, (center_x - st_size[0] // 2, 340), cv2.FONT_HERSHEY_SIMPLEX, 0.95, (230, 230, 230), 2, cv2.LINE_AA)

        draw_match_over_rematch_prompt(frame, center_x, base_y=428)

        p1_rematch_active = (now - p1_last_rematch_ready_time) < 0.35
        p2_rematch_active = (now - p2_last_rematch_ready_time) < 0.35

        if p1_rematch_active and p1_hand_center is not None:
            cv2.circle(frame, p1_hand_center, 24, (255, 255, 0), 3, cv2.LINE_AA)
            cv2.putText(frame, "P1 READY", (p1_hand_center[0] - 44, p1_hand_center[1] - 34),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.60, (255, 255, 0), 2, cv2.LINE_AA)

        if p2_rematch_active and p2_hand_center is not None:
            cv2.circle(frame, p2_hand_center, 24, (0, 140, 255), 3, cv2.LINE_AA)
            cv2.putText(frame, "P2 READY", (p2_hand_center[0] - 44, p2_hand_center[1] - 34),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 140, 255), 2, cv2.LINE_AA)

        both_rematch_now = (p1_rematch_active and p2_rematch_active)
        if both_rematch_now:
            rematch_hold_duration += raw_dt
        else:
            rematch_hold_duration = max(0.0, rematch_hold_duration - raw_dt * 1.5)

        r_prog = min(1.0, rematch_hold_duration / cfg.REMATCH_HOLD_TARGET)
        r_ring_angle = int(360 * r_prog)

        if rematch_hold_duration > 0.0:
            if p1_hand_center is not None:
                cv2.ellipse(frame, p1_hand_center, (35, 35), 0, -90, -90 + r_ring_angle, (0, 255, 0), 5, cv2.LINE_AA)
                cv2.putText(frame, f"{int(r_prog * 100)}%", (p1_hand_center[0] - 22, p1_hand_center[1] + 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

            if p2_hand_center is not None:
                cv2.ellipse(frame, p2_hand_center, (35, 35), 0, -90, -90 + r_ring_angle, (0, 255, 0), 5, cv2.LINE_AA)
                cv2.putText(frame, f"{int(r_prog * 100)}%", (p2_hand_center[0] - 22, p2_hand_center[1] + 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

        if rematch_hold_duration >= cfg.REMATCH_HOLD_TARGET:
            sound_engine.play_sfx("spell_ready", volume_scale=1.0)
            start_new_round(reset_match=True)

    if ko_flash_alpha > 0.0:
        white_screen = np.full_like(frame, 255)
        cv2.addWeighted(white_screen, ko_flash_alpha, frame, 1.0 - ko_flash_alpha, 0, frame)
        ko_flash_alpha = max(0.0, ko_flash_alpha - raw_dt * 2.5)

    frame = apply_screen_shake(frame, raw_dt)

    cv2.putText(frame, f"FPS: {fps:.1f}", (center_x - 38, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

    cv2.imshow(WINDOW_NAME, frame)

    # การจัดการปุ่มคีย์ลัด
    key = cv2.waitKey(1) & 0xFF
    if key in [ord('q'), 27]:
        break
    elif key in [ord('f'), ord('F')]:
        is_fullscreen = not is_fullscreen
        if is_fullscreen:
            cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        else:
            cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(WINDOW_NAME, cfg.FRAME_WIDTH, cfg.FRAME_HEIGHT)
    elif key in [ord(' '), 13] and match_state == "TITLE":
        sound_engine.play_sfx("spell_ready", volume_scale=1.0)
        start_new_round(reset_match=True)
    elif key == ord('r'):
        start_new_round(reset_match=True)
    elif key in [ord('a'), ord('A')] and match_state == "BATTLE":
        p1_state.hollow_purple_unlocked = True
        p2_state.hollow_purple_unlocked = True
        p1_state.mana = 100.0
        p2_state.mana = 100.0
        sound_engine.play_sfx("chant_awakened", volume_scale=1.3)
        trigger_screen_shake(intensity=14.0, duration=0.25)
        ui_engine.spawn_awakened_banner(center_x, h // 2 - 35, text="★ DEV: BOTH AWAKENED! (∞)", is_dual=True, duration=3.0)

# คืนทรัพยากรเมื่อปิดโปรแกรม
cap.release()
cv2.destroyAllWindows()
hands.close()
mp_face.close()