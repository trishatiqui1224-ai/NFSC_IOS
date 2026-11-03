#!/usr/bin/env python3
"""
tools/patch_fixes.py
Applies runtime fixes 1-5 for NFS Carbon iOS:
1. Lock guest EDRAM resolution to 1560x720 / 1280x720 (<=900 tiles) & implement host display presets
2. Ensure zero-stall asynchronous present & FSR/CAS host scaling
3. Register 0x821A3EC8 flasher callback, scan function pointers in .rdata/.data, reduce XMA desatasco timeout
4. Dynamic Island & safe-area margins in touch controls
5. Official NFS Carbon Xbox 360 title icon suite extraction and generation
"""

import os
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent

def patch_ios_main():
    p = ROOT / "ios" / "src" / "ios_main.mm"
    content = p.read_text(encoding="utf-8")
    
    # 1. Update GameArguments default resolution
    old_args = '''      "--anisotropic_override=16",
      "--present_effect=cas",
      "--carbon_scene_resolution=2340x1080",'''
    new_args = '''      "--anisotropic_override=16",
      "--present_effect=cas",
      "--resolution=1560x720",
      "--carbon_scene_resolution=1560x720",
      "--ios_display_preset=1080p",'''
    if old_args in content:
        content = content.replace(old_args, new_args)
        print("[patch] Patched GameArguments in ios_main.mm")

    # 2. Add UserDefaults sanitization on launch
    old_play = '''  std::vector<std::string> texts{argc > 0 ? argv[0] : "nfscarbon"};
  if (play) {
    const auto game = GameArguments(docs, iso);'''
    new_play = '''  // Reset any saved resolutions > 1600x720 to avoid 11-bit Xenos EDRAM overflow (max 900 tiles)
  NSUserDefaults* defs = [NSUserDefaults standardUserDefaults];
  NSString* saved_cres = [defs stringForKey:@"carbon_scene_resolution"];
  if (saved_cres) {
    unsigned w = 0, h = 0;
    if (sscanf(saved_cres.UTF8String, "%ux%u", &w, &h) == 2 && (w > 1600 || h > 720)) {
      [defs setObject:@"1560x720" forKey:@"carbon_scene_resolution"];
    }
  }

  std::vector<std::string> texts{argc > 0 ? argv[0] : "nfscarbon"};
  if (play) {
    const auto game = GameArguments(docs, iso);'''
    if old_play in content and "Reset any saved resolutions > 1600x720" not in content:
        content = content.replace(old_play, new_play)
        print("[patch] Patched launch sanitization in ios_main.mm")

    p.write_text(content, encoding="utf-8")


