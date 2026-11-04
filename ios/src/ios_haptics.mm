#import <UIKit/UIKit.h>
#import "ios_haptics.h"
#include <rex/cvar.h>
#include <algorithm>
#include <atomic>
#include <chrono>

REXCVAR_DEFINE_BOOL(ios_haptics, true, "Input",
                    "iOS: Haptic feedback for touch controls and controller vibration");

namespace {
std::atomic<bool> g_ios_haptics_enabled{true};
UIImpactFeedbackGenerator* g_haptic_light = nil;
UIImpactFeedbackGenerator* g_haptic_medium = nil;
UIImpactFeedbackGenerator* g_haptic_heavy = nil;
std::atomic<uint64_t> g_last_rumble_ms{0};

uint64_t GetCurrentTimeMs() {
  using namespace std::chrono;
  return duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count();
}
}  // namespace

extern "C" {

void IOSHaptics_Init(bool enabled) {
  g_ios_haptics_enabled.store(enabled, std::memory_order_relaxed);
  if (!enabled) return;

  dispatch_async(dispatch_get_main_queue(), ^{
    if (!g_haptic_light) {
      g_haptic_light = [[UIImpactFeedbackGenerator alloc] initWithStyle:UIImpactFeedbackStyleLight];
      g_haptic_medium = [[UIImpactFeedbackGenerator alloc] initWithStyle:UIImpactFeedbackStyleMedium];
      g_haptic_heavy = [[UIImpactFeedbackGenerator alloc] initWithStyle:UIImpactFeedbackStyleHeavy];
    }
    [g_haptic_light prepare];
    [g_haptic_medium prepare];
  });
}

void IOSHaptics_SetEnabled(bool enabled) {
  g_ios_haptics_enabled.store(enabled, std::memory_order_relaxed);
}

bool IOSHaptics_IsEnabled() {
  return g_ios_haptics_enabled.load(std::memory_order_relaxed) && REXCVAR_GET(ios_haptics);
}

void IOSHaptics_TriggerTouch(float intensity) {
  if (!IOSHaptics_IsEnabled()) return;
  float clamped = std::clamp(intensity, 0.0f, 1.0f);
  dispatch_async(dispatch_get_main_queue(), ^{
    if (!g_haptic_light) {
      g_haptic_light = [[UIImpactFeedbackGenerator alloc] initWithStyle:UIImpactFeedbackStyleLight];
    }
    [g_haptic_light impactOccurredWithIntensity:clamped];
    [g_haptic_light prepare];
  });
}

void IOSHaptics_TriggerTap(float intensity) {
  IOSHaptics_TriggerTouch(intensity);
}

void IOSHaptics_TriggerRumble(uint16_t left_motor, uint16_t right_motor, uint64_t now_ms) {
  if (!IOSHaptics_IsEnabled()) return;
  if (left_motor == 0 && right_motor == 0) return;

  uint64_t prev_ms = g_last_rumble_ms.load(std::memory_order_relaxed);
  if (now_ms - prev_ms < 45) return;  // Throttle to ~22 Hz
  g_last_rumble_ms.store(now_ms, std::memory_order_relaxed);

  float strength = std::max(left_motor, right_motor) / 65535.0f;
  if (strength < 0.1f) return;

  dispatch_async(dispatch_get_main_queue(), ^{
    if (strength > 0.7f) {
      if (!g_haptic_heavy) {
        g_haptic_heavy = [[UIImpactFeedbackGenerator alloc] initWithStyle:UIImpactFeedbackStyleHeavy];
      }
      [g_haptic_heavy impactOccurredWithIntensity:strength];
      [g_haptic_heavy prepare];
    } else {
      if (!g_haptic_medium) {
        g_haptic_medium = [[UIImpactFeedbackGenerator alloc] initWithStyle:UIImpactFeedbackStyleMedium];
      }
      [g_haptic_medium impactOccurredWithIntensity:strength];
      [g_haptic_medium prepare];
    }
  });
}

void IOSHaptics_OnGuestRumble(uint16_t left_motor, uint16_t right_motor) {
  IOSHaptics_TriggerRumble(left_motor, right_motor, GetCurrentTimeMs());
}

}  // extern "C"
