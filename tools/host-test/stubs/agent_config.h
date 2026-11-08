/* host-test stub: only the macros tool_recover.c needs */
#pragma once
#ifndef CONFIG_EXAMPLES_AI_AGENT_VELA_DATA_DIR
#define CONFIG_EXAMPLES_AI_AGENT_VELA_DATA_DIR "/tmp/host-test-data"
#endif
#define AGENT_DATA_DIR CONFIG_EXAMPLES_AI_AGENT_VELA_DATA_DIR
#define AGENT_SKILLS_DIR AGENT_DATA_DIR "/skills/"

/* SiliconLoop M4: mirror the canonical hotfix-payload macros from the
 * real include/agent_config.h so tool_recover.c compiles unchanged. */
#define AGENT_PATCHES_DIR AGENT_DATA_DIR "/patches"
#define AGENT_HOTFIX_ELF_PATH AGENT_PATCHES_DIR "/buggy_app_fixed"
