#!/usr/bin/env python3
"""
tools/generate_appicon.py
Generates official Apple iOS/iPadOS AppIcon.appiconset assets for
Need for Speed: Carbon (Xbox 360 Title ID: 454107EC).

Extracts the authentic Xbox 360 Title Thumbnail PNG directly from usa_default.xex
(resource 0x8000 in XDBF section), enhances it via multi-stage high-order Lanczos
supersampling and unsharp masking, guarantees strict 24-bit zero-alpha RGB formatting,
and writes out the complete AppIcon suite + Contents.json for Xcode actool validation.
"""

import argparse
import io
import json
import os
import pathlib
import struct
import sys
from PIL import Image, ImageFilter

ROOT = pathlib.Path(__file__).resolve().parent.parent
APPICONSET_DIR = ROOT / "ios" / "resources" / "Assets.xcassets" / "AppIcon.appiconset"
LOCAL_ICON_PATH = ROOT / "tools" / "xbox_title_icon_8000.png"

ICON_SPECS = [
    # Universal / App Store
    {"idiom": "universal", "size": "1024x1024", "scale": "1x", "pixels": 1024, "filename": "AppIcon-1024.png", "platform": "ios"},
    # iPhone
    {"idiom": "iphone", "size": "20x20", "scale": "2x", "pixels": 40, "filename": "AppIcon-20@2x.png"},
    {"idiom": "iphone", "size": "20x20", "scale": "3x", "pixels": 60, "filename": "AppIcon-20@3x.png"},
    {"idiom": "iphone", "size": "29x29", "scale": "2x", "pixels": 58, "filename": "AppIcon-29@2x.png"},
    {"idiom": "iphone", "size": "29x29", "scale": "3x", "pixels": 87, "filename": "AppIcon-29@3x.png"},
    {"idiom": "iphone", "size": "40x40", "scale": "2x", "pixels": 80, "filename": "AppIcon-40@2x.png"},
    {"idiom": "iphone", "size": "40x40", "scale": "3x", "pixels": 120, "filename": "AppIcon-40@3x.png"},
    {"idiom": "iphone", "size": "60x60", "scale": "2x", "pixels": 120, "filename": "AppIcon-60@2x.png"},
    {"idiom": "iphone", "size": "60x60", "scale": "3x", "pixels": 180, "filename": "AppIcon-60@3x.png"},
    # iPad
    {"idiom": "ipad", "size": "20x20", "scale": "1x", "pixels": 20, "filename": "AppIcon-20@1x.png"},
    {"idiom": "ipad", "size": "20x20", "scale": "2x", "pixels": 40, "filename": "AppIcon-20@2x-ipad.png"},
    {"idiom": "ipad", "size": "29x29", "scale": "1x", "pixels": 29, "filename": "AppIcon-29@1x.png"},
    {"idiom": "ipad", "size": "29x29", "scale": "2x", "pixels": 58, "filename": "AppIcon-29@2x-ipad.png"},
    {"idiom": "ipad", "size": "40x40", "scale": "1x", "pixels": 40, "filename": "AppIcon-40@1x.png"},
    {"idiom": "ipad", "size": "40x40", "scale": "2x", "pixels": 80, "filename": "AppIcon-40@2x-ipad.png"},
    {"idiom": "ipad", "size": "76x76", "scale": "1x", "pixels": 76, "filename": "AppIcon-76@1x.png"},
    {"idiom": "ipad", "size": "76x76", "scale": "2x", "pixels": 152, "filename": "AppIcon-76@2x.png"},
    {"idiom": "ipad", "size": "83.5x83.5", "scale": "2x", "pixels": 167, "filename": "AppIcon-83.5@2x.png"},
]


def extract_title_icon_from_xex(xex_path: pathlib.Path) -> Image.Image | None:
    """Extracts resource ID 0x8000 PNG directly from decrypted XEX2 XDBF section."""
    if not xex_path.is_file():
        return None

    try:
        sys.path.insert(0, str(ROOT / "tools"))
        from xex_image import load_xex_image
        print(f"[AppIcon] Decompressing {xex_path.name} to extract 0x8000 game icon...")
        img, _ = load_xex_image(str(xex_path))
        xdbf_pos = img.find(b"XDBF")
        if xdbf_pos == -1:
            return None

        # Parse XDBF table
        magic, ver, free_off, entry_count, entry_used = struct.unpack_from(">4sIIII", img, xdbf_pos)
        pos = xdbf_pos + 0x18
        for _ in range(entry_count):
            entry = img[pos:pos + 18]
            pos += 18
            if len(entry) < 18:
                break
            etype, eid, eoff, esize = struct.unpack(">HQII", entry)
            if etype == 2 and eid == 0x8000:
                # Found 0x8000 title icon!
                png_offset = xdbf_pos + eoff
                png_bytes = img[png_offset:png_offset + esize]
                # Validate PNG magic
                if png_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                    print(f"[AppIcon] Successfully extracted 0x8000 game icon ({len(png_bytes)} bytes) from XEX!")
                    return Image.open(io.BytesIO(png_bytes))
    except Exception as e:
        print(f"[AppIcon] Could not extract from XEX ({e}), falling back to cached icon.")

    return None