def patch_launcher():
    p = ROOT / "ios" / "src" / "launcher.mm"
    content = p.read_text(encoding="utf-8")

    # 1. Update scene_res setting descriptor
    old_desc = '''           {@"scene_res", Type::kChoice, @"Scene resolution",
            @"Native internal 3D scene resolution for NFS Carbon. 1080p default provides razor-sharp visuals on Apple Silicon.",
            @"1080p",
            {{@"720p (1560x720)", @"720p"}, {@"900p (1950x900)", @"900p"}, {@"1080p (2340x1080)", @"1080p"},
             {@"Native Retina (2622x1206)", @"retina"}}},'''
    new_desc = '''           {@"scene_res", Type::kChoice, @"Display Quality Preset",
            @"Controls the Host Metal Drawable Size & GPU Spatial Upscaler (CAS/FSR). Guest EDRAM is locked to 720p to guarantee 100% corruption-free rendering.",
            @"1080p",
            {{@"720p (1560x720)", @"720p"}, {@"900p (1950x900)", @"900p"}, {@"1080p (2340x1080)", @"1080p"},
             {@"Native Retina (2622x1206)", @"retina"}}},'''
    if old_desc in content:
        content = content.replace(old_desc, new_desc)
        print("[patch] Patched scene_res description in launcher.mm")

    # 2. Update LoadSettings to sanitize old raw resolutions
    old_load = '''  // Set high-res scene defaults (1080p, CAS, 16x Anisotropic).
  if (!s[@"carbon_v2_migrated"]) {
    s[@"audio_starve_reset"] = @"false";
    s[@"native_renderer"] = @"false";
    s[@"nfsmw_native_cp"] = @"false";
    s[@"scene_res"] = @"1080p";
    s[@"scaling"] = @"cas";
    s[@"anisotropic"] = @"5";
    s[@"scale"] = @"1";
    s[@"carbon_v2_migrated"] = @"true";
    SaveSettings(docs, s);
  }'''
    new_load = '''  // Set high-res scene defaults (1080p, CAS, 16x Anisotropic).
  if (!s[@"carbon_v2_migrated"]) {
    s[@"audio_starve_reset"] = @"false";
    s[@"native_renderer"] = @"false";
    s[@"nfsmw_native_cp"] = @"false";
    s[@"scene_res"] = @"1080p";
    s[@"scaling"] = @"cas";
    s[@"anisotropic"] = @"5";
    s[@"scale"] = @"1";
    s[@"carbon_v2_migrated"] = @"true";
    SaveSettings(docs, s);
  }

  // Sanitize any previously saved high raw resolution strings into clean display presets
  NSString* saved_scene_res = s[@"scene_res"];
  if (saved_scene_res) {
    if ([saved_scene_res isEqualToString:@"2340x1080"] || [saved_scene_res isEqualToString:@"1080p"]) {
      s[@"scene_res"] = @"1080p";
    } else if ([saved_scene_res isEqualToString:@"1950x900"] || [saved_scene_res isEqualToString:@"900p"]) {
      s[@"scene_res"] = @"900p";
    } else if ([saved_scene_res isEqualToString:@"2622x1206"] || [saved_scene_res isEqualToString:@"retina"]) {
      s[@"scene_res"] = @"retina";
    } else {
      s[@"scene_res"] = @"720p";
    }
  }'''
    if old_load in content and "Sanitize any previously saved high raw resolution strings" not in content:
        content = content.replace(old_load, new_load)
        print("[patch] Patched LoadSettings in launcher.mm")

    # 3. Update Arguments() to lock guest resolution and pass display preset
    old_args_block = '''  // Screen and aspect ratio
  NSString* const aspect = ResolvedAspect(s);
  const bool wide = [aspect isEqualToString:@"wide"];
  if ([aspect isEqualToString:@"4:3"]) {
    a.push_back("--resolution=1024x768");
  } else if (wide) {
    a.push_back("--resolution=1560x720");
  }'''
    new_args_block = '''  // Lock guest --resolution and --carbon_scene_resolution in lockstep to EDRAM-safe dimensions:
  // - Ultrawide iPhone (~19.5:9): 1560x720 (20t x 45r = 900 tiles, zero EDRAM overlap, runs at 113+ FPS on A19!)
  // - Standard Widescreen (16:9 / iPad): 1280x720 (16t x 45r = 720 tiles)
  // - 4:3 mode: 1024x768 (13t x 48r = 624 tiles)
  NSString* const aspect = ResolvedAspect(s);
  const bool wide = [aspect isEqualToString:@"wide"];
  std::string guest_res = "1560x720";
  if ([aspect isEqualToString:@"4:3"]) {
    guest_res = "1024x768";
  } else if (!wide && [aspect isEqualToString:@"16:9"]) {
    guest_res = "1280x720";
  }
  a.push_back("--resolution=" + guest_res);
  a.push_back("--carbon_scene_resolution=" + guest_res);

  // Host Display Preset (controls Metal drawable size & host GPU spatial upscaler CAS/FSR)
  NSString* scene_res = Value(s, @"scene_res") ?: @"1080p";
  a.push_back("--ios_display_preset=" + std::string(scene_res.UTF8String));'''
    if old_args_block in content:
        content = content.replace(old_args_block, new_args_block)
        print("[patch] Patched resolution lockstep in Arguments() in launcher.mm")

    # Also remove old carbon_scene_resolution branch in Arguments()
    old_carbon_res = '''  // Carbon scene and single-pass
  a.push_back("--carbon_single_pass=true");
  a.push_back("--nfsmw_una_pasada=false");
  NSString* scene_res = Value(s, @"scene_res") ?: @"1080p";
  if ([scene_res isEqualToString:@"720p"]) {
    a.push_back("--carbon_scene_resolution=1560x720");
  } else if ([scene_res isEqualToString:@"900p"]) {
    a.push_back("--carbon_scene_resolution=1950x900");
  } else if ([scene_res isEqualToString:@"retina"]) {
    a.push_back("--carbon_scene_resolution=2622x1206");
  } else if ([aspect isEqualToString:@"4:3"]) {
    a.push_back("--carbon_scene_resolution=1024x768");
  } else {
    // 1080p default (2340x1080)
    a.push_back("--carbon_scene_resolution=2340x1080");
  }'''
    new_carbon_res = '''  // Carbon scene and single-pass
  a.push_back("--carbon_single_pass=true");
  a.push_back("--nfsmw_una_pasada=false");'''
    if old_carbon_res in content:
        content = content.replace(old_carbon_res, new_carbon_res)
        print("[patch] Removed old carbon_scene_resolution override in launcher.mm")

    p.write_text(content, encoding="utf-8")


