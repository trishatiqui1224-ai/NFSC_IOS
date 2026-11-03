#!/usr/bin/env python3
"""
tools/build_usa_codegen.py
Automated PowerPC-to-C++ AOT Code Generation & Unresolved Branch Resolver Pipeline
for Need for Speed: Carbon (USA) (Title ID: 454107EC).

Key Responsibilities:
1. Ground Truth Validation:
   - Unpacks USA default.xex PE image and parses .pdata exception table ranges [start, end).
   - Validates that NO candidate function in nfscarbon_manifest.toml strictly splits any .pdata function
     range (fn_start < candidate < fn_end). Purges all PAL addresses (e.g. 0x824E9780, 0x824FFAB0, etc.).
2. Executes ReXGlue AOT Codegen.
3. Automated Post-Codegen Resolver Loop:
   - Scans generated/default/*.cpp for 'Unresolved branch from 0x... to 0x...'.
   - Resolves splits (backward branches sliced by artificial functions) by removing bogus entries.
   - Resolves external tail-calls by adding genuine target functions to manifest.
   - Iterates up to 3 passes until 0 unresolved branches remain.
4. Hard Assertion:
   - Verifies 0 unresolved branches and all required USA symbols (0x829446E0, 0x824E98B0, etc.) present.
"""

import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = REPO_ROOT.parent.parent

# Known XEX candidate locations
XEX_CANDIDATES = [
    REPO_ROOT / "game" / "default.xex",
    REPO_ROOT / "xex" / "usa_default.xex",
    PROJECT_ROOT / "Need for Speed - Carbon (USA) (En,Es)" / "default.xex",
    PROJECT_ROOT / "nfs-carbon-workspace" / "nfsc-ios" / "xex" / "usa_default.xex",
    PROJECT_ROOT / "nfs-carbon-workspace" / "nfsc-ios" / "game" / "default.xex",
]

# Known ReXGlue binary locations
REXGLUE_CANDIDATES = [
    pathlib.Path(r"E:\Project\NFS Carbon Switch\nfsc-nx\reference\nfsmw-nx\sdk\out\win-amd64\rexglue.exe"),
    REPO_ROOT / "tools" / "rexglue.exe",
    REPO_ROOT / "tools" / "rexglue",
    PROJECT_ROOT / "rexglue-sdk-ios" / "out" / "rexglue",
]

# Required USA symbols that must be present in the final register.cpp
REQUIRED_USA_SYMBOLS = [
    (0x829446E0, "sub_829446E0", "XEX entry point (USA genuine xstart, 0x829446E0..0x829448A0)"),
    (0x82944510, "sub_82944510", "USA display/privilege check function (0x82944510..0x829446D8)"),
    (0x824E98B0, "sub_824E98B0", "Carbon USA main() (0x824E98B0..0x824E9948)"),
    (0x824FFBE0, "sub_824FFBE0", "USA renderer constructor helper (0x824FFBE0..0x82500228)"),
    (0x82500298, "sub_82500298", "USA render output size hook (leaf function)"),
    (0x8250B200, "sub_8250B200", "USA render mode select hook (0x8250B200..0x8250B348)"),
    (0x826E0088, "sub_826E0088", "USA D3D ring wait watchdog (leaf thunk)"),
    (0x823217D0, "sub_823217D0", "USA direct branch entrypoint (0x823217D0..0x82321850)"),
    (0x82A63408, "sub_82A63408", "USA direct branch entrypoint (0x82A63408..0x82A63574)"),
    (0x82A66790, "sub_82A66790", "USA direct branch entrypoint (0x82A66790..0x82A668D8)"),
    (0x824DA968, "sub_824DA968", "USA Frontend init callback (0x824DA968)"),
    (0x825BF728, "sub_825BF728", "USA Car Selection / Quick Race callback (0x825BF728)"),
    (0x821A3EC8, "sub_821A3EC8", "USA flasher/callback method called from 0x82690F0C (0x821A3EC8..0x821A3ED0)"),
]

# Forbidden PAL-only symbols that must NEVER appear as function starts
FORBIDDEN_PAL_SYMBOLS = [
    (0x824E9780, "PAL main() - slices USA function 0x824E9720..0x824E9888"),
    (0x824FFAB0, "PAL renderer ctor - slices USA function 0x824FF858..0x824FFAD4"),
    (0x82500168, "PAL renderer size - slices USA function 0x824FFBE0..0x82500228"),
    (0x8250B0D0, "PAL renderer select - slices USA function 0x8250B028..0x8250B174"),
    (0x822A9490, "PAL story entry - slices USA function 0x822A9410..0x822A94D0"),
    (0x82641480, "PAL adjustor thunk - slices USA function 0x82641240..0x826414AC"),
    (0x82322048, "PAL vtable dispatch"),
    (0x82296468, "PAL state entry"),
]


