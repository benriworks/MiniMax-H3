"""Paste a rendered email onto the computer monitor in a shot, following the screen frame by frame.

Usage: screen_insert.py <source.mp4> <output.mp4> [--debug <dir>]
The monitor's screen is the largest bright, nearly white rectangle near the frame centre. Each frame its
corners are found (largest bright contour, approximated to four points, smoothed over time) and the email
image is warped onto it with a perspective transform, then softly blended so the screen glow stays.
"""
import argparse, json, subprocess
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("source", type=Path)
p.add_argument("output", type=Path)
p.add_argument("--debug", type=Path)
p.add_argument("--zoom", type=float, nargs=3, metavar=("START", "END", "FACTOR"),
               help="slow push-in toward the screen between START and END seconds, up to FACTOR")
a = p.parse_args()
if a.output.exists():
    raise SystemExit(f"{a.output} already exists")

def email_image(w=1200, h=760):
    im = Image.new("RGB", (w, h), (236, 238, 240))
    d = ImageDraw.Draw(im)
    g = r"C:\Windows\Fonts\YuGothM.ttc"
    gb = r"C:\Windows\Fonts\YuGothB.ttc"
    f_small, f, f_b, f_big = (ImageFont.truetype(g, 34), ImageFont.truetype(g, 44), ImageFont.truetype(gb, 46),
                              ImageFont.truetype(gb, 58))
    d.rectangle([0, 0, w, 70], fill=(52, 64, 80))
    d.text((28, 14), "受信トレイ", font=f_b, fill=(240, 240, 240))
    y = 100
    d.text((40, y), "差出人：（非表示）", font=f_small, fill=(90, 90, 96)); y += 50
    d.text((40, y), "件名：第二段階への移行", font=f_b, fill=(20, 20, 24)); y += 74
    d.line([(40, y), (w - 40, y)], fill=(170, 172, 178), width=2); y += 30
    for line in ["第一段階の散布を確認した。", "予定どおり、第二段階へ移行せよ。"]:
        d.text((40, y), line, font=f, fill=(25, 25, 28)); y += 66
    y += 24
    d.rectangle([30, y - 10, w - 30, y + 150], fill=(250, 232, 232), outline=(200, 60, 60), width=3)
    d.text((54, y + 4), "待ち合わせ場所", font=f_small, fill=(170, 30, 30))
    d.text((54, y + 54), "旧港湾 第3倉庫　11月18日 05:00", font=f_big, fill=(150, 20, 20))
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)

def find_screen(frame):
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in cnts:
        area = cv2.contourArea(c)
        x, y, bw, bh = cv2.boundingRect(c)
        if area < 0.02 * w * h or bw < bh * 1.05 or y > 0.7 * h:
            continue
        if best is None or area > cv2.contourArea(best):
            best = c
    if best is None:
        return None
    rect = cv2.minAreaRect(best)
    box = cv2.boxPoints(rect)
    s, d = box.sum(1), np.diff(box, axis=1).ravel()
    return np.array([box[np.argmin(s)], box[np.argmin(d)], box[np.argmax(s)], box[np.argmax(d)]], np.float32)  # tl tr br bl

cap = cv2.VideoCapture(str(a.source))
fps = cap.get(cv2.CAP_PROP_FPS)
frames = []
while True:
    ok, fr = cap.read()
    if not ok:
        break
    frames.append(fr)
cap.release()
quads = [find_screen(f) for f in frames]
found = [q is not None for q in quads]
idx = [i for i, ok in enumerate(found) if ok]
if not idx:
    raise SystemExit("monitor not found")
filled = np.array([quads[i] if found[i] else quads[min(idx, key=lambda j: abs(j - i))] for i in range(len(frames))])
k = 5  # temporal smoothing window
smooth = np.array([filled[max(0, i - k):i + k + 1].mean(0) for i in range(len(filled))])
mail = email_image()
mh, mw = mail.shape[:2]
src = np.array([[0, 0], [mw, 0], [mw, mh], [0, mh]], np.float32)
work = a.output.parent / (a.output.stem + "-frames")
work.mkdir(parents=True, exist_ok=True)
for i, (fr, q) in enumerate(zip(frames, smooth)):
    c = q.mean(0)
    q_in = c + (q - c) * 0.94  # stay inside the bezel
    M = cv2.getPerspectiveTransform(src, q_in.astype(np.float32))
    warped = cv2.warpPerspective(mail, M, (fr.shape[1], fr.shape[0]))
    mask = cv2.warpPerspective(np.full((mh, mw), 255, np.uint8), M, (fr.shape[1], fr.shape[0]))
    # Only where the source still shows the bright screen: anything in front of it (her head) stays on top.
    lit = (cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY) > 120).astype(np.uint8) * 255
    lit = cv2.morphologyEx(lit, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    mask = cv2.bitwise_and(mask, lit)
    mask = cv2.GaussianBlur(mask, (5, 5), 0).astype(np.float32)[..., None] / 255 * 0.93
    out = (fr * (1 - mask) + warped * mask).astype(np.uint8)
    if a.zoom:
        t0, t1, zmax = a.zoom
        t = i / fps
        u = min(max((t - t0) / (t1 - t0), 0.0), 1.0)
        z = 1 + (zmax - 1) * u * u * (3 - 2 * u)  # smooth start and stop
        H, W = out.shape[:2]
        cw, ch = W / z, H / z
        cx = np.clip(c[0], cw / 2, W - cw / 2)
        cy = np.clip(c[1] + H * 0.06, ch / 2, H - ch / 2)
        x0, y0 = cx - cw / 2, cy - ch / 2
        A = np.array([[z, 0, -x0 * z], [0, z, -y0 * z]], np.float32)
        out = cv2.warpAffine(out, A, (W, H), flags=cv2.INTER_LANCZOS4)
    cv2.imwrite(str(work / f"{i:04d}.png"), out)
    if a.debug and i % 24 == 0:
        a.debug.mkdir(parents=True, exist_ok=True)
        dbg = fr.copy()
        cv2.polylines(dbg, [filled[i].astype(np.int32)], True, (0, 0, 255), 3)
        cv2.imwrite(str(a.debug / f"det-{i:04d}.jpg"), dbg)
subprocess.run(["ffmpeg", "-v", "error", "-framerate", f"{fps}", "-i", str(work / "%04d.png"), "-i", str(a.source),
                "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p",
                "-c:a", "copy", "-shortest", str(a.output)], check=True)
(a.output.with_suffix(".json")).write_text(json.dumps({"source": str(a.source), "frames": len(frames),
                                                        "detected": int(sum(found)), "fps": fps}, indent=2) + "\n",
                                           encoding="utf-8")
print("OK", a.output, f"detected {sum(found)}/{len(frames)}")
