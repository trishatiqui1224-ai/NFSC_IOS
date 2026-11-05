#!/usr/bin/env python3
"""
Safeguard Career mode and Quick Race transitions:
1. sub_825F6A78 (nfscarbon_recomp.20.cpp): Prevents read of guest 0x00000000 across car/camera handoff.
2. sub_826D91C0 (nfscarbon_recomp.103.cpp): Prevents write to guest 0x00000000 when command buffer r3 is NULL.
3. sub_82131EA8 (nfscarbon_recomp.94.cpp): Prevents read of guest 0x00000000 when r3 or r11 is NULL.
"""

import pathlib
import sys

TARGET_20 = "generated/default/nfscarbon_recomp.20.cpp"
TARGET_103 = "generated/default/nfscarbon_recomp.103.cpp"
TARGET_94 = "generated/default/nfscarbon_recomp.94.cpp"
TARGET_136 = "generated/default/nfscarbon_recomp.136.cpp"
TARGET_140 = "generated/default/nfscarbon_recomp.140.cpp"
TARGET_19 = "generated/default/nfscarbon_recomp.19.cpp"
TARGET_PCH = "generated/default/nfscarbon_pch.h"

# Raw unpatched block in sub_825F6A78 (between 0x825F6B00 and 0x825F6B74)
OLD_CODE_20_RAW = """\t// lwz r11,24(r31)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r31.u32 + 24);
\t// lwz r21,0(r11)
\tctx.r21.u64 = REX_LOAD_U32(ctx.r11.u32 + 0);
\t// cmpwi cr6,r21,0
\tctx.cr6.compare<int32_t>(ctx.r21.s32, 0, ctx.xer);
\t// ble cr6,0x825f7788
\tif (!ctx.cr6.gt) goto loc_825F7788;
\t// lwz r11,0(r24)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r24.u32 + 0);
\t// addi r4,r1,96
\tctx.r4.s64 = ctx.r1.s64 + 96;
\t// lwz r11,52(r11)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r11.u32 + 52);
\t// mtctr r11
\tctx.ctr.u64 = ctx.r11.u64;
\t// bctrl 
\tctx.lr = 0x825F6B30;
\tREX_CALL_INDIRECT_FUNC(ctx.ctr.u32);
\t// lwz r11,0(r24)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r24.u32 + 0);
\t// mr r3,r24
\tctx.r3.u64 = ctx.r24.u64;
\t// lwz r11,36(r11)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r11.u32 + 36);
\t// mtctr r11
\tctx.ctr.u64 = ctx.r11.u64;
\t// bctrl 
\tctx.lr = 0x825F6B44;
\tREX_CALL_INDIRECT_FUNC(ctx.ctr.u32);
\t// mr r11,r3
\tctx.r11.u64 = ctx.r3.u64;
\t// lwz r10,0(r24)
\tctx.r10.u64 = REX_LOAD_U32(ctx.r24.u32 + 0);
\t// mr r3,r24
\tctx.r3.u64 = ctx.r24.u64;
\t// lwz r9,0(r11)
\tctx.r9.u64 = REX_LOAD_U32(ctx.r11.u32 + 0);
\t// lwz r10,32(r10)
\tctx.r10.u64 = REX_LOAD_U32(ctx.r10.u32 + 32);
\t// stw r9,112(r1)
\tREX_STORE_U32(ctx.r1.u32 + 112, ctx.r9.u32);
\t// lwz r9,4(r11)
\tctx.r9.u64 = REX_LOAD_U32(ctx.r11.u32 + 4);
\t// lwz r11,8(r11)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r11.u32 + 8);
\t// stw r9,116(r1)
\tREX_STORE_U32(ctx.r1.u32 + 116, ctx.r9.u32);
\t// stw r11,120(r1)
\tREX_STORE_U32(ctx.r1.u32 + 120, ctx.r11.u32);
\t// mtctr r10
\tctx.ctr.u64 = ctx.r10.u64;
\t// bctrl 
\tctx.lr = 0x825F6B74;
\tREX_CALL_INDIRECT_FUNC(ctx.ctr.u32);"""

# Partially patched block (from initial single-guard patch)
OLD_CODE_20_PARTIAL = OLD_CODE_20_RAW.replace(
    "\tctx.r11.u64 = REX_LOAD_U32(ctx.r31.u32 + 24);\n\t// lwz r21,0(r11)",
    "\tctx.r11.u64 = REX_LOAD_U32(ctx.r31.u32 + 24);\n\tif (!ctx.r11.u32) goto loc_825F7788;\n\t// lwz r21,0(r11)"
)

