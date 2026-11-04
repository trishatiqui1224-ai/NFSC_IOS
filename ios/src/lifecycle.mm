// NFSMW Recompiled - pausing the GPU emulation while the app is in the background
//
// iOS does not let a background app submit GPU work (patch_ios_pause.py), so
// the GPU emulation is paused there. It used to follow SDL's app events:
// paused on SDL_EVENT_WILL_ENTER_BACKGROUND, resumed on
// SDL_EVENT_DID_ENTER_FOREGROUND. Two problems, seen in the log:
//   - SDL sends "will enter background" on every resign-active: a
//     screenshot, Control Center, a notification, the app switcher. The app is
//     still on screen and may still draw.
//   - under LiveContainer the "did enter foreground" never came: the GPU
//     emulation stayed paused, sound and input went on, the screen stayed
//     black until the game was restarted.
// Now:
//   - paused on "will resign active" (app and scene), and "did enter
//     background" in case that was missed. Not later: pausing only at "did
//     enter background" left GPU work (the command processor's last
//     submissions, the UI thread's repaints) to reach Metal in the
//     background, and iOS answered with "Insufficient Permission": device
//     lost, the game gone. The pause also stops the UI thread's paints
//     (game_app.cpp, patch_ios_paint_suspend.py). A screenshot or Control
//     Center pauses too, for as long as they are up;
//   - resumed on any of "will enter foreground" / "did become active" (app
//     and scene), and, if all of those were missed, on the next tick of the
//     display link (display_rate.mm) once the app is active again.
// Both are idempotent.
//
// The display tick also keeps SDL's Metal view the size of its window. After
// a screenshot, the view (and so the CAMetalLayer) stayed PORTRAIT while the
// window was landscape again: MoltenVK took the portrait bounds, the swapchain
// was rebuilt portrait (patch_ios_suboptimal.py could only rebuild it at the
// same wrong size) and the game was drawn into a corner of the screen. If the
// view or a view holding it is not the size of the window, it is given the
// window's bounds; SDL's layoutSubviews then sets the drawable size and the
// swapchain is rebuilt from it.

#import <UIKit/UIKit.h>
#import <QuartzCore/CAMetalLayer.h>
#include <rex/cvar.h>

REXCVAR_DEFINE_STRING(ios_display_preset, "retina", "Display",
                      "Host display quality preset: 720p, 900p, 1080p, retina");

#include <rex/logging.h>

#include "lifecycle.h"

#include <mach/mach.h>
#include <mach/thread_act.h>
#include <mach/thread_info.h>
#include <pthread.h>
#include <chrono>
#include <thread>
#include <atomic>
#include <spdlog/spdlog.h>

static std::atomic<uint32_t> g_preset_drawable_w{0};
static std::atomic<uint32_t> g_preset_drawable_h{0};

