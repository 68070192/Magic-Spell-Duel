"""
Module: vision_pipeline.py
Description: ระบบท่อประมวลผลภาพแบบหลายเธรด (Threaded Vision Pipeline)
             แยกการอ่านภาพจากกล้อง (CameraStream) และการประมวลผล AI ของ MediaPipe (VisionWorker)
             ออกจากลูปเรนเดอร์หลัก เพื่อไม่ให้ความเร็วกล้องหรือ AI มาถ่วง FPS ของเกม
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
import cv2
import mediapipe as mp


def enable_high_res_timer():
    """ปรับความละเอียด Timer ของ Windows เป็น 1ms เพื่อให้การรอเฟรมและ waitKey ไม่ถูกปัดเป็น ~15ms"""
    try:
        import ctypes
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass


class CameraStream:
    """เธรดอ่านภาพจากกล้องต่อเนื่อง เก็บเฉพาะเฟรมล่าสุดเสมอ (ไม่สะสมคิว ไม่เกิดดีเลย์)"""

    def __init__(self, index, width, height, target_fps=60, fourcc="MJPG"):
        self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        # ต้องตั้ง FOURCC ก่อนความละเอียด: โหมด YUY2 เริ่มต้นของ DirectShow ถูกจำกัดที่ 30 FPS ที่ 720p
        if fourcc:
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, target_fps)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self.size = (width, height)
        self.fps = 0.0
        self._frame = None
        self._seq = 0
        self._cond = threading.Condition()
        self._running = self.cap.isOpened()
        self._thread = threading.Thread(target=self._loop, name="CameraStream", daemon=True)
        if self._running:
            self._thread.start()

    def is_opened(self):
        return self._running

    def _loop(self):
        prev = time.perf_counter()
        while self._running:
            success, frame = self.cap.read()
            if not success:
                time.sleep(0.005)
                continue

            # กล้องบางรุ่นไม่รองรับความละเอียดที่ขอ จึงปรับให้ตรงกับพิกัดที่เกมใช้
            if (frame.shape[1], frame.shape[0]) != self.size:
                frame = cv2.resize(frame, self.size, interpolation=cv2.INTER_LINEAR)

            t = time.perf_counter()
            if t > prev:
                self.fps = 0.9 * self.fps + 0.1 * (1.0 / (t - prev))
            prev = t

            with self._cond:
                self._frame = frame
                self._seq += 1
                self._cond.notify_all()

    def wait_frame(self, last_seq, timeout):
        """
        รอเฟรมใหม่ (หมายเลขลำดับ > last_seq) ไม่เกิน timeout วินาที
        Return: (เฟรมล่าสุด หรือ None หากยังไม่เคยได้ภาพ, หมายเลขลำดับ) — ห้ามแก้ไขเฟรมที่ได้ ให้ .copy() ก่อนวาด
        """
        with self._cond:
            if self._seq == last_seq and self._running:
                self._cond.wait(timeout)
            return self._frame, self._seq

    def release(self):
        self._running = False
        with self._cond:
            self._cond.notify_all()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self.cap.release()


class VisionResult:
    """ผลลัพธ์รวมของผู้เล่นทั้งสองฝั่ง ใช้พิกัด Normalized ของเฟรมเต็ม (รูปแบบเดียวกับผลลัพธ์ของ MediaPipe)"""

    def __init__(self, multi_hand_landmarks=None, detections=None):
        self.multi_hand_landmarks = multi_hand_landmarks or None
        self.detections = detections or None


class PlayerVision:
    """
    ตัวตรวจจับมือและใบหน้าของผู้เล่นหนึ่งฝั่ง ทำงานบนภาพที่ตัดเฉพาะบริเวณของผู้เล่น (ROI) ที่ความละเอียดจริง
    แทนการย่อทั้งเฟรม: โมเดลตรวจจับฝ่ามือของ MediaPipe ย่อภาพที่รับเข้ามาเหลือเพียง 192x192 พิกเซล
    มือของผู้เล่นที่ยืนไกลจึงเล็กเกินกว่าจะตรวจเจอ การตัดภาพให้แคบลงทำให้มือกินพื้นที่ในภาพมากขึ้น

    ROI มี 2 ระดับ:
      - wide: กรอบจัตุรัสครอบคลุมแดนของผู้เล่น (ใช้หาใบหน้า และใช้หามือเมื่อยังไม่รู้ตำแหน่งผู้เล่น)
      - zoom: กรอบจัตุรัสรอบตัวผู้เล่น ขนาดแปรตามขนาดใบหน้า (ยิ่งยืนไกล ยิ่งซูมเข้า)
    """

    FACE_LOST_LIMIT = 10        # จำนวนรอบตรวจใบหน้าที่หาไม่เจอก่อนยกเลิกการซูม
    ZOOM_RECENTER_RATIO = 0.12  # ขยับกรอบซูมเมื่อผู้เล่นเคลื่อนเกินสัดส่วนนี้ของขนาดกรอบ
    ZOOM_RESIZE_RATIO = 1.25    # ปรับขนาดกรอบซูมเมื่อขนาดที่ต้องการต่างจากเดิมเกินอัตราส่วนนี้

    def __init__(self, is_p1, frame_size, max_num_hands, hand_detection_conf, hand_tracking_conf,
                 face_detection_conf, hand_model_complexity, zoom_enabled, zoom_face_scale, zoom_min_size):
        self.is_p1 = is_p1
        self.frame_w, self.frame_h = frame_size
        self.zoom_enabled = zoom_enabled
        self.zoom_face_scale = zoom_face_scale
        self.zoom_min_size = zoom_min_size

        # กรอบ wide ของสองฝั่งซ้อนทับกันบริเวณกลางจอ มือที่ยื่นข้ามเส้นแบ่งแดนจึงไม่ถูกตัดขาด
        wide_w = min(self.frame_w, max(self.frame_h, self.frame_w // 2 + self.frame_w // 16))
        wide_x = 0 if is_p1 else self.frame_w - wide_w
        self.wide_roi = (wide_x, 0, wide_w, self.frame_h)
        self.hand_roi = self.wide_roi
        self.faces = []
        self._face_misses = 0

        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=max_num_hands,
            model_complexity=hand_model_complexity,
            min_detection_confidence=hand_detection_conf,
            min_tracking_confidence=hand_tracking_conf
        )
        self._face = mp.solutions.face_detection.FaceDetection(
            model_selection=1,
            min_detection_confidence=face_detection_conf
        )

    def _crop_rgb(self, frame, roi):
        x, y, w, h = roi
        rgb = cv2.cvtColor(frame[y:y + h, x:x + w], cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        return rgb

    def _detect_faces(self, wide_rgb):
        """ตรวจจับใบหน้าในกรอบ wide แล้วแปลงพิกัดกลับเป็นของเฟรมเต็ม"""
        x, y, w, h = self.wide_roi
        results = self._face.process(wide_rgb)
        self.faces = []
        for detection in results.detections or []:
            bbox = detection.location_data.relative_bounding_box
            bbox.xmin = (bbox.xmin * w + x) / self.frame_w
            bbox.ymin = (bbox.ymin * h + y) / self.frame_h
            bbox.width = bbox.width * w / self.frame_w
            bbox.height = bbox.height * h / self.frame_h
            self.faces.append(detection)

    def _update_hand_roi(self):
        """เลือกกรอบตรวจจับมือจากใบหน้าที่ใหญ่ที่สุดในแดนของผู้เล่น"""
        best = None
        best_area = 0.0
        for detection in self.faces:
            bbox = detection.location_data.relative_bounding_box
            in_own_half = (bbox.xmin + bbox.width / 2.0 < 0.5) == self.is_p1
            if in_own_half and bbox.width * bbox.height > best_area:
                best_area = bbox.width * bbox.height
                best = bbox

        if best is None:
            self._face_misses += 1
            if self._face_misses >= self.FACE_LOST_LIMIT:
                self.hand_roi = self.wide_roi
            return
        self._face_misses = 0

        face_h = best.height * self.frame_h
        side = int(max(self.zoom_min_size, self.zoom_face_scale * face_h))
        if side >= 0.9 * min(self.wide_roi[2], self.wide_roi[3]):
            # ผู้เล่นยืนใกล้พอแล้ว กรอบ wide ให้รายละเอียดเพียงพอและครอบคลุมระยะเอื้อมแขนได้มากกว่า
            self.hand_roi = self.wide_roi
            return

        # จุดศูนย์กลางอยู่ต่ำกว่าใบหน้าหนึ่งช่วงหน้า เพื่อครอบคลุมทั้งมือที่ยกเหนือศีรษะและมือระดับเอว
        center_x = (best.xmin + best.width / 2.0) * self.frame_w
        center_y = (best.ymin + best.height / 2.0) * self.frame_h + face_h
        x = int(min(max(0.0, center_x - side / 2.0), self.frame_w - side))
        y = int(min(max(0.0, center_y - side / 2.0), self.frame_h - side))

        # ขยับกรอบเฉพาะเมื่อผู้เล่นเคลื่อนที่จริง: MediaPipe ติดตามมือด้วยพิกัดของภาพที่รับเข้า
        # กรอบที่สั่นไปมาทุกเฟรมจะทำให้การติดตามหลุดบ่อย
        cur_x, cur_y, cur_w, cur_h = self.hand_roi
        is_zoomed = self.hand_roi != self.wide_roi
        if is_zoomed:
            moved = max(abs(x - cur_x), abs(y - cur_y)) > self.ZOOM_RECENTER_RATIO * cur_w
            resized = max(side, cur_w) / float(min(side, cur_w)) > self.ZOOM_RESIZE_RATIO
            if not moved and not resized:
                return
        self.hand_roi = (x, y, side, side)

    def process(self, frame, run_face):
        """Return: (รายการ hand_landmarks, รายการ face detections) ในพิกัด Normalized ของเฟรมเต็ม"""
        wide_rgb = None
        if run_face:
            wide_rgb = self._crop_rgb(frame, self.wide_roi)
            self._detect_faces(wide_rgb)
            if self.zoom_enabled:
                self._update_hand_roi()

        x, y, w, h = self.hand_roi
        if wide_rgb is None or self.hand_roi != self.wide_roi:
            hand_rgb = self._crop_rgb(frame, self.hand_roi)
        else:
            hand_rgb = wide_rgb
        results = self._hands.process(hand_rgb)

        hands = []
        for hand_landmarks in results.multi_hand_landmarks or []:
            for lm in hand_landmarks.landmark:
                lm.x = (lm.x * w + x) / self.frame_w
                lm.y = (lm.y * h + y) / self.frame_h
            hands.append(hand_landmarks)
        return hands, self.faces

    def close(self):
        self._hands.close()
        self._face.close()


class VisionWorker:
    """เธรดประมวลผล MediaPipe Hands + Face Detection บนเฟรมล่าสุดจาก CameraStream (ผู้เล่นสองฝั่งทำงานขนานกัน)"""

    def __init__(self, camera, max_num_hands, hand_detection_conf, hand_tracking_conf, face_detection_conf,
                 hand_model_complexity=1, face_every=3, zoom_enabled=True, zoom_face_scale=10.0, zoom_min_size=256):
        self.camera = camera
        self.face_every = max(1, face_every)
        self.fps = 0.0

        self.players = [
            PlayerVision(is_p1, camera.size, max_num_hands, hand_detection_conf, hand_tracking_conf,
                         face_detection_conf, hand_model_complexity, zoom_enabled, zoom_face_scale, zoom_min_size)
            for is_p1 in (True, False)
        ]
        self._pool = ThreadPoolExecutor(max_workers=len(self.players), thread_name_prefix="PlayerVision")

        self._lock = threading.Lock()
        self._result = (None, None, 0, 1.0 / 30.0)
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="VisionWorker", daemon=True)
        self._thread.start()

    def _loop(self):
        cam_seq = 0
        counter = 0
        result_seq = 0
        prev = time.perf_counter()

        while self._running:
            frame, seq = self.camera.wait_frame(cam_seq, 0.1)
            if frame is None or seq == cam_seq:
                continue
            cam_seq = seq

            # Face Throttling: ประมวลผลใบหน้าทุกๆ N รอบเพื่อลดภาระ CPU
            run_face = (counter % self.face_every == 0)
            counter += 1

            futures = [self._pool.submit(player.process, frame, run_face) for player in self.players]
            hands = []
            faces = []
            for future in futures:
                player_hands, player_faces = future.result()
                hands.extend(player_hands)
                faces.extend(player_faces)
            vision_result = VisionResult(hands, faces)

            t = time.perf_counter()
            interval = t - prev
            prev = t
            if interval > 0:
                self.fps = 0.9 * self.fps + 0.1 * (1.0 / interval)

            result_seq += 1
            with self._lock:
                self._result = (vision_result, vision_result, result_seq, interval)

    def latest(self):
        """Return: (hand_results, face_results, หมายเลขลำดับผลลัพธ์, ช่วงเวลาระหว่างผลลัพธ์ล่าสุดเป็นวินาที)"""
        with self._lock:
            return self._result

    def close(self):
        self._running = False
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._pool.shutdown(wait=True)
        for player in self.players:
            player.close()
