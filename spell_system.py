"""
Module: spell_system.py
Description: ระบบกำหนดค่าคุณสมบัติของเวทมนตร์ (Spell Configurations) และระบบจัดการสถานะ
             การต่อสู้ของผู้เล่น (Player Combat State Machine) ควบคุมวงจรของคาถา 
             การหักลบและฟื้นฟูมานา การคำนวณคูลดาวน์ และการตรวจสอบเงื่อนไขปลดล็อกสกิลพิเศษ
"""

import time
import config as cfg


class SpellConfig:
    """
    คลังข้อมูลค่าคงที่และคุณสมบัติของเวทมนตร์แต่ละชนิด (Balance Parameters)
    ประกอบด้วย พลังโจมตี, ค่าร่ายมานา, คูลดาวน์, ระยะเวลาชาร์จ, ความเร็ว, และท่าทางTrigger
    """

    SPELLS = {
        "Fireball": {
            "name": "Fireball",
            "damage": 20.0,
            "mana_cost": 30.0,
            "cooldown": 10.0,
            "charge_time": 1.3,
            "speed": 620.0,
            "radius": 24,
            "pierces_shield": False,
            "color": (0, 140, 255),
            "trigger_gesture": "OPEN_HAND",
            "shape": "Triangle"
        },
        "Magic Shield": {
            "name": "Magic Shield",
            "damage": 0.0,
            "mana_cost": 25.0,
            "cooldown": 15.0,
            "charge_time": 0.8,
            "speed": 0.0,
            "radius": 0,
            "pierces_shield": False,
            "color": (255, 220, 0),
            "trigger_gesture": "FIST",
            "shape": "Circle"
        },
        "Lightning Strike": {
            "name": "Lightning Strike",
            "damage": 40.0,
            "mana_cost": 50.0,
            "cooldown": 30.0,
            "charge_time": 2.5,
            "speed": 1150.0,
            "radius": 18,
            "pierces_shield": False,
            "color": (0, 240, 255),
            "trigger_gesture": "PEACE",
            "shape": "Z-Stroke"
        },
        "Terra Boulder": {
            "name": "Terra Boulder",
            "damage": 20.0,
            "mana_cost": 30.0,
            "cooldown": 15.0,
            "charge_time": 1.8,
            "speed": 440.0,
            "radius": 26,
            "pierces_shield": True,
            "color": (45, 140, 215),
            "trigger_gesture": "THREE_FINGERS",
            "shape": "Square"
        },
        "Healing Light": {
            "name": "Healing Light",
            "damage": 0.0,
            "mana_cost": 35.0,
            "cooldown": 20.0,
            "charge_time": 1.5,
            "speed": 0.0,
            "radius": 0,
            "pierces_shield": False,
            "color": (80, 255, 100),
            "trigger_gesture": "THUMBS_UP",
            "shape": "Heart"
        },
        "Hollow Purple": {
            "name": "Hollow Purple",
            "damage": 999.0,
            "mana_cost": 65.0,
            "cooldown": 12.0,
            "charge_time": 10.0,
            "speed": 850.0,
            "radius": 55,
            "pierces_shield": True,
            "color": (220, 40, 200),
            "trigger_gesture": "OK_SIGN",
            "shape": "Infinity"
        }
    }


