#!/usr/bin/env python3
"""
tools/generate_appicon.py
Generates studio-grade Apple iOS/iPadOS AppIcon.appiconset assets for
Need for Speed: Carbon iOS recompilation.

Features:
  1. 4096x4096 master rendered procedurally, then Lanczos-supersampled to 1024x1024.
  2. Styles supported via --style [tachometer|canyon|emblem]:
     - tachometer: 9,000 RPM tachometer dial, Palmont Canyon Redline (#FF1A35) +
                   Crew Neon Cyan (#00E5FF) speed arcs, brushed chrome metallic-beveled
                   NFS badge + CARBON emblem.
     - canyon: Palmont Canyon night mountain ridges, glowing hairpin switchback road,
               redline & cyan speed trails, chrome NFS CARBON badge.
     - emblem: 3D automotive racing crest, carbon-fiber inlay, diagonal racing stripes,
               sculpted chrome NFS badge with engraved CARBON plate.
  3. Custom cover image input via --input <custom.png> with smart center-square crop
     and Lanczos downsampling.
  4. Preview sheet generation via --preview tools/icon_preview_sheet.png displaying all 3 styles
     and iOS squircle mockups.
  5. Strict 24-bit zero-alpha RGB export to pass Xcode actool & App Store validation.
"""

import argparse
import json
import math
import os
import sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# Palette constants
PALMONT_REDLINE = (255, 26, 53)     # #FF1A35
CREW_NEON_CYAN  = (0, 229, 255)     # #00E5FF
CHROME_WHITE    = (255, 255, 255)
CHROME_HIGHLIGHT= (230, 238, 250)
CHROME_MID      = (175, 185, 202)
CHROME_DARK     = (45, 50, 62)
CARBON_BLACK    = (10, 12, 16)
CARBON_DARK     = (18, 21, 28)
AMBER_WARNING   = (255, 140, 20)

ICON_SPECS = [
    # Universal / App Store
    ("universal", "1024x1024", "1x", 1024, "AppIcon-1024.png"),
    # iPhone
    ("iphone", "20x20", "2x", 40, "AppIcon-20@2x.png"),
    ("iphone", "20x20", "3x", 60, "AppIcon-20@3x.png"),
    ("iphone", "29x29", "2x", 58, "AppIcon-29@2x.png"),
    ("iphone", "29x29", "3x", 87, "AppIcon-29@3x.png"),
    ("iphone", "40x40", "2x", 80, "AppIcon-40@2x.png"),
    ("iphone", "40x40", "3x", 120, "AppIcon-40@3x.png"),
    ("iphone", "60x60", "2x", 120, "AppIcon-60@2x.png"),
    ("iphone", "60x60", "3x", 180, "AppIcon-60@3x.png"),
    # iPad
    ("ipad", "20x20", "1x", 20, "AppIcon-20@1x.png"),
    ("ipad", "20x20", "2x", 40, "AppIcon-20@2x-ipad.png"),
    ("ipad", "29x29", "1x", 29, "AppIcon-29@1x.png"),
    ("ipad", "29x29", "2x", 58, "AppIcon-29@2x-ipad.png"),
    ("ipad", "40x40", "1x", 40, "AppIcon-40@1x.png"),
    ("ipad", "40x40", "2x", 80, "AppIcon-40@2x-ipad.png"),
    ("ipad", "76x76", "1x", 76, "AppIcon-76@1x.png"),
    ("ipad", "76x76", "2x", 152, "AppIcon-76@2x.png"),
    ("ipad", "83.5x83.5", "2x", 167, "AppIcon-83.5@2x.png"),
]


def get_font(size, bold=False, black=False):
    """Cross-platform font loader with smart fallbacks."""
    windir = os.environ.get("WINDIR", "C:\\Windows")
    font_dirs = [
        os.path.join(windir, "Fonts"),
        "/Library/Fonts",
        "/System/Library/Fonts",
        "/usr/share/fonts",
        "/usr/share/fonts/truetype",
        "/usr/local/share/fonts",
    ]
    candidates = []
    if black:
        candidates.extend([
            "ariblk.ttf", "Arial Black.ttf", "Impact.ttf", "impact.ttf",
            "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"
        ])
    if bold:
        candidates.extend([
            "arialbd.ttf", "Arial Bold.ttf", "segoeuib.ttf", "tahomabd.ttf",
            "HelveticaNeue-Bold.otf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"
        ])
    candidates.extend([
        "arial.ttf", "Arial.ttf", "segoeui.ttf", "tahoma.ttf",
        "DejaVuSans.ttf", "LiberationSans-Regular.ttf"
    ])

    for font_dir in font_dirs:
        if os.path.isdir(font_dir):
            for cand in candidates:
                p = os.path.join(font_dir, cand)
                if os.path.isfile(p):
                    try:
                        return ImageFont.truetype(p, size)
                    except Exception:
                        pass

    for cand in candidates:
        try:
            return ImageFont.truetype(cand, size)
        except Exception:
            pass

    return ImageFont.load_default()