# Fully hardened block with null guards on r11, r24, r10, and r3
PATCHED_CODE_20 = """\t// lwz r11,24(r31)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r31.u32 + 24);
\tif (!ctx.r11.u32) goto loc_825F7788;
\t// lwz r21,0(r11)
\tctx.r21.u64 = REX_LOAD_U32(ctx.r11.u32 + 0);
\t// cmpwi cr6,r21,0
\tctx.cr6.compare<int32_t>(ctx.r21.s32, 0, ctx.xer);
\t// ble cr6,0x825f7788
\tif (!ctx.cr6.gt) goto loc_825F7788;
\t// lwz r11,0(r24)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r24.u32 + 0);
\tif (!ctx.r11.u32) goto loc_825F7788;
\t// addi r4,r1,96
\tctx.r4.s64 = ctx.r1.s64 + 96;
\t// lwz r11,52(r11)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r11.u32 + 52);
\t// mtctr r11
\tctx.ctr.u64 = ctx.r11.u64;
\t// bctrl 
\tctx.lr = 0x825F6B30;
\tREX_CALL_INDIRECT_FUNC(ctx.ctr.u32);
\t// lwz r11,0(r24)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r24.u32 + 0);
\tif (!ctx.r11.u32) goto loc_825F7788;
\t// mr r3,r24
\tctx.r3.u64 = ctx.r24.u64;
\t// lwz r11,36(r11)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r11.u32 + 36);
\t// mtctr r11
\tctx.ctr.u64 = ctx.r11.u64;
\t// bctrl 
\tctx.lr = 0x825F6B44;
\tREX_CALL_INDIRECT_FUNC(ctx.ctr.u32);
\t// mr r11,r3
\tctx.r11.u64 = ctx.r3.u64;
\tif (!ctx.r11.u32) goto loc_825F7788;
\t// lwz r10,0(r24)
\tctx.r10.u64 = REX_LOAD_U32(ctx.r24.u32 + 0);
\tif (!ctx.r10.u32) goto loc_825F7788;
\t// mr r3,r24
\tctx.r3.u64 = ctx.r24.u64;
\t// lwz r9,0(r11)
\tctx.r9.u64 = REX_LOAD_U32(ctx.r11.u32 + 0);
\t// lwz r10,32(r10)
\tctx.r10.u64 = REX_LOAD_U32(ctx.r10.u32 + 32);
\t// stw r9,112(r1)
\tREX_STORE_U32(ctx.r1.u32 + 112, ctx.r9.u32);
\t// lwz r9,4(r11)
\tctx.r9.u64 = REX_LOAD_U32(ctx.r11.u32 + 4);
\t// lwz r11,8(r11)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r11.u32 + 8);
\t// stw r9,116(r1)
\tREX_STORE_U32(ctx.r1.u32 + 116, ctx.r9.u32);
\t// stw r11,120(r1)
\tREX_STORE_U32(ctx.r1.u32 + 120, ctx.r11.u32);
\t// mtctr r10
\tctx.ctr.u64 = ctx.r10.u64;
\t// bctrl 
\tctx.lr = 0x825F6B74;
\tREX_CALL_INDIRECT_FUNC(ctx.ctr.u32);
\tif (!ctx.r3.u32) goto loc_825F7788;"""

# Minimal fallback anchor
OLD_CODE_20 = """\t// lwz r11,24(r31)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r31.u32 + 24);
\t// lwz r21,0(r11)"""

PATCHED_CODE_20_MINIMAL = """\t// lwz r11,24(r31)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r31.u32 + 24);
\tif (!ctx.r11.u32) goto loc_825F7788;
\t// lwz r21,0(r11)"""

OLD_CODE_103 = """\t// ld r11,80(r1)
\tctx.r11.u64 = REX_LOAD_U64(ctx.r1.u32 + 80);
\t// std r11,0(r3)
\tREX_STORE_U64(ctx.r3.u32 + 0, ctx.r11.u64);
\t// stw r10,13148(r31)
\tREX_STORE_U32(ctx.r31.u32 + 13148, ctx.r10.u32);"""