class PlayerCombatState:
    """
    คลาสจัดการสถานะการต่อสู้ของผู้เล่นรายบุคคล (Player Combat State Manager)
    ควบคุม State Flow: IDLE -> RECOGNIZED -> CHARGING -> IDLE
    """

    def __init__(self, is_p1=True):
        self.is_p1 = is_p1

        # ทรัพยากรพื้นฐานของผู้เล่น
        self.hp = 100.0
        self.mana = 100.0

        # ตัวแปรสถานะและวงจรการร่ายเวท
        self.state = "IDLE"  # สถานะที่เป็นไปได้: IDLE, RECOGNIZED, CHARGING
        self.pending_spell = None
        self.charging_spell = None
        self.charge_timer = 0.0
        self.recognized_start_time = None

        # พิกัดและวิถีการเล็ง
        self.cast_origin = None
        self.cast_target = None
        self.aim_target = None

        # สถานะการป้องกันและการฟื้นฟู
        self.shield_active = False
        self.shield_timer = 0.0
        self.is_recharging = False

        # ระบบคูลดาวน์และประวัติการใช้สกิล
        self.cooldowns = {}
        self.cast_history = set()

        # สถานะสกิลลับขั้นสูง
        self.hollow_purple_unlocked = False
        self.infinity_barrier_active = False

    def update(self, dt):
        """อัปเดตตัวนับเวลาของโล่ป้องกัน การชาร์จเวท และการคำนวณอัตราฟื้นฟูมานาตามเงื่อนไข"""
        # อัปเดตระยะเวลาคงอยู่ของโล่ Magic Shield
        if self.shield_active:
            self.shield_timer -= dt
            if self.shield_timer <= 0.0:
                self.shield_active = False
                self.shield_timer = 0.0

        # อัปเดตระยะเวลาชาร์จเวทมนตร์
        if self.state == "CHARGING":
            self.charge_timer += dt

        # การฟื้นฟูมานา: ระงับการฟื้นฟูทันทีหากกางโล่อยู่ หรืออยู่ในระหว่างการยืนชาร์จเวท
        if not self.shield_active and self.state != "CHARGING":
            if self.is_recharging:
                self.mana = min(100.0, self.mana + 8.0 * dt)
            else:
                self.mana = min(100.0, self.mana + 1.5 * dt)

    def has_cast_all_basic_spells(self):
        """ตรวจสอบว่าผู้เล่นเคยร่ายคาถาพื้นฐานครบทั้ง 5 ชนิดแล้วหรือไม่ (เงื่อนไข Awakened)"""
        basic = {"Fireball", "Magic Shield", "Lightning Strike", "Terra Boulder", "Healing Light"}
        return basic.issubset(self.cast_history)

    def on_shape_recognized(self, spell_name, current_time=None):
        """
        ตรวจสอบเงื่อนไขเมื่อวาดสัญลักษณ์สำเร็จ เพื่อเปลี่ยนสถานะเป็น RECOGNIZED (พร้อมรอทำท่า Trigger)
        Return: (ความสำเร็จ: bool, ข้อความสถานะ: str)
        """
        if spell_name not in SpellConfig.SPELLS:
            return False, "UNKNOWN_SPELL"

        if spell_name == "Hollow Purple" and not self.hollow_purple_unlocked:
            return False, "LOCKED"

        cfg_spell = SpellConfig.SPELLS[spell_name]

        # ตรวจสอบคูลดาวน์คงเหลือ
        if current_time is not None:
            cd_until = self.cooldowns.get(spell_name, 0.0)
            if current_time < cd_until:
                rem = cd_until - current_time
                return False, f"COOLDOWN:{rem:.1f}"

        # ตรวจสอบปริมาณมานา
        if self.mana < cfg_spell["mana_cost"]:
            return False, "NO_MANA"

        self.state = "RECOGNIZED"
        self.pending_spell = spell_name
        self.recognized_start_time = current_time if current_time is not None else time.time()
        return True, "READY"

    def try_trigger_spell(self, gesture, start_ray, end_ray):
        """
        ตรวจสอบท่าทางมือเพื่อเริ่มกระบวนการชาร์จเวทมนตร์ (Transition เข้าสู่สถานะ CHARGING)
        หักลบมานา และบันทึกพิกัดตั้งต้นของวิถีการยิง
        """
        if self.state != "RECOGNIZED" or self.pending_spell is None:
            return False, "NOT_RECOGNIZED"

        cfg_spell = SpellConfig.SPELLS[self.pending_spell]
        if gesture == cfg_spell["trigger_gesture"]:
            if self.mana < cfg_spell["mana_cost"]:
                return False, "NO_MANA"

            self.mana -= cfg_spell["mana_cost"]
            self.state = "CHARGING"
            self.charging_spell = self.pending_spell
            self.charge_timer = 0.0
            self.cast_origin = start_ray
            self.cast_target = end_ray
            self.aim_target = end_ray
            self.pending_spell = None
            self.recognized_start_time = None
            return True, "CHARGING_STARTED"

        return False, "WRONG_GESTURE"

    def update_aim(self, start_ray, end_ray):
        """อัปเดตตำแหน่งจุดกำเนิดและจุดเป้าหมายของการเล็งระหว่างการชาร์จแบบเรียลไทม์"""
        self.cast_origin = start_ray
        self.cast_target = end_ray
        self.aim_target = end_ray

    def get_charging_progress(self):
        """
        คำนวณความคืบหน้าของการชาร์จเวทมนตร์
        Return: (อัตราส่วนความคืบหน้า 0.0-1.0, เวลาที่เหลือในหน่วยวินาที)
        """
        if self.state != "CHARGING" or self.charging_spell is None:
            return 0.0, 0.0

        max_t = SpellConfig.SPELLS[self.charging_spell]["charge_time"]
        ratio = min(1.0, self.charge_timer / max_t) if max_t > 0 else 1.0
        remaining = max(0.0, max_t - self.charge_timer)
        return ratio, remaining

    def finish_cast(self):
        """
        ประมวลผลเมื่อชาร์จเวทมนตร์เสร็จสมบูรณ์: บันทึกคูลดาวน์, เพิ่มประวัติการร่าย, 
        และรีเซ็ตสถานะผู้เล่นกลับสู่ IDLE พร้อมคืนค่าคุณสมบัติของคาถาเพื่อนำไปสร้างโปรเจกไทล์
        """
        if self.state != "CHARGING" or self.charging_spell is None:
            return None, None

        spell_name = self.charging_spell
        s_cfg = SpellConfig.SPELLS[spell_name]

        now = time.time()
        self.cooldowns[spell_name] = now + s_cfg["cooldown"]
        self.cast_history.add(spell_name)

        if spell_name == "Magic Shield":
            self.shield_active = True
            self.shield_timer = 5.5

        self.state = "IDLE"
        self.charging_spell = None
        self.charge_timer = 0.0
        return spell_name, s_cfg