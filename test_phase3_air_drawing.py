"""
Magic Spell Duel - Phase 3: Air-Drawing & Shape Recognition Verification (Flicker Protected)
แก้ปัญหาเส้นขาดตอนวาดเร็วด้วย Gesture Flicker Grace Period (0.15 วิ)
"""

import time
import math
import cv2
import mediapipe as mp
from gesture_recognizer import GestureRecognizer
from unistroke import UnistrokeRecognizer

CAMERA_INDEX = 0
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
MAX_HANDS = 3

COLOR_P1 = (255, 255, 0)
COLOR_P2 = (34, 34, 220)
COLOR_DIVIDER = (80, 80, 80)
STILL_TIMEOUT = 0.35
FLICKER_TOLERANCE = 0.15  # ยอมให้มือหลุดจากท่าชี้ได้ไม่เกิน 0.15 วิ โดยเส้นไม่ขาด

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=MAX_HANDS,
    min_detection_confidence=0.6,
    min_tracking_confidence=0.5
)

gesture_engine = GestureRecognizer()
unistroke_engine = UnistrokeRecognizer()


class PlayerDrawSession:
    def __init__(self, is_p1):
        self.is_p1 = is_p1
        self.raw_points = []
        self.smoothed_pt = None
        self.is_drawing = False
        self.still_timer_start = None
        self.non_draw_timer_start = None
        self.last_result = None
        self.alpha = 0.75  # ตอบสนองไวขึ้นต่อการวาดเร็ว

    def update(self, finger_tip_px, current_gesture, dt):
        now = time.time()

        if current_gesture == "AIR_DRAW":
            self.non_draw_timer_start = None
            self.is_drawing = True
            px, py = finger_tip_px

            if self.smoothed_pt is None:
                self.smoothed_pt = (float(px), float(py))
            else:
                sx = self.alpha * px + (1.0 - self.alpha) * self.smoothed_pt[0]
                sy = self.alpha * py + (1.0 - self.alpha) * self.smoothed_pt[1]
                self.smoothed_pt = (sx, sy)

            current_pt = (int(self.smoothed_pt[0]), int(self.smoothed_pt[1]))

            if len(self.raw_points) > 0:
                last_pt = self.raw_points[-1]
                dist_moved = math.hypot(current_pt[0] - last_pt[0], current_pt[1] - last_pt[1])

                if dist_moved < 6.0:
                    if self.still_timer_start is None:
                        self.still_timer_start = now
                    elif (now - self.still_timer_start) >= STILL_TIMEOUT:
                        self._finish_stroke()
                else:
                    self.still_timer_start = None
                    self.raw_points.append(current_pt)
            else:
                self.raw_points.append(current_pt)

        else:
            # ถ้าหลุดจากท่าชี้ (อาจเพราะตวัดนิ้วเร็ว) ให้หน่วงเวลา FLICKER_TOLERANCE ป้องกันเส้นขาด
            if self.is_drawing:
                # ถ้าเปลี่ยนเป็นท่า Trigger ชัดเจน (เช่น กาง 5 นิ้ว หรือกำหมัด) ตัดจบคำนวณทันที
                if current_gesture in ["FIREBALL", "MAGIC_SHIELD", "LIGHTNING", "TERRA", "HEAL"]:
                    self._finish_stroke()
                else:
                    # ถ้าเป็น Neutral หรือหลุดชั่วคราว รอ 0.15 วิ
                    if self.non_draw_timer_start is None:
                        self.non_draw_timer_start = now
                    elif (now - self.non_draw_timer_start) >= FLICKER_TOLERANCE:
                        self._finish_stroke()

    def _finish_stroke(self):
        if len(self.raw_points) >= 12:
            shape, spell, score = unistroke_engine.recognize(self.raw_points)
            self.last_result = (shape, spell, score, time.time())
        self.raw_points = []
        self.smoothed_pt = None
        self.is_drawing = False
        self.still_timer_start = None
        self.non_draw_timer_start = None


p1_session = PlayerDrawSession(is_p1=True)
p2_session = PlayerDrawSession(is_p1=False)

cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

if not cap.isOpened():
    print(f"❌ ไม่สามารถเปิดกล้อง Index {CAMERA_INDEX} ได้")
    exit()

print("✅ Phase 3 Air-Drawing (Flicker & Corner Enhanced) พร้อมทำงาน | กด 'q' เพื่อออก")

prev_time = time.time()
fps = 0.0

