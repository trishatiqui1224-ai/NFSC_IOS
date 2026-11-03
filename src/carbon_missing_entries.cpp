// Exact translation of executable entries missed by automatic discovery.
// Validated against the loaded original PPC instructions before registration.
#include "generated/default/nfscarbon_pch.h"
#include "carbon_missing_entries.h"
#include <rex/system/function_dispatcher.h>
#include <array>
#include <bit>

namespace {

// Identical eight-instruction member-callback adapters occur consecutively.
// GapFill doesn't split at bctr, so only the first adapter may be discovered.
constexpr std::array<uint32_t, 8> kMemberAdapter = {
  0x7C8B2378, 0x7C641B78, 0x814B0008, 0x812B0004,
  0x816B0000, 0x7C6A4A14, 0x7D6903A6, 0x4E800420,
};

void Carbon_MemberAdapter(PPCContext& ctx, uint8_t* base) {
  ctx.r11.u64 = ctx.r4.u64;
  ctx.r4.u64 = ctx.r3.u64;
  ctx.r10.u64 = REX_LOAD_U32(ctx.r11.u32 + 8);
  ctx.r9.u64 = REX_LOAD_U32(ctx.r11.u32 + 4);
  ctx.r11.u64 = REX_LOAD_U32(ctx.r11.u32);
  ctx.r3.u64 = ctx.r10.u64 + ctx.r9.u64;
  ctx.ctr.u64 = ctx.r11.u64;
  REX_CALL_INDIRECT_FUNC(ctx.ctr.u32);
}

void Carbon_Blr([[maybe_unused]] PPCContext& ctx,
                [[maybe_unused]] uint8_t* base) {}

// USA 0x821A3EC8: flasher callback / thunk (mr r3, r4; b 0x821A35E0), called from lr=0x82690F0C.
void Carbon_821A3EC8(PPCContext& ctx, [[maybe_unused]] uint8_t* base) {
  ctx.r3.u64 = ctx.r4.u64;
  REX_CALL_INDIRECT_FUNC(0x821A35E0);
}

// USA equivalent of PAL 0x82641480: addi r3,r3,-4; b <target>
// PAL target was 0x8262DB10; USA target is 0x82125CD8.
void Carbon_8216D770(PPCContext& ctx, uint8_t* base) {
  ctx.r3.s64 = ctx.r3.s64 - 4;
  REX_CALL_INDIRECT_FUNC(0x82125CD8);
}

// General adjustor thunk templates:
template <int32_t Offset, uint32_t Target>
void Carbon_Adjustor_R3(PPCContext& ctx, [[maybe_unused]] uint8_t* base) {
  ctx.r3.s64 = ctx.r3.s64 + Offset;
  REX_CALL_INDIRECT_FUNC(Target);
}

template <int32_t Offset, uint32_t Target>
void Carbon_Adjustor_R4(PPCContext& ctx, [[maybe_unused]] uint8_t* base) {
  ctx.r4.s64 = ctx.r4.s64 + Offset;
  REX_CALL_INDIRECT_FUNC(Target);
}

template <::PPCFunc Func>
inline void RegisterAdjustor(rex::runtime::FunctionDispatcher* dispatcher, uint32_t addr) {
  if (!dispatcher->GetFunction(addr)) {
    dispatcher->SetFunction(addr, Func);
  }
}

// USA 0x82531FB8: vtable adjustor thunk (addi r3, r3, 84; b 0x8253BFB0)
// Called from lr=0x826091F4 with r3=0xBFAC43CC.
void Carbon_82531FB8(PPCContext& ctx, [[maybe_unused]] uint8_t* base) {
  ctx.r3.s64 = ctx.r3.s64 + 84;
  REX_CALL_INDIRECT_FUNC(0x8253BFB0);
}

// USA 0x8249B6B0: vtable adjustor thunk (addi r3, r3, -8; b 0x82482B10)
// Called from lr=0x821377F8 with r3=0xBFAA32D8.
void Carbon_8249B6B0(PPCContext& ctx, [[maybe_unused]] uint8_t* base) {
  ctx.r3.s64 = ctx.r3.s64 - 8;
  REX_CALL_INDIRECT_FUNC(0x82482B10);
}

// USA 0x8249B7E0: vtable adjustor thunk (addi r3, r3, -8; b 0x82482B20)
// Called from lr=0x82137814 with r3=0xBFAA32D8.
// sub_82482B20 fetches member pointer at *(r11)+0x20 and returns it in r3.
void Carbon_8249B7E0(PPCContext& ctx, [[maybe_unused]] uint8_t* base) {
  ctx.r3.s64 = ctx.r3.s64 - 8;
  REX_CALL_INDIRECT_FUNC(0x82482B20);
}

// USA equivalent of PAL 0x82296468 -- exact byte match at 0x82296388 (-0xE0 shift).
void Carbon_82296388(PPCContext& ctx, [[maybe_unused]] uint8_t* base) {
  ctx.cr6.compare<uint32_t>(ctx.r4.u32, 1, ctx.xer);
  if (ctx.cr6.lt) { ctx.r3.s64 = 1; return; }
  if (ctx.cr6.eq) { ctx.r3.s64 = 12; return; }
  ctx.cr6.compare<uint32_t>(ctx.r4.u32, 3, ctx.xer);
  if (ctx.cr6.lt) { ctx.r3.s64 = 13; return; }
  ctx.r3.s64 = -1;
}

// USA 0x82296388: exact same 13-word sequence (no shift in instructions, just address).
constexpr std::array<uint32_t, 13> kOriginal_82296388 = {
  0x2B040001, 0x41980028, 0x419A001C, 0x2B040003,
  0x4198000C, 0x3860FFFF, 0x4E800020, 0x3860000D,
  0x4E800020, 0x3860000C, 0x4E800020, 0x38600001,
  0x4E800020,
};

// USA 0x822A93B0..0x822A9410: update an object's two resource references and
// clear the original global pair when the resource's field_0x10 is zero.
// USA equivalent of PAL 0x822A9490 -- perfect 24-word fingerprint match.
void Carbon_822A93B0(PPCContext& ctx, uint8_t* base) {
  ctx.r11.u64 = REX_LOAD_U32(ctx.r4.u32 + 0x14);
  ctx.r10.s64 = 0;
  ctx.cr6.compare<int32_t>(ctx.r11.s32, 2, ctx.xer);
  if (ctx.cr6.eq) goto loc_822A94C8;
  ctx.cr6.compare<int32_t>(ctx.r11.s32, 3, ctx.xer);
  if (ctx.cr6.eq) goto loc_822A94C8;
  ctx.cr6.compare<int32_t>(ctx.r11.s32, 4, ctx.xer);
  if (ctx.cr6.eq) goto loc_822A94C8;
  ctx.cr6.compare<int32_t>(ctx.r11.s32, 12, ctx.xer);
  if (ctx.cr6.eq) goto loc_822A94C8;
  ctx.cr6.compare<int32_t>(ctx.r11.s32, 5, ctx.xer);
  if (ctx.cr6.eq) goto loc_822A94C8;
  REX_STORE_U32(ctx.r3.u32 + 0x14, ctx.r10.u32);
  goto loc_822A94CC;
loc_822A94C8:
  REX_STORE_U32(ctx.r3.u32 + 0x14, ctx.r4.u32);
loc_822A94CC:
  REX_STORE_U32(ctx.r3.u32 + 0x10, ctx.r4.u32);
  ctx.r11.u64 = REX_LOAD_U32(ctx.r4.u32 + 0x10);
  ctx.cr6.compare<int32_t>(ctx.r11.s32, 0, ctx.xer);
  if (!ctx.cr6.eq) return;
  ctx.r11.s64 = static_cast<int32_t>(0x82BA0000u);
  ctx.r11.s64 = ctx.r11.s64 + 0x200C;
  REX_STORE_U32(ctx.r11.u32, ctx.r10.u32);
  REX_STORE_U32(ctx.r11.u32 + 4, ctx.r10.u32);
}

// USA 0x822A93B0: identical 24-word fingerprint to PAL 0x822A9490.
constexpr std::array<uint32_t, 24> kOriginal_822A93B0 = {
  0x81640014, 0x39400000, 0x2F0B0002, 0x419A002C,
  0x2F0B0003, 0x419A0024, 0x2F0B0004, 0x419A001C,
  0x2F0B000C, 0x419A0014, 0x2F0B0005, 0x419A000C,
  0x91430014, 0x48000008, 0x90830014, 0x90830010,
  0x81640010, 0x2F0B0000, 0x4C9A0020, 0x3D6082BA,
  0x396B200C, 0x914B0000, 0x914B0004, 0x4E800020,
};

// USA 0x82321FC8: virtual dispatch through object->field_0xB0,
// falling back to original vtable when unavailable.
// USA equivalent of PAL 0x82322048 -- perfect structural match.
void Carbon_82321FC8(PPCContext& ctx, uint8_t* base) {
  ctx.r11.u64 = REX_LOAD_U32(ctx.r3.u32 + 0xB0);
  ctx.cr6.compare<uint32_t>(ctx.r11.u32, 0, ctx.xer);
  if (!ctx.cr6.eq) {
    ctx.r11.u64 = REX_LOAD_U32(ctx.r11.u32 + 0x18);
    ctx.r11.s64 = ctx.r11.s64 + 1;
    ctx.r11.u64 = std::countl_zero(ctx.r11.u32);
    ctx.r11.u64 = (ctx.r11.u32 >> 5) & 1;
    ctx.r11.u64 ^= 1;
    ctx.cr6.compare<uint32_t>(ctx.r11.u32, 0, ctx.xer);
    if (!ctx.cr6.eq) {
      ctx.r3.u64 = REX_LOAD_U32(ctx.r3.u32 + 0xB0);
      ctx.r11.u64 = REX_LOAD_U32(ctx.r3.u32);
      ctx.r11.u64 = REX_LOAD_U32(ctx.r11.u32 + 4);
      ctx.ctr.u64 = ctx.r11.u64;
      REX_CALL_INDIRECT_FUNC(ctx.ctr.u32);
      return;
    }
  }
  ctx.r11.u64 = REX_LOAD_U32(ctx.r3.u32);
  ctx.r11.u64 = REX_LOAD_U32(ctx.r11.u32 + 0x68);
  ctx.ctr.u64 = ctx.r11.u64;
  REX_CALL_INDIRECT_FUNC(ctx.ctr.u32);
}

// USA 0x82321FC8: same structural pattern; lwz r11,4(r3) and lwz r11,0x68(r3) match PAL.
constexpr std::array<uint32_t, 19> kOriginal_82321FC8 = {
  0x816300B0, 0x2B0B0000, 0x419A0034, 0x816B0018, 0x396B0001,
  0x7D6B0034, 0x556BDFFE, 0x696B0001, 0x2B0B0000, 0x419A0018,
  0x806300B0, 0x81630000, 0x816B0004, 0x7D6903A6, 0x4E800420,
  0x81630000, 0x816B0068, 0x7D6903A6, 0x4E800420,
};

} // namespace

