############################################################################
# Contest 2026 team 000 hello app fixed (M4 L3 payload) - CMakeLists.txt
############################################################################

if(CONFIG_LVX_USE_DEMO_CONTEST2026_000_HELLO_APP_FIXED)
  nuttx_add_application(
    PROGNAME buggy_app_fixed
    PRIORITY 50
    STACK 4096
    MODULE
    SRCS buggy_app_fixed_main.c)
endif()