while cap.isOpened():
    success, frame = cap.read()
    if not success:
        continue

    curr_time = time.time()
    dt = curr_time - prev_time
    prev_time = curr_time
    if dt > 0:
        fps = 0.9 * fps + 0.1 * (1.0 / dt)

    h, w, _ = frame.shape
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(rgb_frame)

    center_x = w // 2
    cv2.line(frame, (center_x, 0), (center_x, h), COLOR_DIVIDER, 1)

    p1_candidates = []
    p2_candidates = []
    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            wrist_x = hand_landmarks.landmark[mp_hands.HandLandmark.WRIST].x
            if wrist_x < 0.5:
                p1_candidates.append(hand_landmarks)
            else:
                p2_candidates.append(hand_landmarks)

    active_hands = {}
    if p1_candidates:
        active_hands["P1"] = max(p1_candidates, key=lambda hl: hl.landmark[mp_hands.HandLandmark.WRIST].x)
    if p2_candidates:
        active_hands["P2"] = min(p2_candidates, key=lambda hl: hl.landmark[mp_hands.HandLandmark.WRIST].x)

    sessions = {"P1": (p1_session, COLOR_P1), "P2": (p2_session, COLOR_P2)}

    for tag, (session, theme_color) in sessions.items():
        if tag in active_hands:
            hand_landmarks = active_hands[tag]
            fingers = gesture_engine.get_finger_status(hand_landmarks)
            gesture_key, gesture_name = gesture_engine.classify_gesture(fingers)

            index_tip = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
            tip_px = (int(index_tip.x * w), int(index_tip.y * h))

            session.update(tip_px, gesture_key, dt)

            mp_drawing.draw_landmarks(
                frame, hand_landmarks, mp_hands.HAND_CONNECTIONS,
                mp_drawing.DrawingSpec(color=theme_color, thickness=2, circle_radius=2),
                mp_drawing.DrawingSpec(color=(220, 220, 220), thickness=2)
            )

            wrist = hand_landmarks.landmark[mp_hands.HandLandmark.WRIST]
            wrist_px = (int(wrist.x * w), int(wrist.y * h))
            cv2.putText(frame, f"{tag}: {gesture_name}", (wrist_px[0] - 60, max(30, wrist_px[1] - 30)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, theme_color, 2, cv2.LINE_AA)
        else:
            if session.is_drawing:
                session._finish_stroke()

        # วาดเส้นเรืองแสง
        pts = session.raw_points
        if len(pts) > 1:
            for i in range(1, len(pts)):
                cv2.line(frame, pts[i - 1], pts[i], theme_color, 6, cv2.LINE_AA)
                cv2.line(frame, pts[i - 1], pts[i], (255, 255, 255), 2, cv2.LINE_AA)

            cv2.circle(frame, pts[-1], 8, (255, 255, 255), -1)
            cv2.circle(frame, pts[-1], 12, theme_color, 2)

            if session.still_timer_start is not None:
                still_progress = min(1.0, (curr_time - session.still_timer_start) / STILL_TIMEOUT)
                gauge_w = int(40 * still_progress)
                cv2.rectangle(frame, (pts[-1][0] - 20, pts[-1][1] - 25),
                              (pts[-1][0] - 20 + gauge_w, pts[-1][1] - 20), (0, 255, 0), -1)

        # แสดงผลลัพธ์
        if session.last_result:
            shape, spell, score, res_time = session.last_result
            if curr_time - res_time < 3.0:
                card_x = 30 if session.is_p1 else w - 370
                card_y = 120
                res_color = (0, 255, 0) if score >= 0.65 else (0, 165, 255)

                cv2.rectangle(frame, (card_x, card_y), (card_x + 340, card_y + 70), (15, 15, 15), -1)
                cv2.rectangle(frame, (card_x, card_y), (card_x + 340, card_y + 70), res_color, 2)
                cv2.putText(frame, f"{tag}: {shape} -> {spell}", (card_x + 10, card_y + 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
                cv2.putText(frame, f"Match Score: {score*100:.1f}%", (card_x + 10, card_y + 55),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, res_color, 2, cv2.LINE_AA)

    cv2.rectangle(frame, (10, 10), (450, 75), (20, 20, 20), -1)
    cv2.rectangle(frame, (10, 10), (450, 75), (100, 100, 100), 1)
    cv2.putText(frame, f"FPS: {fps:.1f} | Phase 3: Flicker-Protected Matcher", (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0) if fps >= 28 else (0, 165, 255), 2)
    cv2.putText(frame, "Shapes: Triangle, Circle, Z, Square, Heart", (20, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200, 200, 200), 1)

    cv2.imshow("Magic Spell Duel - Phase 3 Air-Drawing", frame)

    if cv2.waitKey(1) & 0xFF in [ord('q'), 27]:
        break

cap.release()
cv2.destroyAllWindows()
hands.close()