void CarbonRegisterMissingEntries(rex::runtime::FunctionDispatcher* dispatcher,
                                  uint8_t* base) {
  // Boot reached an unregistered 0x823503D0 consisting solely of `blr`.
  // Any indirect entry whose actual first instruction is unconditional `blr`
  // has exactly these semantics, including entry directly at an epilogue.
  // Preserve existing generated functions; never replace an existing compiled function.
  size_t return_entries = 0;
  size_t member_adapters = 0;
  size_t skipped_entries = 0;
  for (uint32_t entry = PPCImageConfig.code_base;
       entry < PPCImageConfig.code_base + PPCImageConfig.code_size; entry += 4) {
    if (REX_LOAD_U32(entry) == 0x4E800020) {
      if (dispatcher->GetFunction(entry)) {
        ++skipped_entries;
      } else {
        if (!dispatcher->SetFunction(entry, &Carbon_Blr))
          REX_FATAL("Could not register original Carbon return instruction");
        ++return_entries;
      }
    }
    if (REX_LOAD_U32(entry) == kMemberAdapter[0] &&
        entry + kMemberAdapter.size() * 4 <= PPCImageConfig.code_base + PPCImageConfig.code_size) {
      if (dispatcher->GetFunction(entry)) {
        ++skipped_entries;
      } else {
        bool matches = true;
        for (size_t index = 1; index < kMemberAdapter.size(); ++index) {
          if (REX_LOAD_U32(entry + static_cast<uint32_t>(index * 4)) != kMemberAdapter[index]) {
            matches = false;
            break;
          }
        }
        if (matches) {
          if (!dispatcher->SetFunction(entry, &Carbon_MemberAdapter))
            REX_FATAL("Could not register original Carbon member adapter");
          ++member_adapters;
        }
      }
    }
  }
  REXLOG_INFO("[carbon] Registered {} original blr entries ({} existing compiled functions skipped)",
              return_entries, skipped_entries);
  REXLOG_INFO("[carbon] Registered {} verified member adapters", member_adapters);
  if (auto logger = spdlog::default_logger()) {
    logger->flush();
  }
  // USA 0x82296388: state/result mapper (exact 13-word fingerprint match to PAL 0x82296468).
  constexpr uint32_t state_entry = 0x82296388;
  if (!dispatcher->GetFunction(state_entry)) {
    bool ok = true;
    for (size_t index = 0; index < kOriginal_82296388.size(); ++index) {
      if (REX_LOAD_U32(state_entry + static_cast<uint32_t>(index * 4)) != kOriginal_82296388[index]) {
        ok = false;
        break;
      }
    }
    if (ok && dispatcher->SetFunction(state_entry, &Carbon_82296388)) {
      REXLOG_INFO("[carbon] Registered verified state entry 0x82296388 (USA)");
    }
  }
  // USA 0x822A93B0: resource-reference updater (perfect 24-word fingerprint match to PAL 0x822A9490).
  constexpr uint32_t story_entry = 0x822A93B0;
  if (!dispatcher->GetFunction(story_entry)) {
    bool ok = true;
    for (size_t index = 0; index < kOriginal_822A93B0.size(); ++index) {
      if (REX_LOAD_U32(story_entry + static_cast<uint32_t>(index * 4)) != kOriginal_822A93B0[index]) {
        ok = false;
        break;
      }
    }
    if (ok && dispatcher->SetFunction(story_entry, &Carbon_822A93B0)) {
      REXLOG_INFO("[carbon] Registered verified story entry 0x822A93B0 (USA)");
    }
  }
  // USA 0x8216D770: adjustor -4 (addi r3,r3,-4; b 0x82125CD8). PAL was 0x82641480.
  // Only verify the first word (addi instruction is identical in both variants).
  constexpr uint32_t adjustor = 0x8216D770;
  if (!dispatcher->GetFunction(adjustor)) {
    if (REX_LOAD_U32(adjustor) == 0x3863FFFC) {
      if (dispatcher->SetFunction(adjustor, &Carbon_8216D770)) {
        REXLOG_INFO("[carbon] Registered verified adjustor 0x8216D770 (USA, PAL was 0x82641480)");
      }
    }
  }
  // USA 0x82321FC8: virtual dispatch (perfect structural match to PAL 0x82322048).
  constexpr uint32_t address = 0x82321FC8;
  if (!dispatcher->GetFunction(address)) {
    bool ok = true;
    for (size_t index = 0; index < kOriginal_82321FC8.size(); ++index) {
      if (REX_LOAD_U32(address + static_cast<uint32_t>(index * 4)) != kOriginal_82321FC8[index]) {
        ok = false;
        break;
      }
    }
    if (ok && dispatcher->SetFunction(address, &Carbon_82321FC8)) {
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

  // USA 0x82531FB8: vtable adjustor (+84 -> 0x8253BFB0) for Career / Car Select
  RegisterAdjustor<Carbon_82531FB8>(dispatcher, 0x82531FB8);

  // USA 0x8249B6B0: vtable adjustor (-8 -> 0x82482B10) for Career / Quick Race
  RegisterAdjustor<Carbon_8249B6B0>(dispatcher, 0x8249B6B0);

  // USA 0x8249B7E0: vtable adjustor (-8 -> 0x82482B20) for Career / Quick Race
  RegisterAdjustor<Carbon_8249B7E0>(dispatcher, 0x8249B7E0);

  // Contiguous virtual adjustor thunk table at 0x8249B688..0x8249B838
  RegisterAdjustor<Carbon_Adjustor_R3<-24, 0x824A0168>>(dispatcher, 0x8249B688);
  RegisterAdjustor<Carbon_Adjustor_R3<-180, 0x82482EB8>>(dispatcher, 0x8249B690);
  RegisterAdjustor<Carbon_Adjustor_R3<-36, 0x8247D628>>(dispatcher, 0x8249B698);
  RegisterAdjustor<Carbon_Adjustor_R3<-16, 0x82482850>>(dispatcher, 0x8249B6A0);
  RegisterAdjustor<Carbon_Adjustor_R3<-24, 0x82482B30>>(dispatcher, 0x8249B6A8);
  RegisterAdjustor<Carbon_Adjustor_R3<-36, 0x824853F0>>(dispatcher, 0x8249B6B8);
  RegisterAdjustor<Carbon_Adjustor_R3<-36, 0x82483CE8>>(dispatcher, 0x8249B6C0);
  RegisterAdjustor<Carbon_Adjustor_R3<-12, 0x82481410>>(dispatcher, 0x8249B6C8);
  RegisterAdjustor<Carbon_Adjustor_R3<-64, 0x82485798>>(dispatcher, 0x8249B6D0);
  RegisterAdjustor<Carbon_Adjustor_R3<-172, 0x8247A590>>(dispatcher, 0x8249B6D8);
  RegisterAdjustor<Carbon_Adjustor_R3<-96, 0x82485798>>(dispatcher, 0x8249B6E0);
  RegisterAdjustor<Carbon_Adjustor_R3<-24, 0x82482AF0>>(dispatcher, 0x8249B6E8);
  RegisterAdjustor<Carbon_Adjustor_R3<-36, 0x82480C08>>(dispatcher, 0x8249B6F0);
  RegisterAdjustor<Carbon_Adjustor_R3<-8, 0x8247FD18>>(dispatcher, 0x8249B6F8);
  RegisterAdjustor<Carbon_Adjustor_R3<-228, 0x82483CE8>>(dispatcher, 0x8249B700);
  RegisterAdjustor<Carbon_Adjustor_R3<-48, 0x8247A8F0>>(dispatcher, 0x8249B708);
  RegisterAdjustor<Carbon_Adjustor_R3<-24, 0x82482B20>>(dispatcher, 0x8249B710);
  RegisterAdjustor<Carbon_Adjustor_R3<-20, 0x824821C8>>(dispatcher, 0x8249B718);
  RegisterAdjustor<Carbon_Adjustor_R3<-48, 0x8247D628>>(dispatcher, 0x8249B720);
  RegisterAdjustor<Carbon_Adjustor_R3<-72, 0x82485798>>(dispatcher, 0x8249B728);
  RegisterAdjustor<Carbon_Adjustor_R3<-24, 0x824A01B8>>(dispatcher, 0x8249B730);
  RegisterAdjustor<Carbon_Adjustor_R3<-48, 0x824853F0>>(dispatcher, 0x8249B738);
  RegisterAdjustor<Carbon_Adjustor_R3<-208, 0x8247A8F0>>(dispatcher, 0x8249B740);
  RegisterAdjustor<Carbon_Adjustor_R3<-48, 0x82483CE8>>(dispatcher, 0x8249B748);
  RegisterAdjustor<Carbon_Adjustor_R3<-12, 0x82481390>>(dispatcher, 0x8249B750);
  RegisterAdjustor<Carbon_Adjustor_R3<-208, 0x8247D628>>(dispatcher, 0x8249B758);
  RegisterAdjustor<Carbon_Adjustor_R3<-8, 0x82482B30>>(dispatcher, 0x8249B760);
  RegisterAdjustor<Carbon_Adjustor_R3<-236, 0x82483CE8>>(dispatcher, 0x8249B768);
  RegisterAdjustor<Carbon_Adjustor_R3<-56, 0x8247A8F0>>(dispatcher, 0x8249B770);
  RegisterAdjustor<Carbon_Adjustor_R3<-20, 0x82482070>>(dispatcher, 0x8249B778);
  RegisterAdjustor<Carbon_Adjustor_R3<-24, 0x82482B10>>(dispatcher, 0x8249B780);
  RegisterAdjustor<Carbon_Adjustor_R3<-48, 0x82480C08>>(dispatcher, 0x8249B788);
  RegisterAdjustor<Carbon_Adjustor_R3<-24, 0x8249FF48>>(dispatcher, 0x8249B790);
  RegisterAdjustor<Carbon_Adjustor_R3<-56, 0x8247D628>>(dispatcher, 0x8249B798);
  RegisterAdjustor<Carbon_Adjustor_R3<-80, 0x82485798>>(dispatcher, 0x8249B7A0);
  RegisterAdjustor<Carbon_Adjustor_R3<-208, 0x82483CE8>>(dispatcher, 0x8249B7A8);
  RegisterAdjustor<Carbon_Adjustor_R3<-24, 0x82482C70>>(dispatcher, 0x8249B7B0);
  RegisterAdjustor<Carbon_Adjustor_R3<-24, 0x824A0190>>(dispatcher, 0x8249B7B8);
  RegisterAdjustor<Carbon_Adjustor_R3<-56, 0x82483CE8>>(dispatcher, 0x8249B7C0);
  RegisterAdjustor<Carbon_Adjustor_R3<-172, 0x8247A598>>(dispatcher, 0x8249B7C8);
  RegisterAdjustor<Carbon_Adjustor_R3<-216, 0x8247D628>>(dispatcher, 0x8249B7D0);
  RegisterAdjustor<Carbon_Adjustor_R3<-172, 0x8247B3A8>>(dispatcher, 0x8249B7D8);
  RegisterAdjustor<Carbon_Adjustor_R3<-180, 0x82482EC0>>(dispatcher, 0x8249B7E8);
  RegisterAdjustor<Carbon_Adjustor_R3<-12, 0x82479900>>(dispatcher, 0x8249B7F0);
  RegisterAdjustor<Carbon_Adjustor_R3<-56, 0x82480C08>>(dispatcher, 0x8249B7F8);
  RegisterAdjustor<Carbon_Adjustor_R3<-12, 0x824812C0>>(dispatcher, 0x8249B800);
  RegisterAdjustor<Carbon_Adjustor_R4<-8, 0x82482CA0>>(dispatcher, 0x8249B808);
  RegisterAdjustor<Carbon_Adjustor_R3<-216, 0x82483CE8>>(dispatcher, 0x8249B810);
  RegisterAdjustor<Carbon_Adjustor_R3<-220, 0x8247D628>>(dispatcher, 0x8249B818);
  RegisterAdjustor<Carbon_Adjustor_R3<-36, 0x8247A8F0>>(dispatcher, 0x8249B820);
  RegisterAdjustor<Carbon_Adjustor_R3<-20, 0x824799F0>>(dispatcher, 0x8249B828);
  RegisterAdjustor<Carbon_Adjustor_R3<-12, 0x824799D0>>(dispatcher, 0x8249B830);

  // Sibling vtable adjustors in .rdata
  RegisterAdjustor<Carbon_Adjustor_R3<-80, 0x82136358>>(dispatcher, 0x8216D608);
  RegisterAdjustor<Carbon_Adjustor_R3<-112, 0x82142540>>(dispatcher, 0x8216D628);
  RegisterAdjustor<Carbon_Adjustor_R3<-600, 0x8213FDB0>>(dispatcher, 0x8216D7B0);
  RegisterAdjustor<Carbon_Adjustor_R3<-40, 0x82125CD8>>(dispatcher, 0x8216D7E0);
  RegisterAdjustor<Carbon_Adjustor_R3<-72, 0x821247A8>>(dispatcher, 0x8216D800);
  RegisterAdjustor<Carbon_Adjustor_R3<-64, 0x82170CB0>>(dispatcher, 0x821896C8);
  RegisterAdjustor<Carbon_Adjustor_R3<-40, 0x82308180>>(dispatcher, 0x82356C68);
  RegisterAdjustor<Carbon_Adjustor_R3<-100, 0x824ABAF0>>(dispatcher, 0x824D5010);
  RegisterAdjustor<Carbon_Adjustor_R3<-304, 0x824A8FE8>>(dispatcher, 0x824D50F8);
  RegisterAdjustor<Carbon_Adjustor_R3<-88, 0x824C7D30>>(dispatcher, 0x824D5148);
  RegisterAdjustor<Carbon_Adjustor_R3<-88, 0x824C84C8>>(dispatcher, 0x824D5198);
  RegisterAdjustor<Carbon_Adjustor_R3<-28, 0x8253A388>>(dispatcher, 0x82541688);
  RegisterAdjustor<Carbon_Adjustor_R3<-36, 0x825310C0>>(dispatcher, 0x825416B0);
  RegisterAdjustor<Carbon_Adjustor_R3<-48, 0x8252E4F8>>(dispatcher, 0x82541708);
  RegisterAdjustor<Carbon_Adjustor_R3<-44, 0x825310C0>>(dispatcher, 0x82541740);
  RegisterAdjustor<Carbon_Adjustor_R3<-36, 0x82535958>>(dispatcher, 0x82541750);
  RegisterAdjustor<Carbon_Adjustor_R3<-72, 0x82533F60>>(dispatcher, 0x82541760);
  RegisterAdjustor<Carbon_Adjustor_R3<-48, 0x82533CD0>>(dispatcher, 0x82541778);
  RegisterAdjustor<Carbon_Adjustor_R3<-72, 0x82535958>>(dispatcher, 0x825417A8);
  RegisterAdjustor<Carbon_Adjustor_R3<-56, 0x82607D58>>(dispatcher, 0x82614018);
  RegisterAdjustor<Carbon_Adjustor_R3<-152, 0x82607D58>>(dispatcher, 0x82614030);
  RegisterAdjustor<Carbon_Adjustor_R3<-36, 0x82607D58>>(dispatcher, 0x82614078);
  RegisterAdjustor<Carbon_Adjustor_R3<-136, 0x82607D58>>(dispatcher, 0x826140C8);
  RegisterAdjustor<Carbon_Adjustor_R3<-4, 0x82639348>>(dispatcher, 0x82642670);
  RegisterAdjustor<Carbon_Adjustor_R3<1, 0x82949918>>(dispatcher, 0x8294CEA8);
  RegisterAdjustor<Carbon_Adjustor_R3<-148, 0x82958500>>(dispatcher, 0x82958518);
  RegisterAdjustor<Carbon_Adjustor_R3<-148, 0x829586D8>>(dispatcher, 0x82958700);
  RegisterAdjustor<Carbon_Adjustor_R3<-148, 0x829EC2C0>>(dispatcher, 0x829EC2D0);
  RegisterAdjustor<Carbon_Adjustor_R3<4, 0x829F4A28>>(dispatcher, 0x829F4A90);
  RegisterAdjustor<Carbon_Adjustor_R4<-8, 0x82A00BD8>>(dispatcher, 0x82A00CF0);
  RegisterAdjustor<Carbon_Adjustor_R3<-8, 0x82A00C10>>(dispatcher, 0x82A00CF8);
  RegisterAdjustor<Carbon_Adjustor_R3<-8, 0x82A01768>>(dispatcher, 0x82A00D00);
  RegisterAdjustor<Carbon_Adjustor_R3<-12, 0x82A01768>>(dispatcher, 0x82A00D10);
  RegisterAdjustor<Carbon_Adjustor_R3<-4, 0x82A13D18>>(dispatcher, 0x82A13D10);
  RegisterAdjustor<Carbon_Adjustor_R3<-8, 0x82A13D18>>(dispatcher, 0x82A13DB0);
  RegisterAdjustor<Carbon_Adjustor_R3<-4, 0x82A469C8>>(dispatcher, 0x82A469C0);
  RegisterAdjustor<Carbon_Adjustor_R3<-4, 0x82A584A8>>(dispatcher, 0x82A584D0);
  RegisterAdjustor<Carbon_Adjustor_R3<-4, 0x82A58460>>(dispatcher, 0x82A584D8);
  RegisterAdjustor<Carbon_Adjustor_R3<-4, 0x82A58B48>>(dispatcher, 0x82A58C00);
  RegisterAdjustor<Carbon_Adjustor_R3<-4, 0x82A59238>>(dispatcher, 0x82A59A88);
  RegisterAdjustor<Carbon_Adjustor_R3<-16, 0x82A634D8>>(dispatcher, 0x82A64218);
  RegisterAdjustor<Carbon_Adjustor_R3<-16, 0x82A63728>>(dispatcher, 0x82A64258);
  RegisterAdjustor<Carbon_Adjustor_R3<-16, 0x82A63218>>(dispatcher, 0x82A64270);
  RegisterAdjustor<Carbon_Adjustor_R3<-16, 0x82A63318>>(dispatcher, 0x82A64288);
  RegisterAdjustor<Carbon_Adjustor_R3<-16, 0x82A63260>>(dispatcher, 0x82A64298);
  RegisterAdjustor<Carbon_Adjustor_R3<-4, 0x82A631C8>>(dispatcher, 0x82A642A0);
  RegisterAdjustor<Carbon_Adjustor_R3<-16, 0x82A64398>>(dispatcher, 0x82A65708);
  RegisterAdjustor<Carbon_Adjustor_R3<-4, 0x82A664C8>>(dispatcher, 0x82A66B60);
  RegisterAdjustor<Carbon_Adjustor_R3<-16, 0x82A66548>>(dispatcher, 0x82A66B80);
  RegisterAdjustor<Carbon_Adjustor_R3<-16, 0x82A66608>>(dispatcher, 0x82A66B88);
  RegisterAdjustor<Carbon_Adjustor_R3<-4, 0x82A66530>>(dispatcher, 0x82A66BA0);
  RegisterAdjustor<Carbon_Adjustor_R3<-16, 0x82A66558>>(dispatcher, 0x82A66BA8);
  RegisterAdjustor<Carbon_Adjustor_R3<-16, 0x82A66570>>(dispatcher, 0x82A66BB0);
  RegisterAdjustor<Carbon_Adjustor_R3<-16, 0x82A666B0>>(dispatcher, 0x82A66BB8);
  RegisterAdjustor<Carbon_Adjustor_R3<-16, 0x82A66540>>(dispatcher, 0x82A66BD0);
  RegisterAdjustor<Carbon_Adjustor_R3<-16, 0x82A66580>>(dispatcher, 0x82A66BD8);
  RegisterAdjustor<Carbon_Adjustor_R3<-16, 0x82A66820>>(dispatcher, 0x82A66BE8);
  RegisterAdjustor<Carbon_Adjustor_R3<-16, 0x82A66660>>(dispatcher, 0x82A66C00);
}
