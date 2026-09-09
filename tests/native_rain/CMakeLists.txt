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

set(RAIN_UPSTREAM_SOURCE "" CACHE PATH "Patched pinned upstream source for real host lifecycle tests")
if(RAIN_UPSTREAM_SOURCE)
    add_executable(rain_host_test rain_host_test.cpp
        ${RAIN_UPSTREAM_SOURCE}/src/core/shaderengine.cpp
        ${RAIN_UPSTREAM_SOURCE}/src/data/shaderlibrary.cpp
        ${RAIN_UPSTREAM_SOURCE}/src/data/shadermetadata.cpp
        ${RAIN_UPSTREAM_SOURCE}/src/rain/rainfieldrenderer.cpp
        ${RAIN_UPSTREAM_SOURCE}/src/rain/raininput.cpp
        ${RAIN_UPSTREAM_SOURCE}/src/rain/dropletsimulation.cpp)
    target_include_directories(rain_host_test PRIVATE ${RAIN_UPSTREAM_SOURCE}/src)
    target_link_libraries(rain_host_test PRIVATE Qt6::Quick Qt6::OpenGL Qt6::Test Qt6::DBus)
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
endif()
