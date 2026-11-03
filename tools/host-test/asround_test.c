/*
 * Host test: ownership safety of the request-assembly teardown (ASan/UBSan).
 *
 * Ghee 11-03 item 2: the tools-array cache and the attach-in-place of the
 * caller's message array (replacing cJSON_Duplicate) introduce shared-tree
 * ownership. This harness replays 20 simulated rounds through the REAL
 * req_serialize/req_release/validate_request_tree code (extracted from
 * firmware sources), cycling the exit paths the firmware takes:
 *   A  normal send
 *   B  API 400 -> request-body dump -> release
 *   C  timeout  -> release without parse
 *   D  tree incomplete -> validator rejects (teardown before return)
 *   E  oversized body -> heap-fallback print path
 * Any use-after-free, double-free or leak fails the run.
 */
#include <assert.h>
#include <sys/stat.h>
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
#define AGENT_DATA_DIR "/data/ai_agent"

static const char *TAG = "hosttest";
static void syslog(int pri, const char *fmt, ...)
{
    (void)pri;
    (void)fmt;
}

#include "cJSON.h"
#include "alloc_guard.inc"
#include "tools_conv.inc"
#include "req_buf.inc"

/* ── the exact teardown sequence of llm_chat_tools ───────────── */

static int g_dump_writes;
static cJSON *g_tools_cache;
static char *g_tools_key;

static int assemble_and_teardown(cJSON *body, cJSON *messages,
    const char *system_prompt, const char *tools_json, int round_kind)
{
    /* mirrors llm_chat_tools: borrow messages + cached tools, validate,
     * serialize, give the borrowed trees back, then delete the body */
    cJSON *s_tools_cache = g_tools_cache;
    char *s_tools_key = g_tools_key;
    if (!s_tools_cache || !s_tools_key
        || strcmp(s_tools_key, tools_json ? tools_json : "") != 0) {
        cJSON_Delete(s_tools_cache);
        free(s_tools_key);
        s_tools_cache = tools_json ? build_openai_tools_array(tools_json)
                                  : NULL;
        s_tools_key = tools_json ? strdup(tools_json) : NULL;
        g_tools_cache = s_tools_cache;
        g_tools_key = s_tools_key;
    }

    cJSON *sys_msg = cJSON_CreateObject();
    cJSON_AddStringToObject(sys_msg, "role", "system");
    cJSON_AddStringToObject(sys_msg, "content", system_prompt);
    cJSON_InsertItemInArray(messages, 0, sys_msg);
    cJSON_AddItemToObject(body, "messages", messages);
    if (s_tools_cache) {
        cJSON_AddItemToObject(body, "tools", s_tools_cache);
    }

    if (round_kind == 4) {
        /* simulate a dropped field: detach a tool's function */
        if (s_tools_cache && s_tools_cache->child) {
            cJSON *fn = cJSON_DetachItemFromObject(
                s_tools_cache->child, "function");
            cJSON_Delete(fn);
        }
    }

    int tree_ok = validate_request_tree(body);

    bool post_is_static = false;
    char *post_data = (tree_ok == OK)
        ? req_serialize(body, &post_is_static) : NULL;

    /* give the borrowed trees back before tearing the body down */
    cJSON_DetachItemViaPointer(body, messages);
    {
        cJSON *sys_back = cJSON_DetachItemFromArray(messages, 0);
        cJSON_Delete(sys_back);
    }
    if (s_tools_cache) {
        cJSON_DetachItemViaPointer(body, s_tools_cache);
    }
    cJSON_Delete(body);

    if (tree_ok != OK) {
        return ERROR;
    }
    if (!post_data) {
        req_release(NULL, false);
        return ERROR;
    }

    /* send phase */
    if (round_kind == 1) {
        /* API 400: dump the body (400-落盘 path) BEFORE release,
         * as reviewed in the UAF audit */
        FILE *f = fopen("/tmp/host-test/dump.json", "w");
        if (f) {
            fputs(post_data, f);
            fclose(f);
            g_dump_writes++;
        }
    }
    if (round_kind == 2) {
        /* timeout: release without touching the body further */
        req_release(post_data, post_is_static);
        return OK;
    }
    req_release(post_data, post_is_static);
    return OK;
}