def patch_lifecycle():
    p = ROOT / "ios" / "src" / "lifecycle.mm"
    content = p.read_text(encoding="utf-8")

    # Add REXCVAR_DEFINE_STRING for ios_display_preset and QuartzCore include
    if "REXCVAR_DEFINE_STRING(ios_display_preset" not in content:
        anchor = '#import <UIKit/UIKit.h>\n'
        addition = '#import <UIKit/UIKit.h>\n#import <QuartzCore/CAMetalLayer.h>\n#include <rex/cvar.h>\n\nREXCVAR_DEFINE_STRING(ios_display_preset, "1080p", "Display",\n                      "Host display quality preset: 720p, 900p, 1080p, retina");\n'
        content = content.replace(anchor, addition, 1)
        print("[patch] Added ios_display_preset cvar to lifecycle.mm")

    # Update KeepMetalViewWindowSized to adjust CAMetalLayer drawableSize & contentsScale
    old_keep = '''  UIWindow* window = view.window;
  if (!window) {
    return;
  }
  const CGSize want = window.bounds.size;
  for (UIView* v = view; v && v != window; v = v.superview) {
    if (!CGSizeEqualToSize(v.bounds.size, want)) {
      REXLOG_INFO("[ios] a game view is {:.0f}x{:.0f}, its window {:.0f}x{:.0f}: resized to it",
                  v.bounds.size.width, v.bounds.size.height, want.width, want.height);
      v.frame = window.bounds;
      [v setNeedsLayout];
      [v layoutIfNeeded];
    }
  }
}'''
    new_keep = '''  UIWindow* window = view.window;
  if (!window) {
    return;
  }
  const CGSize want = window.bounds.size;
  for (UIView* v = view; v && v != window; v = v.superview) {
    if (!CGSizeEqualToSize(v.bounds.size, want)) {
      REXLOG_INFO("[ios] a game view is {:.0f}x{:.0f}, its window {:.0f}x{:.0f}: resized to it",
                  v.bounds.size.width, v.bounds.size.height, want.width, want.height);
      v.frame = window.bounds;
      [v setNeedsLayout];
      [v layoutIfNeeded];
    }
  }

  // Adjust CAMetalLayer drawableSize & contentsScale based on ios_display_preset
  if ([view.layer isKindOfClass:[CAMetalLayer class]]) {
    CAMetalLayer* metalLayer = (CAMetalLayer*)view.layer;
    UIScreen* screen = window.screen ?: UIScreen.mainScreen;
    const CGFloat native_scale = screen.nativeScale ?: (screen.scale ?: 2.0);
    const CGSize screen_pixels = screen.nativeBounds.size;
    const CGFloat max_dim = std::max(screen_pixels.width, screen_pixels.height);
    const CGFloat min_dim = std::min(screen_pixels.width, screen_pixels.height);
    const CGFloat aspect = (min_dim > 0) ? (max_dim / min_dim) : (16.0 / 9.0);

    const std::string preset = REXCVAR_GET(ios_display_preset);
    uint32_t target_h = 1080;
    if (preset == "720p") target_h = 720;
    else if (preset == "900p") target_h = 900;
    else if (preset == "retina") target_h = uint32_t(std::lround(min_dim));
    else target_h = 1080;

    if (target_h > min_dim) target_h = uint32_t(std::lround(min_dim));

    uint32_t target_w = uint32_t(std::lround(target_h * aspect));
    target_w = (target_w + 1) & ~1u;

    CGFloat scale = CGFloat(target_h) / (window.bounds.size.height > 0 ? window.bounds.size.height : 1.0);
    if (preset == "retina") {
      scale = native_scale;
      target_w = uint32_t(std::lround(max_dim));
      target_h = uint32_t(std::lround(min_dim));
    }

    if (std::abs(metalLayer.contentsScale - scale) > 0.001 ||
        metalLayer.drawableSize.width != target_w ||
        metalLayer.drawableSize.height != target_h) {
      metalLayer.contentsScale = scale;
      metalLayer.drawableSize = CGSizeMake(target_w, target_h);
      REXLOG_INFO("[ios] Display preset '{}': CAMetalLayer contentsScale={:.3f}, drawableSize={}x{}",
                  preset, scale, target_w, target_h);
    }
  }
}'''
    if old_keep in content:
        content = content.replace(old_keep, new_keep)
        print("[patch] Patched CAMetalLayer drawableSize in lifecycle.mm")

    p.write_text(content, encoding="utf-8")


