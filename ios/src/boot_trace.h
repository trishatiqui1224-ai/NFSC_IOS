// NFSMW Recompiled - startup trace on iOS (see boot_trace.cpp)

#pragma once

#include <string>
#include <cstdint>

namespace nfsmw::boot {

// Opens (appends to) the trace file and installs the crash hooks. Call first.
void Open(const std::string& path);

// Registers the main log file (nfscarbon.log) so crash dumps are written to both files.
void SetLogFilePath(const std::string& path);

// One line, written and handed to the kernel at once: it survives a crash or
// a hang right after it.
void Trace(const std::string& line);

// Off: Trace writes nothing more (the launcher's Logging switch).
void SetEnabled(bool enabled);

// Allocate and register a 64 KB alternate signal stack via sigaltstack()
void SetupAltStack();

// Thread-local PPC execution breadcrumb for crash reporting
void SetLastPPCBreadcrumb(uint32_t fn_addr, uint32_t lr, uint32_t r3);

// Returns formatted ring buffer of last 16 PPC breadcrumbs
size_t FormatLastPPCBreadcrumbs(char* buf, size_t buf_size);

}  // namespace nfsmw::boot

extern "C" {
size_t CarbonFormatLastPPCBreadcrumbs(char* buf, size_t buf_size);
}
