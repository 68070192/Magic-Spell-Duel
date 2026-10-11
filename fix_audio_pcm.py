"""
Magic Spell Duel - Audio Formatter
แปลงไฟล์ WAV ทั้งหมดใน assets/sounds ให้เป็น 16-bit PCM ที่ Pygame รองรับแน่นอน
"""
import os
import wave
import numpy as np

SOUNDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "sounds")

def normalize_wav(filename):
    filepath = os.path.join(SOUNDS_DIR, filename)
    if not os.path.exists(filepath):
        return

    try:
        with wave.open(filepath, 'rb') as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            raw_data = wf.readframes(n_frames)

        # ถ้าเป็น 16-bit อยู่แล้วและไม่มีปัญหาให้ข้ามได้ แต่แปลงซ้ำเพื่อความชัวร์
        if sampwidth == 2:
            data = np.frombuffer(raw_data, dtype=np.int16)
        elif sampwidth == 3:  # 24-bit WAV (ตัวการหลักที่ทำให้ Pygame เงียบ)
            raw_bytes = np.frombuffer(raw_data, dtype=np.uint8)
            # แปลง 24-bit เป็น 32-bit int แล้วลดลงมาเหลือ 16-bit
            a = np.zeros((len(raw_bytes) // 3, 4), dtype=np.uint8)
            a[:, 1:] = raw_bytes.reshape(-1, 3)
            data = (a.view(np.int32) >> 16).astype(np.int16).flatten()
        elif sampwidth == 4:  # 32-bit float or int
            try:
                data = (np.frombuffer(raw_data, dtype=np.float32) * 32767).astype(np.int16)
            except Exception:
                data = (np.frombuffer(raw_data, dtype=np.int32) >> 16).astype(np.int16)
        else:
            return

        with wave.open(filepath, 'wb') as wf_out:
            wf_out.setnchannels(n_channels)
            wf_out.setsampwidth(2)  # บังคับเป็น 16-bit PCM
            wf_out.setframerate(framerate)
            wf_out.writeframes(data.tobytes())
        print(f"✅ Converted to 16-bit PCM: {filename} (Sample Width: {sampwidth} -> 2)")
    except Exception as e:
        print(f"⚠️ Failed to process {filename}: {e}")

for fname in os.listdir(SOUNDS_DIR):
    if fname.endswith(".wav"):
        normalize_wav(fname)

print("🎉 ปรับฟอร์แมตไฟล์เสียงทั้งหมดเรียบร้อยแล้ว!")