PATCHED_CODE_103 = """\t// ld r11,80(r1)
\tctx.r11.u64 = REX_LOAD_U64(ctx.r1.u32 + 80);
\tif (ctx.r3.u32 != 0) {
\t\t// std r11,0(r3)
\t\tREX_STORE_U64(ctx.r3.u32 + 0, ctx.r11.u64);
\t\t// stw r10,13148(r31)
\t\tREX_STORE_U32(ctx.r31.u32 + 13148, ctx.r10.u32);
\t}"""

OLD_CODE_94_A = """\t// addi r31,r11,1
\tctx.r31.s64 = ctx.r11.s64 + 1;
\t// lwz r11,0(r3)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r3.u32 + 0);
\t// addi r27,r10,18648
\tctx.r27.s64 = ctx.r10.s64 + 18648;
\t// cmplwi cr6,r28,0
\tctx.cr6.compare<uint32_t>(ctx.r28.u32, 0, ctx.xer);
\t// stw r11,80(r1)
\tREX_STORE_U32(ctx.r1.u32 + 80, ctx.r11.u32);
\t// lwz r11,4(r3)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r3.u32 + 4);
\t// lfs f30,-26632(r27)
\tctx.fpscr.disableFlushMode();
\ttemp.u32 = REX_LOAD_U32(ctx.r27.u32 + -26632);
\tctx.f30.f64 = double(temp.f32);
\t// fmr f31,f30
\tctx.f31.f64 = ctx.f30.f64;
\t// stw r11,84(r1)
\tREX_STORE_U32(ctx.r1.u32 + 84, ctx.r11.u32);
\t// lwz r11,8(r3)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r3.u32 + 8);
\t// stw r11,88(r1)
\tREX_STORE_U32(ctx.r1.u32 + 88, ctx.r11.u32);"""

PATCHED_CODE_94_A = """\t// addi r31,r11,1
\tctx.r31.s64 = ctx.r11.s64 + 1;
\t// addi r27,r10,18648
\tctx.r27.s64 = ctx.r10.s64 + 18648;
\t// cmplwi cr6,r28,0
\tctx.cr6.compare<uint32_t>(ctx.r28.u32, 0, ctx.xer);
\tif (ctx.r3.u32 != 0) {
\t\tctx.r11.u64 = REX_LOAD_U32(ctx.r3.u32 + 0);
\t\tREX_STORE_U32(ctx.r1.u32 + 80, ctx.r11.u32);
\t\tctx.r11.u64 = REX_LOAD_U32(ctx.r3.u32 + 4);
\t\tREX_STORE_U32(ctx.r1.u32 + 84, ctx.r11.u32);
\t\tctx.r11.u64 = REX_LOAD_U32(ctx.r3.u32 + 8);
\t\tREX_STORE_U32(ctx.r1.u32 + 88, ctx.r11.u32);
\t} else {
\t\tREX_STORE_U32(ctx.r1.u32 + 80, 0);
\t\tREX_STORE_U32(ctx.r1.u32 + 84, 0);
\t\tREX_STORE_U32(ctx.r1.u32 + 88, 0);
\t}
\t// lfs f30,-26632(r27)
\tctx.fpscr.disableFlushMode();
\ttemp.u32 = REX_LOAD_U32(ctx.r27.u32 + -26632);
\tctx.f30.f64 = double(temp.f32);
\t// fmr f31,f30
\tctx.f31.f64 = ctx.f30.f64;
\t// stw r11,84(r1)
\t// stw r11,88(r1)"""

OLD_CODE_94_B = """loc_82131F74:
\t// li r11,0
\tctx.r11.s64 = 0;
loc_82131F78:
\t// lwz r11,0(r11)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r11.u32 + 0);"""

PATCHED_CODE_94_B = """loc_82131F74:
\t// li r11,0
\tctx.r11.s64 = 0;
loc_82131F78:
\t// lwz r11,0(r11)
\tctx.r11.u64 = ctx.r11.u32 ? REX_LOAD_U32(ctx.r11.u32 + 0) : 0;"""



OLD_CODE_136 = """DEFINE_REX_FUNC(sub_82482B10) {
\tREX_FUNC_PROLOGUE();
\t// lwz r11,48(r3)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r3.u32 + 48);
\t// lwz r11,0(r11)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r11.u32 + 0);
\t// addi r3,r11,16
\tctx.r3.s64 = ctx.r11.s64 + 16;
\t// blr 
\treturn;
}"""

