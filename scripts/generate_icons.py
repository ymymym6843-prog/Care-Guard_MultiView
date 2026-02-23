"""
Generate PWA icons for Sentio.
Blue shield with white cross on dark background.
"""

from PIL import Image, ImageDraw
import os
import math

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "public")

# Colors
BG_COLOR = (15, 23, 42)        # #0f172a - dark background
SHIELD_COLOR = (59, 130, 246)  # #3b82f6 - blue shield
CROSS_COLOR = (255, 255, 255)  # white cross


def draw_shield(draw, cx, cy, size, color):
    """
    Draw a rounded shield shape centered at (cx, cy).
    Wide at the top with rounded shoulders, tapers to a point at the bottom.
    """
    w = size * 0.8
    h = size * 0.85

    top = cy - h * 0.45
    bottom = cy + h * 0.55
    left = cx - w / 2
    right = cx + w / 2

    points = []

    r = w * 0.18

    # Top-left corner arc
    arc_cx_l = left + r
    arc_cy_t = top + r
    for angle_deg in range(180, 270, 5):
        angle = math.radians(angle_deg)
        px = arc_cx_l + r * math.cos(angle)
        py = arc_cy_t + r * math.sin(angle)
        points.append((px, py))

    # Top edge
    points.append((left + r, top))
    points.append((right - r, top))

    # Top-right corner arc
    arc_cx_r = right - r
    for angle_deg in range(270, 360, 5):
        angle = math.radians(angle_deg)
        px = arc_cx_r + r * math.cos(angle)
        py = arc_cy_t + r * math.sin(angle)
        points.append((px, py))

    # Right side going down
    mid_y = cy + h * 0.05
    points.append((right, top + r))
    points.append((right, mid_y))

    # Taper to bottom point with curve
    num_curve_points = 20
    for i in range(num_curve_points + 1):
        t = i / num_curve_points
        ctrl_x = right - w * 0.05
        ctrl_y = bottom - h * 0.15
        x = (1 - t) ** 2 * right + 2 * (1 - t) * t * ctrl_x + t ** 2 * cx
        y = (1 - t) ** 2 * mid_y + 2 * (1 - t) * t * ctrl_y + t ** 2 * bottom
        points.append((x, y))

    # Left side taper from bottom point back up
    for i in range(num_curve_points + 1):
        t = i / num_curve_points
        ctrl_x = left + w * 0.05
        ctrl_y = bottom - h * 0.15
        x = (1 - t) ** 2 * cx + 2 * (1 - t) * t * ctrl_x + t ** 2 * left
        y = (1 - t) ** 2 * bottom + 2 * (1 - t) * t * ctrl_y + t ** 2 * mid_y
        points.append((x, y))

    points.append((left, mid_y))
    points.append((left, top + r))

    draw.polygon(points, fill=color)


def draw_cross(draw, cx, cy, size, color):
    """
    Draw a plus/cross symbol centered at (cx, cy).
    """
    cy_adj = cy - size * 0.03
    arm_length = size * 0.22
    arm_width = size * 0.09
    r = int(arm_width * 0.4)

    # Vertical bar
    vx0 = cx - arm_width
    vy0 = cy_adj - arm_length
    vx1 = cx + arm_width
    vy1 = cy_adj + arm_length
    draw.rounded_rectangle([vx0, vy0, vx1, vy1], radius=r, fill=color)

    # Horizontal bar
    hx0 = cx - arm_length
    hy0 = cy_adj - arm_width
    hx1 = cx + arm_length
    hy1 = cy_adj + arm_width
    draw.rounded_rectangle([hx0, hy0, hx1, hy1], radius=r, fill=color)


def generate_icon(size, filename):
    """Generate a single icon at the given size."""
    scale = 4
    hi_size = size * scale

    img = Image.new("RGBA", (hi_size, hi_size), BG_COLOR + (255,))
    draw = ImageDraw.Draw(img)

    cx = hi_size // 2
    cy = hi_size // 2

    draw_shield(draw, cx, cy, hi_size, SHIELD_COLOR)
    draw_cross(draw, cx, cy, hi_size, CROSS_COLOR)

    # Downscale with high-quality resampling for anti-aliasing
    img = img.resize((size, size), Image.LANCZOS)

    filepath = os.path.join(OUTPUT_DIR, filename)
    if filename.endswith(".ico"):
        img.save(filepath, format="ICO", sizes=[(size, size)])
    else:
        img.save(filepath, format="PNG")

    fsize = os.path.getsize(filepath)
    print(f"Created: {filepath} ({size}x{size}) - {fsize} bytes")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    icons = [
        (192, "icon-192x192.png"),
        (512, "icon-512x512.png"),
        (180, "apple-touch-icon.png"),
        (32, "favicon.ico"),
    ]

    for size, filename in icons:
        generate_icon(size, filename)

    print("\nAll icons generated successfully!")


if __name__ == "__main__":
    main()
