"""
Module: gesture_recognizer.py
Description: ระบบตรวจจับและจำแนกท่าทางของมือ (Hand Gesture Recognition) โดยใช้พิกัดจุดเด่น 
             (Landmarks) จาก MediaPipe Hands ทำหน้าที่ประเมินการเหยียด/งอของนิ้ว, คำนวณทิศทางการเล็ง 
             (Aiming Ray), และติดตามลำดับท่าร่ายคอมโบ (Chant Sequence Tracking)
"""

import math
import mediapipe as mp


class GestureRecognizer:
    """
    คลาสสำหรับประมวลผลและจำแนกท่าทางของมือจากพิกัด Landmark
    ใช้การวัดระยะสัมพัทธ์กับขนาดฝ่ามือ (Dynamic Palm Scale) เพื่อความแม่นยำในทุกระยะกล้อง
    """

    def __init__(self):
        self.mp_hands = mp.solutions.hands

    def get_palm_scale(self, lm):
        """คำนวณขนาดฝ่ามือจริง (Wrist -> Middle Finger MCP) เพื่อใช้เป็นค่าอ้างอิงระยะทางสัมพัทธ์"""
        wrist = lm[self.mp_hands.HandLandmark.WRIST]
        middle_mcp = lm[self.mp_hands.HandLandmark.MIDDLE_FINGER_MCP]
        scale = math.hypot(wrist.x - middle_mcp.x, wrist.y - middle_mcp.y)
        return max(0.015, scale)

    def get_finger_status(self, hand_landmarks):
        """
        ตรวจสอบสถานะการเหยียด (True) หรือพับงอ (False) ของนิ้วทั้ง 5
        Return: List[bool] เรียงลำดับ [โป้ง, ชี้, กลาง, นาง, ก้อย]
        """
        lm = hand_landmarks.landmark
        palm_scale = self.get_palm_scale(lm)
        wrist = lm[self.mp_hands.HandLandmark.WRIST]

        fingers = []

        # 1. การตรวจสอบนิ้วโป้ง (Thumb)
        thumb_tip = lm[self.mp_hands.HandLandmark.THUMB_TIP]
        thumb_ip = lm[self.mp_hands.HandLandmark.THUMB_IP]
        pinky_mcp = lm[self.mp_hands.HandLandmark.PINKY_MCP]
        index_mcp = lm[self.mp_hands.HandLandmark.INDEX_FINGER_MCP]

        dist_tip_pinky = math.hypot(thumb_tip.x - pinky_mcp.x, thumb_tip.y - pinky_mcp.y)
        dist_ip_pinky = math.hypot(thumb_ip.x - pinky_mcp.x, thumb_ip.y - pinky_mcp.y)
        dist_tip_index = math.hypot(thumb_tip.x - index_mcp.x, thumb_tip.y - index_mcp.y)

        thumb_extended = (dist_tip_pinky > dist_ip_pinky * 1.04) and (dist_tip_index > 0.38 * palm_scale)
        fingers.append(thumb_extended)

        # 2. การตรวจสอบนิ้วชี้, กลาง, นาง และก้อย
        tips = [
            self.mp_hands.HandLandmark.INDEX_FINGER_TIP,
            self.mp_hands.HandLandmark.MIDDLE_FINGER_TIP,
            self.mp_hands.HandLandmark.RING_FINGER_TIP,
            self.mp_hands.HandLandmark.PINKY_TIP
        ]
        pips = [
            self.mp_hands.HandLandmark.INDEX_FINGER_PIP,
            self.mp_hands.HandLandmark.MIDDLE_FINGER_PIP,
            self.mp_hands.HandLandmark.RING_FINGER_PIP,
            self.mp_hands.HandLandmark.PINKY_PIP
        ]
        mcps = [
            self.mp_hands.HandLandmark.INDEX_FINGER_MCP,
            self.mp_hands.HandLandmark.MIDDLE_FINGER_MCP,
            self.mp_hands.HandLandmark.RING_FINGER_MCP,
            self.mp_hands.HandLandmark.PINKY_MCP
        ]

        for tip, pip, mcp in zip(tips, pips, mcps):
            d_wrist_tip = math.hypot(lm[tip].x - wrist.x, lm[tip].y - wrist.y)
            d_wrist_pip = math.hypot(lm[pip].x - wrist.x, lm[pip].y - wrist.y)
            d_wrist_mcp = math.hypot(lm[mcp].x - wrist.x, lm[mcp].y - wrist.y)

            is_pointing_up = (lm[tip].y < lm[pip].y)
            is_extended_out = (d_wrist_tip > d_wrist_pip * 1.06) and (d_wrist_tip > d_wrist_mcp * 1.20)
            fingers.append(is_pointing_up or is_extended_out)

        return fingers

    def check_ok_sign(self, hand_landmarks):
        """ตรวจสอบท่า OK Sign โดยวัดระยะระหว่างปลายนิ้วโป้งกับนิ้วชี้ และนิ้วที่เหลือต้องเหยียดออก"""
        lm = hand_landmarks.landmark
        palm_scale = self.get_palm_scale(lm)
        wrist = lm[self.mp_hands.HandLandmark.WRIST]

        thumb_tip = lm[self.mp_hands.HandLandmark.THUMB_TIP]
        index_tip = lm[self.mp_hands.HandLandmark.INDEX_FINGER_TIP]

        dist_thumb_index = math.hypot(thumb_tip.x - index_tip.x, thumb_tip.y - index_tip.y)
        is_pinching = dist_thumb_index < (0.32 * palm_scale)

        middle_tip = lm[self.mp_hands.HandLandmark.MIDDLE_FINGER_TIP]
        middle_pip = lm[self.mp_hands.HandLandmark.MIDDLE_FINGER_PIP]
        middle_up = (middle_tip.y < middle_pip.y) or (
            math.hypot(middle_tip.x - wrist.x, middle_tip.y - wrist.y) > 
            math.hypot(middle_pip.x - wrist.x, middle_pip.y - wrist.y) * 1.06
        )

        ring_tip = lm[self.mp_hands.HandLandmark.RING_FINGER_TIP]
        ring_pip = lm[self.mp_hands.HandLandmark.RING_FINGER_PIP]
        ring_up = (ring_tip.y < ring_pip.y) or (
            math.hypot(ring_tip.x - wrist.x, ring_tip.y - wrist.y) > 
            math.hypot(ring_pip.x - wrist.x, ring_pip.y - wrist.y) * 1.06
        )

        pinky_tip = lm[self.mp_hands.HandLandmark.PINKY_TIP]
        pinky_pip = lm[self.mp_hands.HandLandmark.PINKY_PIP]
        pinky_up = (pinky_tip.y < pinky_pip.y) or (
            math.hypot(pinky_tip.x - wrist.x, pinky_tip.y - wrist.y) > 
            math.hypot(pinky_pip.x - wrist.x, pinky_pip.y - wrist.y) * 1.06
        )

        other_fingers_open = (middle_up and ring_up) or (middle_up and pinky_up)
        return is_pinching and other_fingers_open

    def check_thumbs_up(self, hand_landmarks):
        """ตรวจสอบท่าชูนิ้วโป้ง (Thumbs Up) โดยนิ้วโป้งต้องชี้ขึ้น และนิ้วอื่นพับงออย่างน้อย 3 ใน 4 นิ้ว"""
        lm = hand_landmarks.landmark
        palm_scale = self.get_palm_scale(lm)
        wrist = lm[self.mp_hands.HandLandmark.WRIST]

        thumb_tip = lm[self.mp_hands.HandLandmark.THUMB_TIP]
        thumb_ip = lm[self.mp_hands.HandLandmark.THUMB_IP]
        thumb_mcp = lm[self.mp_hands.HandLandmark.THUMB_MCP]
        pinky_mcp = lm[self.mp_hands.HandLandmark.PINKY_MCP]
        index_mcp = lm[self.mp_hands.HandLandmark.INDEX_FINGER_MCP]
        index_tip = lm[self.mp_hands.HandLandmark.INDEX_FINGER_TIP]

        thumb_pointing_up = (thumb_tip.y < thumb_mcp.y) and (thumb_tip.y < thumb_ip.y)
        thumb_higher_than_index = (thumb_tip.y < index_tip.y)
        thumb_extended = math.hypot(thumb_tip.x - pinky_mcp.x, thumb_tip.y - pinky_mcp.y) > (
            math.hypot(thumb_ip.x - pinky_mcp.x, thumb_ip.y - pinky_mcp.y) * 1.04
        )
        thumb_above_knuckles = (index_mcp.y - thumb_tip.y) > (0.12 * palm_scale)

        if not (thumb_pointing_up and thumb_higher_than_index and thumb_extended and thumb_above_knuckles):
            return False

        # ตรวจสอบการพับงอของนิ้วทั้ง 4
        curled_count = 0
        finger_nodes = [
            (self.mp_hands.HandLandmark.INDEX_FINGER_TIP, self.mp_hands.HandLandmark.INDEX_FINGER_PIP, self.mp_hands.HandLandmark.INDEX_FINGER_MCP),
            (self.mp_hands.HandLandmark.MIDDLE_FINGER_TIP, self.mp_hands.HandLandmark.MIDDLE_FINGER_PIP, self.mp_hands.HandLandmark.MIDDLE_FINGER_MCP),
            (self.mp_hands.HandLandmark.RING_FINGER_TIP, self.mp_hands.HandLandmark.RING_FINGER_PIP, self.mp_hands.HandLandmark.RING_FINGER_MCP),
            (self.mp_hands.HandLandmark.PINKY_TIP, self.mp_hands.HandLandmark.PINKY_PIP, self.mp_hands.HandLandmark.PINKY_MCP)
        ]

        for t_idx, p_idx, m_idx in finger_nodes:
            tip = lm[t_idx]
            pip = lm[p_idx]
            mcp = lm[m_idx]

            d_tip_mcp = math.hypot(tip.x - mcp.x, tip.y - mcp.y)
            d_pip_mcp = math.hypot(pip.x - mcp.x, pip.y - mcp.y)
            d_tip_wrist = math.hypot(tip.x - wrist.x, tip.y - wrist.y)
            d_pip_wrist = math.hypot(pip.x - wrist.x, pip.y - wrist.y)

            if (d_tip_mcp < d_pip_mcp * 1.22) or (d_tip_wrist < d_pip_wrist * 1.08) or (tip.y > pip.y):
                curled_count += 1

        return (curled_count >= 3)

    def classify_gesture(self, fingers, hand_landmarks=None):
        """จำแนกท่าทางหลักของมือตามชุดกฎเกณฑ์ (Rule-based Classification)"""
        if hand_landmarks is not None:
            if self.check_ok_sign(hand_landmarks):
                return "OK_SIGN", "OK Sign"
            if self.check_thumbs_up(hand_landmarks):
                return "THUMBS_UP", "Thumbs Up"

        # ท่าชี้นิ้ววาดเส้น (AIR_DRAW)
        if fingers[1] and not fingers[2] and not fingers[3] and not fingers[4]:
            return "AIR_DRAW", "Point / Draw"

        # ท่ากำหมัด (FIST / Shield)
        if not fingers[1] and not fingers[2] and not fingers[3] and not fingers[4]:
            return "FIST", "Fist / Shield"

        # ท่าชู 2 นิ้ว (PEACE)
        if fingers[1] and fingers[2] and not fingers[3] and not fingers[4]:
            return "PEACE", "Peace / V-Sign"

        # ท่าชู 3 นิ้ว (THREE_FINGERS)
        if fingers[1] and fingers[2] and fingers[3] and not fingers[4]:
            return "THREE_FINGERS", "Three Fingers"

        # ท่าแบมือ (OPEN_HAND) และชาร์จมานา (RECHARGE)
        main_three_up = fingers[1] and fingers[2] and fingers[3]
        if main_three_up:
            if not fingers[0]:
                return "RECHARGE", "Mana Recharge"
            return "OPEN_HAND", "Open Hand"

        return "UNKNOWN", "Unknown"

    def calculate_aiming_ray(self, hand_landmarks, frame_w, frame_h, is_player_1=True):
        """คำนวณเวกเตอร์วิถีการเล็งเวทมนตร์จากตำแหน่งมือไปยังทิศทางของคู่ต่อสู้"""
        lm = hand_landmarks.landmark
        wrist = lm[self.mp_hands.HandLandmark.WRIST]
        mcp = lm[self.mp_hands.HandLandmark.MIDDLE_FINGER_MCP]
        tip = lm[self.mp_hands.HandLandmark.MIDDLE_FINGER_TIP]

        start_x = int(((wrist.x + mcp.x) / 2.0) * frame_w)
        start_y = int(((wrist.y + mcp.y) / 2.0) * frame_h)

        dir_x = tip.x - wrist.x
        dir_y = tip.y - wrist.y
        mag = math.hypot(dir_x, dir_y)

        if is_player_1:
            vx = abs(dir_x / mag) if mag > 0 else 1.0
        else:
            vx = -abs(dir_x / mag) if mag > 0 else -1.0

        vy = (dir_y / mag) if mag > 0 else 0.0

        ray_length = 340
        end_x = int(start_x + vx * ray_length)
        end_y = int(start_y + vy * ray_length)
        return (start_x, start_y), (end_x, end_y)


