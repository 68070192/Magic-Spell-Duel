"""
Module: unistroke.py
Description: ระบบรู้จำเส้นวาดแบบเส้นเดียว ($1 Unistroke Recognizer) สำหรับแปลงท่าทางการวาดเส้นกลางอากาศ 
             (Air Drawing) เป็นสัญลักษณ์เวทมนตร์ (Triangle, Circle, Square, Z, Heart, Infinity) 
             ผ่านกระบวนการปรับมาตรฐานพิกัด (Normalization) และการจับคู่รูปแบบ (Template Matching)
"""

import math
import numpy as np


class Point:
    """คลาสสำหรับจัดเก็บพิกัด 2 มิติ (x, y) ในระบบทศนิยม"""

    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)


class Template:
    """คลาสแม่แบบสัญลักษณ์เวทมนตร์ พร้อมพิกัดมาตรฐานและสถานะเส้นปิด (Closed Loop)"""

    def __init__(self, name, spell_name, raw_points, is_closed=True):
        self.name = name
        self.spell_name = spell_name
        self.is_closed = is_closed
        self.points = UnistrokeRecognizer.normalize_points(raw_points)


class UnistrokeRecognizer:
    """
    คลาสหลักสำหรับรู้จำรูปร่างลายเส้น โดยใช้อัลกอริทึม $1 Recognizer 
    ปรับแก้ให้รองรับการวาดเส้นแบบย้อนกลับ (Bidirectional) และการเลื่อนจุดเริ่มต้น (Cyclic Shift)
    """

    NUM_POINTS = 64
    SQUARE_SIZE = 250.0
    HALF_DIAGONAL = 0.5 * math.sqrt(250.0**2 + 250.0**2)
    PHI = 0.5 * (-1.0 + math.sqrt(5.0))  # อัตราส่วน Golden Ratio สำหรับค้นหามุมที่ดีที่สุด
    MAX_ROTATION_RAD = math.radians(45.0)
    ACCEPT_THRESHOLD = 0.65

    def __init__(self):
        self.templates = []
        self._init_default_templates()

    def _init_default_templates(self):
        """กำหนดแม่แบบรูปทรงเรขาคณิตเริ่มต้นที่เชื่อมโยงกับคาถาแต่ละชนิด"""

        # 1. รูปทรงสามเหลี่ยม (Triangle -> Fireball)
        t_top = [Point(125, 25), Point(225, 225), Point(25, 225), Point(125, 25)]
        self.templates.append(Template("Triangle", "Fireball", t_top, is_closed=True))

        t_bottom_left = [Point(25, 225), Point(125, 25), Point(225, 225), Point(25, 225)]
        self.templates.append(Template("Triangle", "Fireball", t_bottom_left, is_closed=True))

        # 2. รูปทรงวงกลม (Circle -> Magic Shield)
        circle_pts = []
        for deg in range(-90, 270, 10):
            rad = math.radians(deg)
            circle_pts.append(Point(125 + 95 * math.cos(rad), 125 + 95 * math.sin(rad)))
        self.templates.append(Template("Circle", "Magic Shield", circle_pts, is_closed=True))

        # 3. รูปทรงสี่เหลี่ยม (Square -> Terra Boulder)
        sq_sharp = [
            Point(35, 35), Point(215, 35), Point(215, 215), Point(35, 215), Point(35, 35)
        ]
        self.templates.append(Template("Square", "Terra Boulder", sq_sharp, is_closed=True))

        sq_rounded = [
            Point(50, 200), Point(35, 125), Point(50, 50),
            Point(125, 35), Point(200, 50),
            Point(215, 125), Point(200, 200),
            Point(125, 215), Point(50, 200)
        ]
        self.templates.append(Template("Square", "Terra Boulder", sq_rounded, is_closed=True))

        # 4. สัญลักษณ์ตัว Z (Z -> Lightning Strike)
        z_sharp = [Point(30, 40), Point(220, 40), Point(35, 210), Point(225, 210)]
        self.templates.append(Template("Z", "Lightning Strike", z_sharp, is_closed=False))

        z_natural = [
            Point(35, 45), Point(125, 40), Point(215, 45),
            Point(165, 100), Point(125, 140), Point(70, 185),
            Point(45, 210), Point(135, 210), Point(225, 210)
        ]
        self.templates.append(Template("Z", "Lightning Strike", z_natural, is_closed=False))

        # 5. รูปทรงหัวใจ (Heart -> Healing Light)
        heart_pts = []
        for deg in range(0, 360, 10):
            t = math.radians(deg)
            x = 16 * (math.sin(t)**3)
            y = -(13 * math.cos(t) - 5 * math.cos(2*t) - 2 * math.cos(3*t) - math.cos(4*t))
            heart_pts.append(Point(125 + x * 6.5, 130 + y * 6.5))
        self.templates.append(Template("Heart", "Healing Light", heart_pts, is_closed=True))

        # 6. สัญลักษณ์อนันต์ (Infinity -> Hollow Purple)
        infinity_pts_cw = []
        infinity_pts_ccw = []
        for deg in range(0, 360, 6):
            t = math.radians(deg)
            scale = 1.0 + (math.sin(t) ** 2)
            ix = (110.0 * math.cos(t)) / scale
            iy = (110.0 * math.sin(t) * math.cos(t)) / scale
            infinity_pts_cw.append(Point(125.0 + ix, 125.0 + iy))

            t_rev = -t
            scale_rev = 1.0 + (math.sin(t_rev) ** 2)
            ix_rev = (110.0 * math.cos(t_rev)) / scale_rev
            iy_rev = (110.0 * math.sin(t_rev) * math.cos(t_rev)) / scale_rev
            infinity_pts_ccw.append(Point(125.0 + ix_rev, 125.0 + iy_rev))

        self.templates.append(Template("Infinity", "Hollow Purple", infinity_pts_cw, is_closed=True))
        self.templates.append(Template("Infinity", "Hollow Purple", infinity_pts_ccw, is_closed=True))

    @staticmethod
    def prune_jitters(raw_points):
        """กรองจุดพิกัดรบกวน (Noise/Jitter) ที่เกิดขึ้นช่วงเริ่มวาดและจุดที่ซ้ำซ้อนใกล้กันเกินไป"""
        if len(raw_points) < 8:
            return raw_points

        clean = [raw_points[0]]
        for p in raw_points[1:]:
            if math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) >= 4.0:
                clean.append(p)

        if len(clean) < 8:
            return clean

        start_idx = 0
        while start_idx < min(5, len(clean) - 4):
            if math.hypot(clean[start_idx+1][0] - clean[0][0], clean[start_idx+1][1] - clean[0][1]) < 8.0:
                start_idx += 1
            else:
                break

        return clean[start_idx:]

    @staticmethod
    def count_corners(points):
        """ตรวจนับมุมแหลมของเส้นวาดด้วยผลคูณเวกเตอร์ (Dot Product) เพื่อจำแนกสี่เหลี่ยมและสามเหลี่ยม"""
        if len(points) < 16:
            return 0
        step = max(3, len(points) // 16)
        corners = 0
        for i in range(step, len(points) - step, step):
            p_prev = points[i - step]
            p_curr = points[i]
            p_next = points[i + step]

            v1 = (p_curr.x - p_prev.x, p_curr.y - p_prev.y)
            v2 = (p_next.x - p_curr.x, p_next.y - p_curr.y)

            m1 = math.hypot(v1[0], v1[1])
            m2 = math.hypot(v2[0], v2[1])

            if m1 > 0 and m2 > 0:
                cos_theta = (v1[0]*v2[0] + v1[1]*v2[1]) / (m1 * m2)
                cos_theta = max(-1.0, min(1.0, cos_theta))
                angle_deg = math.degrees(math.acos(cos_theta))
                if 55.0 <= angle_deg <= 135.0:
                    corners += 1
        return corners

    @staticmethod
    def resample(points, n):
        """เกลี่ยจำนวนจุดของลายเส้นให้กระจายตัวเท่ากันตลอดเส้นเป็นจำนวน n จุดอย่างสม่ำเสมอ"""
        if len(points) < 2:
            return points

        path_len = 0.0
        for i in range(1, len(points)):
            path_len += math.hypot(points[i].x - points[i-1].x, points[i].y - points[i-1].y)

        interval = path_len / (n - 1) if (n - 1) > 0 else 0
        if interval == 0:
            return [Point(points[0].x, points[0].y) for _ in range(n)]

        new_points = [Point(points[0].x, points[0].y)]
        accum_dist = 0.0
        pts_copy = [Point(p.x, p.y) for p in points]

        i = 1
        while i < len(pts_copy):
            d = math.hypot(pts_copy[i].x - pts_copy[i-1].x, pts_copy[i].y - pts_copy[i-1].y)
            if (accum_dist + d) >= interval:
                ratio = (interval - accum_dist) / d if d > 0 else 0
                qx = pts_copy[i-1].x + ratio * (pts_copy[i].x - pts_copy[i-1].x)
                qy = pts_copy[i-1].y + ratio * (pts_copy[i].y - pts_copy[i-1].y)
                q = Point(qx, qy)
                new_points.append(q)
                pts_copy.insert(i, q)
                accum_dist = 0.0
            else:
                accum_dist += d
            i += 1

        while len(new_points) < n:
            new_points.append(Point(pts_copy[-1].x, pts_copy[-1].y))

        return new_points[:n]

    @staticmethod
    def centroid(points):
        """คำนวณหาจุดศูนย์กลางมวล (Centroid) ของชุดพิกัดทั้งหมด"""
        x = sum(p.x for p in points) / len(points)
        y = sum(p.y for p in points) / len(points)
        return Point(x, y)

    @staticmethod
    def rotate_by(points, angle):
        """หมุนชุดจุดพิกัดรอบจุด Centroid ด้วยมุม angle (หน่วยเรเดียน)"""
        c = UnistrokeRecognizer.centroid(points)
        cos_val = math.cos(angle)
        sin_val = math.sin(angle)
        new_points = []
        for p in points:
            dx = p.x - c.x
            dy = p.y - c.y
            new_points.append(Point(
                dx * cos_val - dy * sin_val + c.x,
                dx * sin_val + dy * cos_val + c.y
            ))
        return new_points

    @staticmethod
    def scale_to(points, size):
        """ปรับสเกลขนาดของ Bounding Box ให้มีขนาดเท่ากับกรอบสี่เหลี่ยมมาตรฐาน size x size"""
        min_x = min(p.x for p in points)
        max_x = max(p.x for p in points)
        min_y = min(p.y for p in points)
        max_y = max(p.y for p in points)
        w = max(1.0, max_x - min_x)
        h = max(1.0, max_y - min_y)
        new_points = []
        for p in points:
            new_points.append(Point(p.x * (size / w), p.y * (size / h)))
        return new_points

    @staticmethod
    def translate_to(points, target_pt):
        """เลื่อนตำแหน่งจุด Centroid ของรูปทรงไปยังพิกัดเป้าหมาย target_pt"""
        c = UnistrokeRecognizer.centroid(points)
        new_points = []
        for p in points:
            new_points.append(Point(p.x + target_pt.x - c.x, p.y + target_pt.y - c.y))
        return new_points

    @classmethod
    def normalize_points(cls, points):
        """ปรับโครงสร้างพิกัดลายเส้นให้เป็นมาตรฐานเดียวกัน (Resample -> Scale -> Translate)"""
        pts = cls.resample(points, cls.NUM_POINTS)
        pts = cls.scale_to(pts, cls.SQUARE_SIZE)
        pts = cls.translate_to(pts, Point(0, 0))
        return pts

    @staticmethod
    def path_distance(pts_a, pts_b):
        """คำนวณระยะห่างเฉลี่ยแบบจุดต่อจุดระหว่างชุดพิกัดสองชุด"""
        d = 0.0
        for i in range(len(pts_a)):
            d += math.hypot(pts_a[i].x - pts_b[i].x, pts_a[i].y - pts_b[i].y)
        return d / len(pts_a)

    def _distance_at_best_angle(self, points, template_points):
        """ค้นหามุมหมุนที่ทำให้ลายเส้นซ้อนทับกับแม่แบบได้แนบเนียนที่สุดด้วย Golden Section Search"""
        a = -self.MAX_ROTATION_RAD
        b = self.MAX_ROTATION_RAD
        threshold = math.radians(2.0)

        x1 = self.PHI * a + (1 - self.PHI) * b
        pts_x1 = self.rotate_by(points, x1)
        f1 = self.path_distance(pts_x1, template_points)

        x2 = (1 - self.PHI) * a + self.PHI * b
        pts_x2 = self.rotate_by(points, x2)
        f2 = self.path_distance(pts_x2, template_points)

        while abs(b - a) > threshold:
            if f1 < f2:
                b = x2
                x2 = x1
                f2 = f1
                x1 = self.PHI * a + (1 - self.PHI) * b
                pts_x1 = self.rotate_by(points, x1)
                f1 = self.path_distance(pts_x1, template_points)
            else:
                a = x1
                x1 = x2
                f2 = f1
                x2 = (1 - self.PHI) * a + self.PHI * b
                pts_x2 = self.rotate_by(points, x2)
                f2 = self.path_distance(pts_x2, template_points)

        return min(f1, f2)

    def recognize(self, raw_points):
        """
        ประมวลผลลายเส้นของผู้ใช้เพื่อจำแนกเป็นสัญลักษณ์เวทมนตร์
        Return: (ชื่อรูปร่าง, ชื่อคาถา, คะแนนความแม่นยำ 0.0-1.0)
        """
        cleaned_raw = self.prune_jitters(raw_points)
        if len(cleaned_raw) < 12:
            return "None", "None", 0.0

        pts_fwd = [Point(p[0], p[1]) for p in cleaned_raw]
        pts_rev = [Point(p[0], p[1]) for p in reversed(cleaned_raw)]

        diag = math.hypot(
            max(p[0] for p in cleaned_raw) - min(p[0] for p in cleaned_raw),
            max(p[1] for p in cleaned_raw) - min(p[1] for p in cleaned_raw)
        )
        endpoint_dist = math.hypot(cleaned_raw[0][0] - cleaned_raw[-1][0], cleaned_raw[0][1] - cleaned_raw[-1][1])
        is_user_stroke_closed = (endpoint_dist / max(1.0, diag)) < 0.45

        candidate_fwd = self.normalize_points(pts_fwd)
        candidate_rev = self.normalize_points(pts_rev)

        # คำนวณพื้นที่รูปปิดด้วย Shoelace Formula เพื่อช่วยแยกแยะรูปร่าง
        n_pts = len(candidate_fwd)
        shoelace_area = 0.5 * abs(sum(
            candidate_fwd[i].x * candidate_fwd[(i + 1) % n_pts].y -
            candidate_fwd[(i + 1) % n_pts].x * candidate_fwd[i].y
            for i in range(n_pts)
        ))
        area_ratio = shoelace_area / (self.SQUARE_SIZE * self.SQUARE_SIZE)
        corner_count = self.count_corners(candidate_fwd)

        box_dists = [125.0 - max(abs(p.x), abs(p.y)) for p in candidate_fwd]
        mean_box_dist = sum(box_dists) / len(box_dists)

        is_square_by_corners = (corner_count >= 3) and (area_ratio >= 0.58)

        best_dist = float("inf")
        best_template = None

        # เปรียบเทียบลายเส้นกับชุดแม่แบบทั้งหมด
        for t in self.templates:
            if is_user_stroke_closed and not t.is_closed:
                continue

            if (not is_user_stroke_closed) and t.is_closed and (endpoint_dist / max(1.0, diag)) > 0.55:
                continue

            if area_ratio > 0.60 and t.name == "Triangle":
                continue

            if is_user_stroke_closed and (is_square_by_corners or mean_box_dist < 13.5) and t.name == "Circle":
                continue

            if is_user_stroke_closed and corner_count <= 1 and mean_box_dist >= 14.0 and t.name == "Square":
                continue

            # วนทดสอบการเลื่อนจุดเริ่มต้น (Cyclic Shift) สำหรับรูปทรงปิด
            shifts = range(0, 64, 2) if t.is_closed else [0]

            for s in shifts:
                shifted_fwd = candidate_fwd[s:] + candidate_fwd[:s]
                shifted_rev = candidate_rev[s:] + candidate_rev[:s]

                d_fwd = self._distance_at_best_angle(shifted_fwd, t.points)
                d_rev = self._distance_at_best_angle(shifted_rev, t.points)
                d_min = min(d_fwd, d_rev)

                if t.name == "Square" and is_square_by_corners:
                    d_min *= 0.70

                if d_min < best_dist:
                    best_dist = d_min
                    best_template = t

        score = max(0.0, min(1.0, 1.0 - (best_dist / self.HALF_DIAGONAL)))

        if best_template and score >= self.ACCEPT_THRESHOLD:
            return best_template.name, best_template.spell_name, score
        elif best_template:
            return "Uncertain", best_template.spell_name, score
        return "None", "None", 0.0