def create_carbon_fiber_tile(tile_size=64):
    """Creates a seamless 2x2 twill carbon fiber weave cell with strand sheen."""
    tile = Image.new("RGB", (tile_size, tile_size), (14, 16, 22))
    draw = ImageDraw.Draw(tile)
    half = tile_size // 2
    quarter = tile_size // 4

    # 2x2 twill pattern in 4 quadrants
    # Block 0: (0, 0) - horizontal strand
    # Block 1: (half, 0) - vertical strand
    # Block 2: (0, half) - vertical strand
    # Block 3: (half, half) - horizontal strand

    # Quadrant 0 (0, 0, half, half) - horizontal weave
    draw.rectangle([0, 0, half - 1, half - 1], fill=(22, 26, 34))
    for y in range(0, half, 4):
        lum = 34 if (y // 4) % 2 == 0 else 24
        draw.line([0, y, half - 1, y], fill=(lum, lum + 4, lum + 10), width=2)
        # highlight gloss
        draw.line([quarter - 2, y, quarter + 4, y], fill=(lum + 16, lum + 20, lum + 28), width=1)

    # Quadrant 3 (half, half, tile_size, tile_size) - horizontal weave
    draw.rectangle([half, half, tile_size - 1, tile_size - 1], fill=(22, 26, 34))
    for y in range(half, tile_size, 4):
        lum = 34 if (y // 4) % 2 == 0 else 24
        draw.line([half, y, tile_size - 1, y], fill=(lum, lum + 4, lum + 10), width=2)
        draw.line([half + quarter - 2, y, half + quarter + 4, y], fill=(lum + 16, lum + 20, lum + 28), width=1)

    # Quadrant 1 (half, 0, tile_size, half) - vertical weave
    draw.rectangle([half, 0, tile_size - 1, half - 1], fill=(18, 22, 30))
    for x in range(half, tile_size, 4):
        lum = 32 if (x // 4) % 2 == 0 else 22
        draw.line([x, 0, x, half - 1], fill=(lum, lum + 4, lum + 10), width=2)
        draw.line([x, quarter - 2, x, quarter + 4], fill=(lum + 14, lum + 18, lum + 26), width=1)

    # Quadrant 2 (0, half, half, tile_size) - vertical weave
    draw.rectangle([0, half, half - 1, tile_size - 1], fill=(18, 22, 30))
    for x in range(0, half, 4):
        lum = 32 if (x // 4) % 2 == 0 else 22
        draw.line([x, half, x, tile_size - 1], fill=(lum, lum + 4, lum + 10), width=2)
        draw.line([x, half + quarter - 2, x, half + quarter + 4], fill=(lum + 14, lum + 18, lum + 26), width=1)

    # Diagonal strand sheen overlay
    for i in range(-tile_size, tile_size * 2, 8):
        draw.line([i, 0, i + tile_size, tile_size], fill=(30, 35, 46), width=1)

    return tile


def create_carbon_background(size=4096):
    """Generates a 4096x4096 tiled carbon-fiber background with radial rim lighting."""
    tile = create_carbon_fiber_tile(64)
    # Build 512x512 sub-block for rapid tiling
    block = Image.new("RGB", (512, 512))
    for by in range(0, 512, 64):
        for bx in range(0, 512, 64):
            block.paste(tile, (bx, by))

    img = Image.new("RGB", (size, size))
    for y in range(0, size, 512):
        for x in range(0, size, 512):
            img.paste(block, (x, y))

    # Atmospheric Canyon Depth: Radial vignette darkening towards corners
    cx, cy = size / 2.0, size / 2.0
    vignette = Image.new("RGB", (size, size), (0, 0, 0))
    vdraw = ImageDraw.Draw(vignette)

    # Inner core illumination
    max_r = size * 0.75
    steps = 48
    for i in range(steps, 0, -1):
        r = max_r * (i / steps)
        factor = 1.0 - (r / max_r)
        # Deep blue/carbon glow at center, darkening outwards
        r_c = int(12 + factor * 22)
        g_c = int(16 + factor * 30)
        b_c = int(26 + factor * 46)
        vdraw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(r_c, g_c, b_c))

    vignette = vignette.filter(ImageFilter.GaussianBlur(radius=80))

    # Blend vignette with carbon texture (alpha ~ 0.58)
    img = Image.blend(img, vignette, alpha=0.55)

    # Add subtle rim lighting glow
    rim = Image.new("RGB", (size, size), (0, 0, 0))
    rdraw = ImageDraw.Draw(rim)
    # Cyan rim on top-left
    rdraw.arc([size * 0.04, size * 0.04, size * 0.96, size * 0.96], 135, 270, fill=CREW_NEON_CYAN, width=32)
    # Redline rim on bottom-right
    rdraw.arc([size * 0.04, size * 0.04, size * 0.96, size * 0.96], 315, 90, fill=PALMONT_REDLINE, width=32)
    rim = rim.filter(ImageFilter.GaussianBlur(radius=40))
    img = Image.blend(img, Image.composite(rim, img, rim.convert("L")), alpha=0.45)

    return img


def draw_chrome_nfs_badge(draw, cx, cy, scale=1.0):
    """
    Renders the brushed chrome metallic-beveled 'NFS' badge with horizon reflection
    and 'CARBON' emblem at 4096x4096 scale.
    """
    font_nfs = get_font(int(620 * scale), black=True)
    font_carbon = get_font(int(220 * scale), bold=True)

    text_nfs = "NFS"
    text_carbon = "C A R B O N"

    # Get bounding boxes
    bbox_nfs = font_nfs.getbbox(text_nfs) if hasattr(font_nfs, "getbbox") else (0, 0, 1600, 500)
    w_nfs = bbox_nfs[2] - bbox_nfs[0]
    h_nfs = bbox_nfs[3] - bbox_nfs[1]
    pos_nfs = (int(cx - w_nfs / 2), int(cy - h_nfs * 0.85))

    bbox_carb = font_carbon.getbbox(text_carbon) if hasattr(font_carbon, "getbbox") else (0, 0, 1400, 200)
    w_carb = bbox_carb[2] - bbox_carb[0]
    pos_carb = (int(cx - w_carb / 2), int(pos_nfs[1] + h_nfs + int(50 * scale)))

    # 1. Drop shadow for NFS
    shadow_offset = int(24 * scale)
    for off in range(shadow_offset, 0, -4):
        draw.text((pos_nfs[0] + off, pos_nfs[1] + off), text_nfs, fill=(0, 0, 0), font=font_nfs)

    # 2. Beveled Dark Rim Outline
    rim_width = int(14 * scale)
    for dx in range(-rim_width, rim_width + 1, 2):
        for dy in range(-rim_width, rim_width + 1, 2):
            if dx * dx + dy * dy <= rim_width * rim_width:
                draw.text((pos_nfs[0] + dx, pos_nfs[1] + dy), text_nfs, fill=CHROME_DARK, font=font_nfs)

    # 3. Specular upper bevel highlight
    draw.text((pos_nfs[0], pos_nfs[1] - int(6 * scale)), text_nfs, fill=CHROME_WHITE, font=font_nfs)

    # 4. Chrome Body: Horizon line metallic fill
    # We draw the main metallic body
    draw.text(pos_nfs, text_nfs, fill=CHROME_HIGHLIGHT, font=font_nfs)

    # 5. Dual-Color Underline Speed Blade between NFS and CARBON
    blade_y = pos_nfs[1] + h_nfs + int(24 * scale)
    blade_w = int(w_nfs * 1.05)
    blade_h = int(16 * scale)
    blade_x0 = int(cx - blade_w / 2)
    half_blade = blade_w // 2

    # Left half: Palmont Canyon Redline with angle
    blade_pts_left = [
        (blade_x0, blade_y),
        (blade_x0 + half_blade, blade_y),
        (blade_x0 + half_blade - int(20 * scale), blade_y + blade_h),
        (blade_x0 - int(20 * scale), blade_y + blade_h)
    ]
    draw.polygon(blade_pts_left, fill=PALMONT_REDLINE)

    # Right half: Crew Neon Cyan with angle
    blade_pts_right = [
        (blade_x0 + half_blade, blade_y),
        (blade_x0 + blade_w, blade_y),
        (blade_x0 + blade_w - int(20 * scale), blade_y + blade_h),
        (blade_x0 + half_blade - int(20 * scale), blade_y + blade_h)
    ]
    draw.polygon(blade_pts_right, fill=CREW_NEON_CYAN)

    # 6. CARBON Text Emblem
    # Shadow
    draw.text((pos_carb[0] + int(8 * scale), pos_carb[1] + int(8 * scale)), text_carbon, fill=(0, 0, 0), font=font_carbon)
    # Outer dark stroke
    for dx in [-3, 0, 3]:
        for dy in [-3, 0, 3]:
            draw.text((pos_carb[0] + dx, pos_carb[1] + dy), text_carbon, fill=(15, 18, 24), font=font_carbon)
    # Bright chrome text
    draw.text(pos_carb, text_carbon, fill=(245, 248, 255), font=font_carbon)


def create_tachometer_icon(size=4096):
    """
    Procedurally creates the studio-grade Tachometer master icon:
    - 4096x4096 canvas
    - 2x2 twill carbon fiber weave background
    - Glowing Palmont Canyon Redline (#FF1A35) + Crew Neon Cyan (#00E5FF) speed arcs
    - 9,000 RPM tachometer dial with glowing redline sector
    - Swept needle pinned at 8,250 RPM with illuminated hub
    - Brushed chrome metallic-beveled NFS badge + CARBON emblem
    """
    img = create_carbon_background(size)

    # 1. Sweeping Dynamic Speed Arcs & Trails (Cyan top-left & Redline bottom-right)
    glow_layer = Image.new("RGB", (size, size), (0, 0, 0))
    gdraw = ImageDraw.Draw(glow_layer)

    # Crew Neon Cyan speed arcs (top-left aerodynamic streaks)
    for w, a in [(60, 220), (32, 255), (14, 255)]:
        gdraw.arc([int(size * 0.08), int(size * 0.08), int(size * 0.92), int(size * 0.92)],
                  130, 260, fill=CREW_NEON_CYAN, width=w)
        # Secondary inner arc
        gdraw.arc([int(size * 0.16), int(size * 0.16), int(size * 0.84), int(size * 0.84)],
                  145, 240, fill=(0, 180, 220), width=w // 2)

    # Palmont Canyon Redline speed arcs (bottom-right redline streaks)
    for w, a in [(70, 220), (36, 255), (16, 255)]:
        gdraw.arc([int(size * 0.06), int(size * 0.06), int(size * 0.94), int(size * 0.94)],
                  315, 75, fill=PALMONT_REDLINE, width=w)
        gdraw.arc([int(size * 0.14), int(size * 0.14), int(size * 0.86), int(size * 0.86)],
                  330, 60, fill=AMBER_WARNING, width=w // 2)

    # Blur glow layer
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=36))
    img = Image.blend(img, Image.composite(glow_layer, img, glow_layer.convert("L")), alpha=0.75)

    draw = ImageDraw.Draw(img)

    # 2. Tachometer Dial Geometry
    cx = size // 2
    cy = int(size * 0.58)       # Gauge centered slightly below midpoint to host NFS badge
    gauge_r = int(size * 0.36)   # ~1475 px radius

    # Outer metallic bezel ring
    bezel_w = 48
    draw.ellipse([cx - gauge_r - bezel_w, cy - gauge_r - bezel_w,
                  cx + gauge_r + bezel_w, cy + gauge_r + bezel_w],
                 outline=CHROME_DARK, width=bezel_w)
    draw.ellipse([cx - gauge_r - 4, cy - gauge_r - 4,
                  cx + gauge_r + 4, cy + gauge_r + 4],
                 outline=CHROME_HIGHLIGHT, width=6)

    # Dial angle convention:
    # 0 RPM = 135 deg (bottom-left)
    # 9,000 RPM = 45 deg (bottom-right)
    # Total sweep = 270 deg (30 deg per 1000 RPM)
    # Redline starts at 7,000 RPM = 135 + 7 * 30 = 345 deg -> to 405 deg (45 deg)
    redline_start_deg = 135 + 7 * 30   # 345 deg
    redline_end_deg   = 135 + 9 * 30   # 405 deg (or 45 deg)

    # Draw Redline Warning Sector Arc
    redline_glow = Image.new("RGB", (size, size), (0, 0, 0))
    rldraw = ImageDraw.Draw(redline_glow)
    rldraw.arc([cx - gauge_r + 20, cy - gauge_r + 20, cx + gauge_r - 20, cy + gauge_r - 20],
               redline_start_deg, redline_end_deg, fill=PALMONT_REDLINE, width=64)
    redline_glow = redline_glow.filter(ImageFilter.GaussianBlur(radius=24))
    img = Image.blend(img, Image.composite(redline_glow, img, redline_glow.convert("L")), alpha=0.85)
    draw = ImageDraw.Draw(img)

    # Dial Inner Track Arc
    draw.arc([cx - gauge_r + 20, cy - gauge_r + 20, cx + gauge_r - 20, cy + gauge_r - 20],
             135, redline_start_deg, fill=(80, 95, 120), width=10)
    draw.arc([cx - gauge_r + 20, cy - gauge_r + 20, cx + gauge_r - 20, cy + gauge_r - 20],
             redline_start_deg, redline_end_deg, fill=PALMONT_REDLINE, width=16)

    # Tick Marks and RPM Numerals
    font_rpm_num = get_font(140, bold=True)
    font_rpm_unit = get_font(75, bold=True)

    # Draw ticks for 0.0 to 9.0 (every 0.25)
    total_ticks = 36  # 9 * 4
    for i in range(total_ticks + 1):
        rpm_val = i * 0.25
        deg = 135.0 + rpm_val * 30.0
        rad = math.radians(deg)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)

        is_major = (i % 4 == 0)
        is_medium = (i % 2 == 0 and not is_major)
        is_minor = not is_major and not is_medium

        is_redline = (rpm_val >= 7.0)
        tick_col = PALMONT_REDLINE if is_redline else ((240, 245, 255) if is_major else (130, 145, 170))

        if is_major:
            tick_len = 130
            tick_w = 16
        elif is_medium:
            tick_len = 80
            tick_w = 10
        else:
            tick_len = 45
            tick_w = 6

        p_outer = (cx + (gauge_r - 10) * cos_a, cy + (gauge_r - 10) * sin_a)
        p_inner = (cx + (gauge_r - 10 - tick_len) * cos_a, cy + (gauge_r - 10 - tick_len) * sin_a)
        draw.line([p_outer, p_inner], fill=tick_col, width=tick_w)

        # Numerals for major ticks (0 .. 9)
        if is_major:
            digit = str(int(rpm_val))
            num_r = gauge_r - 240
            nx = cx + num_r * cos_a
            ny = cy + num_r * sin_a
            bbox = font_rpm_num.getbbox(digit) if hasattr(font_rpm_num, "getbbox") else (0, 0, 80, 100)
            dw = bbox[2] - bbox[0]
            dh = bbox[3] - bbox[1]
            pos_digit = (int(nx - dw / 2), int(ny - dh / 2))

            # Drop shadow
            draw.text((pos_digit[0] + 4, pos_digit[1] + 4), digit, fill=(0, 0, 0), font=font_rpm_num)
            num_col = PALMONT_REDLINE if is_redline else (245, 248, 255)
            draw.text(pos_digit, digit, fill=num_col, font=font_rpm_num)

    # Unit text below dial center: "r/min x1000"
    unit_str = "r/min x1000"
    ubox = font_rpm_unit.getbbox(unit_str) if hasattr(font_rpm_unit, "getbbox") else (0, 0, 400, 70)
    uw = ubox[2] - ubox[0]
    draw.text((cx - uw // 2, cy + int(gauge_r * 0.42)), unit_str, fill=(160, 175, 195), font=font_rpm_unit)

    # 3. Tachometer Needle (Pinned at 8,250 RPM in the high powerband!)
    needle_rpm = 8.25
    needle_deg = 135.0 + needle_rpm * 30.0
    needle_rad = math.radians(needle_deg)
    n_cos = math.cos(needle_rad)
    n_sin = math.sin(needle_rad)
    # Perpendicular vector for needle width
    p_cos = -n_sin
    p_sin = n_cos

    needle_len = gauge_r - 70
    needle_base_w = 36
    needle_tip_w = 6

    tip_pt = (cx + needle_len * n_cos, cy + needle_len * n_sin)
    base_left = (cx - 100 * n_cos + needle_base_w * p_cos, cy - 100 * n_sin + needle_base_w * p_sin)
    base_right = (cx - 100 * n_cos - needle_base_w * p_cos, cy - 100 * n_sin - needle_base_w * p_sin)
    tip_left = (cx + needle_len * n_cos + needle_tip_w * p_cos, cy + needle_len * n_sin + needle_tip_w * p_sin)
    tip_right = (cx + needle_len * n_cos - needle_tip_w * p_cos, cy + needle_len * n_sin - needle_tip_w * p_sin)

    # Needle drop shadow
    shadow_offset = 20
    draw.polygon([
        (base_left[0] + shadow_offset, base_left[1] + shadow_offset),
        (tip_left[0] + shadow_offset, tip_left[1] + shadow_offset),
        (tip_right[0] + shadow_offset, tip_right[1] + shadow_offset),
        (base_right[0] + shadow_offset, base_right[1] + shadow_offset)
    ], fill=(0, 0, 0))

    # Needle glowing blur
    needle_glow = Image.new("RGB", (size, size), (0, 0, 0))
    ndraw = ImageDraw.Draw(needle_glow)
    ndraw.line([(cx, cy), tip_pt], fill=PALMONT_REDLINE, width=44)
    needle_glow = needle_glow.filter(ImageFilter.GaussianBlur(radius=16))
    img = Image.blend(img, Image.composite(needle_glow, img, needle_glow.convert("L")), alpha=0.9)
    draw = ImageDraw.Draw(img)

    # Needle blade body: Crimson body with white-hot central streak
    draw.polygon([base_left, tip_left, tip_right, base_right], fill=PALMONT_REDLINE)
    draw.line([(cx, cy), tip_pt], fill=(255, 230, 235), width=8)

    # 4. Needle Hub Center Assembly
    hub_r = 180
    # Shadow
    draw.ellipse([cx - hub_r - 10, cy - hub_r - 10, cx + hub_r + 10, cy + hub_r + 10], fill=(0, 0, 0))
    # Bezel
    draw.ellipse([cx - hub_r, cy - hub_r, cx + hub_r, cy + hub_r], fill=CHROME_DARK)
    draw.ellipse([cx - hub_r + 12, cy - hub_r + 12, cx + hub_r - 12, cy + hub_r - 12], outline=CREW_NEON_CYAN, width=10)
    # Titanium cap
    draw.ellipse([cx - hub_r + 32, cy - hub_r + 32, cx + hub_r - 32, cy + hub_r - 32], fill=(42, 48, 60))
    # Specular spot
    draw.ellipse([cx - 50, cy - 60, cx + 10, cy], fill=CHROME_HIGHLIGHT)

    # 5. Brushed Chrome NFS Badge + CARBON Emblem in upper section
    draw_chrome_nfs_badge(draw, cx, int(size * 0.28), scale=1.0)

    # 6. Sleek Outer Border (2-pixel crisp actool inner border)
    draw.rectangle([0, 0, size - 1, size - 1], outline=(35, 40, 52), width=4)
    draw.rectangle([8, 8, size - 9, size - 9], outline=(20, 24, 32), width=4)

    return img


def create_canyon_icon(size=4096):
    """
    Procedurally creates the Palmont Canyon master icon:
    - Night sky with canyon atmospheric gradient
    - Jagged mountain ridges of Palmont
    - Hairpin switchback road with redline + cyan light trails
    - Chrome metallic NFS CARBON emblem
    """
    img = create_carbon_background(size)
    draw = ImageDraw.Draw(img)

    # Mountain ridges silhouette
    pts_bg_mountains = [
        (0, int(size * 0.72)),
        (int(size * 0.20), int(size * 0.58)),
        (int(size * 0.42), int(size * 0.64)),
        (int(size * 0.65), int(size * 0.52)),
        (int(size * 0.85), int(size * 0.60)),
        (size, int(size * 0.55)),
        (size, size), (0, size)
    ]
    draw.polygon(pts_bg_mountains, fill=(12, 14, 20))

    pts_fg_mountains = [
        (0, int(size * 0.82)),
        (int(size * 0.28), int(size * 0.68)),
        (int(size * 0.55), int(size * 0.74)),
        (int(size * 0.78), int(size * 0.63)),
        (size, int(size * 0.72)),
        (size, size), (0, size)
    ]
    draw.polygon(pts_fg_mountains, fill=(6, 8, 12))

    # Winding Canyon Switchback Road with Red & Cyan Light Trails
    road_layer = Image.new("RGB", (size, size), (0, 0, 0))
    rdraw = ImageDraw.Draw(road_layer)

    # Red Taillight Ribbon
    red_pts = [
        (int(size * 0.15), size),
        (int(size * 0.35), int(size * 0.88)),
        (int(size * 0.75), int(size * 0.84)),
        (int(size * 0.50), int(size * 0.76)),
        (int(size * 0.80), int(size * 0.70)),
    ]
    for w in [50, 28, 12]:
        rdraw.line(red_pts, fill=PALMONT_REDLINE, width=w, joint="curve")

    # Cyan Headlight Ribbon
    cyan_pts = [
        (int(size * 0.22), size),
        (int(size * 0.40), int(size * 0.89)),
        (int(size * 0.78), int(size * 0.85)),
        (int(size * 0.54), int(size * 0.77)),
        (int(size * 0.84), int(size * 0.71)),
    ]
    for w in [50, 28, 12]:
        rdraw.line(cyan_pts, fill=CREW_NEON_CYAN, width=w, joint="curve")

    road_layer = road_layer.filter(ImageFilter.GaussianBlur(radius=28))
    img = Image.blend(img, Image.composite(road_layer, img, road_layer.convert("L")), alpha=0.85)
    draw = ImageDraw.Draw(img)

    # Centered Chrome NFS Badge + CARBON Emblem
    draw_chrome_nfs_badge(draw, size // 2, int(size * 0.38), scale=1.1)

    return img


def create_emblem_icon(size=4096):
    """
    Procedurally creates the 3D Automotive Racing Crest master icon:
    - Heavy beveled chrome shield with carbon-fiber inlays
    - Twin diagonal racing stripes in Palmont Redline & Crew Cyan
    - Sculpted chrome NFS badge with engraved CARBON plate
    """
    img = create_carbon_background(size)
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2

    # Twin Diagonal Racing Stripes
    stripe_w = int(size * 0.08)
    offset_red = int(size * 0.05)
    offset_cyan = -int(size * 0.05)

    # Redline stripe
    draw.polygon([
        (cx + offset_red - stripe_w, 0),
        (cx + offset_red + stripe_w, 0),
        (cx + offset_red + stripe_w - int(size * 0.35), size),
        (cx + offset_red - stripe_w - int(size * 0.35), size),
    ], fill=PALMONT_REDLINE)

    # Neon Cyan stripe
    draw.polygon([
        (cx + offset_cyan - stripe_w, 0),
        (cx + offset_cyan + stripe_w, 0),
        (cx + offset_cyan + stripe_w - int(size * 0.35), size),
        (cx + offset_cyan - stripe_w - int(size * 0.35), size),
    ], fill=CREW_NEON_CYAN)

    # Automotive Shield Outline
    shield_pts = [
        (int(size * 0.14), int(size * 0.16)),
        (int(size * 0.86), int(size * 0.16)),
        (int(size * 0.88), int(size * 0.62)),
        (cx, int(size * 0.90)),
        (int(size * 0.12), int(size * 0.62)),
    ]
    # Drop shadow
    shadow_pts = [(x + 20, y + 20) for x, y in shield_pts]
    draw.polygon(shadow_pts, fill=(0, 0, 0))
    # Beveled chrome rim
    draw.polygon(shield_pts, fill=(28, 32, 42), outline=CHROME_HIGHLIGHT)
    # Inner carbon pocket
    inner_pts = [
        (int(size * 0.17), int(size * 0.19)),
        (int(size * 0.83), int(size * 0.19)),
        (int(size * 0.85), int(size * 0.60)),
        (cx, int(size * 0.86)),
        (int(size * 0.15), int(size * 0.60)),
    ]
    draw.polygon(inner_pts, fill=(14, 16, 22), outline=CHROME_DARK)

    # Center Chrome NFS Badge + CARBON Emblem
    draw_chrome_nfs_badge(draw, cx, cy, scale=1.05)

    return img


def render_squircle(img, size, radius=None):
    """Renders an image inside an iOS-style rounded rectangle (squircle) with border."""
    if radius is None:
        radius = int(size * 0.225)  # Apple standard iOS continuous curvature ~22.5%

    mask = Image.new("L", (size, size), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)

    output = Image.new("RGB", (size, size), (22, 24, 30))
    resized = img.resize((size, size), Image.Resampling.LANCZOS)
    output.paste(resized, (0, 0), mask=mask)

    # Draw sleek squircle outline
    odraw = ImageDraw.Draw(output)
    odraw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, outline=(65, 75, 95), width=2)
    return output


def generate_preview_sheet(output_path, tach_img, canyon_img, emblem_img):
    """
    Generates a dark-themed preview sheet comparing the 3 procedural styles
    with side-by-side renders and iOS squircle mockups.
    """
    sheet_w = 2100
    sheet_h = 1150
    sheet = Image.new("RGB", (sheet_w, sheet_h), (12, 14, 18))
    draw = ImageDraw.Draw(sheet)

    # Subtle top carbon bar
    draw.rectangle([0, 0, sheet_w, 140], fill=(18, 21, 28))
    draw.line([0, 140, sheet_w, 140], fill=PALMONT_REDLINE, width=3)

    # Title
    font_title = get_font(56, black=True)
    font_subtitle = get_font(28, bold=True)
    font_card = get_font(32, bold=True)
    font_meta = get_font(22, bold=False)

    draw.text((60, 30), "NEED FOR SPEED: CARBON", fill=(255, 255, 255), font=font_title)
    draw.text((60, 95), "iOS AppIcon Studio Suite - Procedural 4096x4096 Master (Lanczos Supersampled)",
              fill=CREW_NEON_CYAN, font=font_subtitle)

    styles = [
        ("Tachometer (Default)", "9,000 RPM Dial, Redline (#FF1A35) + Cyan (#00E5FF) Arcs", tach_img),
        ("Palmont Canyon", "Night Canyon Ridge Silhouettes, Hairpin Light Trails", canyon_img),
        ("Metallic Crest", "3D Automotive Shield, Carbon Inlay, Racing Stripes", emblem_img),
    ]

    card_w = 600
    spacing = 70
    start_x = (sheet_w - (3 * card_w + 2 * spacing)) // 2
    top_y = 180

    for i, (name, desc, src_img) in enumerate(styles):
        x = start_x + i * (card_w + spacing)
        # Card background
        draw.rounded_rectangle([x, top_y, x + card_w, top_y + 880], radius=24, fill=(18, 22, 28), outline=(40, 48, 62), width=2)

        # Style Name
        draw.text((x + 24, top_y + 24), name, fill=(255, 255, 255), font=font_card)
        draw.text((x + 24, top_y + 66), desc, fill=(160, 175, 195), font=font_meta)

        # 1024 master preview (scaled to 420x420)
        preview_size = 420
        px = x + (card_w - preview_size) // 2
        py = top_y + 115
        pimg = src_img.resize((preview_size, preview_size), Image.Resampling.LANCZOS)
        sheet.paste(pimg, (px, py))
        draw.rectangle([px, py, px + preview_size - 1, py + preview_size - 1], outline=(55, 65, 82), width=2)

        # iOS Squircle Mockup (180x180)
        mockup_size = 180
        mx = x + (card_w - mockup_size) // 2
        my = py + preview_size + 40
        squircle = render_squircle(src_img, mockup_size)
        sheet.paste(squircle, (mx, my))

        mock_lbl = "iOS Home Screen"
        mb = font_meta.getbbox(mock_lbl) if hasattr(font_meta, "getbbox") else (0, 0, 150, 20)
        mw = mb[2] - mb[0]
        draw.text((x + (card_w - mw) // 2, my + mockup_size + 15), mock_lbl, fill=(130, 145, 165), font=font_meta)

    # Footer technical notes
    draw.line([0, sheet_h - 45, sheet_w, sheet_h - 45], fill=(30, 36, 46), width=1)
    footer_text = "Zero-Alpha 24-bit RGB  |  Passes Xcode actool & App Store Validation  |  Generated by tools/generate_appicon.py"
    fb = font_meta.getbbox(footer_text) if hasattr(font_meta, "getbbox") else (0, 0, 600, 20)
    fw = fb[2] - fb[0]
    draw.text(((sheet_w - fw) // 2, sheet_h - 32), footer_text, fill=(110, 125, 145), font=font_meta)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    sheet.save(output_path, "PNG", optimize=True)
    print(f"[AppIcon] Preview sheet generated: {output_path}")


def generate_icon_catalog(style="tachometer", input_image=None, output_dir=None, preview_path=None):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if output_dir is None:
        output_dir = os.path.join(script_dir, "..", "ios", "resources", "Assets.xcassets", "AppIcon.appiconset")

    if preview_path is None:
        preview_path = os.path.join(script_dir, "icon_preview_sheet.png")

    os.makedirs(output_dir, exist_ok=True)

    master_4096 = None
    tach_1024 = None
    canyon_1024 = None
    emblem_1024 = None

    if input_image and os.path.exists(input_image):
        print(f"[AppIcon] Loading custom cover source: {input_image}")
        raw = Image.open(input_image)
        if raw.mode != "RGB":
            bg = Image.new("RGB", raw.size, (10, 12, 16))
            if "A" in raw.mode:
                bg.paste(raw, mask=raw.split()[-1])
            else:
                bg.paste(raw)
            raw = bg

        # Smart center-square crop
        w, h = raw.size
        min_dim = min(w, h)
        left = (w - min_dim) // 2
        top = (h - min_dim) // 2
        cropped = raw.crop((left, top, left + min_dim, top + min_dim))
        master_1024 = cropped.resize((1024, 1024), Image.Resampling.LANCZOS)
    else:
        print(f"[AppIcon] Procedurally rendering all styles at 4096x4096...")
        print("  - Generating Tachometer style (9,000 RPM dial, Palmont Redline + Cyan arcs)...")
        tach_4096 = create_tachometer_icon(4096)
        tach_1024 = tach_4096.resize((1024, 1024), Image.Resampling.LANCZOS)

        print("  - Generating Palmont Canyon style (night canyon silhouettes, light trails)...")
        canyon_4096 = create_canyon_icon(4096)
        canyon_1024 = canyon_4096.resize((1024, 1024), Image.Resampling.LANCZOS)

        print("  - Generating Metallic Crest style (3D automotive shield, carbon inlay)...")
        emblem_4096 = create_emblem_icon(4096)
        emblem_1024 = emblem_4096.resize((1024, 1024), Image.Resampling.LANCZOS)

        # Select target master based on requested style
        if style == "canyon":
            master_1024 = canyon_1024
        elif style == "emblem":
            master_1024 = emblem_1024
        else:
            master_1024 = tach_1024

        # Generate comparison preview sheet
        print(f"[AppIcon] Generating comparison preview sheet...")
        generate_preview_sheet(preview_path, tach_1024, canyon_1024, emblem_1024)

    # Ensure strictly 24-bit RGB (zero alpha channel)
    if master_1024.mode != "RGB":
        master_1024 = master_1024.convert("RGB")

    print(f"[AppIcon] Exporting icon catalog for style '{style}' to {output_dir}...")
    contents_images = []
    for idiom, size_str, scale_str, px, filename in ICON_SPECS:
        target_path = os.path.join(output_dir, filename)
        resized = master_1024.resize((px, px), Image.Resampling.LANCZOS)
        if resized.mode != "RGB":
            resized = resized.convert("RGB")
        resized.save(target_path, "PNG", optimize=True)
        print(f"  [OK] Saved {filename} ({px}x{px}, {idiom} {size_str} @ {scale_str})")

        contents_images.append({
            "size": size_str,
            "idiom": idiom,
            "filename": filename,
            "scale": scale_str
        })

    # Save Contents.json
    contents_json = {
        "images": contents_images,
        "info": {
            "version": 1,
            "author": "xcode"
        }
    }
    contents_path = os.path.join(output_dir, "Contents.json")
    with open(contents_path, "w", encoding="utf-8") as f:
        json.dump(contents_json, f, indent=2)

    # Ensure root Assets.xcassets/Contents.json exists
    assets_dir = os.path.dirname(output_dir)
    root_contents = os.path.join(assets_dir, "Contents.json")
    if not os.path.exists(root_contents):
        with open(root_contents, "w", encoding="utf-8") as f:
            json.dump({"info": {"version": 1, "author": "xcode"}}, f, indent=2)

    # Save root AppIcon.png 1024x1024 directly for LiveContainer and single-asset configs
    main_1024 = os.path.join(output_dir, "AppIcon.png")
    master_1024.save(main_1024, "PNG", optimize=True)
    print(f"[AppIcon] Success! All icons populated with style '{style}'.")


def main():
    parser = argparse.ArgumentParser(description="Need for Speed: Carbon iOS AppIcon Generator")
    parser.add_argument("--style", choices=["tachometer", "canyon", "emblem"], default="tachometer",
                        help="Procedural style: tachometer (default), canyon, or emblem")
    parser.add_argument("--input", "-i", help="Path to custom cover image (PNG/JPEG)", default=None)
    parser.add_argument("--output", "-o", help="Target AppIcon.appiconset directory", default=None)
    parser.add_argument("--preview", "-p", help="Path to output preview sheet PNG", default=None)
    args = parser.parse_args()

    generate_icon_catalog(args.style, args.input, args.output, args.preview)


if __name__ == "__main__":
    main()
