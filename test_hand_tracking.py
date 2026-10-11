"""
Magic Spell Duel - Phase 1: Tracking & Benchmark Test
Script สำหรับทดสอบสตรีมภาพ Unflipped, ตรวจจับมือ 21 จุด (max_num_hands=4),
คำนวณ FPS สด และแบ่งโซนผู้เล่นอัตโนมัติ (Spatial Partitioning)
"""

import time
import cv2
import mediapipe as mp

# ==========================================
# 1. การตั้งค่าระบบและตัวแปรคงที่ (Configurations)
# ==========================================
CAMERA_INDEX = 0          # หากเชื่อม Iriun แล้วไม่ขึ้นภาพ ให้สลับเป็น 1 หรือ 2
FRAME_WIDTH = 1280        # ความละเอียด 720p ตามข้อกำหนด
FRAME_HEIGHT = 720
MAX_HANDS = 2             # จำลอง 2 ผู้เล่นยกคนละ 2 มือ สำหรับ Benchmark
DETECTION_CONFIDENCE = 0.6
TRACKING_CONFIDENCE = 0.5

# สีประจำฝั่งในรูปแบบ BGR
COLOR_P1 = (255, 255, 0)   # Cyan สำหรับ Player 1 (ฝั่งซ้าย)
COLOR_P2 = (34, 34, 220)   # Crimson / ส้มแดง สำหรับ Player 2 (ฝั่งขวา)
COLOR_DIVIDER = (100, 100, 100)

# ==========================================
# 2. เริ่มต้นโมดูล MediaPipe Hands
# ==========================================
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=MAX_HANDS,
    min_detection_confidence=DETECTION_CONFIDENCE,
    min_tracking_confidence=TRACKING_CONFIDENCE
)

# ==========================================
# 3. เปิดการเชื่อมต่อกล้อง (Iriun Webcam via USB)
# ==========================================
cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW) # บน Windows แนะนำเปิดผ่าน CAP_DSHOW
cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

if not cap.isOpened():
    print(f"❌ ไม่สามารถเปิดกล้อง Index {CAMERA_INDEX} ได้ กรุณาตรวจสอบ Iriun Webcam")
    exit()

print("✅ เริ่มต้นเปิดกล้องสำเร็จ | กดปุ่ม 'q' หรือ 'ESC' เพื่อปิดโปรแกรม")

# ตัวแปรคำนวณ FPS
prev_frame_time = time.time()
fps = 0.0

# ==========================================
# 4. ลูปประมวลผลวิดีโอแบบเรียลไทม์
# ==========================================
while cap.isOpened():
    success, frame = cap.read()
    if not success:
        print("⚠️ ไม่สามารถอ่านเฟรมจากกล้องได้ กำลังลองใหม่อีกครั้ง...")
        continue

    # คำนวณ FPS แบบ Real-time
    curr_frame_time = time.time()
    time_diff = curr_frame_time - prev_frame_time
    prev_frame_time = curr_frame_time
    if time_diff > 0:
        fps = 0.9 * fps + 0.1 * (1.0 / time_diff)  # Low-pass filter ให้นิ่งขึ้น

    # 📌 ข้อกำหนดสำคัญ: ไม่กลับด้านภาพ (Unflipped / ห้าม cv2.flip)
    # เพื่อรักษาระนาบ Side-View ให้ซีกซ้ายและขวาตรงกับตำแหน่งจริงของผู้เล่น
    h, w, _ = frame.shape

    # แปลง BGR เป็น RGB สำหรับส่งให้ MediaPipe
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(rgb_frame)

    # วาดเส้นแบ่งกึ่งกลางสนามประลอง (X = 0.5)
    center_x = w // 2
    cv2.line(frame, (center_x, 0), (center_x, h), COLOR_DIVIDER, 2)
    cv2.putText(frame, "ZONE P1 (X < 0.5)", (center_x - 220, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_P1, 2)
    cv2.putText(frame, "ZONE P2 (X >= 0.5)", (center_x + 30, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_P2, 2)

    hand_count = 0

    if results.multi_hand_landmarks:
        hand_count = len(results.multi_hand_landmarks)

        for hand_landmarks in results.multi_hand_landmarks:
            # ดึงพิกัดแกน X แบบ Normalized ของจุดข้อมือ (Wrist ID 0)
            wrist_landmark = hand_landmarks.landmark[mp_hands.HandLandmark.WRIST]
            wrist_norm_x = wrist_landmark.x
            wrist_px_x = int(wrist_norm_x * w)
            wrist_px_y = int(wrist_landmark.y * h)

            # Spatial Partitioning: แบ่งฝั่งผู้เล่นเด็ดขาดจากพิกัด X ของข้อมือ
            if wrist_norm_x < 0.5:
                player_tag = "Player 1"
                theme_color = COLOR_P1
            else:
                player_tag = "Player 2"
                theme_color = COLOR_P2

            # ปรับแต่งสีข้อต่อนิ้วตามสีประจำฝั่งของผู้เล่น
            custom_landmark_style = mp_drawing.DrawingSpec(
                color=theme_color, thickness=2, circle_radius=3
            )
            custom_connection_style = mp_drawing.DrawingSpec(
                color=(255, 255, 255), thickness=2
            )

            # วาดโครงกระดูกมือ 21 จุด
            mp_drawing.draw_landmarks(
                frame,
                hand_landmarks,
                mp_hands.HAND_CONNECTIONS,
                custom_landmark_style,
                custom_connection_style
            )

            # ป้ายกำกับ Player เหนือข้อมือ
            cv2.putText(frame, player_tag, (wrist_px_x - 30, wrist_px_y - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, theme_color, 2)

    # ==========================================
    # 5. แสดงผล HUD Performance & Benchmark Info
    # ==========================================
    # กำหนดสี FPS ตามเกณฑ์การตัดสินท่า Mana Recharge
    if fps >= 28.0:
        fps_color = (0, 255, 0)    # เขียว (ผ่านเกณฑ์ ท่า 2 มือได้)
        recharge_status = "Recharge Mode: Two-Hands Clasp (Optimal)"
    elif fps >= 20.0:
        fps_color = (0, 255, 255)  # เหลือง (ปานกลาง)
        recharge_status = "Recharge Mode: Two-Hands Clasp (Monitor)"
    else:
        fps_color = (0, 0, 255)    # แดง (FPS ตก แนะนำสลับใช้ท่ามือเดียว)
        recharge_status = "Recharge Mode: Single-Hand Fist (Fallback Required)"

    # กล่องดำพื้นหลัง HUD ด้านซ้ายบน
    cv2.rectangle(frame, (10, 10), (510, 110), (20, 20, 20), -1)
    cv2.rectangle(frame, (10, 10), (510, 110), (80, 80, 80), 1)

    cv2.putText(frame, f"FPS: {fps:.1f} | Hands Detected: {hand_count}/{MAX_HANDS}",
                (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, fps_color, 2)
    cv2.putText(frame, f"Spatial Logic: P1(X<0.5) Cyan | P2(X>=0.5) Red",
                (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    cv2.putText(frame, recharge_status,
                (20, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.5, fps_color, 1)

    # แสดงหน้าต่างวิดีโอ
    cv2.imshow("Magic Spell Duel - Phase 1 Benchmark", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q') or key == 27:
        break

# คืนหน่วยความจำ
cap.release()
cv2.destroyAllWindows()
hands.close()