def find_xex() -> pathlib.Path:
    for c in XEX_CANDIDATES:
        if c.is_file() and c.stat().st_size > 4_000_000:
            return c
    raise FileNotFoundError("Could not locate USA default.xex in known project locations.")


def find_rexglue(custom_path: str = None) -> pathlib.Path:
    if custom_path:
        p = pathlib.Path(custom_path).resolve()
        if p.is_file():
            return p
        raise FileNotFoundError(f"Custom rexglue not found at {custom_path}")

    # Check PATH
    which_rex = shutil.which("rexglue") or shutil.which("rexglue.exe")
    if which_rex:
        return pathlib.Path(which_rex).resolve()

    for c in REXGLUE_CANDIDATES:
        if c.is_file():
            return c.resolve()

    raise FileNotFoundError("Could not find rexglue executable. Please pass --rexglue.")


def stage_xex(src_xex: pathlib.Path, target_xex: pathlib.Path):
    target_xex.parent.mkdir(parents=True, exist_ok=True)
    if not target_xex.is_file() or target_xex.stat().st_size != src_xex.stat().st_size:
        print(f"[build_usa_codegen] Staging XEX: {src_xex} -> {target_xex}")
        shutil.copy2(str(src_xex), str(target_xex))
    else:
        print(f"[build_usa_codegen] XEX already staged at: {target_xex}")


def load_pdata_functions(xex_path: pathlib.Path) -> list[tuple[int, int]]:
    sys.path.insert(0, str(SCRIPT_DIR))
    from xex_image import load_xex_image
    print(f"[build_usa_codegen] Unpacking PE image and extracting .pdata from {xex_path.name}...")
    _, pdata = load_xex_image(str(xex_path))
    print(f"[build_usa_codegen] Loaded {len(pdata):,} ground-truth .pdata functions.")
    return pdata


