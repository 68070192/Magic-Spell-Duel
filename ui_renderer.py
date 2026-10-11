"""
Module: ui_renderer.py
Description: ระบบประมวลผลการแสดงผลกราฟิก (Graphic & VFX Renderer) และส่วนติดต่อผู้ใช้ (HUD)
             ควบคุมระบบอนุภาค (Particle Systems), การเบลนด์สไปรต์แสงเวทมนตร์ (Additive Blending),
             แอนิเมชันชาร์จคาถา และสถานะการต่อสู้บนหน้าจอแบบเรียลไทม์
"""

import os
import time
import math
import random
import cv2
import numpy as np
from spell_system import SpellConfig
from resource_helper import get_resource_path, get_base_dir

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# ==============================================================================
# 1. ระบบอนุภาคและเอฟเฟกต์ย่อย (Particle & Secondary VFX Classes)
# ==============================================================================

class Particle:
    """อนุภาคประกายเวทมนตร์พื้นฐาน กระจายตัวรอบทิศทางแบบสุ่ม"""

    def __init__(self, x, y, color, speed_range=(80, 260), life_range=(0.25, 0.55), radius_range=(2, 5)):
        self.x = float(x)
        self.y = float(y)
        self.color = color
        angle = np.random.uniform(0, 2 * math.pi)
        speed = np.random.uniform(speed_range[0], speed_range[1])
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.life = np.random.uniform(life_range[0], life_range[1])
        self.max_life = self.life
        self.radius = np.random.randint(radius_range[0], radius_range[1])

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt

    def draw(self, frame):
        if self.life > 0:
            alpha = max(0.0, self.life / self.max_life)
            r = max(1, int(self.radius * alpha))
            cv2.circle(frame, (int(self.x), int(self.y)), r, self.color, -1, cv2.LINE_AA)


class EmberSpark:
    """สะเก็ดไฟลอยขึ้นด้านบนสำหรับเวทมนตร์ลูกไฟ (Fireball)"""

    def __init__(self, x, y):
        self.x = float(x + np.random.uniform(-10, 10))
        self.y = float(y + np.random.uniform(-10, 10))
        angle = np.random.uniform(0, 2 * math.pi)
        speed = np.random.uniform(50, 150)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed - np.random.uniform(30, 80)
        self.life = np.random.uniform(0.20, 0.40)
        self.max_life = self.life
        self.color = (0, 215, 255) if np.random.rand() > 0.3 else (60, 255, 255)

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt

    def draw(self, frame):
        if self.life > 0:
            r = max(1, int(3 * (self.life / self.max_life)))
            cv2.circle(frame, (int(self.x), int(self.y)), r, self.color, -1, cv2.LINE_AA)


class InwardEmber:
    """สะเก็ดพลังงานที่หมุนวนและถูกดูดเข้าสู่จุดศูนย์กลางระหว่างชาร์จเวท"""

    def __init__(self, cx, cy):
        self.cx = float(cx)
        self.cy = float(cy)
        self.angle = np.random.uniform(0, 2 * math.pi)
        self.dist = np.random.uniform(40, 85)
        self.speed = np.random.uniform(160, 280)
        self.rot_speed = np.random.uniform(4.0, 8.0)
        self.life = self.dist / self.speed
        self.max_life = self.life
        self.color = (0, 200, 255) if np.random.rand() > 0.3 else (0, 120, 255)

    def update(self, dt):
        self.dist -= self.speed * dt
        self.angle += self.rot_speed * dt
        self.life -= dt

    def draw(self, frame):
        if self.life > 0 and self.dist > 5:
            alpha = max(0.0, self.life / self.max_life)
            r = max(1, int(3 * alpha))
            px = int(self.cx + self.dist * math.cos(self.angle))
            py = int(self.cy + self.dist * math.sin(self.angle))
            cv2.circle(frame, (px, py), r, self.color, -1, cv2.LINE_AA)


class RockShard:
    """เศษหินรูปทรงหลายเหลี่ยมหมุนตามแรงโน้มถ่วงสำหรับเวทดิน (Terra Boulder)"""

    def __init__(self, x, y, dir_x, dir_y):
        self.x = float(x + np.random.uniform(-8, 8))
        self.y = float(y + np.random.uniform(-8, 8))
        drift_speed = np.random.uniform(80, 220)
        spread_angle = np.random.uniform(-0.7, 0.7)
        back_vx = -dir_x * drift_speed
        back_vy = -dir_y * drift_speed
        cs, sn = math.cos(spread_angle), math.sin(spread_angle)
        self.vx = back_vx * cs - back_vy * sn
        self.vy = back_vx * sn + back_vy * cs + np.random.uniform(30, 90)

        self.angle = np.random.uniform(0, 360)
        self.rot_speed = np.random.uniform(-400, 400)
        self.life = np.random.uniform(0.22, 0.42)
        self.max_life = self.life
        self.radius = np.random.randint(5, 10)

        self.offsets = []
        for a in [0.4, 1.9, 3.5, 5.1]:
            r = self.radius * np.random.uniform(0.65, 1.3)
            self.offsets.append((r * math.cos(a), r * math.sin(a)))

        shade = np.random.randint(40, 75)
        self.color = (shade - 10, shade, shade + 15)
        self.edge_color = (20, 140, 225) if np.random.rand() > 0.65 else (30, 35, 40)

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 260 * dt
        self.angle += self.rot_speed * dt
        self.life -= dt

    def draw(self, frame):
        if self.life > 0:
            rad = math.radians(self.angle)
            cs, sn = math.cos(rad), math.sin(rad)
            pts = []
            for ox, oy in self.offsets:
                rx = ox * cs - oy * sn
                ry = ox * sn + oy * cs
                pts.append([int(self.x + rx), int(self.y + ry)])
            pts = np.array(pts, np.int32)
            cv2.fillConvexPoly(frame, pts, self.color, cv2.LINE_AA)
            if self.radius > 6:
                cv2.polylines(frame, [pts], True, self.edge_color, 1, cv2.LINE_AA)


class ElectricArcParticle:
    """ประกายกระแสไฟฟ้าแลบแบบสุ่มสำหรับเวทสายฟ้า (Lightning Strike)"""

    def __init__(self, x, y):
        self.x = float(x + np.random.uniform(-15, 15))
        self.y = float(y + np.random.uniform(-15, 15))
        angle = np.random.uniform(0, 2 * math.pi)
        speed = np.random.uniform(120, 320)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.life = np.random.uniform(0.10, 0.25)
        self.max_life = self.life
        self.color = (255, 255, 120) if np.random.rand() > 0.5 else (0, 240, 255)

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt

    def draw(self, frame):
        if self.life > 0:
            r = max(1, int(3 * (self.life / self.max_life)))
            cv2.circle(frame, (int(self.x), int(self.y)), r, self.color, -1, cv2.LINE_AA)


class RisingHeart:
    """หัวใจลอยขึ้นพร้อมการแกว่งแบบฮาร์โมนิกสำหรับเวทรักษา (Healing Light)"""

    def __init__(self, img_bgra, x, y):
        self.img = img_bgra
        self.x = float(x + np.random.uniform(-35, 35))
        self.y = float(y + np.random.uniform(-20, 20))
        self.start_x = self.x
        self.vy = np.random.uniform(-75, -120)
        self.duration = np.random.uniform(0.8, 1.2)
        self.timer = 0.0
        self.wobble_freq = np.random.uniform(4.0, 7.0)
        self.size = np.random.randint(32, 48)

    def update(self, dt):
        self.timer += dt
        self.y += self.vy * dt
        self.x = self.start_x + math.sin(self.timer * self.wobble_freq) * 18.0

    def draw(self, frame, w_limit=None, h_limit=None):
        progress = self.timer / self.duration
        if progress < 1.0 and self.img is not None:
            fh, fw = frame.shape[:2]
            max_w = w_limit if w_limit is not None else fw
            max_h = h_limit if h_limit is not None else fh

            cur_size = int(self.size * (1.0 - progress * 0.2))
            x1 = int(self.x) - cur_size // 2
            y1 = int(self.y) - cur_size // 2
            x2 = x1 + cur_size
            y2 = y1 + cur_size

            dx1 = max(0, x1)
            dy1 = max(0, y1)
            dx2 = min(max_w, x2)
            dy2 = min(max_h, y2)

            if dx2 > dx1 and dy2 > dy1:
                resized = cv2.resize(self.img, (cur_size, cur_size), interpolation=cv2.INTER_LINEAR)
                cx1 = dx1 - x1
                cy1 = dy1 - y1
                cx2 = cx1 + (dx2 - dx1)
                cy2 = cy1 + (dy2 - dy1)

                cropped = resized[cy1:cy2, cx1:cx2]
                roi = frame[dy1:dy2, dx1:dx2]

                bgr = cropped[:, :, :3]
                alpha = cropped[:, :, 3]
                fade = math.sin(progress * math.pi)
                alpha_3ch = cv2.merge([alpha, alpha, alpha])
                weighted = cv2.multiply(bgr, alpha_3ch, scale=(fade * 1.4) / 255.0, dtype=cv2.CV_8U)
                cv2.add(roi, weighted, dst=roi)


class SmokePuff:
    """กลุ่มควันกระจายตัวแบบจางหาย (Alpha Fade)"""

    def __init__(self, img_bgra, x, y, size=65, duration=0.45):
        self.img = img_bgra
        self.x = float(x + np.random.uniform(-8, 8))
        self.y = float(y + np.random.uniform(-8, 8))
        self.base_size = size
        self.duration = duration
        self.timer = 0.0
        self.vx = np.random.uniform(-15, 15)
        self.vy = np.random.uniform(-30, -10)

    def update(self, dt):
        self.timer += dt
        self.x += self.vx * dt
        self.y += self.vy * dt

    def draw(self, frame, w_limit=None, h_limit=None):
        progress = self.timer / self.duration
        if progress < 1.0 and self.img is not None:
            fh, fw = frame.shape[:2]
            max_w = w_limit if w_limit is not None else fw
            max_h = h_limit if h_limit is not None else fh

            cur_size = int(self.base_size * (1.0 + 0.8 * progress))
            x1 = int(self.x) - cur_size // 2
            y1 = int(self.y) - cur_size // 2
            x2 = x1 + cur_size
            y2 = y1 + cur_size

            dx1 = max(0, x1)
            dy1 = max(0, y1)
            dx2 = min(max_w, x2)
            dy2 = min(max_h, y2)

            if dx2 > dx1 and dy2 > dy1:
                resized = cv2.resize(self.img, (cur_size, cur_size), interpolation=cv2.INTER_LINEAR)
                cx1 = dx1 - x1
                cy1 = dy1 - y1
                cx2 = cx1 + (dx2 - dx1)
                cy2 = cy1 + (dy2 - dy1)

                cropped = resized[cy1:cy2, cx1:cx2]
                roi = frame[dy1:dy2, dx1:dx2]

                bgr = cropped[:, :, :3]
                alpha = cropped[:, :, 3]
                fade = max(0.0, (1.0 - progress) * 0.7)
                alpha_3ch = cv2.merge([alpha, alpha, alpha])
                fg = cv2.multiply(bgr, alpha_3ch, scale=fade / 255.0, dtype=cv2.CV_8U)
                bg = cv2.multiply(roi, cv2.bitwise_not(alpha_3ch), scale=1.0 / 255.0, dtype=cv2.CV_8U)
                cv2.add(fg, bg, dst=roi)


