"""
Module: resource_helper.py
Description: โมดูลจัดการเส้นทางไฟล์ทรัพยากร (Resource Path Resolution)
             ทำหน้าที่แปลง Relative Path ให้เป็นPathสัมบูรณ์ (Absolute Path)
             รองรับทั้งการรันโปรแกรมผ่าน Python ปกติ และการรันผ่านไฟล์บันเดิล .exe (PyInstaller)
"""

import os
import sys


def get_base_dir():
    """
    ค้นหาและส่งคืนไดเรกทอรีหลัก (Root Directory) ของโปรเจกต์
    - โหมด Executable (PyInstaller): ชี้ไปยังโฟลเดอร์ชั่วคราว sys._MEIPASS
    - โหมด Development (Python): ชี้ไปยังโฟลเดอร์ตำแหน่งที่ตั้งของไฟล์สคริปต์
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def get_resource_path(relative_path=""):
    """
    แปลงพาธสัมพัทธ์ของไฟล์ทรัพยากร (Assets) ให้เป็นพาธสัมบูรณ์ที่ระบบปฏิบัติการเข้าถึงได้ถูกต้อง
    ตัวอย่างการใช้งาน: get_resource_path("assets/sounds/sfx_cast_fire.wav")
    """
    base = get_base_dir()
    if not relative_path:
        return base
    return os.path.normpath(os.path.join(base, relative_path))