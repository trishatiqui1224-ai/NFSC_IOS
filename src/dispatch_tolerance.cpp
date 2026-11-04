#include <cstdio>
#include <cstring>
#include <filesystem>
#include <mutex>
#include <set>

#include <rex/filesystem.h>
#include <rex/logging.h>
#include <rex/ppc/context.h>
#include <rex/runtime.h>
#include <rex/system/function_dispatcher.h>
#include <spdlog/spdlog.h>

#include "carbon_missing_entries.h"

#if __has_include("../ios/src/boot_trace.h")
#include "../ios/src/boot_trace.h"
#elif __has_include("boot_trace.h")
#include "boot_trace.h"
#endif

#if __has_include("../generated/default/nfscarbon_pch.h")
#include "../generated/default/nfscarbon_pch.h"
#elif __has_include("generated/default/nfscarbon_pch.h")
#include "generated/default/nfscarbon_pch.h"
#elif __has_include("nfscarbon_pch.h")
#include "nfscarbon_pch.h"
#elif __has_include("../generated/default/nfsc_pch.h")
#include "../generated/default/nfsc_pch.h"
#elif __has_include("generated/default/nfsc_pch.h")
#include "generated/default/nfsc_pch.h"
#elif __has_include("nfsc_pch.h")
#include "nfsc_pch.h"
#endif

#if defined(__APPLE__)
// On Mach-O, weak_import is required for undefined weak symbols (not [[gnu::weak]]).
#define CARBON_WEAK_IMPORT __attribute__((weak_import))
#elif defined(__GNUC__) || defined(__clang__)
#define CARBON_WEAK_IMPORT __attribute__((weak))
#else
#define CARBON_WEAK_IMPORT
#endif

// Forward declarations of verified compiled guest routines
extern "C" {
// Kernel import __imp__ symbols -- used for version-agnostic address discovery.
// rexglue registers: SetFunction(<guest_addr>, __imp__KernelFunc) in nfsc_register.cpp.
// We find the guest address at runtime by looking up the __imp__ pointer in the dispatcher.
CARBON_WEAK_IMPORT void __imp__XamLoaderTerminateTitle(PPCContext& __restrict ctx, uint8_t* base);
CARBON_WEAK_IMPORT void __imp__ExTerminateThread(PPCContext& __restrict ctx, uint8_t* base);
CARBON_WEAK_IMPORT void __imp__XexUnloadImageAndExitThread(PPCContext& __restrict ctx, uint8_t* base);
CARBON_WEAK_IMPORT void __imp__HalReturnToFirmware(PPCContext& __restrict ctx, uint8_t* base);
CARBON_WEAK_IMPORT void __imp__KeBugCheck(PPCContext& __restrict ctx, uint8_t* base);
CARBON_WEAK_IMPORT void __imp__KeBugCheckEx(PPCContext& __restrict ctx, uint8_t* base);
CARBON_WEAK_IMPORT void __imp__DbgPrint(PPCContext& __restrict ctx, uint8_t* base);
CARBON_WEAK_IMPORT void __imp__NtAllocateVirtualMemory(PPCContext& __restrict ctx, uint8_t* base);
CARBON_WEAK_IMPORT void __imp__MmAllocatePhysicalMemoryEx(PPCContext& __restrict ctx, uint8_t* base);
CARBON_WEAK_IMPORT void __imp__XamInputSetState(PPCContext& __restrict ctx, uint8_t* base);
}

