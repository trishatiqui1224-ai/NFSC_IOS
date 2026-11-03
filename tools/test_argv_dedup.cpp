#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

// Exact logic from ios/src/ios_main.mm
std::string OptionName(const std::string& arg) {
  return arg.substr(0, arg.find('='));
}

void SetArgument(std::vector<std::string>& args, const std::string& arg) {
  if (args.empty()) {
    args.push_back(arg);
    return;
  }
  const std::string name = OptionName(arg);
  if (name.rfind("--", 0) == 0) {
    for (size_t i = 1; i < args.size(); ++i) {
      if (OptionName(args[i]) == name) {
        args[i] = arg;
        return;
      }
    }
  }
  args.push_back(arg);
}

void ApplyUtilityQosDefault(std::vector<std::string>& args) {
  const std::pair<const char*, bool> defaults[] = {{"--ios_utility_qos", false},
                                                   {"--ios_utility_qos_guest", false},
                                                   {"--ios_adaptive_qos", false}};
  for (const auto& [flag, value] : defaults) {
    SetArgument(args, std::string(flag) + (value ? "=true" : "=false"));
  }
}

int main() {
  std::cout << "[test_argv_dedup] Starting tests..." << std::endl;

  // Test 1: Empty vector operations (previously caused SIGSEGV at faulting address 0x2f)
  {
    std::vector<std::string> empty_args;
    SetArgument(empty_args, "nfscarbon");
    assert(empty_args.size() == 1);
    assert(empty_args[0] == "nfscarbon");

    SetArgument(empty_args, "--foo=bar");
    assert(empty_args.size() == 2);
    assert(empty_args[1] == "--foo=bar");

    SetArgument(empty_args, "--foo=baz");
    assert(empty_args.size() == 2);
    assert(empty_args[1] == "--foo=baz");
    std::cout << "[test_argv_dedup] Test 1 (Empty vector handling) PASSED." << std::endl;
  }

  // Test 2: 61 flags from boot.txt + deduplication
  {
    std::vector<std::string> texts{"nfscarbon"};
    const std::vector<std::string> raw_flags = {
        "--carbon_title_id=454107EC",
        "--carbon_enable_hooks=true",
        "--gpu_allow_invalid_fetch_constants=true",
        "--gpu_sin_msaa=false",
        "--gpu_msaa_muestras=2",
        "--vulkan_render_target_path=fbo",
        "--edram_single_allocation=true",
        "--occlusion_query_enable=false",
        "--ios_invalidation_widen_kb=64",
        "--clear_memory_page_state=false",
        "--render_target_path_vulkan=fbo",
        "--ios_readback_max_kb=64",
        "--readback_resolve=none",
        "--readback_memexport=false",
        "--swap_post_effect=none",
        "--resolution=1560x720",
        "--carbon_scene_resolution=1560x720",
        "--carbon_single_pass=true",
        "--nfsmw_una_pasada=false",
        "--audio_maxqframes=64",
        "--ios_xma_starve_reset=false",
        "--ios_utility_qos_guest=false",
        "--ios_utility_qos=false",
        "--anisotropic_override=16",
        "--present_effect=cas",
        "--log_file=/path/to/nfscarbon.log",
        "--log_level=info",
        "--log_flush_interval=1",
        "--game_data_root=/path/to/Need for Speed - Carbon.iso",
        // Settings overrides (re-passed from launcher)
        "--resolution=1560x720",
        "--carbon_scene_resolution=1560x720",
        "--ios_display_preset=1080p",
        "--ios_retina=auto",
        "--resolution_scale=1",
        "--ios_fps_cap=60",
        "--ios_show_fps=true",
        "--ios_gpu_capture=false",
        "--ios_touch_controls=true",
        "--ios_touch_auto_layout=true",
        "--mnk_mode=false",
        "--keybind_a=A",
        "--keybind_b=B",
        "--keybind_x=X",
        "--keybind_y=Y",
        "--keybind_lb=LB",
        "--keybind_rb=RB",
        "--keybind_lt=LT",
        "--keybind_rt=RT",
        "--keybind_dpad_up=Up",
        "--keybind_dpad_down=Down",
        "--keybind_dpad_left=Left",
        "--keybind_dpad_right=Right",
        "--keybind_back=Back",
        "--keybind_start=Start",
        "--keybind_left_thumb=LThumb",
        "--keybind_right_thumb=RThumb",
        "--gpu_sin_msaa=false",
        "--gpu_msaa_muestras=2",
        "--swap_post_effect=none",
        "--present_effect=cas",
        "--anisotropic_override=16",
        "--carbon_single_pass=true",
        "--nfsmw_una_pasada=false",
        "--ios_async_submits=true",
        "--render_target_path_vulkan=fbo",
        "--occlusion_query_enable=false",
        "--ios_readback_max_kb=64",
        "--ios_invalidation_widen_kb=64",
        "--readback_resolve=none",
        "--readback_memexport=false",
        "--clear_memory_page_state=false",
        "--ios_iso_stream=true",
        "--ios_xma_starve_reset=false",
        "--ios_utility_qos_guest=false",
        "--ios_utility_qos=false",
        "--gpu_backend=vulkan",
        "--nfsmw_native_cp=false",
        "--nfsmw_native_present=false",
        "--log_level=info",
        "--ios_mvk_performance=false"
    };

    for (const auto& f : raw_flags) {
      SetArgument(texts, f);
    }

    // Hard defaults
    SetArgument(texts, "--ios_xma_starve_reset=false");
    SetArgument(texts, "--ios_utility_qos_guest=false");
    SetArgument(texts, "--ios_utility_qos=false");

    // Resolution clamp
    for (auto& t : texts) {
      if (OptionName(t) == "--carbon_scene_resolution" || OptionName(t) == "--resolution") {
        unsigned w = 0, h = 0;
        if (std::sscanf(t.c_str() + t.find('=') + 1, "%ux%u", &w, &h) == 2 && (w > 1600 || h > 720 || (w * h > 1560 * 720))) {
          t = OptionName(t) + "=1560x720";
        }
      }
    }

    // Deduplication pass
    std::vector<std::string> dedup_texts;
    if (!texts.empty()) {
      dedup_texts.push_back(texts.front());
      for (size_t i = 1; i < texts.size(); ++i) {
        SetArgument(dedup_texts, texts[i]);
      }
      texts = std::move(dedup_texts);
    }

    assert(!texts.empty());
    assert(texts[0] == "nfscarbon");

    // Build args array
    std::vector<char*> args;
    args.reserve(texts.size() + 1);
    for (auto& t : texts) {
      args.push_back(t.data());
    }
    args.push_back(nullptr);
    const int n = static_cast<int>(texts.size());
    assert(args.size() == texts.size() + 1);
    assert(args[n] == nullptr);

    // Simulate RunGame handoff
    std::vector<std::string> experiment_args;
    experiment_args.reserve(n);
    for (int i = 0; i < n; ++i) {
      if (args[i]) {
        experiment_args.emplace_back(args[i]);
      }
    }
    ApplyUtilityQosDefault(experiment_args);
    std::vector<char*> experiment_argv;
    experiment_argv.reserve(experiment_args.size() + 1);
    for (auto& arg : experiment_args) {
      experiment_argv.push_back(arg.data());
    }
    experiment_argv.push_back(nullptr);

    assert(experiment_argv.size() == experiment_args.size() + 1);
    assert(experiment_argv.back() == nullptr);

    std::cout << "[test_argv_dedup] Test 2 (61 flags + RunGame handoff) PASSED ("
              << experiment_args.size() << " unique flags)." << std::endl;
  }

  // Test 3: Last-occurrence wins deduplication & mnk_mode=false override
  {
    std::vector<std::string> args{"nfscarbon", "--mnk_mode=true", "--ios_display_preset=1080p"};
    SetArgument(args, "--mnk_mode=false");
    SetArgument(args, "--ios_display_preset=720p");

    assert(args.size() == 3);
    assert(args[0] == "nfscarbon");
    assert(args[1] == "--mnk_mode=false");
    assert(args[2] == "--ios_display_preset=720p");

    std::cout << "[test_argv_dedup] Test 3 (Last-wins deduplication for mnk_mode & presets) PASSED." << std::endl;
  }

  std::cout << "[test_argv_dedup] ALL TESTS PASSED." << std::endl;
  return 0;
}