extern "C" {
typedef void (*MetalLayerPresetFn)(void* layer);
typedef uint32_t (*MetalLayerDimFn)();

extern __attribute__((weak)) MetalLayerPresetFn g_apply_metal_preset;
extern __attribute__((weak)) MetalLayerDimFn g_get_drawable_w;
extern __attribute__((weak)) MetalLayerDimFn g_get_drawable_h;

uint32_t GetMetalLayerDrawableWidth() {
  return g_preset_drawable_w.load(std::memory_order_relaxed);
}

uint32_t GetMetalLayerDrawableHeight() {
  return g_preset_drawable_h.load(std::memory_order_relaxed);
}

void ApplyMetalLayerPreset(void* raw_layer) {
  if (!raw_layer) return;
  id obj = (__bridge id)raw_layer;
  if (![obj isKindOfClass:[CAMetalLayer class]]) return;
  CAMetalLayer* metalLayer = (CAMetalLayer*)obj;

  UIScreen* screen = UIScreen.mainScreen;
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

  CGFloat scale = CGFloat(target_h) / (screen.bounds.size.height > 0 ? screen.bounds.size.height : 1.0);
  if (preset == "retina") {
    scale = native_scale;
    target_w = uint32_t(std::lround(max_dim));
    target_h = uint32_t(std::lround(min_dim));
  }

  g_preset_drawable_w.store(target_w, std::memory_order_relaxed);
  g_preset_drawable_h.store(target_h, std::memory_order_relaxed);

  metalLayer.contentsGravity = kCAGravityResize;
  if (UIView* v = [metalLayer.delegate isKindOfClass:[UIView class]] ? (UIView*)metalLayer.delegate : nil) {
    v.contentScaleFactor = scale;
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
}  // extern "C"

namespace nfsmw::lifecycle {

void RegisterMetalPresetCallbacks() {
  if (&g_apply_metal_preset && g_apply_metal_preset != &ApplyMetalLayerPreset) {
    g_apply_metal_preset = &ApplyMetalLayerPreset;
  }
  if (&g_get_drawable_w && g_get_drawable_w != &GetMetalLayerDrawableWidth) {
    g_get_drawable_w = &GetMetalLayerDrawableWidth;
  }
  if (&g_get_drawable_h && g_get_drawable_h != &GetMetalLayerDrawableHeight) {
    g_get_drawable_h = &GetMetalLayerDrawableHeight;
  }
}

namespace {

std::function<void()> g_pause, g_resume;

std::atomic<bool> g_paused{false};
std::atomic<bool> g_guest_booted{false};
std::atomic<std::chrono::steady_clock::time_point> g_last_present_time{std::chrono::steady_clock::now()};

void StartStallWatchdog() {
  static std::atomic<bool> started{false};
  if (started.exchange(true)) return;

  std::thread([]() {
    pthread_setname_np("GPUStallWatchdog");
    while (true) {
      std::this_thread::sleep_for(std::chrono::seconds(1));
      if (!g_guest_booted.load(std::memory_order_relaxed)) {
        continue;
      }
      if (g_paused.load(std::memory_order_relaxed)) {
        continue;
      }
      const auto now = std::chrono::steady_clock::now();
      const auto last = g_last_present_time.load(std::memory_order_acquire);
      if (std::chrono::duration_cast<std::chrono::seconds>(now - last).count() >= 5) {
        static auto last_warn = std::chrono::steady_clock::time_point{};
        if (now - last_warn < std::chrono::seconds(5)) continue;
        last_warn = now;

        REXLOG_ERROR("[stall-watchdog] STALL DETECTED: 0 frames presented for >= 5s! Dumping active threads:");

        thread_act_array_t threads = nullptr;
        mach_msg_type_number_t count = 0;
        if (task_threads(mach_task_self(), &threads, &count) == KERN_SUCCESS) {
          for (mach_msg_type_number_t i = 0; i < count; ++i) {
            pthread_t thread = pthread_from_mach_thread_np(threads[i]);
            char name[64] = {};
            thread_identifier_info_data_t id = {};
            thread_basic_info_data_t basic = {};
            mach_msg_type_number_t n = THREAD_IDENTIFIER_INFO_COUNT, b = THREAD_BASIC_INFO_COUNT;

            if (thread && pthread_getname_np(thread, name, sizeof(name)) == 0 &&
                thread_info(threads[i], THREAD_IDENTIFIER_INFO, thread_info_t(&id), &n) == KERN_SUCCESS &&
                thread_info(threads[i], THREAD_BASIC_INFO, thread_info_t(&basic), &b) == KERN_SUCCESS) {
              const uint64_t cpu_us = uint64_t(basic.user_time.seconds + basic.system_time.seconds) * 1000000 +
                                      basic.user_time.microseconds + basic.system_time.microseconds;
              REXLOG_ERROR("  [stall-thread] id=0x{:X} name='{}' run_state={} cpu_time={}us",
                           id.thread_id, name, basic.run_state, cpu_us);
            }
            mach_port_deallocate(mach_task_self(), threads[i]);
          }
          vm_deallocate(mach_task_self(), vm_address_t(threads), count * sizeof(thread_act_t));
        }
        rex::FlushLogging();
        if (auto logger = spdlog::default_logger()) {
          logger->flush();
        }
      }
    }
  }).detach();
}

void Pause(const char* why) {
  if (g_paused.load(std::memory_order_relaxed) || !g_pause) {
    return;
  }
  g_paused.store(true, std::memory_order_relaxed);
  REXLOG_INFO("[ios] to the background ({}): pausing the GPU emulation", why);
  g_pause();
}

void Resume(const char* why) {
  if (!g_paused.load(std::memory_order_relaxed) || !g_resume) {
    return;
  }
  g_paused.store(false, std::memory_order_relaxed);
  REXLOG_INFO("[ios] back on screen ({}): resuming the GPU emulation", why);
  g_resume();
}

UIView* FindMetalView(UIView* view, Class metal) {
  if ([view isKindOfClass:metal]) {
    return view;
  }
  for (UIView* sub in view.subviews) {
    if (UIView* found = FindMetalView(sub, metal)) {
      return found;
    }
  }
  return nil;
}

}  // namespace

void Install(std::function<void()> pause, std::function<void()> resume) {
  g_pause = std::move(pause);
  g_resume = std::move(resume);
  NSNotificationCenter* center = NSNotificationCenter.defaultCenter;
  NSOperationQueue* main = NSOperationQueue.mainQueue;
  auto on = [&](NSNotificationName name, void (*action)(const char*), const char* why) {
    [center addObserverForName:name
                        object:nil
                         queue:main
                    usingBlock:^(NSNotification*) {
                      action(why);
                    }];
  };
  on(UIApplicationWillResignActiveNotification, Pause, "app resigns active");
  on(UISceneWillDeactivateNotification, Pause, "scene resigns active");
  on(UIApplicationDidEnterBackgroundNotification, Pause, "app");
  on(UISceneDidEnterBackgroundNotification, Pause, "scene");
  // Only "active" resumes: "will enter foreground" comes before the app may
  // draw, and an inactive app (a screenshot's preview, Control Center) is
  // still paused.
  on(UIApplicationDidBecomeActiveNotification, Resume, "app active");
  on(UISceneDidActivateNotification, Resume, "scene active");
  StartStallWatchdog();
}

void KeepMetalViewWindowSized() {
  static Class metal = NSClassFromString(@"SDL_uikitmetalview");
  static __weak UIView* cached = nil;
  if (!metal) {
    return;
  }
  UIView* view = cached;
  if (!view || !view.window) {
    view = nil;
    for (UIScene* scene in UIApplication.sharedApplication.connectedScenes) {
      if (![scene isKindOfClass:UIWindowScene.class] ||
          ((UIWindowScene*)scene).screen != UIScreen.mainScreen) {
        continue;
      }
      for (UIWindow* w in ((UIWindowScene*)scene).windows) {
        if ((view = FindMetalView(w, metal))) {
          break;
        }
      }
      if (view) {
        break;
      }
    }
    cached = view;
  }
  UIWindow* window = view.window;
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
    ApplyMetalLayerPreset((__bridge void*)view.layer);
  }
}

void OnDisplayTick() {
  g_guest_booted.store(true, std::memory_order_relaxed);
  g_last_present_time.store(std::chrono::steady_clock::now(), std::memory_order_release);
  KeepMetalViewWindowSized();
  if (g_paused.load(std::memory_order_relaxed) && UIApplication.sharedApplication.applicationState == UIApplicationStateActive) {
    Resume("display refresh");
  }
}

}  // namespace nfsmw::lifecycle