namespace {

void LogBootBreadcrumb(const char* message) {
  std::filesystem::path docs = rex::filesystem::GetUserFolder();
  if (!docs.empty()) {
    if (std::FILE* f = std::fopen((docs / "logs" / "boot.txt").string().c_str(), "a")) {
      std::fprintf(f, "%s\n", message);
      std::fflush(f);
      std::fclose(f);
    }
    if (std::FILE* f = std::fopen((docs / "logs" / "nfscarbon.log").string().c_str(), "a")) {
      std::fprintf(f, "%s\n", message);
      std::fflush(f);
      std::fclose(f);
    }
  }
}

inline void RecordPPCBreadcrumb(uint32_t fn, uint32_t lr, uint32_t r3) {
#if defined(__APPLE__)
  nfsmw::boot::SetLastPPCBreadcrumb(fn, lr, r3);
#else
  (void)fn; (void)lr; (void)r3;
#endif
}

thread_local uint32_t tl_last_indirect_target = 0;

void RecordUnregisteredTarget(uint32_t address, uint32_t caller_lr, uint64_t tid, uint32_t r3) {
  static std::mutex mutex;
  static std::set<std::pair<uint32_t, uint32_t>> seen_pairs;
  std::lock_guard<std::mutex> lock(mutex);
  if (seen_pairs.insert({address, caller_lr}).second) {
    REXLOG_ERROR("[dispatch] UNRESOLVED INDIRECT CALL: target=0x{:08X}, lr=0x{:08X}, r3=0x{:08X}, thread=0x{:X}",
                 address, caller_lr, r3, tid);
    rex::FlushLogging();
    if (auto logger = spdlog::default_logger()) {
      logger->flush();
    }

    char breadcrumb[256];
    std::snprintf(breadcrumb, sizeof(breadcrumb),
                  "[dispatch] UNRESOLVED INDIRECT CALL: target=0x%08X, lr=0x%08X, r3=0x%08X, thread=0x%llX",
                  address, caller_lr, r3, static_cast<unsigned long long>(tid));
    LogBootBreadcrumb(breadcrumb);

    std::filesystem::path log_path = "unregistered_targets.txt";
    std::filesystem::path docs = rex::filesystem::GetUserFolder();
    if (!docs.empty()) {
      log_path = docs / "logs" / "unregistered_targets.txt";
    }
    if (std::FILE* f = std::fopen(log_path.string().c_str(), "a")) {
      std::fprintf(f, "0x%08X (caller lr=0x%08X, r3=0x%08X, thread=0x%llX)\n",
                   address, caller_lr, r3, static_cast<unsigned long long>(tid));
      std::fclose(f);
    }
  }
}

void NoopTrap(PPCContext& ctx, uint8_t* base) {
  const uint32_t target = ctx.last_indirect_target ? static_cast<uint32_t>(ctx.last_indirect_target)
                                                   : tl_last_indirect_target;
  if (!target || target < 0x82000000) {
    SPDLOG_ERROR("[core] [dispatch] CAUGHT NULL/INVALID INDIRECT TARGET: 0x{0:X}", target);
    char breadcrumb[128];
    std::snprintf(breadcrumb, sizeof(breadcrumb),
                  "[core] [dispatch] CAUGHT NULL/INVALID INDIRECT TARGET: 0x%X", target);
    LogBootBreadcrumb(breadcrumb);
    ctx.r3.u64 = 0;
    return;
  }

  // Dynamic instruction decoder for uncompiled adjustors and leaf returns in .text
  if (base && target >= 0x82110000u && target + 8 <= 0x82B35C64u && (target & 3) == 0) {
    const uint32_t inst0 = REX_LOAD_U32(target);
    const uint32_t inst1 = REX_LOAD_U32(target + 4);

    // 1. Unconditional blr: preserve caller registers and return safely.
    if (inst0 == 0x4E800020u) {
      REXLOG_WARN("[dispatch] DYNAMIC RESOLVE: target 0x{:08X} is blr (leaf return), returning safely", target);
      return;
    }

    // 2. addi r3, r3, simm; b target2
    if ((inst0 & 0xFFFF0000u) == 0x38630000u && ((inst1 >> 26) & 0x3Fu) == 18u) {
      const int16_t simm = static_cast<int16_t>(inst0 & 0xFFFFu);
      uint32_t li = inst1 & 0x03FFFFFCu;
      if (li & 0x02000000u) {
        li |= 0xFC000000u;
      }
      const bool aa = (inst1 & 2u) != 0;
      const uint32_t branch_target = aa ? li : (target + 4u + li);

      REXLOG_WARN("[dispatch] DYNAMIC ADJUSTOR: target 0x{:08X} (addi r3, r3, {}; b 0x{:08X})",
                  target, simm, branch_target);
      ctx.r3.s64 = ctx.r3.s64 + simm;
      REX_CALL_INDIRECT_FUNC(branch_target);
      return;
    }

    // 3. addi r4, r4, simm; b target2
    if ((inst0 & 0xFFFF0000u) == 0x38840000u && ((inst1 >> 26) & 0x3Fu) == 18u) {
      const int16_t simm = static_cast<int16_t>(inst0 & 0xFFFFu);
      uint32_t li = inst1 & 0x03FFFFFCu;
      if (li & 0x02000000u) {
        li |= 0xFC000000u;
      }
      const bool aa = (inst1 & 2u) != 0;
      const uint32_t branch_target = aa ? li : (target + 4u + li);

      REXLOG_WARN("[dispatch] DYNAMIC ADJUSTOR: target 0x{:08X} (addi r4, r4, {}; b 0x{:08X})",
                  target, simm, branch_target);
      ctx.r4.s64 = ctx.r4.s64 + simm;
      REX_CALL_INDIRECT_FUNC(branch_target);
      return;
    }

    // 4. mr r3, r4; b target2
    if (inst0 == 0x7C832378u && ((inst1 >> 26) & 0x3Fu) == 18u) {
      uint32_t li = inst1 & 0x03FFFFFCu;
      if (li & 0x02000000u) {
        li |= 0xFC000000u;
      }
      const bool aa = (inst1 & 2u) != 0;
      const uint32_t branch_target = aa ? li : (target + 4u + li);

      REXLOG_WARN("[dispatch] DYNAMIC THUNK: target 0x{:08X} (mr r3, r4; b 0x{:08X})",
                  target, branch_target);
      ctx.r3.u64 = ctx.r4.u64;
      REX_CALL_INDIRECT_FUNC(branch_target);
      return;
    }

    // 5. Unconditional direct branch: b target2 (not bl)
    if (((inst0 >> 26) & 0x3Fu) == 18u && (inst0 & 1u) == 0) {
      uint32_t li = inst0 & 0x03FFFFFCu;
      if (li & 0x02000000u) {
        li |= 0xFC000000u;
      }
      const bool aa = (inst0 & 2u) != 0;
      const uint32_t branch_target = aa ? li : (target + li);

      REXLOG_WARN("[dispatch] DYNAMIC BRANCH: target 0x{:08X} (b 0x{:08X})",
                  target, branch_target);
      REX_CALL_INDIRECT_FUNC(branch_target);
      return;
    }

    // 6. li r3, simm; blr (0x3860xxxx; 0x4E800020)
    if ((inst0 & 0xFFFF0000u) == 0x38600000u && inst1 == 0x4E800020u) {
      const int16_t simm = static_cast<int16_t>(inst0 & 0xFFFFu);
      REXLOG_WARN("[dispatch] DYNAMIC CONSTANT RETURN: target 0x{:08X} (li r3, {}; blr)",
                  target, simm);
      ctx.r3.s64 = simm;
      return;
    }

    // 7. lis r11, high; lwz r11, low(r11); mtctr r11; bctr (e.g., 0x82235638)
    if ((inst0 & 0xFFFF0000u) == 0x3D600000u && (inst1 & 0xFFFF0000u) == 0x816B0000u &&
        target + 16 <= 0x82B35C64u) {
      const uint32_t inst2 = REX_LOAD_U32(target + 8);
      const uint32_t inst3 = REX_LOAD_U32(target + 12);
      if (inst2 == 0x7D6903A6u && inst3 == 0x4E800420u) {
        const int16_t high = static_cast<int16_t>(inst0 & 0xFFFFu);
        const int16_t low = static_cast<int16_t>(inst1 & 0xFFFFu);
        const uint32_t ptr = (static_cast<uint32_t>(high) << 16) + low;
        const uint32_t indirect_target = REX_LOAD_U32(ptr);
        REXLOG_WARN("[dispatch] DYNAMIC POINTER THUNK: target 0x{:08X} -> *(0x{:08X}) = 0x{:08X}",
                    target, ptr, indirect_target);
        if (indirect_target) {
          REX_CALL_INDIRECT_FUNC(indirect_target);
          return;
        }
      }
    }

    // 8. MemberAdapter Variant 2 (e.g. 0x82575CF0):
    // mr r11, r4; mr r10, r3; mr r4, r10; lwz r3, 4(r11); lwz r11, 0(r11); mtctr r11; bctr
    if (inst0 == 0x7C8B2378u && inst1 == 0x7C6A1B78u && target + 28 <= 0x82B35C64u) {
      const uint32_t inst2 = REX_LOAD_U32(target + 8);
      const uint32_t inst3 = REX_LOAD_U32(target + 12);
      const uint32_t inst4 = REX_LOAD_U32(target + 16);
      const uint32_t inst5 = REX_LOAD_U32(target + 20);
      const uint32_t inst6 = REX_LOAD_U32(target + 24);
      if (inst2 == 0x7D445378u && inst3 == 0x806B0004u &&
          inst4 == 0x816B0000u && inst5 == 0x7D6903A6u && inst6 == 0x4E800420u) {
        ctx.r11.u64 = ctx.r4.u64;
        ctx.r10.u64 = ctx.r3.u64;
        ctx.r4.u64 = ctx.r10.u64;
        ctx.r3.u64 = REX_LOAD_U32(ctx.r11.u32 + 4);
        ctx.r11.u64 = REX_LOAD_U32(ctx.r11.u32 + 0);
        ctx.ctr.u64 = ctx.r11.u64;
        REXLOG_WARN("[dispatch] DYNAMIC MEMBER ADAPTER V2: target 0x{:08X} -> ctr 0x{:08X}, r3 0x{:08X}",
                    target, ctx.ctr.u32, ctx.r3.u32);
        REX_CALL_INDIRECT_FUNC(ctx.ctr.u32);
        return;
      }
    }

    // 9. Setter tail-call (e.g. 0x82287280):
    // li r11, 0; stw r11, simm(r3); b target2
    if (inst0 == 0x39600000u && (inst1 & 0xFFFF0000u) == 0x91630000u && target + 12 <= 0x82B35C64u) {
      const uint32_t inst2 = REX_LOAD_U32(target + 8);
      if (((inst2 >> 26) & 0x3Fu) == 18u && (inst2 & 1u) == 0) {
        const int16_t simm = static_cast<int16_t>(inst1 & 0xFFFFu);
        uint32_t li = inst2 & 0x03FFFFFCu;
        if (li & 0x02000000u) {
          li |= 0xFC000000u;
        }
        const bool aa = (inst2 & 2u) != 0;
        const uint32_t branch_target = aa ? li : (target + 8u + li);
        REXLOG_WARN("[dispatch] DYNAMIC SETTER TAILCALL: target 0x{:08X} (stw 0, {}(0x{:08X}); b 0x{:08X})",
                    target, simm, ctx.r3.u32, branch_target);
        if (ctx.r3.u32 != 0) {
          REX_STORE_U32(ctx.r3.u32 + simm, 0);
        }
        REX_CALL_INDIRECT_FUNC(branch_target);
        return;
      }
    }
  }

  uint32_t caller_lr = static_cast<uint32_t>(ctx.lr);
  if (caller_lr == 0 && base) {
    const uint32_t sp = ctx.r1.u32;
    if (sp >= 0x70000000u && sp < 0x80000000u && (sp & 3) == 0) {
      uint32_t v;
      std::memcpy(&v, base + sp, 4);
      const uint32_t up = __builtin_bswap32(v);
      if (up > sp && up - sp <= 0x40000 && up < 0x80000000u) {
        uint32_t saved_lr_raw;
        std::memcpy(&saved_lr_raw, base + up - 8, 4);
        const uint32_t candidate_lr = __builtin_bswap32(saved_lr_raw);
        if (candidate_lr >= 0x82000000u && candidate_lr < 0x82B40000u) {
          caller_lr = candidate_lr;
        } else {
          std::memcpy(&saved_lr_raw, base + up + 8, 4);
          const uint32_t candidate_lr2 = __builtin_bswap32(saved_lr_raw);
          if (candidate_lr2 >= 0x82000000u && candidate_lr2 < 0x82B40000u) {
            caller_lr = candidate_lr2;
          }
        }
      }
    }
  }

  uint64_t tid = 0;
#if defined(__APPLE__)
  pthread_threadid_np(nullptr, &tid);
#elif defined(_WIN32)
  tid = static_cast<uint64_t>(GetCurrentThreadId());
#else
  tid = static_cast<uint64_t>(pthread_self());
#endif

  RecordUnregisteredTarget(target, caller_lr, tid, ctx.r3.u32);
  RecordPPCBreadcrumb(target, caller_lr, ctx.r3.u32);
  // Defensive null-guard for post-race Career / Quick Race state machine (Xenon ABI struct-return)
  if (ctx.r4.u32 >= 0x70000000 && ctx.r4.u32 == ctx.r31.u32) {
    // Xenon ABI struct return: caller set r4 and r31 to the return struct buffer!
    if (base && (ctx.r4.u32 & 3) == 0) {
      std::memset(base + ctx.r4.u32, 0, 64);
    }
    ctx.r3.u64 = ctx.r4.u32;
  } else if (caller_lr == 0x82137814 || target == 0x8249B7E0) {
    uint32_t out_struct_guest = ctx.r4.u32 ? ctx.r4.u32 : (ctx.r31.u32 ? ctx.r31.u32 : 0xBFAA5730);
    if (base && out_struct_guest != 0) {
      std::memset(base + out_struct_guest, 0, 64);
    }
    ctx.r3.u64 = out_struct_guest;
  } else if (target == 0x8249B6B0) {
    ctx.r3.u64 = ctx.r3.u32 ? ctx.r3.u32 : 0xBFAA32D8;
  } else if (target == 0x82235638 || (ctx.r3.u32 == 0 && ctx.r31.u32 != 0)) {
    // Route through r31 instance pointer to prevent crash when vehicle physics/controller initialize
    ctx.r3.u64 = ctx.r31.u32;
  } else {
    ctx.r3.u64 = 0;
  }
}

static ::PPCFunc* original_terminate_title = nullptr;
static ::PPCFunc* original_terminate_thread = nullptr;
static ::PPCFunc* original_unload_and_exit = nullptr;
static ::PPCFunc* original_return_to_firmware = nullptr;
static ::PPCFunc* original_bug_check = nullptr;
static ::PPCFunc* original_bug_check_ex = nullptr;
static ::PPCFunc* original_dbg_print = nullptr;
static ::PPCFunc* original_nt_allocate_virtual_memory = nullptr;
static ::PPCFunc* original_mm_allocate_physical_memory_ex = nullptr;
static ::PPCFunc* original_xam_input_set_state = nullptr;

extern "C" {
#if defined(__APPLE__)
void IOSHaptics_OnGuestRumble(uint16_t left_motor, uint16_t right_motor);
#else
inline void IOSHaptics_OnGuestRumble(uint16_t, uint16_t) {}
#endif
}

void Carbon_XamInputSetState_Hook(PPCContext& ctx, uint8_t* base) {
  if (base && ctx.r4.u32 != 0) {
    const uint16_t left = REX_LOAD_U16(ctx.r4.u32);
    const uint16_t right = REX_LOAD_U16(ctx.r4.u32 + 2);
    IOSHaptics_OnGuestRumble(left, right);
  }
  if (original_xam_input_set_state) {
    original_xam_input_set_state(ctx, base);
  } else {
    ctx.r3.u64 = 0; // ERROR_SUCCESS
  }
}

void Carbon_NtAllocateVirtualMemory_Hook(PPCContext& ctx, uint8_t* base) {
  if (original_nt_allocate_virtual_memory) {
    original_nt_allocate_virtual_memory(ctx, base);
  }
  if (static_cast<int32_t>(ctx.r3.u32) < 0) {
    char buf[256];
    std::snprintf(buf, sizeof(buf),
                  "[carbon-boot] NtAllocateVirtualMemory FAILED! status=0x%08X, lr=0x%08X",
                  ctx.r3.u32, static_cast<uint32_t>(ctx.lr));
    REXLOG_ERROR("{}", buf);
    LogBootBreadcrumb(buf);
  }
}

void Carbon_MmAllocatePhysicalMemoryEx_Hook(PPCContext& ctx, uint8_t* base) {
  if (original_mm_allocate_physical_memory_ex) {
    original_mm_allocate_physical_memory_ex(ctx, base);
  }
  if (ctx.r3.u32 == 0) {
    char buf[256];
    std::snprintf(buf, sizeof(buf),
                  "[carbon-boot] MmAllocatePhysicalMemoryEx FAILED (out of physical memory)! lr=0x%08X",
                  static_cast<uint32_t>(ctx.lr));
    REXLOG_ERROR("{}", buf);
    LogBootBreadcrumb(buf);
  }
}
static ::PPCFunc* original_carbon_main = nullptr;
static ::PPCFunc* original_entry_point = nullptr;

// =============================================================================
//  Startup Breadcrumb Hooks
// =============================================================================

// 1. Entry point 0x829446E0 breadcrumb:
// In the USA default.xex, 0x829446E0 IS the genuine XEX entry point compiled by
// rexglue into sub_829446E0. This is NOT a blr stub (that was the PAL XEX).
// We log entry for boot diagnostics and then delegate to the compiled USA code.
//
// The hook delegates dynamically to original_entry_point captured from the
// dispatcher at initialization time.
void Carbon_EntryPoint_0x829446E0_Hook(PPCContext& ctx, uint8_t* base) {
  char buf[256];
  std::snprintf(buf, sizeof(buf),
                "[carbon-boot] GUEST ENTRY 0x829446E0 (USA genuine entry point) called (lr=0x%08X, sp=0x%08X, r13=0x%08X)",
                static_cast<uint32_t>(ctx.lr), ctx.r1.u32, ctx.r13.u32);
  REXLOG_INFO("{}", buf);
  LogBootBreadcrumb(buf);
  rex::FlushLogging();
  if (auto logger = spdlog::default_logger()) {
    logger->flush();
  }

  // Delegate to genuine USA compiled entry point via the saved dispatcher pointer.
  if (original_entry_point) {
    original_entry_point(ctx, base);
  }

  REXLOG_INFO("[carbon-boot] <<< sub_829446E0 (USA entry 0x829446E0) finished (r3={})", ctx.r3.s32);
  LogBootBreadcrumb("[carbon-boot] <<< sub_829446E0 (USA entry 0x829446E0) finished");
  rex::FlushLogging();
  if (auto logger = spdlog::default_logger()) {
    logger->flush();
  }
}

// NOTE: sub_829446E0 is NOT redefined here as REX_FUNC -- doing so conflicts with
// DEFINE_REX_FUNC(sub_829446E0) in the recomp library (nfsc_recomp.113.cpp).
// The hook is installed at runtime via CarbonInstallDiagnosticHooks()->dispatcher->SetFunction().

// 2. USA display/privilege check (0x82944510) hook:
// In USA xstart (0x829446E0):
//   0x8294471C: bl 0x82944510
//   0x82944720: cmpwi r3, 0; beq 0x82944730
//   0x82944728: bl 0x82AACFC4 (XamLoaderTerminateTitle)
// If r3 == 0, xstart branches to 0x82944730, runs CRT init, and proceeds to main().
// If r3 != 0, xstart terminates the title immediately!
// We override this function to force success (r3 = 0).
void Carbon_DisplayCheck_0x82944510_Hook(PPCContext& ctx, uint8_t* /*base*/) {
  char buf[256];
  std::snprintf(buf, sizeof(buf),
                "[carbon-boot] sub_82944510 (USA display/privilege check) called from lr=0x%08X -> forcing r3=0 (proceed to CRT init)",
                static_cast<uint32_t>(ctx.lr));
  REXLOG_INFO("{}", buf);
  LogBootBreadcrumb(buf);
  rex::FlushLogging();
  if (auto logger = spdlog::default_logger()) {
    logger->flush();
  }
  ctx.r3.s64 = 0;
}

// 3. Carbon genuine USA main() (0x824E98B0) hook:
// Called by USA xstart (0x829446E0) at 0x82944874 after CRT initialization.
void Carbon_Main_Hook(PPCContext& ctx, uint8_t* base) {
  char buf[256];
  std::snprintf(buf, sizeof(buf),
                "[carbon-boot] ========================================================\n"
                "[carbon-boot] >>> CARBON USA main() REACHED at 0x824E98B0! argc=%d, argv=0x%08X\n"
                "[carbon-boot] ========================================================",
                ctx.r3.s32, ctx.r4.u32);
  REXLOG_INFO("{}", buf);
  LogBootBreadcrumb(buf);
  rex::FlushLogging();
  if (auto logger = spdlog::default_logger()) {
    logger->flush();
  }

  if (original_carbon_main) {
    original_carbon_main(ctx, base);
  }

  REXLOG_INFO("[carbon-boot] <<< CARBON USA main() returned with code={:d} (0x{:08X})",
              ctx.r3.s32, ctx.r3.u32);
  rex::FlushLogging();
  if (auto logger = spdlog::default_logger()) {
    logger->flush();
  }
}

// 5. Kernel exit hooks:
void Carbon_TerminateTitle_Hook(PPCContext& ctx, uint8_t* base) {
  char buf[256];
  std::snprintf(buf, sizeof(buf),
                "[carbon-boot] XamLoaderTerminateTitle CALLED! lr=0x%08X, exit_code=%d (0x%08X), r4=0x%08X",
                static_cast<uint32_t>(ctx.lr), ctx.r3.s32, ctx.r3.u32, ctx.r4.u32);
  REXLOG_ERROR("{}", buf);
  LogBootBreadcrumb(buf);
  rex::FlushLogging();
  if (auto logger = spdlog::default_logger()) {
    logger->flush();
  }
  std::fflush(nullptr);

  if (original_terminate_title) {
    original_terminate_title(ctx, base);
  }
}

void Carbon_ExTerminateThread_Hook(PPCContext& ctx, uint8_t* base) {
  char buf[256];
  std::snprintf(buf, sizeof(buf),
                "[carbon-boot] ExTerminateThread CALLED! lr=0x%08X, exit_code=%d (0x%08X)",
                static_cast<uint32_t>(ctx.lr), ctx.r3.s32, ctx.r3.u32);
  REXLOG_ERROR("{}", buf);
  LogBootBreadcrumb(buf);
  rex::FlushLogging();
  if (auto logger = spdlog::default_logger()) {
    logger->flush();
  }
  std::fflush(nullptr);

  if (original_terminate_thread) {
    original_terminate_thread(ctx, base);
  }
}

void Carbon_XexUnloadImageAndExitThread_Hook(PPCContext& ctx, uint8_t* base) {
  char buf[256];
  std::snprintf(buf, sizeof(buf),
                "[carbon-boot] XexUnloadImageAndExitThread CALLED! lr=0x%08X, handle=0x%08X, exit_code=%d",
                static_cast<uint32_t>(ctx.lr), ctx.r3.u32, ctx.r4.s32);
  REXLOG_ERROR("{}", buf);
  LogBootBreadcrumb(buf);
  rex::FlushLogging();
  if (auto logger = spdlog::default_logger()) {
    logger->flush();
  }
  std::fflush(nullptr);

  if (original_unload_and_exit) {
    original_unload_and_exit(ctx, base);
  }
}

void Carbon_HalReturnToFirmware_Hook(PPCContext& ctx, uint8_t* base) {
  char buf[256];
  std::snprintf(buf, sizeof(buf),
                "[carbon-boot] HalReturnToFirmware CALLED! lr=0x%08X, routine=%d (0x%08X)",
                static_cast<uint32_t>(ctx.lr), ctx.r3.s32, ctx.r3.u32);
  REXLOG_ERROR("{}", buf);
  LogBootBreadcrumb(buf);
  rex::FlushLogging();
  if (auto logger = spdlog::default_logger()) {
    logger->flush();
  }
  std::fflush(nullptr);

  if (original_return_to_firmware) {
    original_return_to_firmware(ctx, base);
  }
}

void Carbon_KeBugCheck_Hook(PPCContext& ctx, uint8_t* base) {
  char buf[256];
  std::snprintf(buf, sizeof(buf),
                "[carbon-boot] KeBugCheck CALLED! lr=0x%08X, code=0x%08X",
                static_cast<uint32_t>(ctx.lr), ctx.r3.u32);
  REXLOG_ERROR("{}", buf);
  LogBootBreadcrumb(buf);
  rex::FlushLogging();
  if (auto logger = spdlog::default_logger()) {
    logger->flush();
  }
  std::fflush(nullptr);

  if (original_bug_check) {
    original_bug_check(ctx, base);
  }
}

void Carbon_KeBugCheckEx_Hook(PPCContext& ctx, uint8_t* base) {
  char buf[256];
  std::snprintf(buf, sizeof(buf),
                "[carbon-boot] KeBugCheckEx CALLED! lr=0x%08X, code=0x%08X, p1=0x%08X, p2=0x%08X, p3=0x%08X, p4=0x%08X",
                static_cast<uint32_t>(ctx.lr), ctx.r3.u32, ctx.r4.u32, ctx.r5.u32, ctx.r6.u32, ctx.r7.u32);
  REXLOG_ERROR("{}", buf);
  LogBootBreadcrumb(buf);
  rex::FlushLogging();
  if (auto logger = spdlog::default_logger()) {
    logger->flush();
  }
  std::fflush(nullptr);

  if (original_bug_check_ex) {
    original_bug_check_ex(ctx, base);
  }
}

void Carbon_DbgPrint_Hook(PPCContext& ctx, uint8_t* base) {
  const char* str = ctx.r3.u32 ? reinterpret_cast<const char*>(base + ctx.r3.u32) : "<null>";
  REXLOG_INFO("[carbon] DbgPrint: format='{}', r4=0x{:08X} ({:d})", str, ctx.r4.u32, ctx.r4.s32);
  rex::FlushLogging();
  if (auto logger = spdlog::default_logger()) {
    logger->flush();
  }
  if (original_dbg_print) {
    original_dbg_print(ctx, base);
  }
}

}  // namespace

