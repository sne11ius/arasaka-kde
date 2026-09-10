cmake_minimum_required(VERSION 3.22)
project(ArasakaWindowPolicy VERSION 1.0 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_AUTOMOC ON)
find_package(ECM REQUIRED NO_MODULE)
list(APPEND CMAKE_MODULE_PATH ${ECM_MODULE_PATH})
find_package(Qt6 REQUIRED COMPONENTS Quick DBus Widgets)
qt_policy(SET QTP0001 NEW)
find_package(KF6Config REQUIRED)
find_package(KF6WindowSystem REQUIRED)
# Only the window-management API is used. The full KWin CMake target also pulls
# rendering development dependencies (DRM/Vulkan) that this module does not use.
find_path(KWIN_INCLUDE_DIR window.h PATH_SUFFIXES kwin REQUIRED)
find_library(KWIN_LIBRARY kwin REQUIRED)
# A new native implementation needs its own module/SONAME: QQmlEngine and the
# dynamic linker otherwise reuse an old plugin during an in-session reapply.
file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/windowpolicy.h" header_hash)
file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/windowpolicy.cpp" source_hash)
file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/CMakeLists.txt" build_hash)
string(SHA256 revision "${header_hash}${source_hash}${build_hash}")
string(SUBSTRING "${revision}" 0 16 revision)
set(policy_target "arasaka_window_policy_${revision}")
set(policy_directory "${CMAKE_BINARY_DIR}/Arasaka/WindowPolicy/v${revision}")
qt_add_qml_module(${policy_target}
    URI Arasaka.WindowPolicy.v${revision}
    VERSION 1.0
    OUTPUT_DIRECTORY "${policy_directory}"
    SOURCES windowpolicy.h windowpolicy.cpp
)
target_compile_definitions(${policy_target} PRIVATE ARASAKA_POLICY_REVISION="${revision}")
target_include_directories(${policy_target} PRIVATE ${KWIN_INCLUDE_DIR})
target_link_libraries(${policy_target} PRIVATE ${KWIN_LIBRARY}
    Qt6::Quick Qt6::DBus Qt6::Widgets KF6::ConfigCore KF6::WindowSystem)
set_target_properties(${policy_target} ${policy_target}plugin PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${policy_directory}"
    BUILD_RPATH "$ORIGIN"
)
file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/policy-build.json"
    CONTENT "{\"directory\":\"${policy_directory}\",\"revision\":\"${revision}\"}\n")
