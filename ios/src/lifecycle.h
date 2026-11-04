// NFSMW Recompiled - pausing the GPU emulation while the app is in the background

#pragma once

#include <functional>

namespace nfsmw::lifecycle {

// Watches UIKit for the app going to the background and coming back, and
// calls pause / resume (main thread). Once, from OnPostSetup.
void Install(std::function<void()> pause, std::function<void()> resume);

// From the display link's tick (only runs while the app is on screen): if the
// emulation is still paused, a missed "back to the foreground" is made up for.
void OnDisplayTick();

// Synchronizes the CAMetalLayer drawableSize & contentsScale with the active
// display preset (720p, 900p, 1080p, retina).
void KeepMetalViewWindowSized();

// Connects function pointer hooks in WindowSDL to ApplyMetalLayerPreset.
void RegisterMetalPresetCallbacks();

}  // namespace nfsmw::lifecycle

extern "C" {
uint32_t GetMetalLayerDrawableWidth();
uint32_t GetMetalLayerDrawableHeight();
void ApplyMetalLayerPreset(void* raw_layer);
}