def scan_code_referenced_functions(xex_path: pathlib.Path, pdata: list[tuple[int, int]]) -> list[int]:
    """Scans USA default.xex PE image for:
    1. lis + addi/ori address formation pairs resolving to code addresses in [0x82110000, 0x82B35C64).
    2. Filters candidates: 4-byte aligned, outside .pdata function interiors, and preceded by a
       control transfer barrier (b, blr, bctr, nop/zero padding) or having a function prologue (mflr r0, stwu r1).
    """
    import struct
    from xex_image import load_xex_image, secciones

    base = 0x82000000
    img, _ = load_xex_image(str(xex_path))
    secs = secciones(img)

    code_ranges = [(s, e) for name, s, e in secs if name in ['.text', '.embsec_']]
    candidates = set()

    for c_start, c_end in code_ranges:
        for pc in range(c_start, c_end - 4, 4):
            inst = struct.unpack_from('>I', img, pc - base)[0]
            op = inst >> 26
            if op == 15:  # lis rD, simm
                rd = (inst >> 21) & 0x1F
                simm = inst & 0xFFFF
                high_val = (simm << 16)
                for step in range(1, 9):
                    look_pc = pc + step * 4
                    if look_pc >= c_end:
                        break
                    look_inst = struct.unpack_from('>I', img, look_pc - base)[0]
                    look_op = look_inst >> 26
                    if look_op in [16, 18]:
                        if look_op == 18 and (look_inst & 1) == 0:
                            break
                    if look_op == 19 and (look_inst & 0x7FE) in [32, 1056]:
                        break

                    if look_op == 14:  # addi rD, rA, simm
                        look_ra = (look_inst >> 16) & 0x1F
                        if look_ra == rd:
                            look_simm = look_inst & 0xFFFF
                            if look_simm >= 0x8000:
                                look_simm -= 0x10000
                            addr = (high_val + look_simm) & 0xFFFFFFFF
                            if 0x82110000 <= addr < 0x82B35C64 and (addr % 4) == 0:
                                candidates.add(addr)
                            look_rd = (look_inst >> 21) & 0x1F
                            if look_rd == rd:
                                break
                    elif look_op == 24:  # ori rA, rS, uimm
                        look_rs = (look_inst >> 21) & 0x1F
                        if look_rs == rd:
                            uimm = look_inst & 0xFFFF
                            addr = (high_val | uimm) & 0xFFFFFFFF
                            if 0x82110000 <= addr < 0x82B35C64 and (addr % 4) == 0:
                                candidates.add(addr)
                            look_ra = (look_inst >> 16) & 0x1F
                            if look_ra == rd:
                                break

    # Filter out any candidate that strictly splits an existing .pdata function range
    valid = []
    for c in sorted(candidates):
        if any(s < c < e for s, e in pdata):
            continue  # strictly inside [start, end)
        if any(s == c for s, _ in pdata):
            continue  # already known in .pdata

        offset = c - base
        if offset < 4 or offset >= len(img) - 8:
            continue
        prev_inst = struct.unpack_from('>I', img, offset - 4)[0]
        inst0 = struct.unpack_from('>I', img, offset)[0]

        is_prev_barrier = (
            (prev_inst & 0xFC000003) == 0x48000000 or
            prev_inst == 0x4E800020 or
            (prev_inst & 0xFC0007FE) == 0x4C000420 or
            prev_inst in [0x00000000, 0x60000000]
        )
        is_prologue = (
            inst0 == 0x7C0802A6 or
            (inst0 & 0xFFFF0000) == 0x94210000
        )
        if is_prev_barrier or is_prologue:
            valid.append(c)

    # Also scan .rdata and .data sections for 32-bit aligned function pointers (e.g. vtables, callback tables)
    import bisect
    pdata_starts = [s for s, e in pdata]
    pdata_ends = [e for s, e in pdata]
    rdata_candidates = set()
    data_ranges = [(s, e) for name, s, e in secs if name in ['.rdata', '.data']]
    for d_start, d_end in data_ranges:
        for ptr_addr in range(d_start, d_end - 4, 4):
            val = struct.unpack_from('>I', img, ptr_addr - base)[0]
            if 0x82110000 <= val < 0x82B35C64 and (val % 4) == 0:
                # Check that val is not strictly inside any [start, end)
                idx = bisect.bisect_right(pdata_starts, val)
                if idx > 0 and val < pdata_ends[idx - 1]:
                    continue
                if idx < len(pdata_starts) and val == pdata_starts[idx]:
                    continue
                rdata_candidates.add(val)

    # Validate each candidate has a barrier or prologue
    for c in sorted(rdata_candidates):
        offset = c - base
        if offset < 4 or offset >= len(img) - 8:
            continue
        prev_inst = struct.unpack_from('>I', img, offset - 4)[0]
        inst0 = struct.unpack_from('>I', img, offset)[0]
        is_prev_barrier = (
            (prev_inst & 0xFC000003) == 0x48000000 or
            prev_inst == 0x4E800020 or
            (prev_inst & 0xFC0007FE) == 0x4C000420 or
            prev_inst in [0x00000000, 0x60000000]
        )
        is_prologue = (
            inst0 == 0x7C0802A6 or
            (inst0 & 0xFFFF0000) == 0x94210000 or
            (inst0 & 0xFFFF0000) == 0x7C830000  # mr r3, r4
        )
        if is_prev_barrier or is_prologue:
            if c not in valid:
                valid.append(c)

    print(f"[build_usa_codegen] Code + data scan discovered {len(valid)} candidate non-pdata leaf functions.")
    return valid


def parse_manifest_functions(manifest_path: pathlib.Path) -> list[int]:
    if not manifest_path.is_file():
        return []
    content = manifest_path.read_text(encoding="utf-8")
    in_funcs = False
    funcs = []
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("[entrypoint.functions]"):
            in_funcs = True
            continue
        if in_funcs:
            if line.startswith("["):
                break
            m = re.match(r'^(0x[0-9A-Fa-f]{8})\s*=', line)
            if m:
                funcs.append(int(m.group(1), 16))
    return funcs


