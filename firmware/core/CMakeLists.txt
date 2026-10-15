# Portable device core. Builds as an ESP-IDF component or a plain CMake library.
set(HG_CORE_SOURCES
    src/app.cpp
    src/app_bench.cpp
    src/app_settings.cpp
    src/app_power.cpp
    src/canvas.cpp
    src/crypto.cpp
    src/font5x7.cpp
    src/json.cpp
    src/protocol.cpp
    src/setup.cpp
    src/touch.cpp
    src/ui.cpp
    src/vad.cpp
)

# The legacy 1-bit mascot (about 27 KB of flash). Round 466px companion boards draw the
# expression video instead and link a size-only stub (CONFIG_HG_LEGACY_MASCOT=n).
if(ESP_PLATFORM)
  if(CONFIG_HG_LEGACY_MASCOT)
    list(APPEND HG_CORE_SOURCES src/mascot_data.cpp)
  else()
    list(APPEND HG_CORE_SOURCES src/mascot_stub.cpp)
  endif()
  idf_component_register(SRCS ${HG_CORE_SOURCES} INCLUDE_DIRS include)
  return()
endif()

# The host simulator serves every board profile, so it keeps the mascot unless asked.
option(HG_LEGACY_MASCOT "Link the legacy 1-bit mascot bitmaps" ON)
if(HG_LEGACY_MASCOT)
  list(APPEND HG_CORE_SOURCES src/mascot_data.cpp)
else()
  list(APPEND HG_CORE_SOURCES src/mascot_stub.cpp)
endif()

add_library(hg_core STATIC ${HG_CORE_SOURCES})
target_include_directories(hg_core PUBLIC include)
target_compile_features(hg_core PUBLIC cxx_std_17)
set_target_properties(hg_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
if(MSVC)
  target_compile_options(hg_core PRIVATE /W4 /utf-8)
else()
  target_compile_options(hg_core PRIVATE -Wall -Wextra -fno-exceptions -fno-rtti)
endif()
