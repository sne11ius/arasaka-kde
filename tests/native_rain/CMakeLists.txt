cmake_minimum_required(VERSION 3.22)
project(arasaka_rain_graphics_tests LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
find_package(Qt6 6.6 REQUIRED COMPONENTS Quick OpenGL Test DBus)
add_executable(rain_graphics_test rain_graphics_test.cpp
    ../../native/rain/rainfieldrenderer.cpp
    ../../native/rain/raininput.cpp
    ../../native/rain/dropletsimulation.cpp)
target_include_directories(rain_graphics_test PRIVATE ../../native/rain)
target_link_libraries(rain_graphics_test PRIVATE Qt6::Quick Qt6::OpenGL Qt6::Test Qt6::DBus)
target_compile_options(rain_graphics_test PRIVATE -Wall -Wextra -Wpedantic)
enable_testing()
add_test(NAME rain_graphics COMMAND rain_graphics_test)

add_executable(login_pointer_test login_pointer_test.cpp ../../native/rain/raininput.cpp)
target_include_directories(login_pointer_test PRIVATE ../../native/rain)
target_link_libraries(login_pointer_test PRIVATE Qt6::Quick Qt6::Test Qt6::DBus)
target_compile_options(login_pointer_test PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME login_pointer COMMAND dbus-run-session -- $<TARGET_FILE:login_pointer_test>)
set_tests_properties(login_pointer PROPERTIES TIMEOUT 20
    ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QT_QPA_PLATFORMTHEME=")

set(RAIN_UPSTREAM_SOURCE "" CACHE PATH "Patched pinned upstream source for real host lifecycle tests")
if(RAIN_UPSTREAM_SOURCE)
    find_package(LibTaskManager REQUIRED)
    find_package(KF6WindowSystem REQUIRED)
    add_executable(rain_host_test rain_host_test.cpp
        ${RAIN_UPSTREAM_SOURCE}/src/core/shaderengine.cpp
        ${RAIN_UPSTREAM_SOURCE}/src/data/shaderlibrary.cpp
        ${RAIN_UPSTREAM_SOURCE}/src/data/shadermetadata.cpp
        ${RAIN_UPSTREAM_SOURCE}/src/rain/rainfieldrenderer.cpp
        ${RAIN_UPSTREAM_SOURCE}/src/rain/raininput.cpp
        ${RAIN_UPSTREAM_SOURCE}/src/rain/windowcountmodel.cpp
        ${RAIN_UPSTREAM_SOURCE}/src/rain/dropletsimulation.cpp)
    target_include_directories(rain_host_test PRIVATE ${RAIN_UPSTREAM_SOURCE}/src)
    target_link_libraries(rain_host_test PRIVATE Qt6::Quick Qt6::OpenGL Qt6::Test Qt6::DBus PW::LibTaskManager KF6::WindowSystem)
    target_compile_options(rain_host_test PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME rain_host COMMAND rain_host_test)

    find_package(PlasmaQuick REQUIRED)
    find_package(KF6Config REQUIRED)
    add_executable(rain_wallpaper_test rain_wallpaper_test.cpp)
    target_link_libraries(rain_wallpaper_test PRIVATE Qt6::Quick Qt6::Test
        Plasma::PlasmaQuick KF6::ConfigGui KF6::ConfigQml)
    target_compile_definitions(rain_wallpaper_test PRIVATE RAIN_PACKAGE="${RAIN_UPSTREAM_SOURCE}/package")
    target_compile_options(rain_wallpaper_test PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME rain_wallpaper COMMAND rain_wallpaper_test)

    add_executable(window_count_test window_count_test.cpp ../../native/rain/windowcountmodel.cpp)
    target_link_libraries(window_count_test PRIVATE Qt6::Quick Qt6::Test Qt6::DBus PW::LibTaskManager KF6::WindowSystem)
    target_compile_definitions(window_count_test PRIVATE RAIN_PACKAGE="${RAIN_UPSTREAM_SOURCE}/package")
    # Requires a private two-output compositor; invoked by window_illumination_smoke.py.
endif()