def clean_manifest(manifest_path: pathlib.Path, pdata: list[tuple[int, int]],
                   add_entries: list[int] = None, remove_entries: set[int] = None) -> list[int]:
    """Ensures manifest has no PAL/split addresses, has all required USA addresses, and writes back."""
    current_funcs = set(parse_manifest_functions(manifest_path))

    # Add required USA symbols
    for addr, _, _ in REQUIRED_USA_SYMBOLS:
        current_funcs.add(addr)
    if add_entries:
        for addr in add_entries:
            current_funcs.add(addr)

    # Purge forbidden PAL symbols
    forbidden_addrs = {addr for addr, _ in FORBIDDEN_PAL_SYMBOLS}
    if remove_entries:
        forbidden_addrs.update(remove_entries)

    # Filter out strict splits in .pdata (fn_start < candidate < fn_end)
    cleaned = []
    purged_splits = []
    for addr in current_funcs:
        if addr in forbidden_addrs:
            purged_splits.append((addr, "forbidden/marked for removal"))
            continue
        # Check if strictly inside a .pdata range
        split_match = [p for p in pdata if p[0] < addr < p[1]]
        if split_match:
            purged_splits.append((addr, f"strictly inside [0x{split_match[0][0]:08X}, 0x{split_match[0][1]:08X})"))
            continue
        cleaned.append(addr)

    cleaned.sort()

    print(f"[build_usa_codegen] Manifest sanitization: {len(purged_splits)} invalid/split functions purged:")
    for a, reason in purged_splits:
        print(f"  - Purged 0x{a:08X} ({reason})")

    # Re-write manifest
    lines = [
        "# Generated by ReXGlue - USA default.xex ahead-of-time codegen manifest",
        "# All addresses verified against USA default.xex .pdata exception table.",
        "",
        "[project]",
        'name = "nfscarbon"',
        'sdk_version = "1.0.0"',
        'game_root = "game"',
        "",
        "[entrypoint]",
        'file_path = "game/default.xex"',
        'out_directory_path = "generated/default"',
        "includes = []",
        "",
        "[entrypoint.functions]",
    ]
    for addr in cleaned:
        # Check if known symbol for documentation comment
        comment = ""
        for req_addr, sym, desc in REQUIRED_USA_SYMBOLS:
            if req_addr == addr:
                comment = f"  # {desc}"
                break
        lines.append(f"0x{addr:08X} = {{}}{comment}")

    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[build_usa_codegen] Wrote {len(cleaned)} verified entries to {manifest_path.name}")
    return cleaned


def scan_unresolved_branches(gen_dir: pathlib.Path) -> list[tuple[int, int, pathlib.Path, int]]:
    """Scans all generated C++ files for 'Unresolved branch from 0x... to 0x...'."""
    pattern = re.compile(r'Unresolved branch from 0x([0-9A-Fa-f]+) to 0x([0-9A-Fa-f]+)')
    unresolved = []
    cpp_files = list(gen_dir.glob("*.cpp"))
    for f in cpp_files:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for line_idx, line in enumerate(content.splitlines(), 1):
            for m in pattern.finditer(line):
                src = int(m.group(1), 16)
                dst = int(m.group(2), 16)
                unresolved.append((src, dst, f, line_idx))
    return unresolved


def run_codegen(rexglue_bin: pathlib.Path, manifest_path: pathlib.Path, cwd: pathlib.Path):
    cmd = [str(rexglue_bin), "codegen", str(manifest_path), "--ignore-stamp"]
    print(f"[build_usa_codegen] Running: {' '.join(cmd)} (cwd={cwd})")
    res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[build_usa_codegen] ERROR: codegen exited with code {res.returncode}")
        print(res.stdout[-2000:])
        print(res.stderr[-2000:])
        raise RuntimeError("rexglue codegen failed")
    print("[build_usa_codegen] Codegen completed successfully.")


def resolver_loop(rexglue_bin: pathlib.Path, manifest_path: pathlib.Path,
                  gen_dir: pathlib.Path, pdata: list[tuple[int, int]],
                  cwd: pathlib.Path, initial_add: list[int] = None, max_passes: int = 3):
    """Iteratively runs codegen, scans for unresolved branches, and resolves them."""
    remove_set = set()
    add_set = list(initial_add) if initial_add else []

    for pass_num in range(1, max_passes + 1):
        print(f"\n============================================================")
        print(f"  [Codegen Pass {pass_num}/{max_passes}]")
        print(f"============================================================")
        clean_manifest(manifest_path, pdata, add_entries=add_set, remove_entries=remove_set)
        run_codegen(rexglue_bin, manifest_path, cwd)

        unresolved = scan_unresolved_branches(gen_dir)
        print(f"[build_usa_codegen] Scan found {len(unresolved)} unresolved branch(es) in generated C++.")

        if not unresolved:
            print("[build_usa_codegen] SUCCESS: ZERO (0) unresolved branches detected!")
            break

        print("[build_usa_codegen] Analyzing unresolved branches:")
        remove_set.clear()
        add_set.clear()

        manifest_funcs = set(parse_manifest_functions(manifest_path))

        for src, dst, file_path, line_no in unresolved:
            print(f"  - 0x{src:08X} -> 0x{dst:08X} in {file_path.name}:{line_no}")
            if dst < src:
                # Backward branch (likely a loop). Check if an artificial function split exists in (dst, src]
                splits_in_loop = [f for f in manifest_funcs if dst < f <= src]
                if splits_in_loop:
                    for s in splits_in_loop:
                        print(f"    -> Loop cut by artificial function 0x{s:08X}. Removing from manifest.")
                        remove_set.add(s)
                else:
                    # Target might be unmapped function start
                    print(f"    -> Backward target 0x{dst:08X} not recognized as start. Adding to manifest.")
                    add_set.append(dst)
            else:
                # Forward branch / tail-call to unmapped external function
                print(f"    -> Forward tail-call to unmapped 0x{dst:08X}. Adding to manifest.")
                add_set.append(dst)

        if not remove_set and not add_set:
            print("[build_usa_codegen] Warning: Could not deduce automatic fixes for remaining branches.")
            break

    # Final assertion
    final_unresolved = scan_unresolved_branches(gen_dir)
    if final_unresolved:
        print(f"\n[build_usa_codegen] FATAL: {len(final_unresolved)} unresolved branches remain after {max_passes} passes:")
        for src, dst, file_path, line_no in final_unresolved:
            print(f"  FAILED: 0x{src:08X} -> 0x{dst:08X} ({file_path.name}:{line_no})")
        sys.exit(1)

    print("\n[build_usa_codegen] ALL UNRESOLVED BRANCHES ELIMINATED SUCCESSFULLY!")