PATCHED_CODE_136 = """DEFINE_REX_FUNC(sub_82482B10) {
\tREX_FUNC_PROLOGUE();
\tif (ctx.r3.u32 < 0x1000) { ctx.r3.u64 = 0; return; }
\t// lwz r11,48(r3)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r3.u32 + 48);
\tif (!ctx.r11.u32) { ctx.r3.u64 = 0; return; }
\t// lwz r11,0(r11)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r11.u32 + 0);
\tif (!ctx.r11.u32) { ctx.r3.u64 = 0; return; }
\t// addi r3,r11,16
\tctx.r3.s64 = ctx.r11.s64 + 16;
\t// blr 
\treturn;
}"""

OLD_CODE_140 = """DEFINE_REX_FUNC(sub_82482B20) {
\tREX_FUNC_PROLOGUE();
\t// lwz r11,48(r3)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r3.u32 + 48);
\t// lwz r11,0(r11)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r11.u32 + 0);
\t// addi r3,r11,32
\tctx.r3.s64 = ctx.r11.s64 + 32;
\t// blr 
\treturn;
}"""

PATCHED_CODE_140 = """DEFINE_REX_FUNC(sub_82482B20) {
\tREX_FUNC_PROLOGUE();
\tif (ctx.r3.u32 < 0x1000) { ctx.r3.u64 = 0; return; }
\t// lwz r11,48(r3)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r3.u32 + 48);
\tif (!ctx.r11.u32) { ctx.r3.u64 = 0; return; }
\t// lwz r11,0(r11)
\tctx.r11.u64 = REX_LOAD_U32(ctx.r11.u32 + 0);
\tif (!ctx.r11.u32) { ctx.r3.u64 = 0; return; }
\t// addi r3,r11,32
\tctx.r3.s64 = ctx.r11.s64 + 32;
\t// blr 
\treturn;
}"""

OLD_CODE_19_A = """\t// bctrl 
\tctx.lr = 0x82137814;
\tREX_CALL_INDIRECT_FUNC(ctx.ctr.u32);
\t// lis r11,-32250"""

PATCHED_CODE_19_A = """\t// bctrl 
\tctx.lr = 0x82137814;
\tREX_CALL_INDIRECT_FUNC(ctx.ctr.u32);
\tif (!ctx.r3.u32 || !ctx.r29.u32) goto loc_82137914;
\t// lis r11,-32250"""

OLD_CODE_19_B = """\t// bctrl 
\tctx.lr = 0x821378D4;
\tREX_CALL_INDIRECT_FUNC(ctx.ctr.u32);
\t// mr r11,r3
\tctx.r11.u64 = ctx.r3.u64;
\t// addi r4,r30,160"""

PATCHED_CODE_19_B = """\t// bctrl 
\tctx.lr = 0x821378D4;
\tREX_CALL_INDIRECT_FUNC(ctx.ctr.u32);
\t// mr r11,r3
\tctx.r11.u64 = ctx.r3.u64;
\tif (!ctx.r11.u32) goto loc_82137914;
\t// addi r4,r30,160"""

OLD_CODE_PCH_DECL = """#define REX_LOOKUP_FUNC(x, y) \\"""

PATCHED_CODE_PCH_DECL = """#if defined(__APPLE__)
namespace nfsmw::boot { void SetLastPPCBreadcrumb(uint32_t fn_addr, uint32_t lr, uint32_t r3); }
#define REX_RECORD_PPC_BREADCRUMB(tgt, lr, r3) nfsmw::boot::SetLastPPCBreadcrumb(tgt, lr, r3)
#else
#define REX_RECORD_PPC_BREADCRUMB(tgt, lr, r3) do {} while(0)
#endif

#define REX_LOOKUP_FUNC(x, y) \\"""

OLD_CODE_PCH = """    if (!rex_indirect_func_) [[unlikely]] {                                                \\
      ctx.last_indirect_target = rex_indirect_target_;                                     \\
      rex_indirect_func_ = rex::runtime::ResolveIndirectFunction(rex_indirect_target_);    \\
    }                                                                                      \\
    rex_indirect_func_(ctx, base);                                                         \\
  } while (0)"""

