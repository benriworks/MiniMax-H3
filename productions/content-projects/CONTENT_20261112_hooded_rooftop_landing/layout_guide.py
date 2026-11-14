"""Render a to-scale layout guide (z-buffered): two roofs, 2 m gap, far roof exactly 1 m lower, 1.65 m figure for scale."""
import sys
import numpy as np
from PIL import Image

W, H = 540, 960
DROP, GAP = 1.0, 2.0
cam = np.array([float(v) for v in sys.argv[2].split(",")]); target = np.array([float(v) for v in sys.argv[3].split(",")])
fov_v = np.radians(float(sys.argv[4]))
f = target - cam; f /= np.linalg.norm(f)
r = np.cross(f, [0, 0, 1]); r /= np.linalg.norm(r)
u = np.cross(r, f)
focal = (H / 2) / np.tan(fov_v / 2)
color = np.zeros((H, W, 3), np.uint8); color[:] = (120, 140, 180)
depth = np.full((H, W), np.inf)
ys, xs = np.mgrid[0:H, 0:W]

def tri(p0, p1, p2, col):
    P = []
    for p in (p0, p1, p2):
        d = np.asarray(p, float) - cam
        z = d @ f
        if z < 0.1:
            return
        P.append((W / 2 + focal * (d @ r) / z, H / 2 - focal * (d @ u) / z, z))
    (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = P
    den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if abs(den) < 1e-9:
        return
    a = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / den
    b = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / den
    c = 1 - a - b
    inv = a / z0 + b / z1 + c / z2
    m = (a >= 0) & (b >= 0) & (c >= 0) & (inv > 0)
    z = np.where(m, 1 / np.where(inv > 0, inv, 1), np.inf)
    m &= z < depth
    depth[m] = z[m]; color[m] = col

def quad(a, b, c, d, col):
    tri(a, b, c, col); tri(a, c, d, col)

def box(x0, x1, y0, y1, z0, z1, top, sx, sy):
    quad((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1), top)
    quad((x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1), sx)
    quad((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1), sx)
    quad((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1), sy)
    quad((x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1), sy)

for gx in range(-60, 60, 10):
    for gy in range(-60, 60, 10):
        quad((gx, gy, -14), (gx + 10, gy, -14), (gx + 10, gy + 10, -14), (gx, gy + 10, -14), (30, 32, 40))
box(-6, 6, GAP, GAP + 12, -14, -DROP, (62, 68, 80), (92, 98, 110), (40, 44, 54))            # far building: roof 1 m lower
box(-6, 6, -14, 0, -14, 0, (176, 182, 190), (150, 156, 166), (110, 116, 126))               # near building
quad((-5.6, -1.2, 0.02), (5.6, -1.2, 0.02), (5.6, -1.0, 0.02), (-5.6, -1.0, 0.02), (230, 180, 40))
box(3.4, 5.0, GAP + 8.5, GAP + 10.1, -DROP, -DROP + 2.4, (170, 50, 40), (150, 40, 34), (160, 45, 36))
for i in range(3):
    box(4.2, 5.0, GAP + 2.5 + i * 1.3, GAP + 3.6 + i * 1.3, -DROP, -DROP + 1.0, (225, 225, 225), (200, 200, 200), (210, 210, 210))
if "stairwell" in sys.argv:
    box(1.0, 3.6, -9.5, -7.0, 0, 2.5, (150, 150, 146), (128, 128, 124), (118, 118, 114))            # stairwell penthouse on the pale roof
    quad((1.8, -6.99, 0), (2.8, -6.99, 0), (2.8, -6.99, 2.0), (1.8, -6.99, 2.0), (70, 74, 80))        # its steel door, facing the gap
if "nomarkers" not in sys.argv:
  box(-0.25, 0.25, -5.2, -4.9, 0, 1.65, (200, 60, 200), (180, 50, 180), (190, 55, 190))       # 1.65 m person marker (start)
  box(-0.25, 0.25, 3.6, 3.9, -DROP, -DROP + 1.65, (60, 200, 200), (50, 180, 180), (55, 190, 190))  # 1.65 m person marker (landing)
Image.fromarray(color).resize((1080, 1920), Image.NEAREST).save(sys.argv[1])