def verify_register(gen_dir: pathlib.Path):
    """Verifies that required USA symbols are registered and PAL symbols are absent."""
    reg_file = gen_dir / "nfscarbon_register.cpp"
    if not reg_file.is_file():
        reg_file = gen_dir / "nfsc_register.cpp"
    if not reg_file.is_file():
        print(f"[build_usa_codegen] WARNING: register file not found in {gen_dir}")
        return

    content = reg_file.read_text(encoding="utf-8", errors="replace")
    failures = []
    for addr, sym, desc in REQUIRED_USA_SYMBOLS:
        hex_str = f"0x{addr:08X}"
        if hex_str.lower() not in content.lower() and sym not in content:
            failures.append(f"Missing required USA symbol: {hex_str} ({sym}) - {desc}")

    for addr, desc in FORBIDDEN_PAL_SYMBOLS:
        hex_str = f"0x{addr:08X}"
        if hex_str.lower() in content.lower():
            failures.append(f"Found forbidden PAL symbol: {hex_str} - {desc}")

    if failures:
        print("[build_usa_codegen] Register verification failed:")
        for f in failures:
            print(f"  [ERROR] {f}")
        sys.exit(1)
    else:
        print("[build_usa_codegen] Register verification PASSED! All USA symbols present, all PAL symbols absent.")


def main():
    parser = argparse.ArgumentParser(description="USA AOT Code Generator & Unresolved Branch Resolver")
    parser.add_argument("--xex", help="Path to USA default.xex")
    parser.add_argument("--rexglue", help="Path to rexglue binary")
    parser.add_argument("--manifest", help="Path to nfscarbon_manifest.toml")
    parser.add_argument("--passes", type=int, default=3, help="Max resolver loop passes")
    args = parser.parse_args()

    xex_src = pathlib.Path(args.xex).resolve() if args.xex else find_xex()
    rexglue_bin = find_rexglue(args.rexglue)
    manifest_path = pathlib.Path(args.manifest).resolve() if args.manifest else (REPO_ROOT / "nfscarbon_manifest.toml")
    staged_xex = REPO_ROOT / "game" / "default.xex"
    gen_dir = REPO_ROOT / "generated" / "default"

    print("============================================================")
    print("  NFS Carbon USA AOT Codegen & Resolver Pipeline")
    print(f"  Source XEX:  {xex_src}")
    print(f"  Staged XEX:  {staged_xex}")
    print(f"  Manifest:    {manifest_path}")
    print(f"  ReXGlue:     {rexglue_bin}")
    print(f"  Output Dir:  {gen_dir}")
    print("============================================================")

    # 1. Stage USA XEX
    stage_xex(xex_src, staged_xex)

    # 2. Extract .pdata functions from USA XEX
    pdata = load_pdata_functions(staged_xex)

    # 3. Discover unmapped code-referenced callbacks
    discovered = scan_code_referenced_functions(staged_xex, pdata)

    # 4. Execute Resolver Loop (Sanitize Manifest -> Codegen -> Scan -> Resolve -> Loop)
    resolver_loop(
        rexglue_bin=rexglue_bin,
        manifest_path=manifest_path,
        gen_dir=gen_dir,
        pdata=pdata,
        cwd=REPO_ROOT,
        initial_add=discovered,
        max_passes=args.passes
    )

    # 5. Final verification of register.cpp
    verify_register(gen_dir)
    print("\n[build_usa_codegen] PIPELINE COMPLETED SUCCESSFULLY.")


if __name__ == "__main__":
    main()