void CarbonInstallDiagnosticHooks(rex::runtime::FunctionDispatcher* dispatcher, uint8_t* /*base*/) {
  if (!dispatcher) return;

  // 1. Instrument entry point 0x829446E0 with a breadcrumb logger.
  // The recomp-generated sub_829446E0 is registered in the dispatcher.
  // Save the original function pointer so the hook delegates to it.
  if (auto* orig = dispatcher->GetFunction(0x829446E0)) {
    original_entry_point = orig;
  }
  dispatcher->SetFunction(0x829446E0, &Carbon_EntryPoint_0x829446E0_Hook);
  REXLOG_INFO("[carbon] Hooked USA entry point 0x829446E0 with breadcrumb logger (dispatcher)");

  const uint32_t kImportScanStart = PPCImageConfig.code_base + PPCImageConfig.code_size - 0x100000;
  const uint32_t kImportScanEnd   = PPCImageConfig.code_base + PPCImageConfig.code_size;
  constexpr uint32_t kImportStep  = 4;

  // 2. Override USA display/privilege check sub_82944510 to force success (r3 = 0).
  // In USA xstart (0x829446E0), this function is called at 0x8294471C.
  dispatcher->SetFunction(0x82944510, &Carbon_DisplayCheck_0x82944510_Hook);
  REXLOG_INFO("[carbon] Overrode USA display/privilege check sub_82944510 with success handler (r3 = 0)");

  // 3. Instrument Carbon's genuine USA main() (0x824E98B0).
  // Called by USA xstart at 0x82944874 after CRT initialization.
  if (auto* orig = dispatcher->GetFunction(0x824E98B0)) {
    original_carbon_main = orig;
  }
  dispatcher->SetFunction(0x824E98B0, &Carbon_Main_Hook);
  REXLOG_INFO("[carbon] Hooked Carbon USA main() (0x824E98B0) with breadcrumb logger");

  // 5. Instrument kernel import thunks.
  // We use __imp__ function pointers directly: rexglue registers them as
  // SetFunction(<guest_thunk_addr>, __imp__KernelFunc) in nfsc_register.cpp.
  // By looking up the function pointer in the dispatcher we get the correct
  // guest address regardless of which XEX (PAL or USA) was used for codegen.
  struct KernelHook {
    ::PPCFunc* imp_ptr;          // __imp__KernelFunc pointer
    ::PPCFunc* hook;             // our diagnostic wrapper
    ::PPCFunc** original_out;    // where to save the original (may be nullptr)
    const char* name;            // for logging
  };
  const KernelHook kernel_hooks[] = {
    { reinterpret_cast<::PPCFunc*>(&__imp__XamLoaderTerminateTitle),
      &Carbon_TerminateTitle_Hook, &original_terminate_title,
      "XamLoaderTerminateTitle" },
    { reinterpret_cast<::PPCFunc*>(&__imp__ExTerminateThread),
      &Carbon_ExTerminateThread_Hook, &original_terminate_thread,
      "ExTerminateThread" },
    { reinterpret_cast<::PPCFunc*>(&__imp__XexUnloadImageAndExitThread),
      &Carbon_XexUnloadImageAndExitThread_Hook, &original_unload_and_exit,
      "XexUnloadImageAndExitThread" },
    { reinterpret_cast<::PPCFunc*>(&__imp__HalReturnToFirmware),
      &Carbon_HalReturnToFirmware_Hook, &original_return_to_firmware,
      "HalReturnToFirmware" },
    { reinterpret_cast<::PPCFunc*>(&__imp__KeBugCheck),
      &Carbon_KeBugCheck_Hook, &original_bug_check,
      "KeBugCheck" },
    { reinterpret_cast<::PPCFunc*>(&__imp__KeBugCheckEx),
      &Carbon_KeBugCheckEx_Hook, &original_bug_check_ex,
      "KeBugCheckEx" },
    { reinterpret_cast<::PPCFunc*>(&__imp__DbgPrint),
      &Carbon_DbgPrint_Hook, &original_dbg_print,
      "DbgPrint" },
    { reinterpret_cast<::PPCFunc*>(&__imp__NtAllocateVirtualMemory),
      &Carbon_NtAllocateVirtualMemory_Hook, &original_nt_allocate_virtual_memory,
      "NtAllocateVirtualMemory" },
    { reinterpret_cast<::PPCFunc*>(&__imp__MmAllocatePhysicalMemoryEx),
      &Carbon_MmAllocatePhysicalMemoryEx_Hook, &original_mm_allocate_physical_memory_ex,
      "MmAllocatePhysicalMemoryEx" },
    { reinterpret_cast<::PPCFunc*>(&__imp__XamInputSetState),
      &Carbon_XamInputSetState_Hook, &original_xam_input_set_state,
      "XamInputSetState" },
  };
  for (const auto& h : kernel_hooks) {
    if (!h.imp_ptr) continue;
    bool hooked = false;
    for (uint32_t addr = kImportScanStart; addr < kImportScanEnd; addr += kImportStep) {
      if (dispatcher->GetFunction(addr) == h.imp_ptr) {
        if (h.original_out) *h.original_out = h.imp_ptr;
        dispatcher->SetFunction(addr, h.hook);
        REXLOG_INFO("[carbon] Hooked {} at 0x{:08X}", h.name, addr);
        hooked = true;
        break;
      }
    }
    if (!hooked) {
      REXLOG_WARN("[carbon] Could not find {} thunk in dispatcher (wrong XEX version?)", h.name);
    }
  }


  if (auto logger = spdlog::default_logger()) {
    logger->flush();
  }
}

namespace rex::runtime {

::PPCFunc* ResolveIndirectFunction(uint32_t guest_address) {
  if (!guest_address || guest_address < 0x82000000) {
    SPDLOG_ERROR("[core] [dispatch] CAUGHT NULL/INVALID INDIRECT TARGET: 0x{0:X}", guest_address);
    char breadcrumb[128];
    std::snprintf(breadcrumb, sizeof(breadcrumb),
                  "[core] [dispatch] CAUGHT NULL/INVALID INDIRECT TARGET: 0x%X", guest_address);
    LogBootBreadcrumb(breadcrumb);
    tl_last_indirect_target = guest_address;
    RecordPPCBreadcrumb(guest_address, 0, 0);
    return &NoopTrap;
  }

  tl_last_indirect_target = guest_address;
  if (Runtime* rt = Runtime::instance()) {
    if (FunctionDispatcher* d = rt->function_dispatcher()) {
      if (::PPCFunc* f = d->GetFunction(guest_address)) {
        return f;
      }
    }
  }
  RecordPPCBreadcrumb(guest_address, 0, 0);
  return &NoopTrap;
}

}  // namespace rex::runtime