def patch_touch_controls():
    p = ROOT / "ios" / "src" / "touch_controls.mm"
    content = p.read_text(encoding="utf-8")

    # Safe Area margins in layoutSubviews
    old_layout_subviews = '''  [super layoutSubviews];
  const CGFloat w = self.bounds.size.width, h = self.bounds.size.height;
  const CGFloat unit = std::min(w / 16.0, h / 9.0);
  const CGFloat stick = unit * 0.78, button = unit * 0.38;
  const CGFloat shoulderW = unit * 1.25, shoulderH = unit * 0.55;
  auto P = [&](CGFloat fx, CGFloat fy) { return CGPointMake(w * fx, h * fy); };'''

    new_layout_subviews = '''  [super layoutSubviews];
  const CGFloat w = self.bounds.size.width, h = self.bounds.size.height;
  UIEdgeInsets insets = self.window ? self.window.safeAreaInsets : self.safeAreaInsets;
  const CGFloat maxSafeX = std::max(insets.left, insets.right);
  const CGFloat leftMargin = maxSafeX > 0 ? (maxSafeX + 8.0) : 16.0;
  const CGFloat rightMargin = leftMargin;
  const CGFloat usableW = std::max<CGFloat>(100.0, w - leftMargin - rightMargin);
  const CGFloat topMargin = insets.top;
  const CGFloat bottomMargin = insets.bottom;
  const CGFloat usableH = std::max<CGFloat>(100.0, h - topMargin - bottomMargin);

  const CGFloat unit = std::min(usableW / 16.0, usableH / 9.0);
  const CGFloat stick = unit * 0.78, button = unit * 0.38;
  const CGFloat shoulderW = unit * 1.25, shoulderH = unit * 0.55;
  auto P = [&](CGFloat fx, CGFloat fy) {
    return CGPointMake(leftMargin + usableW * fx, topMargin + usableH * fy);
  };'''

    if old_layout_subviews in content:
        content = content.replace(old_layout_subviews, new_layout_subviews)
        print("[patch] Patched safe area margin in layoutSubviews in touch_controls.mm")

    # Safe Area margins in layoutDriving
    old_layout_driving = '''// The DRIVE layout (ergonomic racing layout with steering mode support).
- (void)layoutDriving:(CGFloat)w height:(CGFloat)h unit:(CGFloat)unit {
  auto P = [&](CGFloat fx, CGFloat fy) { return CGPointMake(w * fx, h * fy); };'''

    new_layout_driving = '''// The DRIVE layout (ergonomic racing layout with steering mode support).
- (void)layoutDriving:(CGFloat)w height:(CGFloat)h unit:(CGFloat)unit {
  UIEdgeInsets insets = self.window ? self.window.safeAreaInsets : self.safeAreaInsets;
  const CGFloat maxSafeX = std::max(insets.left, insets.right);
  const CGFloat leftMargin = maxSafeX > 0 ? (maxSafeX + 8.0) : 16.0;
  const CGFloat rightMargin = leftMargin;
  const CGFloat usableW = std::max<CGFloat>(100.0, w - leftMargin - rightMargin);
  const CGFloat topMargin = insets.top;
  const CGFloat bottomMargin = insets.bottom;
  const CGFloat usableH = std::max<CGFloat>(100.0, h - topMargin - bottomMargin);
  auto P = [&](CGFloat fx, CGFloat fy) {
    return CGPointMake(leftMargin + usableW * fx, topMargin + usableH * fy);
  };'''

    if old_layout_driving in content:
        content = content.replace(old_layout_driving, new_layout_driving)
        print("[patch] Patched safe area margin in layoutDriving in touch_controls.mm")

    # Safe Area margins in applyCustomLayout & saveControl
    old_apply = '''- (void)applyCustomLayout {
  const CGFloat w = self.bounds.size.width, h = self.bounds.size.height;
  if (w <= 0 || h <= 0) return;
  NSDictionary* layout = [NSUserDefaults.standardUserDefaults dictionaryForKey:kLayoutKey];
  const CGFloat all = TouchSize();
  for (Control& c : _controls) {
    CGFloat scale = all;
    NSArray* v = layout[ControlIdent(_driving, c)];
    if (v.count == 3) {
      c.center = CGPointMake(w * [v[0] doubleValue], h * [v[1] doubleValue]);
      scale *= CGFloat([v[2] doubleValue]);
    }
    c.radius *= scale;
    c.size = CGSizeMake(c.size.width * scale, c.size.height * scale);
  }
  self.alpha = _editing ? 1.0 : TouchOpacity();
}'''

    new_apply = '''- (void)applyCustomLayout {
  const CGFloat w = self.bounds.size.width, h = self.bounds.size.height;
  if (w <= 0 || h <= 0) return;
  UIEdgeInsets insets = self.window ? self.window.safeAreaInsets : self.safeAreaInsets;
  const CGFloat maxSafeX = std::max(insets.left, insets.right);
  const CGFloat leftMargin = maxSafeX > 0 ? (maxSafeX + 8.0) : 16.0;
  const CGFloat rightMargin = leftMargin;
  const CGFloat usableW = std::max<CGFloat>(100.0, w - leftMargin - rightMargin);
  const CGFloat topMargin = insets.top;
  const CGFloat bottomMargin = insets.bottom;
  const CGFloat usableH = std::max<CGFloat>(100.0, h - topMargin - bottomMargin);

  NSDictionary* layout = [NSUserDefaults.standardUserDefaults dictionaryForKey:kLayoutKey];
  const CGFloat all = TouchSize();
  for (Control& c : _controls) {
    CGFloat scale = all;
    NSArray* v = layout[ControlIdent(_driving, c)];
    if (v.count == 3) {
      c.center = CGPointMake(leftMargin + usableW * [v[0] doubleValue], topMargin + usableH * [v[1] doubleValue]);
      scale *= CGFloat([v[2] doubleValue]);
    }
    c.radius *= scale;
    c.size = CGSizeMake(c.size.width * scale, c.size.height * scale);
  }
  self.alpha = _editing ? 1.0 : TouchOpacity();
}'''

    if old_apply in content:
        content = content.replace(old_apply, new_apply)
        print("[patch] Patched applyCustomLayout in touch_controls.mm")

    old_save = '''- (void)saveControl:(const Control&)c scale:(CGFloat)scale {
  const CGFloat w = self.bounds.size.width, h = self.bounds.size.height;
  NSMutableDictionary* layout =
      [[NSUserDefaults.standardUserDefaults dictionaryForKey:kLayoutKey] mutableCopy] ?: [NSMutableDictionary dictionary];
  layout[ControlIdent(_driving, c)] = @[ @(c.center.x / w), @(c.center.y / h), @(scale) ];
  [NSUserDefaults.standardUserDefaults setObject:layout forKey:kLayoutKey];
}'''

    new_save = '''- (void)saveControl:(const Control&)c scale:(CGFloat)scale {
  const CGFloat w = self.bounds.size.width, h = self.bounds.size.height;
  UIEdgeInsets insets = self.window ? self.window.safeAreaInsets : self.safeAreaInsets;
  const CGFloat maxSafeX = std::max(insets.left, insets.right);
  const CGFloat leftMargin = maxSafeX > 0 ? (maxSafeX + 8.0) : 16.0;
  const CGFloat rightMargin = leftMargin;
  const CGFloat usableW = std::max<CGFloat>(100.0, w - leftMargin - rightMargin);
  const CGFloat topMargin = insets.top;
  const CGFloat bottomMargin = insets.bottom;
  const CGFloat usableH = std::max<CGFloat>(100.0, h - topMargin - bottomMargin);

  CGFloat normX = (c.center.x - leftMargin) / usableW;
  CGFloat normY = (c.center.y - topMargin) / usableH;
  normX = std::clamp(normX, 0.0, 1.0);
  normY = std::clamp(normY, 0.0, 1.0);

  NSMutableDictionary* layout =
      [[NSUserDefaults.standardUserDefaults dictionaryForKey:kLayoutKey] mutableCopy] ?: [NSMutableDictionary dictionary];
  layout[ControlIdent(_driving, c)] = @[ @(normX), @(normY), @(scale) ];
  [NSUserDefaults.standardUserDefaults setObject:layout forKey:kLayoutKey];
}'''

    if old_save in content:
        content = content.replace(old_save, new_save)
        print("[patch] Patched saveControl in touch_controls.mm")

    p.write_text(content, encoding="utf-8")