class SpriteBurst:
    """เอฟเฟกต์การระเบิดขยายขนาดอย่างรวดเร็ว (Impact Flash)"""

    def __init__(self, img_bgra, x, y, start_size=120, end_size=280, duration=0.40):
        self.img = img_bgra
        self.x = int(x)
        self.y = int(y)
        self.start_size = start_size
        self.end_size = end_size
        self.duration = duration
        self.timer = 0.0

    def update(self, dt):
        self.timer += dt

    def draw(self, frame, w_limit=None, h_limit=None):
        progress = self.timer / self.duration
        if progress < 1.0 and self.img is not None:
            fh, fw = frame.shape[:2]
            max_w = w_limit if w_limit is not None else fw
            max_h = h_limit if h_limit is not None else fh

            cur_size = int(self.start_size + (self.end_size - self.start_size) * progress)
            x1 = self.x - cur_size // 2
            y1 = self.y - cur_size // 2
            x2 = x1 + cur_size
            y2 = y1 + cur_size

            draw_x1 = max(0, x1)
            draw_y1 = max(0, y1)
            draw_x2 = min(max_w, x2)
            draw_y2 = min(max_h, y2)

            if draw_x2 > draw_x1 and draw_y2 > draw_y1:
                resized = cv2.resize(self.img, (cur_size, cur_size), interpolation=cv2.INTER_LINEAR)
                crop_x1 = draw_x1 - x1
                crop_y1 = draw_y1 - y1
                crop_x2 = crop_x1 + (draw_x2 - draw_x1)
                crop_y2 = crop_y1 + (draw_y2 - draw_y1)

                cropped = resized[crop_y1:crop_y2, crop_x1:crop_x2]
                roi = frame[draw_y1:draw_y2, draw_x1:draw_x2]

                bgr = cropped[:, :, :3]
                alpha = cropped[:, :, 3]
                fade = max(0.0, 1.0 - progress)
                alpha_3ch = cv2.merge([alpha, alpha, alpha])
                weighted = cv2.multiply(bgr, alpha_3ch, scale=(fade * 1.5) / 255.0, dtype=cv2.CV_8U)
                cv2.add(roi, weighted, dst=roi)


class InwardManaParticle:
    """ละอองพลังงานที่ถูกดูดเข้าสู่มือขณะฟื้นฟูมานา (Mana Recharge)"""

    def __init__(self, hand_x, hand_y):
        self.cx = float(hand_x)
        self.cy = float(hand_y)
        self.angle = np.random.uniform(0, 2 * math.pi)
        self.dist = np.random.uniform(50, 110)
        self.speed = np.random.uniform(220, 360)
        self.rot_speed = np.random.uniform(5.0, 9.0)
        self.life = self.dist / self.speed
        self.max_life = self.life
        self.color = (255, 230, 80) if np.random.rand() > 0.4 else (255, 255, 255)

    def update(self, dt):
        self.dist -= self.speed * dt
        self.angle += self.rot_speed * dt
        self.life -= dt

    def draw(self, frame):
        if self.life > 0 and self.dist > 6:
            alpha = max(0.0, self.life / self.max_life)
            r = max(1, int(3 * alpha))
            px = int(self.cx + self.dist * math.cos(self.angle))
            py = int(self.cy + self.dist * math.sin(self.angle))
            cv2.circle(frame, (px, py), r, self.color, -1, cv2.LINE_AA)


class Shockwave:
    """คลื่นกระแทกวงแหวนขยายตัว (Expanding Shockwave Ring)"""

    def __init__(self, x, y, color, max_radius=85, duration=0.35):
        self.x = int(x)
        self.y = int(y)
        self.color = color
        self.max_radius = max_radius
        self.duration = duration
        self.timer = 0.0

    def update(self, dt):
        self.timer += dt

    def draw(self, frame):
        progress = self.timer / self.duration
        if progress < 1.0:
            r = int(10 + (self.max_radius - 10) * progress)
            thickness = max(1, int(5 * (1.0 - progress)))
            cv2.circle(frame, (self.x, self.y), r, self.color, thickness, cv2.LINE_AA)


