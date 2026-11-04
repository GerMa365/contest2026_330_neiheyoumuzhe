/* host-test stub: status codes only */
#pragma once
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <syslog.h> /* LOG_INFO / LOG_ERR, like the real agent_compat.h */
#include <unistd.h>
#ifndef OK
#define OK 0
#endif
#ifndef ERROR
#define ERROR (-1)
#endif
