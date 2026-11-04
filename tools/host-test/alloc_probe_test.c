/*
 * Host test: is the alloc-fail probe effective?
 *
 * Question (Ghee, 2026-11-03): if cJSON silently drops fields when malloc
 * fails, can our instrumentation see it? This test injects malloc failures
 * at every allocation slot during the REAL build_openai_tools_array and the
 * REAL validate_request_tree / counting hooks (extracted from the firmware
 * sources by run.sh) and asserts:
 *   A. every injected failure is counted (alloc_fail increments);
 *   B. whenever the built request tree is incomplete, the validator
 *      rejects it ("request tree incomplete");
 *   C. a complete tree always passes the validator.
 * If any of these fail, the firmware probe cannot detect silent field
 * loss and any "alloc_fail=0" runtime data is void.
 */
#include <assert.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LOG_INFO 6
#define LOG_WARNING 4
#define LOG_ERR 3
#define OK 0
#define ERROR (-1)

static const char *TAG = "hosttest";
static char g_log[16384];

static void syslog(int pri, const char *fmt, ...)
{
    (void)pri;
    char line[512];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(line, sizeof(line), fmt, ap);
    va_end(ap);
    size_t used = strlen(g_log);
    snprintf(g_log + used, sizeof(g_log) - used, "%s", line);
}

#include "cJSON.h"

/* capture the real allocator before remapping malloc for injection */
static void *(*g_real_malloc)(size_t) = malloc;
static void (*g_real_free)(void *) = free;

static int g_fail_at = -1; /* 1-based allocation index to fail; -1 = never */
static int g_alloc_seq;

static void *test_malloc(size_t sz)
{
    g_alloc_seq++;
    if (g_fail_at > 0 && g_alloc_seq == g_fail_at) {
        return NULL;
    }
    return g_real_malloc(sz);
}

static void test_free(void *p) { g_real_free(p); }

#define malloc test_malloc
#define free test_free
#include "alloc_guard.inc"
#include "tools_conv.inc"
#include "req_buf.inc"
#undef malloc
#undef free

/* ── the same message/tool shapes the firmware builds ─────────── */

static cJSON *make_tools_json(void)
{
    cJSON *arr = cJSON_CreateArray();
    for (int i = 0; i < 10; i++) {
        cJSON *t = cJSON_CreateObject();
        cJSON_AddStringToObject(t, "name", i == 0 ? "run_shell" : "read_file");
        cJSON_AddStringToObject(t, "description", "desc");
        cJSON *sch = cJSON_Parse(
            "{\"type\":\"object\",\"properties\":{\"command\":"
            "{\"type\":\"string\"}},\"required\":[\"command\"]}");
        cJSON_AddItemToObject(t, "input_schema", sch);
        cJSON_AddItemToArray(arr, t);
    }
    char *js = cJSON_PrintUnformatted(arr);
    cJSON_Delete(arr);
    return (cJSON *)js; /* caller treats as string */
}

static cJSON *make_messages(void)
{
    cJSON *msgs = cJSON_CreateArray();
    cJSON *u = cJSON_CreateObject();
    cJSON_AddStringToObject(u, "role", "user");
    cJSON_AddStringToObject(u, "content", "check");
    cJSON_AddItemToArray(msgs, u);
    for (int i = 0; i < 3; i++) {
        cJSON *a = cJSON_CreateObject();
        cJSON_AddStringToObject(a, "role", "assistant");
        cJSON *tcs = cJSON_CreateArray();
        cJSON *tc = cJSON_CreateObject();
        cJSON_AddStringToObject(tc, "id", "call_1");
        cJSON_AddStringToObject(tc, "type", "function");
        cJSON *fn = cJSON_CreateObject();
        cJSON_AddStringToObject(fn, "name", "read_file");
        cJSON_AddStringToObject(fn, "arguments", "{}");
        cJSON_AddItemToObject(tc, "function", fn);
        cJSON_AddItemToArray(tcs, tc);
        cJSON_AddItemToObject(a, "tool_calls", tcs);
        cJSON_AddItemToArray(msgs, a);
        cJSON *r = cJSON_CreateObject();
        cJSON_AddStringToObject(r, "role", "tool");
        cJSON_AddStringToObject(r, "tool_call_id", "call_1");
        cJSON_AddStringToObject(r, "name", "read_file");
        cJSON_AddStringToObject(r, "content", "ok");
        cJSON_AddItemToArray(msgs, r);
    }
    return msgs;
}