class ChantSequenceTracker:
    """คลาสสำหรับติดตามลำดับท่าร่าย (Sequence State Machine) เพื่อปลดล็อกสกิลพิเศษ"""

    def __init__(self, timeout=2.5):
        self.step = 0
        self.last_step_time = 0.0
        self.timeout = timeout
        self.is_unlocked = False

    def update(self, gesture_key, current_time):
        """ตรวจสอบและอัปเดตสเต็ปคอมโบ: FIST -> PEACE -> OPEN_HAND"""
        if self.is_unlocked:
            return False

        if self.step > 0 and (current_time - self.last_step_time) > self.timeout:
            self.step = 0

        if self.step == 0:
            if gesture_key == "FIST":
                self.step = 1
                self.last_step_time = current_time
                return False
        elif self.step == 1:
            if gesture_key == "PEACE":
                self.step = 2
                self.last_step_time = current_time
                return False
            elif gesture_key not in ["FIST", "UNKNOWN"]:
                self.step = 0
        elif self.step == 2:
            if gesture_key == "OPEN_HAND":
                self.step = 3
                self.is_unlocked = True
                self.last_step_time = current_time
                return True
            elif gesture_key not in ["PEACE", "UNKNOWN"]:
                self.step = 0

        return False

    def reset(self):
        """รีเซ็ตสถานะการร่ายคอมโบกลับสู่จุดเริ่มต้น"""
        self.step = 0
        self.last_step_time = 0.0
        self.is_unlocked = False