static char *make_tools_json(void)
{
    cJSON *arr = cJSON_CreateArray();
    const char *names[3] = { "run_shell", "read_file", "write_file" };
    for (int i = 0; i < 3; i++) {
        cJSON *t = cJSON_CreateObject();
        cJSON_AddStringToObject(t, "name", names[i]);
        cJSON_AddStringToObject(t, "description",
            "NuttX command tool with a description long enough to "
            "exercise string allocation paths");
        cJSON *sch = cJSON_Parse(
            "{\"type\":\"object\",\"properties\":{\"command\":"
            "{\"type\":\"string\",\"description\":\"cmd\"}},"
            "\"required\":[\"command\"]}");
        cJSON_AddItemToObject(t, "input_schema", sch);
        cJSON_AddItemToArray(arr, t);
    }
    char *js = cJSON_PrintUnformatted(arr);
    cJSON_Delete(arr);
    return js;
}

int main(void)
{
    install_alloc_hooks();
    mkdir("/tmp/host-test", 0777);

    char *tools_json = make_tools_json();
    char reasoning[900];
    memset(reasoning, 'x', sizeof(reasoning) - 1);
    reasoning[sizeof(reasoning) - 1] = '\0';
    memcpy(reasoning, "\xe6\xb7\xb1\xe5\xba\xa6\xe6\x80\x9d\xe8\x80\x83 ", 13);

    for (int round = 0; round < 20; round++) {
        int kind = round % 5; /* 0 normal, 1 400-dump, 2 timeout,
                               * 3 serialize-fail, 4 tree-incomplete */
        cJSON *messages = cJSON_CreateArray();
        cJSON *u = cJSON_CreateObject();
        cJSON_AddStringToObject(u, "role", "user");
        cJSON_AddStringToObject(u, "content", "run the check");
        cJSON_AddItemToArray(messages, u);

        for (int pair = 0; pair < 3; pair++) {
            cJSON *a = cJSON_CreateObject();
            cJSON_AddStringToObject(a, "role", "assistant");
            cJSON_AddStringToObject(a, "reasoning_content", reasoning);
            cJSON *tcs = cJSON_CreateArray();
            cJSON *tc = cJSON_CreateObject();
            char id[24];
            snprintf(id, sizeof(id), "call_%d_%d", round, pair);
            cJSON_AddStringToObject(tc, "id", id);
            cJSON_AddStringToObject(tc, "type", "function");
            cJSON *fn = cJSON_CreateObject();
            cJSON_AddStringToObject(fn, "name", "run_shell");
            cJSON_AddStringToObject(fn, "arguments", "{\"command\":\"ps\"}");
            cJSON_AddItemToObject(tc, "function", fn);
            cJSON_AddItemToArray(tcs, tc);
            cJSON_AddItemToObject(a, "tool_calls", tcs);
            cJSON_AddItemToArray(messages, a);
            cJSON *r = cJSON_CreateObject();
            cJSON_AddStringToObject(r, "role", "tool");
            cJSON_AddStringToObject(r, "tool_call_id", id);
            cJSON_AddStringToObject(r, "name", "run_shell");
            cJSON_AddStringToObject(r, "content",
                "PID GROUP PRI ... \xe6\xb7\xb1 output with CJK tail");
            cJSON_AddItemToArray(messages, r);
        }

        cJSON *body = cJSON_CreateObject();
        cJSON_AddStringToObject(body, "model", "mimo-v2.6-flash");

        int rc;
        if (kind == 3) {
            /* oversized body forces the heap-fallback print path:
             * pad with a huge string then exercise the same teardown */
            cJSON *pad = cJSON_CreateObject();
            cJSON_AddStringToObject(pad, "role", "user");
            char *big = malloc(20000);
            memset(big, 'z', 19999);
            big[19999] = '\0';
            cJSON_AddStringToObject(pad, "content", big);
            free(big);
            cJSON_AddItemToArray(messages, pad);
        }

        rc = assemble_and_teardown(body, messages, "system prompt text",
            tools_json, kind);
        (void)rc;

        cJSON_Delete(messages); /* caller frees its array at round end */
    }

    free(tools_json);
    cJSON_Delete(g_tools_cache);
    free(g_tools_key);
    printf("20 rounds replayed (normal/400-dump/timeout/oversize/incomplete)\n");
    printf("400-dump writes: %d\n", g_dump_writes);
    printf("ASAN ROUND TEST: PASS\n");
    return 0;
}