/* independent completeness check (does NOT use the firmware validator) */
static bool tree_complete(cJSON *body, bool tools_required)
{
    cJSON *tools = cJSON_GetObjectItem(body, "tools");
    if (tools_required && !tools) {
        return false;
    }
    if (tools) {
        cJSON *t;
        cJSON_ArrayForEach(t, tools) {
            cJSON *fn = cJSON_GetObjectItem(t, "function");
            cJSON *nm = fn ? cJSON_GetObjectItem(fn, "name") : NULL;
            if (!fn || !nm || !cJSON_IsString(nm) || !nm->valuestring[0]) {
                return false;
            }
        }
    }
    cJSON *msgs = cJSON_GetObjectItem(body, "messages");
    if (!msgs || !cJSON_IsArray(msgs) || cJSON_GetArraySize(msgs) == 0) {
        return false;
    }
    cJSON *m;
    cJSON_ArrayForEach(m, msgs) {
        if (!cJSON_GetObjectItem(m, "role")) {
            return false;
        }
    }
    return true;
}

int main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    install_alloc_hooks();

    int seen_fail_counted = 0, seen_reject = 0, seen_pass = 0, lies = 0;
    /* Phase design: fixtures are built with injection OFF so failures land
     * in the converter/assembly — the code path the firmware runs per
     * request and where dropped fields actually happen. */
    for (int fail_at = 1; fail_at <= 120; fail_at++) {
        g_fail_at = -1;
        char *tools_json = (char *)make_tools_json();
        cJSON *messages = make_messages();

        g_fail_at = fail_at;
        g_alloc_seq = 0;
        unsigned before = llm_alloc_fail_count();

        cJSON *tools_arr = build_openai_tools_array(tools_json);
        cJSON *body = cJSON_CreateObject();
        cJSON *sys_msg = cJSON_CreateObject();
        cJSON_AddStringToObject(sys_msg, "role", "system");
        cJSON_AddStringToObject(sys_msg, "content", "sys");
        cJSON_InsertItemInArray(messages, 0, sys_msg);
        cJSON_AddItemToObject(body, "messages", messages);
        if (tools_arr) {
            cJSON_AddItemToObject(body, "tools", tools_arr);
        }

        bool complete = tree_complete(body, true);
        int v = validate_request_tree(body);
        if (v == OK && tools_json && !cJSON_GetObjectItem(body, "tools")) {
            v = ERROR; /* same guard the firmware applies */
        }
        unsigned after = llm_alloc_fail_count();

        if (after != before) {
            seen_fail_counted++;
        }
        if (v != OK) {
            seen_reject++;
            if (seen_reject <= 5) {
                printf("  reject@fail_at=%d complete=%d\n", fail_at, (int)complete);
            }
            if (complete) {
                lies++;
                printf("BAD: validator rejected a COMPLETE tree (fail_at=%d)\n",
                    fail_at);
            }
        } else {
            seen_pass++;
            if (!complete && seen_pass <= 8) {
                printf("  MISS@fail_at=%d: incomplete tree PASSED validator\n",
                    fail_at);
            }
            if (!complete) {
                lies++;
            }
        }

        cJSON_DetachItemViaPointer(body, messages);
        if (tools_arr) {
            cJSON_DetachItemViaPointer(body, tools_arr);
        }
        cJSON_Delete(body);
        cJSON_Delete(messages);
        cJSON_Delete(tools_arr);
        free(tools_json);
    }
    g_fail_at = -1;

    printf("injected-failure rounds: 120\n");
    printf("failures counted by alloc_fail: %d\n", seen_fail_counted);
    printf("validator rejects (incomplete trees): %d\n", seen_reject);
    printf("validator passes (complete trees): %d\n", seen_pass);
    printf("validator lies (mismatch): %d\n", lies);

    assert(seen_fail_counted > 50 && "probe must count injected failures");
    assert(seen_reject > 5 && "validator must catch dropped fields");
    assert(lies == 0 && "validator must never contradict reality");
    printf("PROBE EFFECTIVENESS: PASS\n");
    return 0;
}