class AwakenedBanner:
    """ป้ายแบนเนอร์แสดงสถานะปลดล็อกสกิลขั้นสูง (Awakened State)"""

    def __init__(self, img, cx, cy, text="★ AWAKENED! (∞)", is_dual=False, duration=3.0):
        self.img = img
        self.cx = int(cx)
        self.cy = int(cy)
        self.text = text
        self.is_dual = is_dual
        self.duration = duration
        self.timer = 0.0
        self.width = 420 if is_dual else 200
        self.height = int(self.width * 9 / 16)

    def update(self, dt):
        self.timer += dt

    def draw(self, frame, screen_w, screen_h):
        if self.timer >= self.duration:
            return

        progress = self.timer / self.duration
        alpha_mult = min(1.0, (1.0 - progress) * 3.0) if progress > 0.66 else 1.0
        if alpha_mult <= 0.0:
            return

        x1 = self.cx - self.width // 2
        y1 = self.cy - self.height // 2
        x1 = max(15, min(screen_w - self.width - 15, x1))
        y1 = max(55, min(screen_h - self.height - 55, y1))
        x2 = x1 + self.width
        y2 = y1 + self.height

        if self.img is not None:
            resized = cv2.resize(self.img, (self.width, self.height), interpolation=cv2.INTER_LINEAR)
            roi = frame[y1:y2, x1:x2]
            if resized.shape[2] == 4:
                bgr = resized[:, :, :3]
                alpha = (resized[:, :, 3].astype(np.float32) / 255.0) * alpha_mult
                a3 = alpha[:, :, np.newaxis]
                roi[:] = np.clip(bgr.astype(np.float32) * a3 + roi.astype(np.float32) * (1.0 - a3), 0, 255).astype(np.uint8)
            else:
                cv2.addWeighted(resized, alpha_mult, roi, 1.0 - alpha_mult, 0, roi)

            flash_col = (230, 40, 220) if int(self.timer * 8) % 2 == 0 else (0, 215, 255)
            border_thick = 3 if self.is_dual else 2
            cv2.rectangle(frame, (x1, y1), (x2, y2), flash_col, border_thick, cv2.LINE_AA)

        font_scale = 0.85 if self.is_dual else 0.65
        thick = 2
        (tw, th), _ = cv2.getTextSize(self.text, cv2.FONT_HERSHEY_DUPLEX, font_scale, thick)
        tx = self.cx - tw // 2
        ty = y2 + th + 14
        tx = max(15, min(screen_w - tw - 15, tx))
        ty = min(screen_h - 15, ty)

        cv2.putText(frame, self.text, (tx + 2, ty + 2), cv2.FONT_HERSHEY_DUPLEX, font_scale, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(frame, self.text, (tx, ty), cv2.FONT_HERSHEY_DUPLEX, font_scale, (235, 60, 225), thick, cv2.LINE_AA)


# ==============================================================================
# 2. คลาสหลักจัดการกราฟิกและเรนเดอร์ (Core Graphic & HUD Renderer)
# ==============================================================================

class UIRenderer:
    """คลาสหลักสำหรับบริหารจัดการทรัพยากรภาพ เรนเดอร์เอฟเฟกต์เวทมนตร์ และวาดอินเทอร์เฟซ"""

    SPELL_TIMER_COLORS = {
        "Fireball": (0, 140, 255),
        "Magic Shield": (255, 220, 0),
        "Lightning Strike": (0, 240, 255),
        "Terra Boulder": (45, 140, 215),
        "Healing Light": (80, 255, 100),
        "Hollow Purple": (220, 40, 200)
    }

    def __init__(self, frame_width=1280, frame_height=720):
        self.w = frame_width
        self.h = frame_height

        # คลังจัดเก็บอนุภาคแอนิเมชันที่กำลังทำงาน
        self.particles = []
        self.ember_sparks = []
        self.inward_embers = []
        self.rock_shards = []
        self.rising_hearts = []
        self.electric_particles = []
        self.smoke_puffs = []
        self.sprite_bursts = []
        self.mana_particles = []
        self.shockwaves = []
        self.awakened_banners = []

        self.assets_dir = get_resource_path("assets")
        os.makedirs(self.assets_dir, exist_ok=True)

        self.images = {}
        self.texture_cache = {}

        self._init_all_assets()

    def _find_asset_file(self, filename):
        """ค้นหาไฟล์ภาพจากทั้งใน Bundled Executable และโฟลเดอร์โปรเจกต์"""
        base_dir = get_base_dir()
        candidates = [
            os.path.join(self.assets_dir, filename),
            os.path.join(self.assets_dir, "PNG (Transparent)", filename),
            os.path.join(self.assets_dir, "vfx", filename),
            os.path.join(self.assets_dir, "images", filename),
            get_resource_path(filename),
            os.path.join(base_dir, filename),
            os.path.join(base_dir, "PNG (Transparent)", filename),
            os.path.join(base_dir, "assets", filename),
            os.path.join(base_dir, "assets", "vfx", filename),
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return None

    def _init_all_assets(self):
        """โหลดและเตรียมทรัพยากรภาพ สไปรต์ และไอคอนทั้งหมดเข้าสู่หน่วยความจำ"""
        spell_files = {
            "spell_Fireball": "icon_fire.png",
            "spell_Magic Shield": "icon_shield.png",
            "spell_Lightning Strike": "icon_lightning.png",
            "spell_Terra Boulder": "icon_terra.png",
            "spell_Healing Light": "icon_heal.png"
        }
        shape_files = {
            "shape_Fireball": "shape_triangle.png",
            "shape_Magic Shield": "shape_circle.png",
            "shape_Lightning Strike": "shape_z.png",
            "shape_Terra Boulder": "shape_square.png",
            "shape_Healing Light": "shape_heart.png"
        }
        pose_defs = {
            "pose_Fireball": ("pose_fireball.png", "🖐"),
            "pose_Magic Shield": ("pose_shield.png", "✊"),
            "pose_Lightning Strike": ("pose_lightning.png", "✌"),
            "pose_Healing Light": ("pose_heal.png", "👍")
        }

        for key, fname in {**spell_files, **shape_files}.items():
            fpath = self._find_asset_file(fname)
            if fpath:
                img = cv2.imread(fpath, cv2.IMREAD_UNCHANGED)
                if img is not None:
                    self.images[key] = img

        for key, (fname, emoji_char) in pose_defs.items():
            fpath = self._find_asset_file(fname)
            if not fpath and HAS_PIL:
                save_p = os.path.join(self.assets_dir, fname)
                self._generate_emoji_image(save_p, emoji_char)
                fpath = save_p
            if fpath and os.path.exists(fpath):
                img = cv2.imread(fpath, cv2.IMREAD_UNCHANGED)
                if img is not None:
                    self.images[key] = img

        terra_path = self._find_asset_file("pose_terra.png")
        if terra_path:
            t_img = cv2.imread(terra_path, cv2.IMREAD_UNCHANGED)
            if t_img is not None:
                self.images["pose_Terra Boulder"] = self._make_square_padded(t_img)

        self._init_fireball_vfx_assets()
        self._init_shield_vfx_assets()
        self._init_lightning_vfx_assets()
        self._init_terra_vfx_assets()
        self._init_heal_vfx_assets()
        self._init_mana_recharge_vfx_assets()
        self._init_charge_base_and_fire_assets()
        self._init_charge_shield_assets()
        self._init_charge_lightning_assets()
        self._init_charge_terra_assets()
        self._init_charge_heal_assets()
        self._init_hollow_purple_vfx_assets()

        spell_names = ["Fireball", "Magic Shield", "Lightning Strike", "Terra Boulder", "Healing Light"]
        for sname in spell_names:
            self.get_cached_texture(f"shape_{sname}", 28)
            self.get_cached_texture(f"pose_{sname}", 32)
            self.get_cached_texture(f"spell_{sname}", 46)
            self.get_cached_texture(f"pose_{sname}", 52)
            self.get_cached_texture(f"spell_{sname}", 105)

    def _init_hollow_purple_vfx_assets(self):
        c05_p = self._find_asset_file("circle_05.png")
        if c05_p:
            raw = cv2.imread(c05_p, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_hp_aura_red"] = self._tint_grayscale(raw, (20, 50, 255), core_boost=True)
                self.images["vfx_hp_aura_blue"] = self._tint_grayscale(raw, (255, 170, 30), core_boost=True)
                self.images["vfx_hp_aura_purple"] = self._tint_grayscale(raw, (240, 50, 225), core_boost=True)

        flare_p = self._find_asset_file("flare_01.png")
        if flare_p:
            raw = cv2.imread(flare_p, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_hp_flare"] = self._tint_grayscale(raw, (255, 245, 255), core_boost=True)

        twirl_p = self._find_asset_file("twirl_02.png") or self._find_asset_file("twirl_01.png")
        if twirl_p:
            raw = cv2.imread(twirl_p, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_hp_twirl"] = self._tint_grayscale(raw, (230, 60, 220), core_boost=False)

        spark_p = self._find_asset_file("spark_05.png") or self._find_asset_file("spark_06.png")
        if spark_p:
            raw = cv2.imread(spark_p, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_hp_spark"] = self._tint_grayscale(raw, (255, 175, 255), core_boost=True)

        ring_p = (self._find_asset_file("circle_03.png") or 
                  self._find_asset_file("circle_02.png") or 
                  self._find_asset_file("circle_04.png") or 
                  self._find_asset_file("circle_01.png"))
        if ring_p:
            raw = cv2.imread(ring_p, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_hp_ring"] = self._tint_grayscale(raw, (235, 45, 215), core_boost=False)

        gojo_candidates = [
            "shooting hollow purple.PNG",
            "shooting hollow purple.png",
            "shooting hollow purple.webp",
            "gojo_purple.png",
            "gojo_purple.PNG"
        ]
        for g_name in gojo_candidates:
            gp = self._find_asset_file(g_name)
            if gp:
                raw_g = cv2.imread(gp, cv2.IMREAD_UNCHANGED)
                if raw_g is not None:
                    self.images["gojo_shoot_callout"] = raw_g
                    break

        gojo_awk_candidates = [
            "Gojo awakened_2.png",
            "Gojo awakened_2.PNG",
            "Gojo awakened.png",
            "Gojo awakened.PNG",
            "gojo_awakened.png",
            "gojo_awakened.PNG",
            "Gojo awakened.webp"
        ]
        for g_name in gojo_awk_candidates:
            gp = self._find_asset_file(g_name)
            if gp:
                raw_g = cv2.imread(gp, cv2.IMREAD_UNCHANGED)
                if raw_g is not None:
                    self.images["gojo_awakened"] = raw_g
                    break

    def spawn_awakened_banner(self, cx, cy, text="★ AWAKENED! (∞)", is_dual=False, duration=3.0):
        img = self.images.get("gojo_awakened")
        self.awakened_banners.append(AwakenedBanner(img, cx, cy, text=text, is_dual=is_dual, duration=duration))

    def _init_fireball_vfx_assets(self):
        bullet_path = self._find_asset_file("vfx_fireball_bullet.png")
        tail_path = self._find_asset_file("vfx_fireball_tail.png")
        hit_path = self._find_asset_file("vfx_fireball_hit.png")
        smoke_path = self._find_asset_file("vfx_fireball_smoke.png")

        if bullet_path:
            raw = cv2.imread(bullet_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_fire_bullet"] = self._tint_grayscale(raw, (0, 140, 255), core_boost=True)
        if tail_path:
            raw = cv2.imread(tail_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_fire_tail"] = self._tint_grayscale(raw, (0, 110, 255), core_boost=False)
        if hit_path:
            raw = cv2.imread(hit_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_fire_hit"] = self._tint_grayscale(raw, (0, 160, 255), core_boost=True)
        if smoke_path:
            raw = cv2.imread(smoke_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_fire_smoke"] = self._tint_grayscale(raw, (30, 45, 90), core_boost=False)

    def _init_shield_vfx_assets(self):
        dome_path = self._find_asset_file("vfx_shield_dome.png")
        rune_path = self._find_asset_file("vfx_shield_rune.png")
        hit_path = self._find_asset_file("vfx_shield_hit.png")

        if dome_path:
            raw = cv2.imread(dome_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_shield_dome"] = self._tint_grayscale(raw, (255, 230, 50), core_boost=False)
        if rune_path:
            raw = cv2.imread(rune_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_shield_rune"] = self._tint_grayscale(raw, (0, 220, 255), core_boost=True)
        if hit_path:
            raw = cv2.imread(hit_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_shield_hit"] = self._tint_grayscale(raw, (60, 240, 255), core_boost=True)

    def _init_lightning_vfx_assets(self):
        bolt_path = self._find_asset_file("vfx_lightning_bolt.png")
        hit_path = self._find_asset_file("vfx_lightning_hit.png")
        spark_path = self._find_asset_file("vfx_lightning_spark.png")

        if bolt_path:
            raw = cv2.imread(bolt_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_lightning_bolt"] = self._tint_grayscale(raw, (0, 240, 255), core_boost=True)
        if hit_path:
            raw = cv2.imread(hit_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_lightning_hit"] = self._tint_grayscale(raw, (0, 230, 255), core_boost=True)
        if spark_path:
            raw = cv2.imread(spark_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_lightning_spark"] = self._tint_grayscale(raw, (0, 255, 255), core_boost=True)

    def _init_terra_vfx_assets(self):
        boulder_path = self._find_asset_file("vfx_terra_boulder.png")
        shatter_path = self._find_asset_file("vfx_terra_shatter.png")
        debris_path = self._find_asset_file("vfx_terra_debris.png")
        smoke_path = self._find_asset_file("vfx_fireball_smoke.png")

        if boulder_path:
            raw = cv2.imread(boulder_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_terra_boulder"] = self._create_solid_rock_texture(raw)
        if shatter_path:
            raw = cv2.imread(shatter_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_terra_shatter"] = self._tint_grayscale(raw, (65, 80, 95), core_boost=False)
        if debris_path:
            raw = cv2.imread(debris_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_terra_debris"] = self._tint_grayscale(raw, (60, 75, 90), core_boost=False)
        if smoke_path:
            raw = cv2.imread(smoke_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_terra_dust"] = self._tint_grayscale(raw, (115, 140, 160), core_boost=False)

    def _init_heal_vfx_assets(self):
        heart_path = self._find_asset_file("vfx_heal_heart.png")
        flare_path = self._find_asset_file("vfx_heal_flare.png")
        ring_path = self._find_asset_file("vfx_heal_ring.png")

        if heart_path:
            raw = cv2.imread(heart_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_heal_heart"] = self._tint_grayscale(raw, (80, 240, 100), core_boost=True)
        if flare_path:
            raw = cv2.imread(flare_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_heal_flare"] = self._tint_grayscale(raw, (120, 255, 200), core_boost=True)
        if ring_path:
            raw = cv2.imread(ring_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_heal_ring"] = self._tint_grayscale(raw, (100, 245, 120), core_boost=False)

    def _init_mana_recharge_vfx_assets(self):
        vortex_path = self._find_asset_file("vfx_mana_vortex.png")
        star_path = self._find_asset_file("vfx_mana_star.png")
        ring_path = self._find_asset_file("vfx_mana_ring.png")

        if vortex_path:
            raw = cv2.imread(vortex_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_mana_vortex"] = self._tint_grayscale(raw, (255, 215, 30), core_boost=True)
        if star_path:
            raw = cv2.imread(star_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_mana_star"] = self._tint_grayscale(raw, (255, 245, 160), core_boost=True)
        if ring_path:
            raw = cv2.imread(ring_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_mana_ring"] = self._tint_grayscale(raw, (255, 210, 40), core_boost=False)

    def _init_charge_base_and_fire_assets(self):
        seal_path = self._find_asset_file("vfx_charge_seal.png") or self._find_asset_file("magic_04.png")
        ring_path = self._find_asset_file("vfx_charge_ring.png")
        core_path = self._find_asset_file("vfx_charge_core.png")

        if seal_path:
            raw = cv2.imread(seal_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_charge_seal"] = self._tint_grayscale(raw, (0, 150, 255), core_boost=True)
        if ring_path:
            raw = cv2.imread(ring_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_charge_ring"] = self._tint_grayscale(raw, (0, 175, 255), core_boost=True)
        if core_path:
            raw = cv2.imread(core_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_charge_core"] = self._tint_grayscale(raw, (0, 130, 255), core_boost=True)

        f_core_path = self._find_asset_file("vfx_charge_fire_core.png")
        f_aura_path = self._find_asset_file("vfx_charge_fire_aura.png")
        f_flare_path = self._find_asset_file("vfx_charge_fire_flare.png")

        if f_core_path:
            raw = cv2.imread(f_core_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_charge_fire_core"] = self._tint_grayscale(raw, (0, 140, 255), core_boost=True)
        if f_aura_path:
            raw = cv2.imread(f_aura_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_charge_fire_aura"] = self._tint_grayscale(raw, (0, 180, 255), core_boost=False)
        if f_flare_path:
            raw = cv2.imread(f_flare_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_charge_fire_flare"] = self._tint_grayscale(raw, (0, 210, 255), core_boost=True)

    def _init_charge_shield_assets(self):
        compass_path = self._find_asset_file("vfx_charge_shield_compass.png")
        field_path = self._find_asset_file("vfx_charge_shield_field.png")
        sring_path = self._find_asset_file("vfx_charge_shield_ring.png")

        if compass_path:
            raw = cv2.imread(compass_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_charge_shield_compass"] = self._tint_grayscale(raw, (255, 220, 30), core_boost=True)
        if field_path:
            raw = cv2.imread(field_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_charge_shield_field"] = self._tint_grayscale(raw, (255, 230, 60), core_boost=True)
        if sring_path:
            raw = cv2.imread(sring_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_charge_shield_ring"] = self._tint_grayscale(raw, (255, 200, 20), core_boost=False)

    def _init_charge_lightning_assets(self):
        arc_path = self._find_asset_file("vfx_charge_lightning_arc.png")
        bolt_path = self._find_asset_file("vfx_charge_lightning_bolt.png")
        spark_path = self._find_asset_file("vfx_charge_lightning_spark.png")

        if arc_path:
            raw = cv2.imread(arc_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_charge_lightning_arc"] = self._tint_grayscale(raw, (0, 240, 255), core_boost=True)
        if bolt_path:
            raw = cv2.imread(bolt_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_charge_lightning_bolt"] = self._tint_grayscale(raw, (0, 230, 255), core_boost=True)
        if spark_path:
            raw = cv2.imread(spark_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_charge_lightning_spark"] = self._tint_grayscale(raw, (0, 255, 255), core_boost=True)

    def _init_charge_terra_assets(self):
        dust_path = self._find_asset_file("vfx_charge_terra_dust_ring.png")
        debris_path = self._find_asset_file("vfx_charge_terra_debris.png")
        core_path = self._find_asset_file("vfx_charge_terra_core.png")

        if dust_path:
            raw = cv2.imread(dust_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_charge_terra_dust_ring"] = self._tint_grayscale(raw, (70, 115, 155), core_boost=False)
        if debris_path:
            raw = cv2.imread(debris_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_charge_terra_debris"] = self._tint_grayscale(raw, (45, 55, 65), core_boost=False)
        if core_path:
            raw = cv2.imread(core_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_charge_terra_core"] = self._tint_grayscale(raw, (55, 85, 125), core_boost=False)

    def _init_charge_heal_assets(self):
        heart_path = self._find_asset_file("vfx_charge_heal_heart.png")
        halo_path = self._find_asset_file("vfx_charge_heal_halo.png")
        aura_path = self._find_asset_file("vfx_charge_heal_aura.png")

        if heart_path:
            raw = cv2.imread(heart_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_charge_heal_heart"] = self._tint_grayscale(raw, (80, 240, 100), core_boost=True)
        if halo_path:
            raw = cv2.imread(halo_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_charge_heal_halo"] = self._tint_grayscale(raw, (120, 255, 180), core_boost=True)
        if aura_path:
            raw = cv2.imread(aura_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                self.images["vfx_charge_heal_aura"] = self._tint_grayscale(raw, (90, 240, 120), core_boost=False)

    def _create_solid_rock_texture(self, img):
        if len(img.shape) == 2:
            gray = img.copy()
        elif img.shape[2] == 4:
            gray = cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY)
        else:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        h, w = gray.shape
        out = np.zeros((h, w, 4), dtype=np.uint8)
        norm = gray.astype(np.float32) / 255.0

        rock_b = 40.0 + norm * 55.0
        rock_g = 48.0 + norm * 62.0
        rock_r = 55.0 + norm * 70.0

        crack_mask = np.clip((norm - 0.52) / 0.48, 0.0, 1.0)
        rock_b = rock_b * (1.0 - crack_mask) + 15.0 * crack_mask
        rock_g = rock_g * (1.0 - crack_mask) + 175.0 * crack_mask
        rock_r = rock_r * (1.0 - crack_mask) + 245.0 * crack_mask

        out[:, :, 0] = np.clip(rock_b, 0, 255).astype(np.uint8)
        out[:, :, 1] = np.clip(rock_g, 0, 255).astype(np.uint8)
        out[:, :, 2] = np.clip(rock_r, 0, 255).astype(np.uint8)

        alpha_solid = np.clip((norm - 0.06) / 0.12, 0.0, 1.0) * 255.0
        out[:, :, 3] = alpha_solid.astype(np.uint8)
        return out

    def _tint_grayscale(self, img, target_color_bgr, core_boost=True):
        if len(img.shape) == 2:
            gray = img.copy()
            alpha = img.copy()
        elif img.shape[2] == 4:
            alpha = img[:, :, 3]
            gray = cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY)
            if np.min(alpha) > 235:
                alpha = gray.copy()
        else:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            alpha = gray.copy()

        norm = gray.astype(np.float32) / 255.0
        h, w = gray.shape
        out = np.zeros((h, w, 4), dtype=np.uint8)

        tb, tg, tr = target_color_bgr
        for c, t_val in enumerate([tb, tg, tr]):
            tinted = norm * t_val
            if core_boost:
                white_mask = np.clip((norm - 0.40) / 0.60, 0.0, 1.0)
                tinted = tinted * (1.0 - white_mask) + 255.0 * white_mask
            out[:, :, c] = np.clip(tinted, 0, 255).astype(np.uint8)

        out[:, :, 3] = alpha
        return out

    def _make_square_padded(self, img):
        h_orig, w_orig = img.shape[:2]
        max_dim = max(h_orig, w_orig)
        if len(img.shape) == 3 and img.shape[2] == 4:
            square_img = np.zeros((max_dim, max_dim, 4), dtype=np.uint8)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
            square_img = np.zeros((max_dim, max_dim, 4), dtype=np.uint8)

        off_x = (max_dim - w_orig) // 2
        off_y = (max_dim - h_orig) // 2
        square_img[off_y:off_y + h_orig, off_x:off_x + w_orig] = img
        return square_img

    def _generate_emoji_image(self, save_path, emoji_char, img_size=120):
        try:
            pil_img = Image.new("RGBA", (img_size, img_size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(pil_img)
            font_path = "C:/Windows/Fonts/seguiemj.ttf" if os.path.exists("C:/Windows/Fonts/seguiemj.ttf") else "C:/Windows/Fonts/segoeui.ttf"
            font = ImageFont.truetype(font_path, int(img_size * 0.72))
            bbox = font.getbbox(emoji_char)
            pos_x = (img_size - (bbox[2] - bbox[0])) // 2 - bbox[0]
            pos_y = (img_size - (bbox[3] - bbox[1])) // 2 - bbox[1]
            draw.text((pos_x, pos_y), emoji_char, font=font, embedded_color=True)

            cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGBA2BGRA)
            b = cv_img[:, :, 0].astype(np.float32)
            g = cv_img[:, :, 1].astype(np.float32)
            r = cv_img[:, :, 2].astype(np.float32)
            a = cv_img[:, :, 3]

            yellow_mask = (a > 30) & (r > b + 45) & (g > b + 25)
            new_b = np.clip(b + (g - b) * 0.68, 0, 255)
            cv_img[yellow_mask, 0] = new_b[yellow_mask].astype(np.uint8)

            cv2.imwrite(save_path, cv_img)
        except Exception:
            pass

    def get_cached_texture(self, key, size):
        cache_key = (key, size)
        if cache_key in self.texture_cache:
            return self.texture_cache[cache_key]

        if key not in self.images:
            return None

        img = self.images[key]
        resized = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)

        if resized.shape[2] == 4:
            alpha = (resized[:, :, 3:4] / 255.0).astype(np.float32)
            bgr = resized[:, :, :3].astype(np.float32)
        else:
            bgr = resized.astype(np.float32)
            alpha = np.ones((size, size, 1), dtype=np.float32)

        self.texture_cache[cache_key] = (bgr, alpha)
        return self.texture_cache[cache_key]

    def draw_texture(self, frame, key, cx, cy, size=40):
        tex_data = self.get_cached_texture(key, size)
        if tex_data is None:
            return False

        bgr, alpha = tex_data
        x1 = cx - size // 2
        y1 = cy - size // 2
        x2 = x1 + size
        y2 = y1 + size

        draw_x1 = max(0, x1)
        draw_y1 = max(0, y1)
        draw_x2 = min(self.w, x2)
        draw_y2 = min(self.h, y2)

        if draw_x2 > draw_x1 and draw_y2 > draw_y1:
            crop_x1 = draw_x1 - x1
            crop_y1 = draw_y1 - y1
            crop_x2 = crop_x1 + (draw_x2 - draw_x1)
            crop_y2 = crop_y1 + (draw_y2 - draw_y1)

            c_bgr = bgr[crop_y1:crop_y2, crop_x1:crop_x2]
            c_alpha = alpha[crop_y1:crop_y2, crop_x1:crop_x2]
            roi = frame[draw_y1:draw_y2, draw_x1:draw_x2].astype(np.float32)
            frame[draw_y1:draw_y2, draw_x1:draw_x2] = (c_bgr * c_alpha + roi * (1.0 - c_alpha)).astype(np.uint8)
            return True
        return False

    def _draw_additive_sprite(self, frame, img, cx, cy, size, angle=0.0, alpha_mult=1.0):
        """เบลนด์ภาพแบบ Additive Blending สำหรับเอฟเฟกต์แสงเรืองและประกายไฟ"""
        if img is None or size <= 0:
            return

        r = size // 2
        x1, y1 = cx - r, cy - r
        x2, y2 = x1 + size, y1 + size

        dx1 = max(0, x1)
        dy1 = max(0, y1)
        dx2 = min(self.w, x2)
        dy2 = min(self.h, y2)

        if dx2 <= dx1 or dy2 <= dy1:
            return

        resized = cv2.resize(img, (size, size), interpolation=cv2.INTER_LINEAR)
        if angle != 0.0:
            M = cv2.getRotationMatrix2D((size / 2.0, size / 2.0), angle, 1.0)
            resized = cv2.warpAffine(resized, M, (size, size), flags=cv2.INTER_LINEAR,
                                     borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))

        cx1 = dx1 - x1
        cy1 = dy1 - y1
        cx2 = cx1 + (dx2 - dx1)
        cy2 = cy1 + (dy2 - dy1)

        cropped = resized[cy1:cy2, cx1:cx2]
        roi = frame[dy1:dy2, dx1:dx2]

        bgr = cropped[:, :, :3]
        if cropped.shape[2] == 4:
            alpha = cropped[:, :, 3]
            alpha_3ch = cv2.merge([alpha, alpha, alpha])
        else:
            alpha_3ch = np.full_like(bgr, 255)

        scale = (float(alpha_mult) * 1.4) / 255.0
        weighted_bgr = cv2.multiply(bgr, alpha_3ch, scale=scale, dtype=cv2.CV_8U)
        cv2.add(roi, weighted_bgr, dst=roi)

    def _draw_normal_sprite(self, frame, img, cx, cy, size, angle=0.0, alpha_mult=1.0):
        """เบลนด์ภาพแบบ Standard Alpha Blending สำหรับวัตถุทึบแสง เช่น ก้อนหิน"""
        if img is None or size <= 0:
            return

        r = size // 2
        x1, y1 = cx - r, cy - r
        x2, y2 = x1 + size, y1 + size

        dx1 = max(0, x1)
        dy1 = max(0, y1)
        dx2 = min(self.w, x2)
        dy2 = min(self.h, y2)

        if dx2 <= dx1 or dy2 <= dy1:
            return

        resized = cv2.resize(img, (size, size), interpolation=cv2.INTER_LINEAR)
        if angle != 0.0:
            M = cv2.getRotationMatrix2D((size / 2.0, size / 2.0), angle, 1.0)
            resized = cv2.warpAffine(resized, M, (size, size), flags=cv2.INTER_LINEAR,
                                     borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))

        cx1 = dx1 - x1
        cy1 = dy1 - y1
        cx2 = cx1 + (dx2 - dx1)
        cy2 = cy1 + (dy2 - dy1)

        cropped = resized[cy1:cy2, cx1:cx2]
        roi = frame[dy1:dy2, dx1:dx2]

        bgr = cropped[:, :, :3]
        if cropped.shape[2] == 4:
            alpha = (cropped[:, :, 3].astype(np.float32) / 255.0) * min(1.0, float(alpha_mult))
            a3 = alpha[:, :, np.newaxis]
            blended = (bgr.astype(np.float32) * a3 + roi.astype(np.float32) * (1.0 - a3)).astype(np.uint8)
            roi[:] = blended
        else:
            cv2.addWeighted(bgr, alpha_mult, roi, 1.0 - alpha_mult, 0, roi)

    def draw_infinity_barrier(self, frame, torso_box, now):
        tx1, ty1, tx2, ty2 = torso_box
        cx = (tx1 + tx2) // 2
        cy = (ty1 + ty2) // 2

        if "vfx_hp_ring" in self.images:
            for ring_idx in range(3):
                phase = ((now * 1.8) + ring_idx * 0.33) % 1.0
                r_size = int(180 + phase * 160)
                fade = math.sin(phase * math.pi) * 0.55
                self._draw_additive_sprite(
                    frame,
                    self.images["vfx_hp_ring"],
                    cx, cy,
                    r_size,
                    angle=now * 15.0 * (1 if ring_idx % 2 == 0 else -1),
                    alpha_mult=fade
                )
        else:
            for ring_idx in range(2):
                phase = ((now * 2.0) + ring_idx * 0.5) % 1.0
                r_rad = int(80 + phase * 65)
                cv2.circle(frame, (cx, cy), r_rad, (240, 80, 230), 2, cv2.LINE_AA)

        inf_txt = "INFINITY"
        font = cv2.FONT_HERSHEY_DUPLEX
        scale = 0.70
        (tw, th), _ = cv2.getTextSize(inf_txt, font, scale, 2)
        tx = cx - tw // 2
        ty = max(45, ty1 - 25)

        cv2.putText(frame, inf_txt, (tx + 2, ty + 2), font, scale, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(frame, inf_txt, (tx, ty), font, scale, (255, 230, 255), 2, cv2.LINE_AA)

    def draw_charging_timer_badge(self, frame, spell_name, cx, cy, ratio, remaining):
        theme_color = self.SPELL_TIMER_COLORS.get(spell_name, (255, 255, 255))

        sweep_angle = int(360 * ratio)
        cv2.ellipse(frame, (cx, cy), (48, 48), 0, -90, -90 + sweep_angle, theme_color, 3, cv2.LINE_AA)
        cv2.circle(frame, (cx, cy), 48, (80, 80, 80), 1, cv2.LINE_AA)

        txt = f"{remaining:.1f}s"
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.65
        thick = 2
        (tw, th), _ = cv2.getTextSize(txt, font, scale, thick)
        tx = cx - tw // 2
        ty = cy + th // 2

        cv2.putText(frame, txt, (tx, ty), font, scale, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(frame, txt, (tx, ty), font, scale, theme_color, thick, cv2.LINE_AA)

    def draw_fireball_charging(self, frame, cx, cy, ratio, remaining, now):
        if np.random.rand() > 0.25:
            self.inward_embers.append(InwardEmber(cx, cy))

        seal_img = self.images.get("vfx_charge_seal")
        if seal_img is not None:
            rot_spd = 90.0 + ratio * 320.0
            seal_angle = (now * rot_spd) % 360.0
            self._draw_additive_sprite(frame, seal_img, cx, cy, 145, angle=seal_angle, alpha_mult=0.75 + 0.25 * ratio)

        ring_img = self.images.get("vfx_charge_ring")
        if ring_img is not None:
            ring_size = int(160 - ratio * 60)
            ring_pulse = 1.0 + 0.08 * math.sin(now * 10.0)
            self._draw_additive_sprite(frame, ring_img, cx, cy, int(ring_size * ring_pulse), angle=-now * 60.0, alpha_mult=0.85)

        aura_img = self.images.get("vfx_charge_fire_aura")
        if aura_img is not None:
            aura_size = int(70 + ratio * 65)
            self._draw_additive_sprite(frame, aura_img, cx, cy, aura_size, angle=-now * 220.0, alpha_mult=0.90)

        core_img = self.images.get("vfx_charge_fire_core", self.images.get("vfx_charge_core"))
        if core_img is not None:
            core_size = int(45 + ratio * 75)
            core_pulse = 1.0 + 0.10 * math.sin(now * 15.0)
            self._draw_additive_sprite(frame, core_img, cx, cy, int(core_size * core_pulse), angle=now * 180.0, alpha_mult=1.3)

        if ratio >= 0.70:
            flare_img = self.images.get("vfx_charge_fire_flare")
            if flare_img is not None:
                flare_progress = (ratio - 0.70) / 0.30
                flare_pulse = 1.0 + 0.25 * math.sin(now * 24.0)
                flare_size = int((80 + flare_progress * 80) * flare_pulse)
                self._draw_additive_sprite(frame, flare_img, cx, cy, flare_size, angle=now * 90.0, alpha_mult=flare_progress * 1.5)

        self.draw_charging_timer_badge(frame, "Fireball", cx, cy, ratio, remaining)

    def draw_shield_charging(self, frame, cx, cy, ratio, remaining, now):
        seal_img = self.images.get("vfx_charge_seal")
        if seal_img is not None:
            self._draw_additive_sprite(frame, seal_img, cx, cy, 140, angle=-now * 75.0, alpha_mult=0.65 + 0.35 * ratio)

        compass_img = self.images.get("vfx_charge_shield_compass")
        if compass_img is not None:
            rot_spd = 120.0 + ratio * 260.0
            comp_angle = (now * rot_spd) % 360.0
            self._draw_additive_sprite(frame, compass_img, cx, cy, 155, angle=comp_angle, alpha_mult=0.85 + 0.25 * ratio)

        field_img = self.images.get("vfx_charge_shield_field", self.images.get("vfx_charge_core"))
        if field_img is not None:
            field_pulse = 1.0 + 0.08 * math.sin(now * 12.0)
            field_size = int((65 + ratio * 60) * field_pulse)
            self._draw_additive_sprite(frame, field_img, cx, cy, field_size, angle=now * 45.0, alpha_mult=1.1)

        sring_img = self.images.get("vfx_charge_shield_ring")
        if sring_img is not None:
            for i in range(2):
                phase = ((now * 2.2) + i * 0.5) % 1.0
                r_size = int(60 + phase * 90)
                fade = math.sin(phase * math.pi) * 0.85
                self._draw_additive_sprite(frame, sring_img, cx, cy, r_size, alpha_mult=fade)

        self.draw_charging_timer_badge(frame, "Magic Shield", cx, cy, ratio, remaining)

    def draw_lightning_charging(self, frame, cx, cy, ratio, remaining, now):
        if np.random.rand() > 0.20:
            self.electric_particles.append(ElectricArcParticle(cx, cy))

        seal_img = self.images.get("vfx_charge_seal")
        if seal_img is not None:
            rot_spd = 140.0 + ratio * 380.0
            seal_angle = (now * rot_spd) % 360.0
            self._draw_additive_sprite(frame, seal_img, cx, cy, 135, angle=seal_angle, alpha_mult=0.70 + 0.30 * ratio)

        arc_img = self.images.get("vfx_charge_lightning_arc")
        if arc_img is not None:
            jitter = np.random.uniform(-4, 4)
            arc_size = int((95 + ratio * 45) + jitter)
            arc_angle = (-now * 420.0) % 360.0
            self._draw_additive_sprite(frame, arc_img, cx, cy, arc_size, angle=arc_angle, alpha_mult=1.0)

        bolt_img = self.images.get("vfx_charge_lightning_bolt")
        if bolt_img is not None and np.random.rand() > 0.15:
            bolt_rot = np.random.choice([0.0, 90.0, 180.0, 270.0]) + np.random.uniform(-15, 15)
            bolt_size = int(120 + ratio * 50)
            self._draw_additive_sprite(frame, bolt_img, cx, cy, bolt_size, angle=bolt_rot, alpha_mult=1.2)

        if ratio >= 0.70:
            spark_img = self.images.get("vfx_charge_lightning_spark")
            if spark_img is not None:
                spark_prog = (ratio - 0.70) / 0.30
                pulse = 1.0 + 0.30 * math.sin(now * 30.0)
                spark_size = int((85 + spark_prog * 85) * pulse)
                self._draw_additive_sprite(frame, spark_img, cx, cy, spark_size, angle=now * 160.0, alpha_mult=spark_prog * 1.6)

        self.draw_charging_timer_badge(frame, "Lightning Strike", cx, cy, ratio, remaining)

    def draw_terra_charging(self, frame, cx, cy, ratio, remaining, now):
        if np.random.rand() > 0.35:
            self.rock_shards.append(RockShard(cx, cy, np.random.uniform(-1, 1), np.random.uniform(-1, 1)))

        dust_img = self.images.get("vfx_charge_terra_dust_ring")
        if dust_img is not None:
            d_size = int(140 + ratio * 35)
            self._draw_normal_sprite(frame, dust_img, cx, cy, d_size, angle=-now * 140.0, alpha_mult=0.75)

        debris_img = self.images.get("vfx_charge_terra_debris")
        if debris_img is not None:
            deb_size = int(135 - ratio * 45)
            self._draw_normal_sprite(frame, debris_img, cx, cy, deb_size, angle=now * 95.0, alpha_mult=0.85)

        core_img = self.images.get("vfx_charge_terra_core")
        if core_img is not None:
            c_size = int(55 + ratio * 55)
            self._draw_normal_sprite(frame, core_img, cx, cy, c_size, angle=-now * 60.0, alpha_mult=0.70)

        if "vfx_terra_boulder" in self.images:
            b_size = int(40 + ratio * 65)
            rot_b = (now * 160.0) % 360.0
            self._draw_normal_sprite(frame, self.images["vfx_terra_boulder"], cx, cy, b_size, angle=rot_b, alpha_mult=1.0)
            cv2.circle(frame, (cx, cy), int(b_size * 0.45), (35, 110, 185), 1, cv2.LINE_AA)

        self.draw_charging_timer_badge(frame, "Terra Boulder", cx, cy, ratio, remaining)

    def draw_healing_charging(self, frame, cx, cy, ratio, remaining, now):
        if np.random.rand() > 0.25:
            p = Particle(cx + np.random.uniform(-25, 25), cy + np.random.uniform(-15, 15),
                         (90, 255, 120) if np.random.rand() > 0.3 else (150, 255, 210),
                         speed_range=(40, 120), life_range=(0.3, 0.6), radius_range=(2, 4))
            p.vy = -abs(p.vy) - 30.0
            self.particles.append(p)

        seal_img = self.images.get("vfx_charge_seal")
        if seal_img is not None:
            rot_spd = 50.0 + ratio * 120.0
            seal_angle = (now * rot_spd) % 360.0
            self._draw_additive_sprite(frame, seal_img, cx, cy, 140, angle=seal_angle, alpha_mult=0.60 + 0.30 * ratio)

        halo_img = self.images.get("vfx_charge_heal_halo")
        if halo_img is not None:
            h_size = int(115 + ratio * 35)
            self._draw_additive_sprite(frame, halo_img, cx, cy, h_size, angle=-now * 65.0, alpha_mult=0.85 + 0.35 * ratio)

        aura_img = self.images.get("vfx_charge_heal_aura")
        if aura_img is not None:
            for i in range(2):
                phase = ((now * 1.8) + i * 0.5) % 1.0
                a_size = int(50 + phase * 85)
                fade = math.sin(phase * math.pi) * 0.90
                self._draw_additive_sprite(frame, aura_img, cx, cy, a_size, alpha_mult=fade)

        heart_img = self.images.get("vfx_charge_heal_heart")
        if heart_img is not None:
            hb_phase = (now * 3.5) % 1.0
            hb_pulse = 1.0 + 0.18 * math.sin(hb_phase * 2 * math.pi) if hb_phase < 0.5 else 1.0
            heart_size = int((45 + ratio * 50) * hb_pulse)
            self._draw_additive_sprite(frame, heart_img, cx, cy, heart_size, alpha_mult=1.2)

        self.draw_charging_timer_badge(frame, "Healing Light", cx, cy, ratio, remaining)

    def _draw_crackling_purple_lightning(self, frame, cx, cy, orb_radius, now, count=3):
        num_arcs = 4
        for i in range(num_arcs):
            time_step = int(now * 18.0) + i * 7
            rng = random.Random(time_step)
            
            base_angle = rng.uniform(0, 2 * math.pi)
            arc_span = rng.uniform(0.35, 0.75)
            steps = 5
            
            arc_pts = []
            for s in range(steps + 1):
                cur_ang = base_angle + (s / float(steps)) * arc_span
                radial_jitter = rng.uniform(-10.0, 28.0)
                r_dist = orb_radius + radial_jitter
                ax = int(cx + r_dist * math.cos(cur_ang))
                ay = int(cy + r_dist * math.sin(cur_ang))
                arc_pts.append((ax, ay))
            
            for p_idx in range(len(arc_pts) - 1):
                cv2.line(frame, arc_pts[p_idx], arc_pts[p_idx + 1], (240, 60, 225), 4, cv2.LINE_AA)
                cv2.line(frame, arc_pts[p_idx], arc_pts[p_idx + 1], (255, 255, 255), 1, cv2.LINE_AA)

        if "vfx_hp_spark" in self.images:
            for s_idx in range(count):
                spark_time_step = int(now * 16.0) + s_idx * 13
                rng_sp = random.Random(spark_time_step)
                
                if rng_sp.random() > 0.15:
                    sp_rot = rng_sp.uniform(0, 360)
                    sp_scale = rng_sp.uniform(1.15, 1.45)
                    sp_sz = int(orb_radius * 2 * sp_scale)
                    sp_alpha = rng_sp.uniform(0.85, 1.35)
                    
                    self._draw_additive_sprite(
                        frame,
                        self.images["vfx_hp_spark"],
                        cx, cy,
                        sp_sz,
                        angle=sp_rot,
                        alpha_mult=sp_alpha
                    )

    def draw_hollow_purple_charging(self, frame, cx, cy, ratio, remaining, now):
        """แอนิเมชันชาร์จ Hollow Purple: บอลแดง-น้ำเงินโคจรรอบกันก่อนผสานเป็นบอลม่วงขนาดยักษ์"""
        elapsed = 10.00 * ratio

        # ระยะที่ 1: บอลสีแดงและสีน้ำเงินโคจรรอบจุดศูนย์กลาง
        if elapsed < 4.00:
            stage_prog = elapsed / 4.00
            orbit_r = 160.0 - stage_prog * 15.0
            orbit_angle = -math.pi / 2.0 + (elapsed * 1.2)

            red_x = int(cx + orbit_r * math.cos(orbit_angle))
            red_y = int(cy + orbit_r * math.sin(orbit_angle))

            blue_x = int(cx + orbit_r * math.cos(orbit_angle + math.pi))
            blue_y = int(cy + orbit_r * math.sin(orbit_angle + math.pi))

            seal_img = self.images.get("vfx_charge_seal")
            if seal_img is not None:
                self._draw_additive_sprite(frame, seal_img, cx, cy, 230, angle=now * 20.0, alpha_mult=0.65)

            for trail_idx in [1, 2]:
                lag_angle = orbit_angle - trail_idx * 0.15
                t_rx = int(cx + orbit_r * math.cos(lag_angle))
                t_ry = int(cy + orbit_r * math.sin(lag_angle))
                t_bx = int(cx + orbit_r * math.cos(lag_angle + math.pi))
                t_by = int(cy + orbit_r * math.sin(lag_angle + math.pi))
                if "vfx_hp_aura_red" in self.images:
                    self._draw_additive_sprite(frame, self.images["vfx_hp_aura_red"], t_rx, t_ry, 95, alpha_mult=0.35 / trail_idx)
                if "vfx_hp_aura_blue" in self.images:
                    self._draw_additive_sprite(frame, self.images["vfx_hp_aura_blue"], t_bx, t_by, 95, alpha_mult=0.35 / trail_idx)

            pulse_red = 1.0 + 0.08 * math.sin(now * 7.0)
            size_red = int(205 * pulse_red)
            if "vfx_hp_aura_red" in self.images:
                self._draw_additive_sprite(frame, self.images["vfx_hp_aura_red"], red_x, red_y, size_red, angle=now * 50.0, alpha_mult=1.4)
            if "vfx_hp_flare" in self.images:
                self._draw_additive_sprite(frame, self.images["vfx_hp_flare"], red_x, red_y, int(size_red * 0.55), angle=-now * 80.0, alpha_mult=1.5)

            pulse_blue = 1.0 + 0.08 * math.cos(now * 7.0)
            size_blue = int(205 * pulse_blue)
            if "vfx_hp_aura_blue" in self.images:
                self._draw_additive_sprite(frame, self.images["vfx_hp_aura_blue"], blue_x, blue_y, size_blue, angle=-now * 50.0, alpha_mult=1.4)
            if "vfx_hp_flare" in self.images:
                self._draw_additive_sprite(frame, self.images["vfx_hp_flare"], blue_x, blue_y, int(size_blue * 0.55), angle=now * 80.0, alpha_mult=1.5)

            if np.random.rand() > 0.40:
                self.particles.append(Particle(red_x, red_y, (30, 80, 255), speed_range=(35, 95), life_range=(0.3, 0.5), radius_range=(3, 6)))
                self.particles.append(Particle(blue_x, blue_y, (255, 180, 40), speed_range=(35, 95), life_range=(0.3, 0.5), radius_range=(3, 6)))

        # ระยะที่ 2: บอลทั้งสองถูกดึงดูดเข้าสู่ศูนย์กลาง
        elif elapsed < 6.20:
            stage_prog = (elapsed - 4.00) / 2.20
            curr_r = 145.0 * math.cos(stage_prog * (math.pi / 2.0))

            base_angle_1 = -math.pi / 2.0 + (4.00 * 1.2)
            orbit_angle = base_angle_1 + (stage_prog * 1.4)

            red_x = int(cx + curr_r * math.cos(orbit_angle))
            red_y = int(cy + curr_r * math.sin(orbit_angle))

            blue_x = int(cx + curr_r * math.cos(orbit_angle + math.pi))
            blue_y = int(cy + curr_r * math.sin(orbit_angle + math.pi))

            if "vfx_hp_twirl" in self.images:
                twirl_sz = int(180 + stage_prog * 80)
                self._draw_additive_sprite(frame, self.images["vfx_hp_twirl"], cx, cy, twirl_sz, angle=-now * 160.0, alpha_mult=0.90 + 0.35 * stage_prog)

            s_shrink = max(45, int(180 * (1.0 - stage_prog * 0.65)))
            if "vfx_hp_aura_red" in self.images:
                self._draw_additive_sprite(frame, self.images["vfx_hp_aura_red"], red_x, red_y, s_shrink, alpha_mult=1.1)
            if "vfx_hp_aura_blue" in self.images:
                self._draw_additive_sprite(frame, self.images["vfx_hp_aura_blue"], blue_x, blue_y, s_shrink, alpha_mult=1.1)

            core_sz = int(60 + stage_prog * 95)
            if "vfx_hp_flare" in self.images:
                self._draw_additive_sprite(frame, self.images["vfx_hp_flare"], cx, cy, core_sz, angle=now * 120.0, alpha_mult=1.1 + stage_prog * 0.5)

        # ระยะที่ 3: รวมพลังงานเป็นลูกแก้วสีม่วง
        elif elapsed < 8.20:
            stage_prog = (elapsed - 6.20) / 2.00

            if stage_prog < 0.20 and np.random.rand() > 0.35:
                self.shockwaves.append(Shockwave(cx, cy, (230, 50, 220), max_radius=260, duration=0.45))

            base_sz = int(320 + 120 * stage_prog)
            pulse = int(10 * math.sin(now * 20.0))
            purple_sz = max(280, base_sz + pulse)

            if "vfx_hp_aura_purple" in self.images:
                self._draw_additive_sprite(frame, self.images["vfx_hp_aura_purple"], cx, cy, int(purple_sz * 1.35), angle=now * 40.0, alpha_mult=1.6)
                self._draw_additive_sprite(frame, self.images["vfx_hp_aura_purple"], cx, cy, purple_sz, angle=-now * 60.0, alpha_mult=2.0)

            if "vfx_hp_flare" in self.images:
                self._draw_additive_sprite(frame, self.images["vfx_hp_flare"], cx, cy, int(purple_sz * 0.85), angle=-now * 70.0, alpha_mult=1.8)

            if "vfx_hp_ring" in self.images:
                ring_phase = (now * 2.4) % 1.0
                r_sz = int(purple_sz * (1.15 + ring_phase * 0.55))
                r_al = math.sin(ring_phase * math.pi) * 0.48
                self._draw_additive_sprite(frame, self.images["vfx_hp_ring"], cx, cy, r_sz, angle=now * 15.0, alpha_mult=r_al)

            self._draw_crackling_purple_lightning(frame, cx, cy, purple_sz // 2, now, count=2)

            if np.random.rand() > 0.30:
                self.particles.append(Particle(cx, cy, (230, 50, 220), speed_range=(100, 320), life_range=(0.3, 0.55), radius_range=(4, 8)))

        # ระยะที่ 4: พลังงานเสถียรสมบูรณ์พร้อมยิง
        else:
            final_sz = int(440 + 8 * math.sin(now * 30.0))

            if "vfx_hp_aura_purple" in self.images:
                self._draw_additive_sprite(frame, self.images["vfx_hp_aura_purple"], cx, cy, int(final_sz * 1.35), angle=now * 30.0, alpha_mult=1.7)
                self._draw_additive_sprite(frame, self.images["vfx_hp_aura_purple"], cx, cy, final_sz, angle=-now * 45.0, alpha_mult=2.1)

            if "vfx_hp_flare" in self.images:
                self._draw_additive_sprite(frame, self.images["vfx_hp_flare"], cx, cy, int(final_sz * 0.85), angle=now * 60.0, alpha_mult=1.9)

            if "vfx_hp_ring" in self.images:
                ring_phase = (now * 2.4) % 1.0
                r_sz = int(final_sz * (1.15 + ring_phase * 0.55))
                r_al = math.sin(ring_phase * math.pi) * 0.48
                self._draw_additive_sprite(frame, self.images["vfx_hp_ring"], cx, cy, r_sz, angle=now * 15.0, alpha_mult=r_al)

            self._draw_crackling_purple_lightning(frame, cx, cy, final_sz // 2, now, count=3)

        self.draw_charging_timer_badge(frame, "Hollow Purple", cx, cy, ratio, remaining)

    def draw_hollow_purple_projectile(self, frame, x, y, vx, vy, now, size=180):
        ix, iy = int(x), int(y)
        speed = math.hypot(vx, vy)
        dir_x = (vx / speed) if speed > 0 else 1.0
        dir_y = (vy / speed) if speed > 0 else 0.0

        core_sz = 440 + int(10 * math.sin(now * 25.0))

        for trail_step in [2, 1]:
            t_dist = trail_step * 55
            t_x = int(ix - dir_x * t_dist)
            t_y = int(iy - dir_y * t_dist)
            t_sz = int(core_sz * (1.0 - trail_step * 0.16))
            t_alpha = 0.35 / trail_step
            if "vfx_hp_aura_purple" in self.images:
                self._draw_additive_sprite(frame, self.images["vfx_hp_aura_purple"], t_x, t_y, t_sz, angle=now * 30.0, alpha_mult=t_alpha)

        if "vfx_hp_aura_purple" in self.images:
            self._draw_additive_sprite(frame, self.images["vfx_hp_aura_purple"], ix, iy, int(core_sz * 1.25), angle=now * 45.0, alpha_mult=1.6)
            self._draw_additive_sprite(frame, self.images["vfx_hp_aura_purple"], ix, iy, core_sz, angle=-now * 65.0, alpha_mult=2.0)

        if "vfx_hp_flare" in self.images:
            self._draw_additive_sprite(frame, self.images["vfx_hp_flare"], ix, iy, int(core_sz * 0.85), angle=now * 80.0, alpha_mult=1.8)

        if "vfx_hp_ring" in self.images:
            ring_phase = (now * 2.2) % 1.0
            r_size = int(core_sz * (1.15 + ring_phase * 0.50))
            r_alpha = 0.45
            self._draw_additive_sprite(frame, self.images["vfx_hp_ring"], ix, iy, r_size, angle=now * 12.0, alpha_mult=r_alpha)

        self._draw_crackling_purple_lightning(frame, ix, iy, core_sz // 2, now, count=3)

        if np.random.rand() > 0.20:
            self.particles.append(Particle(ix, iy, (240, 70, 230), speed_range=(60, 180), life_range=(0.20, 0.45), radius_range=(3, 8)))
            self.particles.append(Particle(ix, iy, (255, 240, 255), speed_range=(40, 110), life_range=(0.15, 0.35), radius_range=(2, 5)))

    def spawn_hollow_purple_impact(self, x, y):
        pass

    def draw_generic_charging(self, frame, spell_name, cx, cy, ratio, remaining, now):
        seal_img = self.images.get("vfx_charge_seal")
        if seal_img is not None:
            rot_angle = (now * 110.0) % 360.0
            self._draw_additive_sprite(frame, seal_img, cx, cy, 110, angle=rot_angle, alpha_mult=0.55)

        self.draw_charging_timer_badge(frame, spell_name, cx, cy, ratio, remaining)

    def draw_magic_shield(self, frame, cx, cy, now, radius=180, rem_duration=4.0):
        pulse = 1.0 + 0.05 * math.sin(now * 6.0)

        if "vfx_shield_dome" in self.images:
            dome_img = self.images["vfx_shield_dome"]
            dome_size = int((radius * 2.45) * pulse)
            self._draw_additive_sprite(frame, dome_img, cx, cy, dome_size, angle=0.0, alpha_mult=1.0)
        else:
            pulse_r = int(radius + 8 * math.sin(now * 8))
            cv2.circle(frame, (cx, cy), pulse_r, (255, 220, 0), 4, cv2.LINE_AA)

        if "vfx_shield_rune" in self.images:
            rune_img = self.images["vfx_shield_rune"]
            rune_size = int((radius * 1.75) * pulse)
            rot_angle = (now * 25.0) % 360.0
            self._draw_additive_sprite(frame, rune_img, cx, cy, rune_size, angle=rot_angle, alpha_mult=1.1)

        shield_txt = f"SHIELD ({rem_duration:.1f}s)" if rem_duration > 0 else "SHIELD"
        cv2.putText(frame, shield_txt, (cx - 65, cy - radius - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 230, 80), 2, cv2.LINE_AA)

    def spawn_shield_block_fx(self, hit_x, hit_y):
        if "vfx_shield_hit" in self.images:
            self.sprite_bursts.append(SpriteBurst(self.images["vfx_shield_hit"], hit_x, hit_y, start_size=80, end_size=220, duration=0.28))

        self.shockwaves.append(Shockwave(hit_x, hit_y, (255, 220, 0), max_radius=90, duration=0.30))
        for _ in range(24):
            self.particles.append(Particle(hit_x, hit_y, (255, 230, 100), speed_range=(90, 340), life_range=(0.2, 0.45), radius_range=(2, 5)))

    def spawn_shield_broken_fx(self, cx, cy):
        self.shockwaves.append(Shockwave(cx, cy, (50, 255, 50), max_radius=150, duration=0.45))
        for _ in range(40):
            self.particles.append(Particle(cx, cy, (255, 220, 0), speed_range=(120, 420), life_range=(0.3, 0.6), radius_range=(3, 7)))

    def draw_spell_ready_callout(self, frame, spell_name, wrist_px, is_p1, now, rem_cd=0.0):
        if spell_name == "Hollow Purple":
            if rem_cd > 0:
                badge_w, badge_h = 240, 135
                bx = wrist_px[0] - badge_w // 2
                by = max(15, min(self.h - badge_h - 15, wrist_px[1] - badge_h - 35))
                bx = max(15, min(self.w - badge_w - 15, bx))
                border_col = (0, 0, 255) if int(now * 8) % 2 == 0 else (0, 0, 150)
                cv2.rectangle(frame, (bx, by), (bx + badge_w, by + badge_h), (15, 15, 30), -1)
                cv2.rectangle(frame, (bx, by), (bx + badge_w, by + badge_h), border_col, 2, cv2.LINE_AA)
                cv2.putText(frame, "COOLDOWN", (bx + 40, by + 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.70, (0, 0, 255), 2, cv2.LINE_AA)
                cv2.putText(frame, f"Wait: {rem_cd:.1f}s", (bx + 55, by + 95),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.60, (200, 200, 255), 2, cv2.LINE_AA)
                return

            gojo_img = self.images.get("gojo_shoot_callout")
            if gojo_img is not None:
                gw, gh = 240, 135
                gx1 = wrist_px[0] - gw // 2
                gy1 = max(15, min(self.h - gh - 15, wrist_px[1] - gh - 35))
                gx1 = max(15, min(self.w - gw - 15, gx1))
                gx2 = gx1 + gw
                gy2 = gy1 + gh

                resized = cv2.resize(gojo_img, (gw, gh), interpolation=cv2.INTER_LINEAR)
                roi = frame[gy1:gy2, gx1:gx2]

                if resized.shape[2] == 4:
                    alpha = (resized[:, :, 3:4] / 255.0).astype(np.float32)
                    bgr = resized[:, :, :3].astype(np.float32)
                    roi[:] = np.clip(bgr * alpha + roi.astype(np.float32) * (1.0 - alpha), 0, 255).astype(np.uint8)
                else:
                    roi[:] = resized

                flash = (0, 255, 255) if int(now * 8) % 2 == 0 else (230, 40, 220)
                cv2.rectangle(frame, (gx1, gy1), (gx2, gy2), flash, 2, cv2.LINE_AA)
                return

        cfg = SpellConfig.SPELLS[spell_name]
        spell_col = cfg["color"]

        badge_w, badge_h = 200, 84
        bx = wrist_px[0] - 100
        by = max(90, wrist_px[1] - 125)
        bx = max(20, min(self.w - badge_w - 20, bx))

        if rem_cd > 0:
            border_col = (0, 0, 255) if int(now * 8) % 2 == 0 else (0, 0, 150)
            cv2.rectangle(frame, (bx, by), (bx + badge_w, by + badge_h), (15, 15, 30), -1)
            cv2.rectangle(frame, (bx, by), (bx + badge_w, by + badge_h), border_col, 2, cv2.LINE_AA)
            cv2.putText(frame, "COOLDOWN", (bx + 18, by + 34),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2, cv2.LINE_AA)
            cv2.putText(frame, f"Wait: {rem_cd:.1f}s", (bx + 18, by + 62),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 255), 2, cv2.LINE_AA)
            return

        flash = (0, 255, 255) if int(now * 8) % 2 == 0 else spell_col
        cv2.rectangle(frame, (bx, by), (bx + badge_w, by + badge_h), (20, 20, 20), -1)
        cv2.rectangle(frame, (bx, by), (bx + badge_w, by + badge_h), flash, 2, cv2.LINE_AA)

        spell_icon_drawn = self.draw_texture(frame, f"spell_{spell_name}", bx + 28, by + badge_h // 2, size=46)
        if not spell_icon_drawn:
            cv2.circle(frame, (bx + 28, by + badge_h // 2), 20, spell_col, -1)

        disp_title = spell_name.upper()
        cv2.putText(frame, disp_title, (bx + 56, by + 34),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, f"{cfg['mana_cost']} MP", (bx + 56, by + 58),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 215, 255), 1, cv2.LINE_AA)

        icon_cx = bx + badge_w - 38
        icon_cy = by + badge_h // 2
        cv2.circle(frame, (icon_cx, icon_cy), 28, (45, 45, 45), -1)
        cv2.circle(frame, (icon_cx, icon_cy), 28, flash, 1, cv2.LINE_AA)
        self.draw_texture(frame, f"pose_{spell_name}", icon_cx, icon_cy, size=52)

    def draw_mana_recharge(self, frame, cx, cy, now):
        if "vfx_mana_ring" in self.images:
            for i in range(3):
                phase = ((now * 1.6) + i * 0.33) % 1.0
                ring_size = int(140 * (1.0 - phase) + 20)
                fade = math.sin(phase * math.pi) * 1.1
                self._draw_additive_sprite(frame, self.images["vfx_mana_ring"], cx, cy, ring_size, alpha_mult=fade)
        else:
            for i in range(2):
                phase = ((now * 2.0) + i * 0.5) % 1.0
                r = int(50 * (1.0 - phase) + 12)
                cv2.circle(frame, (cx, cy), r, (255, 215, 30), 2, cv2.LINE_AA)

        if "vfx_mana_vortex" in self.images:
            vortex_size = int(120 + 8 * math.sin(now * 8.0))
            rot_angle = (-now * 320.0) % 360.0
            self._draw_additive_sprite(frame, self.images["vfx_mana_vortex"], cx, cy, vortex_size, angle=rot_angle, alpha_mult=0.95)

        if "vfx_mana_star" in self.images:
            star_pulse = 1.0 + 0.22 * math.sin(now * 12.0)
            star_size = int(68 * star_pulse)
            star_angle = (now * 140.0) % 360.0
            self._draw_additive_sprite(frame, self.images["vfx_mana_star"], cx, cy, star_size, angle=star_angle, alpha_mult=1.3)
        else:
            cv2.circle(frame, (cx, cy), 14, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(frame, (cx, cy), 22, (255, 215, 30), 2, cv2.LINE_AA)

    def spawn_healing_fx(self, hand_x, hand_y, torso_x, torso_y):
        if "vfx_heal_flare" in self.images:
            self.sprite_bursts.append(SpriteBurst(self.images["vfx_heal_flare"], hand_x, hand_y, start_size=50, end_size=150, duration=0.30))

        for _ in range(12):
            self.particles.append(Particle(hand_x, hand_y, (80, 240, 100), speed_range=(60, 200), life_range=(0.2, 0.45), radius_range=(2, 5)))

        if "vfx_heal_flare" in self.images:
            self.sprite_bursts.append(SpriteBurst(self.images["vfx_heal_flare"], torso_x, torso_y, start_size=80, end_size=230, duration=0.45))

        if "vfx_heal_ring" in self.images:
            self.sprite_bursts.append(SpriteBurst(self.images["vfx_heal_ring"], torso_x, torso_y, start_size=70, end_size=280, duration=0.55))

        self.shockwaves.append(Shockwave(torso_x, torso_y, (80, 240, 120), max_radius=130, duration=0.40))

        if "vfx_heal_heart" in self.images:
            for _ in range(4):
                self.rising_hearts.append(RisingHeart(self.images["vfx_heal_heart"], torso_x, torso_y))

        for _ in range(26):
            p = Particle(torso_x + np.random.uniform(-40, 40), torso_y + np.random.uniform(-30, 30),
                         (100, 255, 120) if np.random.rand() > 0.4 else (60, 220, 255),
                         speed_range=(80, 240), life_range=(0.35, 0.65), radius_range=(2, 6))
            p.vy = -abs(p.vy) - 40.0
            self.particles.append(p)

    def draw_fireball_projectile(self, frame, x, y, vx, vy, size=240):
        px, py = int(x), int(y)
        speed = math.hypot(vx, vy)
        dir_x = (vx / speed) if speed > 0 else 1.0
        dir_y = (vy / speed) if speed > 0 else 0.0
        angle = math.degrees(math.atan2(vy, -vx))

        tail_back_x = px - dir_x * 85
        tail_back_y = py - dir_y * 85

        if np.random.rand() > 0.35 and "vfx_fire_smoke" in self.images:
            self.smoke_puffs.append(SmokePuff(self.images["vfx_fire_smoke"], tail_back_x, tail_back_y, size=75, duration=0.45))

        if np.random.rand() > 0.2:
            self.ember_sparks.append(EmberSpark(tail_back_x, tail_back_y))

        if "vfx_fire_tail" in self.images:
            t_size = int(size * 1.15)
            t_px = int(px - dir_x * 45)
            t_py = int(py - dir_y * 45)
            self._draw_additive_sprite(frame, self.images["vfx_fire_tail"], t_px, t_py, t_size, angle=angle, alpha_mult=0.90)

        if "vfx_fire_bullet" in self.images:
            self._draw_additive_sprite(frame, self.images["vfx_fire_bullet"], px, py, size, angle=angle, alpha_mult=1.15)
            cv2.circle(frame, (px, py), 16, (0, 200, 255), -1, cv2.LINE_AA)
            cv2.circle(frame, (px, py), 9, (255, 255, 255), -1, cv2.LINE_AA)
        else:
            cv2.circle(frame, (px, py), 35, (0, 140, 255), -1, cv2.LINE_AA)
            cv2.circle(frame, (px, py), 18, (255, 255, 255), -1, cv2.LINE_AA)

    def spawn_fireball_impact(self, x, y):
        if "vfx_fire_hit" in self.images:
            self.sprite_bursts.append(SpriteBurst(self.images["vfx_fire_hit"], x, y, start_size=130, end_size=310, duration=0.38))

        if "vfx_fire_smoke" in self.images:
            self.sprite_bursts.append(SpriteBurst(self.images["vfx_fire_smoke"], x, y, start_size=90, end_size=240, duration=0.65))

        self.shockwaves.append(Shockwave(x, y, (0, 180, 255), max_radius=120, duration=0.35))

        for _ in range(40):
            self.particles.append(Particle(x, y, (0, 140, 255), speed_range=(150, 480), life_range=(0.3, 0.7), radius_range=(3, 8)))
        for _ in range(20):
            self.ember_sparks.append(EmberSpark(x, y))

    def draw_lightning_projectile(self, frame, x, y, vx, vy, size=260):
        px, py = int(x), int(y)
        angle = math.degrees(math.atan2(-vy, vx))

        if np.random.rand() > 0.15:
            self.electric_particles.append(ElectricArcParticle(px, py))

        if "vfx_lightning_spark" in self.images and np.random.rand() > 0.25:
            s_size = int(size * 0.85)
            self._draw_additive_sprite(frame, self.images["vfx_lightning_spark"], px, py, s_size, angle=angle + np.random.uniform(-10, 10), alpha_mult=1.0)

        if "vfx_lightning_bolt" in self.images:
            jitter_size = int(size * np.random.uniform(0.92, 1.10))
            self._draw_additive_sprite(frame, self.images["vfx_lightning_bolt"], px, py, jitter_size, angle=angle, alpha_mult=1.2)
            cv2.circle(frame, (px, py), 12, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(frame, (px, py), 20, (50, 240, 255), 2, cv2.LINE_AA)
        else:
            cv2.circle(frame, (px, py), 18, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(frame, (px, py), 26, (0, 240, 255), 3, cv2.LINE_AA)

    def spawn_lightning_impact(self, x, y):
        if "vfx_lightning_hit" in self.images:
            self.sprite_bursts.append(SpriteBurst(self.images["vfx_lightning_hit"], x, y, start_size=110, end_size=320, duration=0.32))

        self.shockwaves.append(Shockwave(x, y, (255, 255, 255), max_radius=110, duration=0.25))
        self.shockwaves.append(Shockwave(x, y, (0, 240, 255), max_radius=150, duration=0.35))

        for _ in range(35):
            self.electric_particles.append(ElectricArcParticle(x, y))
        for _ in range(25):
            self.particles.append(Particle(x, y, (30, 240, 255), speed_range=(160, 480), life_range=(0.25, 0.55), radius_range=(2, 6)))

    def draw_terra_projectile(self, frame, x, y, vx, vy, now, size=125):
        px, py = int(x), int(y)
        speed = math.hypot(vx, vy)
        dir_x = (vx / speed) if speed > 0 else 1.0
        dir_y = (vy / speed) if speed > 0 else 0.0

        tail_x = px - dir_x * (size * 0.35)
        tail_y = py - dir_y * (size * 0.35)

        if np.random.rand() > 0.15:
            for _ in range(np.random.randint(1, 3)):
                self.rock_shards.append(RockShard(tail_x, tail_y, dir_x, dir_y))

        dust_img = self.images.get("vfx_terra_dust", self.images.get("vfx_fireball_smoke"))
        if np.random.rand() > 0.40 and dust_img is not None:
            self.smoke_puffs.append(SmokePuff(dust_img, tail_x, tail_y, size=48, duration=0.32))

        cv2.circle(frame, (px, py), int(size * 0.32), (32, 40, 48), -1, cv2.LINE_AA)

        spin_dir = 1.0 if vx >= 0 else -1.0
        rot_angle = (now * 520.0 * spin_dir) % 360.0

        if "vfx_terra_boulder" in self.images:
            self._draw_normal_sprite(frame, self.images["vfx_terra_boulder"], px, py, size, angle=rot_angle, alpha_mult=1.0)
            cv2.circle(frame, (px, py), int(size * 0.35), (20, 140, 215), 1, cv2.LINE_AA)
        else:
            cv2.circle(frame, (px, py), 26, (32, 40, 48), -1, cv2.LINE_AA)

    def spawn_terra_impact(self, x, y, pierced_shield=False):
        shatter_size = 320 if pierced_shield else 240
        debris_size = 260 if pierced_shield else 190

        if "vfx_terra_shatter" in self.images:
            self.sprite_bursts.append(SpriteBurst(self.images["vfx_terra_shatter"], x, y, start_size=100, end_size=shatter_size, duration=0.38))

        if "vfx_terra_debris" in self.images:
            self.sprite_bursts.append(SpriteBurst(self.images["vfx_terra_debris"], x, y, start_size=80, end_size=debris_size, duration=0.50))

        shock_radius = 150 if pierced_shield else 110
        self.shockwaves.append(Shockwave(x, y, (30, 80, 130), max_radius=shock_radius, duration=0.35))

        count = 45 if pierced_shield else 30
        for _ in range(count):
            self.particles.append(Particle(x, y, (55, 70, 85), speed_range=(120, 440), life_range=(0.25, 0.60), radius_range=(3, 7)))

    def spawn_impact_fx(self, x, y, color, count=24):
        self.shockwaves.append(Shockwave(x, y, color))
        for _ in range(count):
            self.particles.append(Particle(x, y, color, speed_range=(100, 380), life_range=(0.3, 0.6), radius_range=(3, 6)))

    def spawn_trail_particle(self, x, y, color):
        self.particles.append(Particle(x, y, color, speed_range=(10, 50), life_range=(0.15, 0.35), radius_range=(3, 7)))

    def spawn_mana_recharge_fx(self, hand_x, hand_y, count=3):
        for _ in range(count):
            self.mana_particles.append(InwardManaParticle(hand_x, hand_y))

    def update_vfx(self, dt):
        """อัปเดตสถานะและอายุขัยของอนุภาคทั้งหมดตามเวลาจริง (Delta Time)"""
        for p in list(self.particles):
            p.update(dt)
            if p.life <= 0:
                self.particles.remove(p)

        for ep in list(self.ember_sparks):
            ep.update(dt)
            if ep.life <= 0:
                self.ember_sparks.remove(ep)

        for ie in list(self.inward_embers):
            ie.update(dt)
            if ie.life <= 0 or ie.dist <= 5:
                self.inward_embers.remove(ie)

        for rs in list(self.rock_shards):
            rs.update(dt)
            if rs.life <= 0:
                self.rock_shards.remove(rs)

        for rh in list(self.rising_hearts):
            rh.update(dt)
            if rh.timer >= rh.duration:
                self.rising_hearts.remove(rh)

        for el in list(self.electric_particles):
            el.update(dt)
            if el.life <= 0:
                self.electric_particles.remove(el)

        for sp in list(self.smoke_puffs):
            sp.update(dt)
            if sp.timer >= sp.duration:
                self.smoke_puffs.remove(sp)

        for sb in list(self.sprite_bursts):
            sb.update(dt)
            if sb.timer >= sb.duration:
                self.sprite_bursts.remove(sb)

        for mp_p in list(self.mana_particles):
            mp_p.update(dt)
            if mp_p.dist <= 6 or mp_p.life <= 0:
                self.mana_particles.remove(mp_p)

        for sw in list(self.shockwaves):
            sw.update(dt)
            if sw.timer >= sw.duration:
                self.shockwaves.remove(sw)

        for ab in list(self.awakened_banners):
            ab.update(dt)
            if ab.timer >= ab.duration:
                self.awakened_banners.remove(ab)

    def draw_vfx(self, frame):
        """วาดอนุภาคทั้งหมดลงบนเฟรมตามลำดับเลเยอร์ (Layer Stacking)"""
        for sp in self.smoke_puffs:
            sp.draw(frame)
        for ep in self.ember_sparks:
            ep.draw(frame)
        for ie in self.inward_embers:
            ie.draw(frame)
        for rs in self.rock_shards:
            rs.draw(frame)
        for rh in self.rising_hearts:
            rh.draw(frame)
        for el in self.electric_particles:
            el.draw(frame)
        for sb in self.sprite_bursts:
            sb.draw(frame)
        for sw in self.shockwaves:
            sw.draw(frame)
        for p in self.particles:
            p.draw(frame)
        for mp_p in self.mana_particles:
            mp_p.draw(frame)
        for ab in self.awakened_banners:
            ab.draw(frame, self.w, self.h)

    def draw_soul_core(self, frame, torso_box, is_shielded, now):
        """วาดแกนดวงจิต (Soul Core Diamond) บริเวณกึ่งกลางลำตัวของผู้เล่น"""
        x1, y1, x2, y2 = torso_box
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2

        pulse = 1.0 + 0.12 * math.sin(now * 5.0)
        r_w = int(32 * pulse)
        r_h = int(50 * pulse)

        diamond_pts = np.array([
            [cx, cy - r_h],
            [cx + r_w, cy],
            [cx, cy + r_h],
            [cx - r_w, cy]
        ], np.int32)

        aura_r = int(65 * pulse)
        aura_color = (255, 220, 0) if is_shielded else (0, 215, 255)
        cv2.circle(frame, (cx, cy), aura_r, (50, 50, 50), 1, cv2.LINE_AA)
        cv2.circle(frame, (cx, cy), aura_r - 12, aura_color, 1, cv2.LINE_AA)

        cv2.fillPoly(frame, [diamond_pts], aura_color, cv2.LINE_AA)
        cv2.polylines(frame, [diamond_pts], True, (255, 255, 255), 2, cv2.LINE_AA)

        inner_diamond = np.array([
            [cx, cy - r_h // 2],
            [cx + r_w // 2, cy],
            [cx, cy + r_h // 2],
            [cx - r_w // 2, cy]
        ], np.int32)
        cv2.fillPoly(frame, [inner_diamond], (255, 255, 255), cv2.LINE_AA)

    def draw_spell_icons(self, frame, p_state, is_p1, now):
        """วาดการ์ดไอคอนคาถาด้านล่างจอ แสดงรูปวาด ท่าทาง คูลดาวน์ และค่าร่ายมานา"""
        spell_keys = [
            ("Fireball", "FIRE", 30),
            ("Magic Shield", "SHIELD", 25),
            ("Lightning Strike", "LIGHTN", 50),
            ("Terra Boulder", "TERRA", 30),
            ("Healing Light", "HEAL", 35)
        ]

        card_w = 68
        card_h = 96
        spacing = 8
        total_w = len(spell_keys) * card_w + (len(spell_keys) - 1) * spacing
        start_x = 20 if is_p1 else (self.w - total_w - 20)
        start_y = self.h - 110

        for i, (name, label, cost) in enumerate(spell_keys):
            cfg = SpellConfig.SPELLS[name]
            ix = start_x + i * (card_w + spacing)
            iy = start_y

            cd_until = p_state.cooldowns.get(name, 0.0)
            rem_cd = max(0.0, cd_until - now)
            is_on_cd = (rem_cd > 0)
            has_mana = (p_state.mana >= cost)
            is_active_ready = (p_state.state == "RECOGNIZED" and p_state.pending_spell == name)

            if is_on_cd:
                bg_col = (18, 18, 18)
                border_col = (50, 50, 50)
            elif not has_mana:
                bg_col = (30, 20, 20)
                border_col = (60, 60, 120)
            elif is_active_ready:
                flash_gold = (0, 255, 255) if int(now * 8) % 2 == 0 else (0, 180, 255)
                bg_col = (45, 55, 35)
                border_col = flash_gold
            else:
                bg_col = (38, 38, 38)
                border_col = cfg["color"]

            cv2.rectangle(frame, (ix, iy), (ix + card_w, iy + card_h), bg_col, -1)
            cv2.rectangle(frame, (ix, iy), (ix + card_w, iy + card_h), border_col, 3 if is_active_ready else 2)

            icx = ix + card_w // 2

            shape_drawn = self.draw_texture(frame, f"shape_{name}", icx, iy + 18, size=28)
            if not shape_drawn:
                cv2.circle(frame, (icx, iy + 18), 9, cfg["color"], 2)

            cv2.line(frame, (ix + 8, iy + 33), (ix + card_w - 8, iy + 33), (60, 60, 60), 1)
            self.draw_texture(frame, f"pose_{name}", icx, iy + 52, size=32)

            cv2.putText(frame, label, (ix + 5, iy + 76), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (220, 220, 220), 1)
            cv2.putText(frame, f"{cost} MP", (ix + 5, iy + 90), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 215, 255) if has_mana else (100, 100, 100), 1)

            if is_on_cd:
                cd_txt = f"{rem_cd:.1f}s" if rem_cd < 10 else f"{int(rem_cd)}s"
                cv2.rectangle(frame, (ix + 2, iy + 20), (ix + card_w - 2, iy + 65), (0, 0, 0), -1)
                cv2.putText(frame, cd_txt, (ix + 8, iy + 46), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 0, 255), 2, cv2.LINE_AA)