PATCHED_CODE_PCH = """    if (!rex_indirect_func_) [[unlikely]] {                                                \\
      ctx.last_indirect_target = rex_indirect_target_;                                     \\
      rex_indirect_func_ = rex::runtime::ResolveIndirectFunction(rex_indirect_target_);    \\
    }                                                                                      \\
    REX_RECORD_PPC_BREADCRUMB(rex_indirect_target_, ctx.lr, ctx.r3.u32);                   \\
    rex_indirect_func_(ctx, base);                                                         \\
  } while (0)"""

def apply_patch(root_dir: pathlib.Path) -> bool:
    success = True
    # 1. Patch recomp.20 (Career cutscene)
    target_20 = root_dir / TARGET_20
    if target_20.is_file():
        text_20 = target_20.read_text(encoding="utf-8")
        if "if (!ctx.r3.u32) goto loc_825F7788;" in text_20 and "sub_825F6A78" in text_20:
            print("[patch_career_null_check] Already fully applied in nfscarbon_recomp.20.cpp")
        elif OLD_CODE_20_PARTIAL in text_20:
            text_20 = text_20.replace(OLD_CODE_20_PARTIAL, PATCHED_CODE_20, 1)
            target_20.write_text(text_20, encoding="utf-8")
            print("[patch_career_null_check] Successfully applied hardened null-checks in sub_825F6A78")
        elif OLD_CODE_20_RAW in text_20:
            text_20 = text_20.replace(OLD_CODE_20_RAW, PATCHED_CODE_20, 1)
            target_20.write_text(text_20, encoding="utf-8")
            print("[patch_career_null_check] Successfully applied hardened null-checks in sub_825F6A78")
        elif OLD_CODE_20 in text_20:
            text_20 = text_20.replace(OLD_CODE_20, PATCHED_CODE_20_MINIMAL, 1)
            target_20.write_text(text_20, encoding="utf-8")
            print("[patch_career_null_check] Applied minimal null-check in sub_825F6A78")
        else:
            print("[patch_career_null_check] WARNING: Anchor not found in nfscarbon_recomp.20.cpp")
            success = False

    # 2. Patch recomp.103 (D3D command packet buffer write)
    target_103 = root_dir / TARGET_103
    if target_103.is_file():
        text_103 = target_103.read_text(encoding="utf-8")
        if "if (ctx.r3.u32 != 0) {" in text_103 and "sub_826D91C0" in text_103:
            print("[patch_career_null_check] Already applied in nfscarbon_recomp.103.cpp")
        elif OLD_CODE_103 in text_103:
            text_103 = text_103.replace(OLD_CODE_103, PATCHED_CODE_103, 1)
            target_103.write_text(text_103, encoding="utf-8")
            print("[patch_career_null_check] Successfully applied null-check in sub_826D91C0")
        else:
            print("[patch_career_null_check] WARNING: Anchor not found in nfscarbon_recomp.103.cpp")
            success = False

    # 3. Patch recomp.94 (D3D caller sub_82131EA8)
    target_94 = root_dir / TARGET_94
    if target_94.is_file():
        text_94 = target_94.read_text(encoding="utf-8")
        patched_any = False
        if "if (ctx.r3.u32 != 0) {" in text_94 and "sub_82131EA8" in text_94:
            print("[patch_career_null_check] Already applied (part A) in nfscarbon_recomp.94.cpp")
        elif OLD_CODE_94_A in text_94:
            text_94 = text_94.replace(OLD_CODE_94_A, PATCHED_CODE_94_A, 1)
            patched_any = True
            print("[patch_career_null_check] Successfully applied null-check (part A) in sub_82131EA8")
        else:
            print("[patch_career_null_check] WARNING: Anchor A not found in nfscarbon_recomp.94.cpp")
            success = False

        if "ctx.r11.u32 ? REX_LOAD_U32(ctx.r11.u32 + 0) : 0;" in text_94:
            print("[patch_career_null_check] Already applied (part B) in nfscarbon_recomp.94.cpp")
        elif OLD_CODE_94_B in text_94:
            text_94 = text_94.replace(OLD_CODE_94_B, PATCHED_CODE_94_B, 1)
            patched_any = True
            print("[patch_career_null_check] Successfully applied null-check (part B) in sub_82131EA8")
        else:
            print("[patch_career_null_check] WARNING: Anchor B not found in nfscarbon_recomp.94.cpp")
            success = False

        if patched_any:
            target_94.write_text(text_94, encoding="utf-8")

    
    # 4. Patch recomp.136 (sub_82482B10 Position getter)
    target_136 = root_dir / TARGET_136
    if target_136.is_file():
        text_136 = target_136.read_text(encoding="utf-8")
        if "if (ctx.r3.u32 < 0x1000)" in text_136 and "sub_82482B10" in text_136:
            print("[patch_career_null_check] Already applied in nfscarbon_recomp.136.cpp")
        elif OLD_CODE_136 in text_136:
            text_136 = text_136.replace(OLD_CODE_136, PATCHED_CODE_136, 1)
            target_136.write_text(text_136, encoding="utf-8")
            print("[patch_career_null_check] Successfully applied null-check in sub_82482B10")
        else:
            print("[patch_career_null_check] WARNING: Anchor not found in nfscarbon_recomp.136.cpp")
            success = False

    # 5. Patch recomp.140 (sub_82482B20 Velocity getter)
    target_140 = root_dir / TARGET_140
    if target_140.is_file():
        text_140 = target_140.read_text(encoding="utf-8")
        if "if (ctx.r3.u32 < 0x1000)" in text_140 and "sub_82482B20" in text_140:
            print("[patch_career_null_check] Already applied in nfscarbon_recomp.140.cpp")
        elif OLD_CODE_140 in text_140:
            text_140 = text_140.replace(OLD_CODE_140, PATCHED_CODE_140, 1)
            target_140.write_text(text_140, encoding="utf-8")
            print("[patch_career_null_check] Successfully applied null-check in sub_82482B20")
        else:
            print("[patch_career_null_check] WARNING: Anchor not found in nfscarbon_recomp.140.cpp")
            success = False

    # 6. Patch recomp.19 (sub_821377B0 AI Navigation/Steering calculation)
    target_19 = root_dir / TARGET_19
    if target_19.is_file():
        text_19 = target_19.read_text(encoding="utf-8")
        patched_19 = False
        if "if (!ctx.r3.u32 || !ctx.r29.u32) goto loc_82137914;" in text_19:
            print("[patch_career_null_check] Already applied (part A) in nfscarbon_recomp.19.cpp")
        elif OLD_CODE_19_A in text_19:
            text_19 = text_19.replace(OLD_CODE_19_A, PATCHED_CODE_19_A, 1)
            patched_19 = True
            print("[patch_career_null_check] Successfully applied null-check (part A) in sub_821377B0")
        else:
            print("[patch_career_null_check] WARNING: Anchor A not found in nfscarbon_recomp.19.cpp")
            success = False

        if "if (!ctx.r11.u32) goto loc_82137914;" in text_19:
            print("[patch_career_null_check] Already applied (part B) in nfscarbon_recomp.19.cpp")
        elif OLD_CODE_19_B in text_19:
            text_19 = text_19.replace(OLD_CODE_19_B, PATCHED_CODE_19_B, 1)
            patched_19 = True
            print("[patch_career_null_check] Successfully applied null-check (part B) in sub_821377B0")
        else:
            print("[patch_career_null_check] WARNING: Anchor B not found in nfscarbon_recomp.19.cpp")
            success = False

        if patched_19:
            target_19.write_text(text_19, encoding="utf-8")

    # 7. Patch nfscarbon_pch.h (REX_CALL_INDIRECT_FUNC Breadcrumb hook)
    target_pch = root_dir / TARGET_PCH
    if target_pch.is_file():
        text_pch = target_pch.read_text(encoding="utf-8")
        patched_pch = False
        if "REX_RECORD_PPC_BREADCRUMB" in text_pch:
            print("[patch_career_null_check] Already applied in nfscarbon_pch.h")
        else:
            if OLD_CODE_PCH_DECL in text_pch:
                text_pch = text_pch.replace(OLD_CODE_PCH_DECL, PATCHED_CODE_PCH_DECL, 1)
                patched_pch = True
            if OLD_CODE_PCH in text_pch:
                text_pch = text_pch.replace(OLD_CODE_PCH, PATCHED_CODE_PCH, 1)
                patched_pch = True
            if patched_pch:
                target_pch.write_text(text_pch, encoding="utf-8")
                print("[patch_career_null_check] Successfully applied breadcrumb hook in nfscarbon_pch.h")
            else:
                print("[patch_career_null_check] WARNING: Anchor not found in nfscarbon_pch.h")
                success = False

    return success


if __name__ == "__main__":
    root = pathlib.Path(__file__).resolve().parents[2]
    ok = apply_patch(root)
    sys.exit(0 if ok else 1)
