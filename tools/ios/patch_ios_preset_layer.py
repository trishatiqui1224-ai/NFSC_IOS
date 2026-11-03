#!/usr/bin/env python3
"""
Applies host display preset (720p, 900p, 1080p, retina) to CAMetalLayer
before swapchain creation, and updates WindowSDL actual dimensions to match.

    python3 tools/ios/patch_ios_preset_layer.py            apply
    python3 tools/ios/patch_ios_preset_layer.py --status
    python3 tools/ios/patch_ios_preset_layer.py --revert

Touches src/ui/window_sdl.cpp.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from patch_engine import run  # noqa: E402

W = "src/ui/window_sdl.cpp"

LAYER_ANCHOR = '''#elif REX_PLATFORM_MAC
  if (allowed_types & Surface::kTypeFlag_CAMetalLayer) {
    SDL_MetalView metal_view = SDL_Metal_CreateView(sdl_window_);
    if (metal_view) {
      void* layer = SDL_Metal_GetLayer(metal_view);
      if (layer) {
        return std::make_unique<CAMetalLayerSurface>(sdl_window_, metal_view, layer);
      }
      SDL_Metal_DestroyView(metal_view);
    }
  }
'''

LAYER_NEW = '''#elif REX_PLATFORM_MAC
  if (allowed_types & Surface::kTypeFlag_CAMetalLayer) {
    SDL_MetalView metal_view = SDL_Metal_CreateView(sdl_window_);
    if (metal_view) {
      void* layer = SDL_Metal_GetLayer(metal_view);
      if (layer) {
#if REX_PLATFORM_IOS
        // LOCAL PATCH - iOS: configure preset on CAMetalLayer before swapchain creation
        // and update actual window dimensions so VulkanPresenter matches drawable size.
        extern void ApplyMetalLayerPreset(void* layer);
        extern uint32_t GetMetalLayerDrawableWidth();
        extern uint32_t GetMetalLayerDrawableHeight();
        ApplyMetalLayerPreset(layer);
        if (uint32_t dw = GetMetalLayerDrawableWidth()) {
          uint32_t dh = GetMetalLayerDrawableHeight();
          WindowDestructionReceiver destruction_receiver(this);
          OnActualSizeUpdate(dw, dh, destruction_receiver);
        }
#endif
        return std::make_unique<CAMetalLayerSurface>(sdl_window_, metal_view, layer);
      }
      SDL_Metal_DestroyView(metal_view);
    }
  }
'''

SIZE_ANCHOR = '''  int pixel_width = 0;
  int pixel_height = 0;
  SDL_GetWindowSizeInPixels(sdl_window_, &pixel_width, &pixel_height);
  WindowDestructionReceiver destruction_receiver(this);
  OnActualSizeUpdate(uint32_t(pixel_width), uint32_t(pixel_height), destruction_receiver);
'''

SIZE_NEW = '''  int pixel_width = 0;
  int pixel_height = 0;
  SDL_GetWindowSizeInPixels(sdl_window_, &pixel_width, &pixel_height);
#if REX_PLATFORM_IOS
  extern uint32_t GetMetalLayerDrawableWidth();
  extern uint32_t GetMetalLayerDrawableHeight();
  if (uint32_t dw = GetMetalLayerDrawableWidth()) pixel_width = int(dw);
  if (uint32_t dh = GetMetalLayerDrawableHeight()) pixel_height = int(dh);
#endif
  WindowDestructionReceiver destruction_receiver(this);
  OnActualSizeUpdate(uint32_t(pixel_width), uint32_t(pixel_height), destruction_receiver);
'''

BLOCKS = [
    (W, "apply preset to CAMetalLayer on creation", LAYER_ANCHOR, LAYER_NEW),
    (W, "update initial actual size for iOS preset", SIZE_ANCHOR, SIZE_NEW),
]

if __name__ == "__main__":
    sys.exit(run("ios_preset_layer", BLOCKS))