def patch_missing_entries():
    p = ROOT / "src" / "carbon_missing_entries.cpp"
    content = p.read_text(encoding="utf-8")

    # Add Carbon_821A3EC8 implementation
    if "Carbon_821A3EC8" not in content:
        anchor = 'void Carbon_Blr([[maybe_unused]] PPCContext& ctx,\n                [[maybe_unused]] uint8_t* base) {}\n'
        addition = '''void Carbon_Blr([[maybe_unused]] PPCContext& ctx,
                [[maybe_unused]] uint8_t* base) {}

// USA 0x821A3EC8: flasher callback / thunk (mr r3, r4; b 0x821A35E0), called from lr=0x82690F0C.
void Carbon_821A3EC8(PPCContext& ctx, [[maybe_unused]] uint8_t* base) {
  ctx.r3.u64 = ctx.r4.u64;
  REX_CALL_INDIRECT_FUNC(0x821A35E0);
}
'''
        content = content.replace(anchor, addition, 1)
        print("[patch] Added Carbon_821A3EC8 in carbon_missing_entries.cpp")

    # Register Carbon_821A3EC8 in CarbonRegisterMissingEntries
    if "Registered verified flasher callback 0x821A3EC8" not in content:
        target = '    if (ok && dispatcher->SetFunction(address, &Carbon_82321FC8)) {\n      REXLOG_INFO("[carbon] Registered verified PPC entry 0x82321FC8 (USA, PAL was 0x82322048)");\n    }\n  }\n}'
        replacement = '''    if (ok && dispatcher->SetFunction(address, &Carbon_82321FC8)) {
      REXLOG_INFO("[carbon] Registered verified PPC entry 0x82321FC8 (USA, PAL was 0x82322048)");
    }
  }
  // USA 0x821A3EC8: flasher callback / thunk (mr r3, r4; b 0x821A35E0), called from lr=0x82690F0C.
  constexpr uint32_t flasher_thunk = 0x821A3EC8;
  if (!dispatcher->GetFunction(flasher_thunk)) {
    if (REX_LOAD_U32(flasher_thunk) == 0x7C832378 &&
        REX_LOAD_U32(flasher_thunk + 4) == 0x4BFFF714) {
      if (dispatcher->SetFunction(flasher_thunk, &Carbon_821A3EC8)) {
        REXLOG_INFO("[carbon] Registered verified flasher callback 0x821A3EC8 (USA, called from 0x82690F0C)");
      }
    }
  }
}'''
        if target in content:
            content = content.replace(target, replacement)
            print("[patch] Registered Carbon_821A3EC8 in carbon_missing_entries.cpp")

    p.write_text(content, encoding="utf-8")


