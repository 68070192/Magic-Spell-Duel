"""
Magic Spell Duel - Master Game Configuration
(ศูนย์รวมการตั้งค่าฮาร์ดแวร์, สมดุลเกม, จังหวะเสียง, และเอฟเฟกต์ทั้งหมด)
"""

# ==========================================
# 1. การตั้งค่ากล้องและหน้าจอ (Hardware & Display)
# ==========================================
CAMERA_INDEX = 0             # หมายเลขกล้อง (0 = กล้องในตัว, 1 หรือ 2 = เว็บบอร์ด/Webcam นอก)
FRAME_WIDTH = 1280           # ความกว้างหน้าจอแสดงผล (px)
FRAME_HEIGHT = 720           # ความสูงหน้าจอแสดงผล (px)

# ==========================================
# 2. การตรวจจับ AI (MediaPipe Settings)
# ==========================================
MAX_NUM_HANDS = 3            # รองรับตรวจจับสูงสุด 3 มือ (เพื่อความเสถียรเมื่อยืนคู่)
HAND_MIN_DETECTION_CONF = 0.60
HAND_MIN_TRACKING_CONF = 0.50
FACE_MIN_DETECTION_CONF = 0.25

# ==========================================
# 3. ธีมสีประจำตัวผู้เล่น (Player Visual Theme)
# ==========================================
COLOR_P1 = (255, 255, 0)     # P1: สีฟ้าสว่าง (Cyan - BGR)
COLOR_P2 = (34, 34, 220)     # P2: สีแดงส้มเข้ม (Crimson - BGR)
COLOR_DIVIDER = (80, 80, 80) # เส้นแบ่งแดนกลางจอ

# ==========================================
# 4. ขนาดตำแหน่งเป้าหมายและร่างกาย (Hitbox & Body Tracking)
# ==========================================
TORSO_WIDTH = 210            # ความกว้าง Hitbox ลำตัว
TORSO_HEIGHT = 260           # ความสูง Hitbox ลำตัว
CHEST_OFFSET_Y = 110         # ระยะห่างจากใบหน้าลงมาที่กึ่งกลางหน้าอก
SHIELD_RADIUS = 180          # รัศมีครอบคลุมของบาเรียเวทมนตร์

# ==========================================
# 5. การวาดสัญลักษณ์และท่าทาง (AirDraw & Gestures)
# ==========================================
STILL_TIMEOUT = 0.48         # เวลาหยุดนิ่งเพื่อยืนยันรูปทรง (วินาที)
CONFIRM_HOLD_DELAY = 0.20    # เวลาเริ่มแสดงวงแหวนยืนยันการวาด (วินาที)
FLICKER_TOLERANCE = 0.15     # ความยืดหยุ่นเมื่อนิ้วหลุดเฟรมชั่วคราว (วินาที)
SPELL_CALLOUT_DURATION = 4.0 # ระยะเวลาแสดงป้ายรอร่ายสกิลก่อนสลายตัว (วินาที)

# ==========================================
# 6. กติกาและการแข่งขัน (Tournament & Match Rules)
# ==========================================
MAX_ROUND_WINS = 2           # จำนวนรอบที่ต้องชนะเพื่อเป็นแชมป์ (Best of 3 = 2 รอบ)
TITLE_READY_TARGET = 1.2     # เวลาชูนิ้วค้างหน้า Title เพื่อเริ่มเกม (วินาที)
REMATCH_HOLD_TARGET = 1.5    # เวลาชูนิ้วโป้งค้างหน้าสรุปผลเพื่อ Rematch (วินาที)
COUNTDOWN_DURATION = 3.6     # เวลานับถอยหลังก่อนเริ่มสู้ในแต่ละยก (วินาที)
ROUND_OVER_DELAY = 2.4       # เวลาพักระหว่างยก (วินาที)

# ==========================================
# 7. การสั่นหน้าจอ (Screen Shake Intensities & Durations)
# ==========================================
# Lightning Strike: แรงสุด
SHAKE_LIGHTNING_INTENSITY = 22.0
SHAKE_LIGHTNING_DURATION = 0.35

# Terra Boulder: ปานกลาง
SHAKE_TERRA_INTENSITY = 15.0
SHAKE_TERRA_DURATION = 0.25

# Fireball: เบาสุด
SHAKE_FIREBALL_INTENSITY = 9.0
SHAKE_FIREBALL_DURATION = 0.16

# ป้องกันและเจาะเกราะ
SHAKE_SHIELD_BREAK_INTENSITY = 22.0  
SHAKE_SHIELD_BREAK_DURATION = 0.35
SHAKE_SHIELD_BLOCK_INTENSITY = 8.0   
SHAKE_SHIELD_BLOCK_DURATION = 0.15

# K.O. Final Impact
SHAKE_KO_INTENSITY = 28.0
SHAKE_KO_DURATION = 0.45

# ==========================================
# 8. เอฟเฟกต์ปิดฉาก K.O. (Dramatic Slow-Mo & Flash)
# ==========================================
KO_SLOWMO_DURATION = 0.75    # ระยะเวลาสโลว์โมชัน (วินาทีจริง)
KO_SLOWMO_TIMESCALE = 0.25   # ความเร็วของเกมช่วงสโลว์ (25% ของปกติ)
KO_FLASH_ALPHA = 0.85        # ความสว่างเริ่มต้นของแฟลชขาวตอน K.O.

# ==========================================
# 9. คิวเวลาเสียงผู้ประกาศ (Announcer Audio Timing Delays)
# ==========================================
ANNOUNCER_ROUND_DELAY = 0.20 # หน่วงเวลาประกาศ Round 1/2/Final (วินาที)
ANNOUNCER_DUEL_DELAY = 0.20  # หน่วงเวลาประกาศ Duel! / Fight! (วินาที)
ANNOUNCER_KO_DELAY = 0.5    # หน่วงเวลาประกาศ K.O.! (วินาที)
ANNOUNCER_WIN_DELAY = 0.90   # หน่วงเวลาประกาศ Player Win! (วินาที)