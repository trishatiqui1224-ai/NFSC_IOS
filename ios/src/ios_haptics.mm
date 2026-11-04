#import <UIKit/UIKit.h>
#import "ios_haptics.h"
#include <rex/cvar.h>
#include <algorithm>
#include <chrono>

REXCVAR_DEFINE_BOOL(ios_haptics, true, "Input",
                    "iOS: Haptic feedback for touch controls and controller vibration");

@interface IOSHapticsHelper : NSObject
@property(nonatomic, strong) UIImpactFeedbackGenerator* lightGen;
@property(nonatomic, strong) UIImpactFeedbackGenerator* mediumGen;
@property(nonatomic, strong) UIImpactFeedbackGenerator* heavyGen;
@end

@implementation IOSHapticsHelper
- (instancetype)init {
  self = [super init];
  if (self) {
    _lightGen = [[UIImpactFeedbackGenerator alloc] initWithStyle:UIImpactFeedbackStyleLight];
    _mediumGen = [[UIImpactFeedbackGenerator alloc] initWithStyle:UIImpactFeedbackStyleMedium];
    _heavyGen = [[UIImpactFeedbackGenerator alloc] initWithStyle:UIImpactFeedbackStyleHeavy];
    [_lightGen prepare];
    [_mediumGen prepare];
  }
  return self;
}
@end

static IOSHapticsHelper* g_helper = nil;
static uint64_t g_last_rumble_ms = 0;

static uint64_t GetCurrentTimeMs() {
  using namespace std::chrono;
  return duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count();
}

extern "C" {

void IOSHaptics_Init(bool enabled) {
  if (!enabled) return;
  dispatch_async(dispatch_get_main_queue(), ^{
    if (!g_helper) {
      g_helper = [[IOSHapticsHelper alloc] init];
    }
  });
}

void IOSHaptics_TriggerTap(float intensity) {
  if (!REXCVAR_GET(ios_haptics)) return;
  dispatch_async(dispatch_get_main_queue(), ^{
    if (!g_helper) {
      g_helper = [[IOSHapticsHelper alloc] init];
    }
    [g_helper.lightGen impactOccurredWithIntensity:intensity];
    [g_helper.lightGen prepare];
  });
}

void IOSHaptics_OnGuestRumble(uint16_t left_motor, uint16_t right_motor) {
  if (!REXCVAR_GET(ios_haptics) || (left_motor == 0 && right_motor == 0)) return;
  const uint64_t now_ms = GetCurrentTimeMs();
  if (now_ms - g_last_rumble_ms < 45) return; // Throttle to ~22 Hz max
  g_last_rumble_ms = now_ms;

  const float strength = float(std::max(left_motor, right_motor)) / 65535.0f;
  if (strength < 0.1f) return;

  dispatch_async(dispatch_get_main_queue(), ^{
    if (!g_helper) {
      g_helper = [[IOSHapticsHelper alloc] init];
    }
    if (strength > 0.7f) {
      [g_helper.heavyGen impactOccurredWithIntensity:strength];
    } else {
      [g_helper.mediumGen impactOccurredWithIntensity:strength];
    }
  });
}

}  // extern "C"