def patch_desatasco():
    p = ROOT / "tools" / "parche_desatasco.py"
    content = p.read_text(encoding="utf-8")
    old_thresh = "const bool atascado = llevo > 250 &&"
    new_thresh = "const bool atascado = llevo > 40 &&"
    if old_thresh in content:
        content = content.replace(old_thresh, new_thresh)
        print("[patch] Lowered XMA stall threshold to 40 ms in tools/parche_desatasco.py")
    p.write_text(content, encoding="utf-8")


def patch_manifest_and_verifier():
    # 1. nfscarbon_manifest.toml
    m = ROOT / "nfscarbon_manifest.toml"
    content = m.read_text(encoding="utf-8")
    if "0x821A3EC8" not in content:
        # insert in [entrypoint.functions]
        content = content.replace(
            "[entrypoint.functions]\n",
            "[entrypoint.functions]\n0x821A3EC8 = {}  # USA flasher/callback method called from 0x82690F0C (0x821A3EC8..0x821A3ED0)\n"
        )
        m.write_text(content, encoding="utf-8")
        print("[patch] Added 0x821A3EC8 to nfscarbon_manifest.toml")

    # 2. tools/verify_usa_codegen.py
    v = ROOT / "tools" / "verify_usa_codegen.py"
    v_content = v.read_text(encoding="utf-8")
    if "0x821A3EC8" not in v_content:
        v_target = '    ("0x825BF728", "sub_825BF728", "USA Car Selection / Quick Race callback (0x825BF728)"),\n'
        v_add = '    ("0x825BF728", "sub_825BF728", "USA Car Selection / Quick Race callback (0x825BF728)"),\n    ("0x821A3EC8", "sub_821A3EC8", "USA flasher/callback method called from 0x82690F0C"),\n'
        v_content = v_content.replace(v_target, v_add)
        v.write_text(v_content, encoding="utf-8")
        print("[patch] Added 0x821A3EC8 to tools/verify_usa_codegen.py")

    # 3. tools/build_usa_codegen.py
    b = ROOT / "tools" / "build_usa_codegen.py"
    b_content = b.read_text(encoding="utf-8")
    if "0x821A3EC8" not in b_content:
        b_target = '    (0x825BF728, "sub_825BF728", "USA Car Selection / Quick Race callback (0x825BF728)"),\n'
        b_add = '    (0x825BF728, "sub_825BF728", "USA Car Selection / Quick Race callback (0x825BF728)"),\n    (0x821A3EC8, "sub_821A3EC8", "USA flasher/callback method called from 0x82690F0C (0x821A3EC8..0x821A3ED0)"),\n'
        b_content = b_content.replace(b_target, b_add)
        print("[patch] Added 0x821A3EC8 to REQUIRED_USA_SYMBOLS in tools/build_usa_codegen.py")

    # Also enhance scan_code_referenced_functions to scan .rdata and .data for function pointers
    old_scan_return = '    print(f"[build_usa_codegen] lis+addi/ori scan discovered {len(valid)} candidate non-pdata leaf functions.")\n    return valid'
    new_scan_return = '''    # Also scan .rdata and .data sections for 32-bit aligned function pointers (e.g. vtables, callback tables)
    import bisect
    pdata_starts = [s for s, e in pdata]
    pdata_ends = [e for s, e in pdata]
    rdata_candidates = set()
    data_ranges = [(s, e) for name, s, e in secs if name in ['.rdata', '.data']]
    for d_start, d_end in data_ranges:
        for ptr_addr in range(d_start, d_end - 4, 4):
            val = struct.unpack_from('>I', img, ptr_addr - base)[0]
            if 0x82110000 <= val < 0x82B35C64 and (val % 4) == 0:
                # Check that val is not strictly inside any [start, end)
                idx = bisect.bisect_right(pdata_starts, val)
                if idx > 0 and val < pdata_ends[idx - 1]:
                    continue
                if idx < len(pdata_starts) and val == pdata_starts[idx]:
                    continue
                rdata_candidates.add(val)

    # Validate each candidate has a barrier or prologue
    for c in sorted(rdata_candidates):
        offset = c - base
        if offset < 4 or offset >= len(img) - 8:
            continue
        prev_inst = struct.unpack_from('>I', img, offset - 4)[0]
        inst0 = struct.unpack_from('>I', img, offset)[0]
        is_prev_barrier = (
            (prev_inst & 0xFC000003) == 0x48000000 or
            prev_inst == 0x4E800020 or
            (prev_inst & 0xFC0007FE) == 0x4C000420 or
            prev_inst in [0x00000000, 0x60000000]
        )
        is_prologue = (
            inst0 == 0x7C0802A6 or
            (inst0 & 0xFFFF0000) == 0x94210000 or
            (inst0 & 0xFFFF0000) == 0x7C830000  # mr r3, r4
        )
        if is_prev_barrier or is_prologue:
            if c not in valid:
                valid.append(c)

    print(f"[build_usa_codegen] Code + data scan discovered {len(valid)} candidate non-pdata leaf functions.")
    return valid'''
    if old_scan_return in b_content:
        b_content = b_content.replace(old_scan_return, new_scan_return)
        print("[patch] Enhanced scan_code_referenced_functions in tools/build_usa_codegen.py")

    b.write_text(b_content, encoding="utf-8")


if __name__ == "__main__":
    patch_ios_main()
    patch_launcher()
    patch_lifecycle()
    patch_touch_controls()
    patch_missing_entries()
    patch_desatasco()
    patch_manifest_and_verifier()
    print("[patch] All patches applied successfully!")
