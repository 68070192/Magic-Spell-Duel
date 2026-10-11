"""
Module: sound_manager.py
Description: ระบบจัดการเสียงประกอบและดนตรี (Sound & Audio Management Engine)
             ควบคุมการเล่นเพลงพื้นหลัง (BGM), เสียงเอฟเฟกต์เวทมนตร์ (Magic SFX),
             และเสียงสถานะต่อเนื่องผ่านระบบจัดสรรช่องเสียงอิสระ (Dedicated Reserved Channels)
"""

import os
import pygame
from resource_helper import get_resource_path, get_base_dir


class SoundManager:
    """
    คลาสจัดการระบบเสียงทั้งหมดของเกมผ่าน Pygame Mixer
    แยกการทำงานระหว่างเสียงลูปประจำการกระทำ และเสียงเอฟเฟกต์ทั่วไปเพื่อป้องกันปัญหาเสียงตัด
    """

    def __init__(self, master_volume=1.0):
        self.master_volume = master_volume
        self.sounds = {}
        self.channel_map = {}
        self.is_initialized = False

        self.search_dirs = [
            get_resource_path("assets/sounds"),
            get_resource_path("assets/audio"),
            get_resource_path("assets"),
            get_base_dir(),
        ]

        self._init_mixer()
        if self.is_initialized:
            self._load_all_sounds()

    def _init_mixer(self):
        """กำหนดค่า Pygame Mixer และจองช่อง 0-7 สำหรับเสียงลูปโดยเฉพาะ"""
        try:
            pygame.mixer.pre_init(44100, -16, 2, 1024)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(32)
            pygame.mixer.set_reserved(8)

            # กำหนดช่องเสียงประจำแต่ละ Action ล่วงหน้า ป้องกันการแย่งช่องกัน
            self.channel_map = {
                "draw_P1": pygame.mixer.Channel(0),
                "draw_P2": pygame.mixer.Channel(1),
                "charge_P1": pygame.mixer.Channel(2),
                "charge_P2": pygame.mixer.Channel(3),
                "shield_P1": pygame.mixer.Channel(4),
                "shield_P2": pygame.mixer.Channel(5),
                "recharge_P1": pygame.mixer.Channel(6),
                "recharge_P2": pygame.mixer.Channel(7),
            }

            self.is_initialized = True
            print("[SoundManager] Pygame Audio Engine Initialized with 32 Dedicated Channels")
        except Exception as e:
            print(f"[SoundManager] Audio Init Error: {e}")
            self.is_initialized = False

    def _clean_name(self, text):
        """ปรับแต่งสตริงชื่อไฟล์เพื่อใช้ในการค้นหาแบบยืดหยุ่น (Fuzzy Matching)"""
        t = text.lower().replace(" ", "").replace("_", "").replace("-", "")
        if t.startswith("sfx"):
            t = t[3:]
        return t

    def _find_audio_file(self, candidate_names):
        """ค้นหาไฟล์เสียงจากชื่อที่ระบุและรูปแบบนามสกุลที่เป็นไปได้ทั้งหมด"""
        if isinstance(candidate_names, str):
            candidate_names = [candidate_names]

        # 1. ค้นหาแบบตรงตามชื่อไฟล์
        for s_dir in self.search_dirs:
            if not os.path.exists(s_dir):
                continue
            for name in candidate_names:
                base, ext = os.path.splitext(name)
                exts = [ext] if ext else [".wav", ".mp3", ".ogg"]
                for e in exts:
                    target = os.path.join(s_dir, f"{base}{e}")
                    if os.path.isfile(target):
                        return target

        # 2. ค้นหาแบบยืดหยุ่น (Fuzzy Matching) ในไดเรกทอรี
        clean_candidates = [self._clean_name(os.path.splitext(c)[0]) for c in candidate_names]
        for s_dir in self.search_dirs:
            if not os.path.exists(s_dir):
                continue
            try:
                files_in_dir = os.listdir(s_dir)
            except Exception:
                continue

            for f in files_in_dir:
                f_base, f_ext = os.path.splitext(f)
                if f_ext.lower() not in [".mp3", ".wav", ".ogg"]:
                    continue

                f_clean = self._clean_name(f_base)
                for c_clean in clean_candidates:
                    if f_clean == c_clean:
                        return os.path.join(s_dir, f)

        return None

    def _load_sound(self, key, candidates, volume=1.0):
        """โหลดไฟล์เสียงและบันทึกลงใน Dictionary ตามระดับความดังที่กำหนด"""
        if not self.is_initialized:
            return
        fpath = self._find_audio_file(candidates)
        if fpath:
            try:
                snd = pygame.mixer.Sound(fpath)
                snd.set_volume(volume * self.master_volume)
                self.sounds[key] = snd
            except Exception as e:
                print(f"[SoundManager] Failed to load '{key}': {e}")

    def _load_all_sounds(self):
        """ลงทะเบียนและโหลดไฟล์เสียงประกอบทั้งหมดของเกม"""
        sound_mappings = {
            # สกิลร่าย (Cast SFX)
            "cast_Fireball": (["sfx_cast_fire.wav", "sfx_cast_fireball", "cast_fire"], 0.95),
            "cast_Magic Shield": (["sfx_cast_shield.wav", "cast_shield"], 0.90),
            "cast_Lightning Strike": (["sfx_cast_lightning.wav", "cast_lightning"], 1.0),
            "cast_Terra Boulder": (["sfx_cast_terra.wav", "cast_terra"], 0.95),
            "cast_Healing Light": (["sfx_cast_heal.wav", "cast_heal"], 0.90),
            "cast_Hollow Purple": (["cast_Hollow-Purple.wav", "cast_hollow_purple"], 1.4),

            # สกิลชาร์จ (Charge Loop SFX)
            "charge_Fireball": (["sfx_charge_fire.wav", "charge_fire"], 0.75),
            "charge_Magic Shield": (["sfx_charge_shield.wav", "charge_shield"], 0.75),
            "charge_Lightning Strike": (["sfx_charge_lightning.wav", "charge_lightning"], 0.8),
            "charge_Terra Boulder": (["sfx_charge_terra.wav", "charge_terra"], 0.75),
            "charge_Healing Light": (["sfx_charge_heal.wav", "charge_heal"], 0.75),
            "charge_Hollow Purple": (["charge_Hollow-Purple.wav", "charge_hollow_purple"], 1.3),

            # สกิลปะทะ (Hit & Shield SFX)
            "hit_Fireball": (["sfx_hit_fire.wav", "hit_fire"], 1.0),
            "hit_Lightning Strike": (["sfx_hit_lightning.wav", "hit_lightning"], 1.1),
            "hit_Terra Boulder": (["sfx_hit_terra.wav", "hit_terra"], 1.0),
            "shield_block": (["sfx_shield_block.wav", "shield_block"], 0.95),
            "shield_broken": (["sfx_shield_broken.wav", "shield_broken"], 1.1),

            # เสียงลูปสถานะ (Continuous Loop SFX)
            "shield_loop": (["sfx_loop_shield.wav", "shield_loop"], 0.5),
            "draw_loop": (["sfx_draw.wav", "sfx_draw_loop"], 0.45),
            "recharge_loop": (["sfx_recharge_loop.wav", "recharge_loop"], 0.65),

            # ระบบและอินเทอร์เฟซ (UI & System SFX)
            "chant_awakened": (["chant_awakened.wav", "chant_awakened"], 1.3),
            "spell_ready": (["sfx_spell_ready.wav", "spell_ready"], 0.85),
            "no_mana": (["sfx_no_mana.wav", "no_mana"], 0.75),

            # เสียงผู้บรรยาย (Announcer SFX)
            "announcer_round1": (["announcer_round1.mp3", "round1"], 1.1),
            "announcer_round2": (["announcer_round2.mp3", "round2"], 1.1),
            "announcer_round_final": (["announcer_round_final.mp3", "round_final"], 1.15),
            "announcer_duel": (["announcer_duel.mp3", "duel"], 1.2),
            "announcer_ko": (["announcer_ko.mp3", "ko"], 1.25),
            "announcer_p1_win": (["announcer_p1_win.mp3", "p1_win"], 1.2),
            "announcer_p2_win": (["announcer_p2_win.mp3", "p2_win"], 1.2),
        }

        for key, (candidates, vol) in sound_mappings.items():
            self._load_sound(key, candidates, vol)

        print(f"[SoundManager] Successfully registered {len(self.sounds)} sound assets")

    def play_bgm(self, track="title", loop=True, volume_scale=0.5):
        """ควบคุมการเล่นดนตรีประกอบพื้นหลังผ่านช่องเพลงหลักของ Pygame"""
        if not self.is_initialized:
            return
        bgm_map = {
            "title": ["bgm_title.mp3", "bgm_title"],
            "battle": ["bgm_battle.mp3", "bgm_battle"],
            "victory": ["bgm_victory.mp3", "bgm_victory"]
        }
        candidates = bgm_map.get(track, ["bgm_battle.mp3"])
        fpath = self._find_audio_file(candidates)
        if fpath:
            try:
                pygame.mixer.music.load(fpath)
                pygame.mixer.music.set_volume(volume_scale * self.master_volume)
                pygame.mixer.music.play(-1 if loop else 0)
            except Exception as e:
                print(f"[SoundManager] BGM Error: {e}")

    def stop_bgm(self):
        """หยุดการเล่นเพลงพื้นหลังทั้งหมด"""
        if self.is_initialized:
            pygame.mixer.music.stop()

    def play_sfx(self, key, volume_scale=1.0):
        """เล่นเสียงเอฟเฟกต์แบบครั้งเดียว โดยใช้ช่องสัญญาณอิสระ 8-31 อัตโนมัติ"""
        if not self.is_initialized or key not in self.sounds:
            return
        try:
            snd = self.sounds[key]
            snd.set_volume(min(1.0, volume_scale * self.master_volume))
            snd.play()
        except Exception as e:
            print(f"[SoundManager] SFX Error '{key}': {e}")

    def play_announcer(self, key, volume_scale=1.15):
        """เล่นเสียงประกาศของผู้บรรยาย"""
        self.play_sfx(key, volume_scale=volume_scale)

    # --------------------------------------------------------------------------
    # การควบคุมเสียงลูปประจำการกระทำ (ใช้ช่อง 0-7 ที่จองไว้โดยเฉพาะ)
    # --------------------------------------------------------------------------

    def start_draw_sound(self, tag):
        ch = self.channel_map.get(f"draw_{tag}")
        snd = self.sounds.get("draw_loop")
        if ch and snd and not ch.get_busy():
            ch.play(snd, loops=-1)

    def stop_draw_sound(self, tag):
        ch = self.channel_map.get(f"draw_{tag}")
        if ch and ch.get_busy():
            ch.stop()

    def start_charge_sound(self, tag, spell_name):
        ch = self.channel_map.get(f"charge_{tag}")
        key = f"charge_{spell_name}"
        snd = self.sounds.get(key, self.sounds.get("charge_Fireball"))
        if ch and snd:
            ch.play(snd, loops=-1)

    def ensure_charge_sound(self, tag, spell_name):
        ch = self.channel_map.get(f"charge_{tag}")
        if ch and not ch.get_busy():
            self.start_charge_sound(tag, spell_name)

    def stop_charge_sound(self, tag):
        ch = self.channel_map.get(f"charge_{tag}")
        if ch and ch.get_busy():
            ch.stop()

    def set_shield_loop_sound(self, tag, is_active):
        ch = self.channel_map.get(f"shield_{tag}")
        snd = self.sounds.get("shield_loop")
        if not ch or not snd:
            return
        if is_active and not ch.get_busy():
            ch.play(snd, loops=-1)
        elif not is_active and ch.get_busy():
            ch.stop()

    def set_recharge_sound(self, tag, is_active):
        ch = self.channel_map.get(f"recharge_{tag}")
        snd = self.sounds.get("recharge_loop")
        if not ch or not snd:
            return
        if is_active and not ch.get_busy():
            ch.play(snd, loops=-1)
        elif not is_active and ch.get_busy():
            ch.stop()