def get_base_artwork() -> Image.Image:
    """Gets the official base NFS Carbon icon artwork."""
    # 1. Check local pre-extracted authentic Xbox 360 title icon
    if LOCAL_ICON_PATH.is_file():
        print(f"[AppIcon] Loading pre-extracted official Xbox 360 title icon from {LOCAL_ICON_PATH.name}...")
        return Image.open(LOCAL_ICON_PATH)

    # 2. Try extracting from usa_default.xex or game/default.xex
    xex_candidates = [
        ROOT / "xex" / "usa_default.xex",
        ROOT / "game" / "default.xex",
    ]
    for cand in xex_candidates:
        im = extract_title_icon_from_xex(cand)
        if im is not None:
            # Cache locally for future offline builds
            try:
                LOCAL_ICON_PATH.parent.mkdir(parents=True, exist_ok=True)
                im.save(LOCAL_ICON_PATH, format="PNG")
            except Exception:
                pass
            return im

    # 3. Fallback: create emergency clean solid base if no file present
    print("[AppIcon] WARNING: No XEX or cached icon found. Creating clean fallback...")
    im = Image.new("RGB", (64, 64), (18, 21, 28))
    return im


def upscale_master(src_img: Image.Image, target_size: int = 1024) -> Image.Image:
    """Enhances source game icon via multi-stage Lanczos supersampling and unsharp masking."""
    # Strict 24-bit RGB, no alpha channel
    rgb_img = Image.new("RGB", src_img.size, (10, 12, 16))
    if src_img.mode in ("RGBA", "LA") or ("transparency" in src_img.info):
        rgb_img.paste(src_img, mask=src_img.split()[-1])
    else:
        rgb_img.paste(src_img)

    # Stage 1: 4x intermediate scale with unsharp masking
    mid_size = min(target_size, max(256, rgb_img.width * 4))
    step1 = rgb_img.resize((mid_size, mid_size), Image.Resampling.LANCZOS)
    step1 = step1.filter(ImageFilter.UnsharpMask(radius=2.0, percent=140, threshold=3))

    # Stage 2: Final scale to target master size with fine sharpening
    master = step1.resize((target_size, target_size), Image.Resampling.LANCZOS)
    master = master.filter(ImageFilter.UnsharpMask(radius=1.2, percent=110, threshold=2))

    return master


def generate_icon_suite(master: Image.Image, out_dir: pathlib.Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    images_json = []
    print(f"[AppIcon] Generating {len(ICON_SPECS)} icon sizes in {out_dir}...")

    for spec in ICON_SPECS:
        size = spec["pixels"]
        filename = spec["filename"]
        out_path = out_dir / filename

        # Resample from high-res master
        icon = master.resize((size, size), Image.Resampling.LANCZOS)
        # Ensure strict 24-bit zero-alpha RGB
        if icon.mode != "RGB":
            icon = icon.convert("RGB")
        icon.save(out_path, format="PNG", optimize=True)

        entry = {
            "idiom": spec["idiom"],
            "size": spec["size"],
            "scale": spec["scale"],
            "filename": filename,
        }
        if "platform" in spec:
            entry["platform"] = spec["platform"]
        images_json.append(entry)

    # Generate Contents.json
    contents = {
        "images": images_json,
        "info": {
            "author": "xcode",
            "version": 1
        }
    }
    contents_path = out_dir / "Contents.json"
    with open(contents_path, "w", encoding="utf-8") as f:
        json.dump(contents, f, indent=2)

    print(f"[AppIcon] Wrote {contents_path.name}")
    print(f"[AppIcon] Master 1024x1024 icon: {(out_dir / 'AppIcon-1024.png').stat().st_size} bytes (RGB, 0 alpha)")


def main():
    parser = argparse.ArgumentParser(description="Generate official NFS Carbon AppIcon suite.")
    parser.add_argument("--output", type=pathlib.Path, default=APPICONSET_DIR, help="Output appiconset dir")
    args = parser.parse_args()

    base = get_base_artwork()
    master = upscale_master(base, 1024)
    generate_icon_suite(master, args.output)
    print("[AppIcon] All icons successfully generated!")


if __name__ == "__main__":
    main()
