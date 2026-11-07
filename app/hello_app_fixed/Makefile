############################################################################
# Contest 2026 team 000 hello app fixed (M4 L3 payload) - Makefile
############################################################################

include $(APPDIR)/Make.defs

PROGNAME  = buggy_app_fixed
PRIORITY  = 50
STACKSIZE = 4096

# SiliconLoop: build as a relocatable ELF module (apps/bin/buggy_app_fixed)
# instead of a builtin. This is the L3 hotfix payload that recover_task
# exec's from /data/patches/ - it must never be linked into the firmware
# image, or the "hotfix" would ship inside the same binary as the bug.
MODULE    = m

MAINSRC = buggy_app_fixed_main.c

include $(APPDIR)/Application.mk
