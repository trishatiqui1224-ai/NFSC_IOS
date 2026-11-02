cmake_minimum_required(VERSION 3.25)

# Objective-C languages are only available on Apple platforms.
# On Windows/Linux we skip them so the non-iOS desktop build configures cleanly.
if(APPLE)
    project(nfscarbon LANGUAGES C CXX OBJC OBJCXX ASM)
else()
    project(nfscarbon LANGUAGES C CXX ASM)
endif()

if(IOS OR CMAKE_SYSTEM_NAME STREQUAL "iOS")
    add_subdirectory(ios)
else()
    set(CMAKE_CXX_STANDARD 23)
    set(CMAKE_CXX_STANDARD_REQUIRED ON)

    # Pull in the ReXGlue SDK and generated code (sets up rex::runtime, include dirs,
    # REXGLUE_ENTRYPOINT_GENERATED_SOURCES, and the nfscarbon_codegen custom target).
    include(generated/rexglue.cmake)

    # Core Carbon source files
    set(NFSCARBON_SOURCES
        src/main.cpp
        src/dispatch_tolerance.cpp
        src/render_mode_hook.cpp
        src/ring_wait_hook.cpp
        src/carbon_missing_entries.cpp
        src/carbon_nativo_enlaces.cpp
        src/carbon_nativo_ganchos.cpp
    )

    if(WIN32)
        list(APPEND NFSCARBON_SOURCES src/crash_diag.cpp)
        add_executable(nfscarbon WIN32 ${NFSCARBON_SOURCES})
        target_link_libraries(nfscarbon PRIVATE dbghelp)
        target_link_options(nfscarbon PRIVATE "LINKER:/force:multiple")
    else()
        add_executable(nfscarbon ${NFSCARBON_SOURCES})
    endif()

    # Apply ReXGlue SDK libraries, include paths, and generated recomp sources.
    rexglue_setup_target(nfscarbon GPU_PLUGINS xenos)

    # Expose the generated include dir so host sources find nfscarbon_pch.h etc.
    target_include_directories(nfscarbon PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/generated/default"
        "${CMAKE_CURRENT_SOURCE_DIR}/src"
        "${CMAKE_CURRENT_SOURCE_DIR}"
    )
endif()
