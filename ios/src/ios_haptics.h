#pragma once

#include <cstdint>

#ifdef __cplusplus
extern "C" {
#endif

void IOSHaptics_Init(bool enabled);
void IOSHaptics_TriggerTap(float intensity);
void IOSHaptics_OnGuestRumble(uint16_t left_motor, uint16_t right_motor);

#ifdef __cplusplus
}
#endif
