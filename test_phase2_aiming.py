"""
Magic Spell Duel - Phase 2 (Fixed: Multi-hand Arbitration & Starvation Prevention)
ระบบจัดสรรมือแบบ 1 คน 1 มือ พร้อมระบบ Forward-Hand Selection ป้องกันการแย่งโควตา
"""

import time
import cv2
import mediapipe as mp
from gesture_recognizer import GestureRecognizer

# ==========================================
# 1. ตั้งค่าระบบ
# ==========================================
CAMERA_INDEX = 0
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
MAX_HANDS = 3  # ปรับเป็น 3 เพื่อให้มี Buffer กันฝั่งใดฝั่งหนึ่งขโมยโควตา

COLOR_P1 = (255, 255, 0)       # Cyan สำหรับ Player 1
COLOR_P2 = (34, 34, 220)       # Crimson สำหรับ Player 2
COLOR_DIVIDER = (80, 80, 80)
COLOR_WARNING = (0, 140, 255)  # สีส้มสำหรับเตือนเมื่อยกเกิน 1 มือ

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=MAX_HANDS,
    min_detection_confidence=0.6,
    min_tracking_confidence=0.5
)

recognizer = GestureRecognizer()

cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

if not cap.isOpened():
    print(f"❌ ไม่สามารถเปิดกล้อง Index {CAMERA_INDEX} ได้")
    exit()

print("✅ Phase 2 Arbitration Engine พร้อมทำงาน | กด 'q' เพื่อออก")

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

    # ========================================================
    # 2. จัดกลุ่มมือตามโซน (Spatial Partitioning)
    # ========================================================
    p1_candidates = []
    p2_candidates = []

    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            wrist_x = hand_landmarks.landmark[mp_hands.HandLandmark.WRIST].x
            if wrist_x < 0.5:
                p1_candidates.append(hand_landmarks)
            else:
                p2_candidates.append(hand_landmarks)

    # ========================================================
    # 3. อัลกอริทึม Forward-Hand Selection (เลือกมือด้านหน้าที่แท้จริง)
    # ========================================================
    active_players = {}

    # สำหรับ Player 1 (ยืนซ้าย หันขวา): มือร่ายเวทจะยื่นไปทางขวา -> เลือกมือที่มี X มากที่สุด
    if len(p1_candidates) == 1:
        active_players["P1"] = (p1_candidates[0], True, False)  # (landmarks, is_p1, is_foul)
    elif len(p1_candidates) > 1:
        best_p1 = max(p1_candidates, key=lambda hl: hl.landmark[mp_hands.HandLandmark.WRIST].x)
        active_players["P1"] = (best_p1, True, True)

    # สำหรับ Player 2 (ยืนขวา หันซ้าย): มือร่ายเวทจะยื่นไปทางซ้าย -> เลือกมือที่มี X น้อยที่สุด
    if len(p2_candidates) == 1:
        active_players["P2"] = (p2_candidates[0], False, False)
    elif len(p2_candidates) > 1:
        best_p2 = min(p2_candidates, key=lambda hl: hl.landmark[mp_hands.HandLandmark.WRIST].x)
        active_players["P2"] = (best_p2, False, True)

    # ========================================================
    # 4. วิเคราะห์ท่าทางและวาดผลลัพธ์ของมือที่ผ่านการคัดเลือก
    # ========================================================
    for player_tag, (hand_landmarks, is_p1, is_foul) in active_players.items():
        wrist = hand_landmarks.landmark[mp_hands.HandLandmark.WRIST]
        wrist_px = (int(wrist.x * w), int(wrist.y * h))
        theme_color = COLOR_P1 if is_p1 else COLOR_P2

        # อ่านท่าทาง 7 ท่า และคำนวณเวกเตอร์เล็ง
        fingers = recognizer.get_finger_status(hand_landmarks)
        gesture_key, gesture_name = recognizer.classify_gesture(fingers)
        start_pt, end_pt = recognizer.calculate_aiming_ray(hand_landmarks, w, h, is_player_1=is_p1)

        # วาดเส้นเล็งเลเซอร์
        cv2.line(frame, start_pt, end_pt, theme_color, 3, cv2.LINE_AA)
        cv2.circle(frame, start_pt, 5, (255, 255, 255), -1)
        cv2.circle(frame, end_pt, 7, theme_color, -1)

        # วาดโครงสร้างมือ 21 จุด
        mp_drawing.draw_landmarks(
            frame,
            hand_landmarks,
            mp_hands.HAND_CONNECTIONS,
            mp_drawing.DrawingSpec(color=theme_color, thickness=2, circle_radius=2),
            mp_drawing.DrawingSpec(color=(220, 220, 220), thickness=2)
        )

        # แสดงป้ายชื่อท่าทาง
        finger_str = f"[{','.join(str(f) for f in fingers)}]"
        label_y = max(30, wrist_px[1] - 40)
        cv2.putText(frame, f"{player_tag}: {gesture_name}", (wrist_px[0] - 60, label_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, theme_color, 2, cv2.LINE_AA)
        cv2.putText(frame, finger_str, (wrist_px[0] - 40, label_y + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

        # ถ้าพบมือเกินในฝั่งนั้น ให้แสดงป้ายเตือน FOUL สีส้ม
        if is_foul:
            cv2.putText(frame, f"WARNING: {player_tag} HAS 2+ HANDS! (USE FRONT HAND)",
                        (wrist_px[0] - 100, label_y - 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_WARNING, 2, cv2.LINE_AA)

    # ========================================================
    # 5. แสดงผล HUD
    # ========================================================
    cv2.rectangle(frame, (10, 10), (420, 85), (20, 20, 20), -1)
    cv2.rectangle(frame, (10, 10), (420, 85), (100, 100, 100), 1)

    cv2.putText(frame, f"FPS: {fps:.1f} | Buffer: {MAX_HANDS} | Active: {len(active_players)}/2",
                (20, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                (0, 255, 0) if fps >= 28 else (0, 165, 255), 2)
    cv2.putText(frame, "Arbitration: Front Hand Auto-Selected", (20, 65),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200, 200, 200), 1)

    cv2.imshow("Magic Spell Duel - Phase 2 Pose & Aiming", frame)

    if cv2.waitKey(1) & 0xFF in [ord('q'), 27]:
        break

cap.release()
cv2.destroyAllWindows()
hands.close()