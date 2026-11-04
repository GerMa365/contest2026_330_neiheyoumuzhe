/*
 * Host test: fallback report on LLM failure (2026-11-04, ASan/UBSan).
 * Compiles the REAL src/tools/tool_recover.c against the real headers.
 *
 * The guarded state machine itself is covered by recover_guard_test.c;
 * this file covers the tail-failure path: recover_task ran, then the
 * LLM call that writes report.md fails - C code must then write
 * report.md from its fixed template (and never in any other case).
 *
 *   A. stall persists (scenario C shape): ladder -> needs_human, then
 *      the report LLM call "fails" -> fallback report.md is written
 *      with the verdict fields, target, time and the marker line.
 *   B. stall -> L1 recovers (scenario B shape): recovered, LLM failure
 *      -> fallback report carries the temporary-stall conclusion.
 *   C. healthy system: the tool refuses, the ladder never runs -> an
 *      LLM failure must NOT produce a fallback report (never armed).
 *   D. normal path wins: recovery ran and report.md was written by
 *      write_file -> a later LLM failure must NOT overwrite it.
 *   E. session boundary: recovery ran, then a new message begins -> a
 *      later LLM failure must NOT produce a stale fallback report.
 *   F. one-shot + re-arm: the fallback fires once per recovery; a new
 *      session with a new recovery arms it again.
 *
 * ASan/UBSan with leak detection must stay silent ("零报告").
 */
#include <assert.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

#include "tools/tool_recover.h"

#define DATA "/tmp/host-test-data"
#define HB   DATA "/evidence/heartbeat.txt"
#define PIDF DATA "/evidence/buggy_app.pid"
#define NEEDS DATA "/evidence/needs_human"
#define REPORT DATA "/evidence/report.md"

static void reset_env(void)
{
    mkdir(DATA, 0777);
    mkdir(DATA "/evidence", 0777);
    unlink(NEEDS);
    unlink(REPORT);
    unlink(DATA "/evidence/actions.log");
    FILE *f = fopen(HB, "w");
    if (f) {
        fprintf(f, "0\n");
        fclose(f);
    }
    tool_recover_reset();
    tool_recover_session_begin();
}

static void bump_hb(void)
{
    static long v;
    FILE *f = fopen(HB, "w");
    if (f) {
        fprintf(f, "%ld\n", ++v);
        fclose(f);
    }
}

static volatile sig_atomic_t g_run;

static void on_usr1(int sig)
{
    (void)sig;
    g_run = 1;
}

/* worker modes: 0 = healthy writer; 1 = stalled, SIGUSR1 resumes it;
 * 3 = stalled, SIGUSR1 has no handler (terminates it: L1 clearly does
 * not fix this fault) */
static pid_t spawn_worker(int mode)
{
    pid_t pid = fork();
    if (pid != 0) {
        return pid;
    }
    prctl(PR_SET_NAME, "buggy_app", 0, 0, 0); /* the PID guard checks it */
    if (mode == 0) {
        g_run = 1;
    }
    if (mode == 1) {
        signal(SIGUSR1, on_usr1);
    }
    for (;;) {
        if (g_run) {
            bump_hb();
        }
        usleep(200000); /* fast cadence: keeps re-sample windows safe
                         * even when the host is loaded */
    }
    return 0;
}

static void write_pid(pid_t pid)
{
    FILE *f = fopen(PIDF, "w");
    assert(f);
    fprintf(f, "%d\n", (int)pid);
    fclose(f);
}

static int call_tool(const char *action, char *out, size_t out_size)
{
    char input[128];
    snprintf(input, sizeof(input),
        "{\"action\":\"%s\",\"target\":\"buggy_app\"}", action);
    out[0] = '\0';
    return tool_recover_execute(input, out, out_size);
}

/* what agent_loop does when the report-writing LLM call fails */
static void llm_report_fails(void)
{
    tool_recover_write_fallback_report();
}

static int read_report(char *buf, size_t cap)
{
    FILE *f = fopen(REPORT, "r");
    if (!f) {
        return -1;
    }
    size_t n = fread(buf, 1, cap - 1, f);
    fclose(f);
    buf[n] = '\0';
    return (int)n;
}

static int report_exists(void)
{
    return access(REPORT, F_OK) == 0;
}

int main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    char out[320];
    char rep[2048];
    int n;

    /* ── A. C shape: ladder exhausts -> needs_human -> LLM fails ── */
    reset_env();
    pid_t w = spawn_worker(3); /* stalled; SIGUSR1 terminates it */
    write_pid(w);
    call_tool("restart", out, sizeof(out));
    printf("A: %s\n", out);
    assert(strstr(out, "needs_human") != NULL
        || strstr(out, "recurred") != NULL);
    llm_report_fails();
    assert(report_exists() && "A: fallback report must be written");
    n = read_report(rep, sizeof(rep));
    printf("A: report (%d bytes)\n%s\n", n, rep);
    assert(strstr(rep, "LLM unavailable: fallback report") != NULL);
    assert(strstr(rep, "target: buggy_app") != NULL);
    assert(strstr(rep, "level: 2") != NULL);
    assert(strstr(rep, "action: restart") != NULL);
    assert(strstr(rep, "pre_delta: 0") != NULL);
    assert(strstr(rep, "post_delta: ") != NULL);
    assert(strstr(rep, "time: ") != NULL);
    assert(strstr(rep, "result: needs_human") != NULL
        || strstr(rep, "result: recurred") != NULL);
    assert(strstr(rep, "## Conclusion") != NULL);
    assert(strstr(rep, "code defect") != NULL
        && "A: conclusion rule = fault after L2");
    kill(w, SIGKILL);
    waitpid(w, NULL, 0);

    /* ── B. B shape: L1 recovers -> recovered -> LLM fails ─────── */
    reset_env();
    w = spawn_worker(1); /* stalled until SIGUSR1 */
    write_pid(w);
    call_tool("resume", out, sizeof(out));
    printf("B: %s\n", out);
    assert(strstr(out, "\"result\":\"recovered\"") != NULL);
    assert(strstr(out, "\"level\":1") != NULL);
    llm_report_fails();
    assert(report_exists() && "B: fallback report must be written");
    n = read_report(rep, sizeof(rep));
    printf("B: report (%d bytes)\n%s\n", n, rep);
    assert(strstr(rep, "LLM unavailable: fallback report") != NULL);
    assert(strstr(rep, "level: 1") != NULL);
    assert(strstr(rep, "action: resume") != NULL);
    assert(strstr(rep, "result: recovered") != NULL);
    assert(strstr(rep, "temporary stall") != NULL
        && "B: conclusion rule = L1 recovery");
    kill(w, SIGTERM);
    waitpid(w, NULL, 0);

    /* ── C. healthy: refused, never armed -> no report ─────────── */
    reset_env();
    w = spawn_worker(0); /* running: heartbeat advances */
    sleep(2);
    write_pid(w);
    call_tool("resume", out, sizeof(out));
    printf("C: %s\n", out);
    assert(strstr(out, "refused") != NULL);
    llm_report_fails();
    assert(!report_exists() && "C: healthy round must write no report");
    kill(w, SIGTERM);
    waitpid(w, NULL, 0);

    /* ── D. normal report wins -> fallback must not overwrite ──── */
    reset_env();
    w = spawn_worker(3);
    write_pid(w);
    call_tool("restart", out, sizeof(out));
    printf("D: %s\n", out);
    /* write_file's success hook after an LLM-written report.md */
    FILE *f = fopen(REPORT, "w");
    assert(f);
    fputs("REAL LLM REPORT\n", f);
    fclose(f);
    tool_recover_report_written();
    llm_report_fails();
    n = read_report(rep, sizeof(rep));
    printf("D: report after LLM failure (%d bytes)\n%s\n", n, rep);
    assert(strstr(rep, "REAL LLM REPORT") != NULL
        && "D: normal report must survive");
    assert(strstr(rep, "fallback report") == NULL
        && "D: fallback must not overwrite");
    kill(w, SIGKILL);
    waitpid(w, NULL, 0);

    /* ── E. new message begins -> stale arm must be cleared ────── */
    reset_env();
    w = spawn_worker(3);
    write_pid(w);
    call_tool("restart", out, sizeof(out));
    printf("E: %s\n", out);
    tool_recover_session_begin(); /* next inbound message */
    llm_report_fails();
    assert(!report_exists()
        && "E: previous session's recovery must not arm this one");
    kill(w, SIGKILL);
    waitpid(w, NULL, 0);

    /* ── F. one-shot per recovery, re-armed by a new recovery ──── */
    reset_env();
    w = spawn_worker(3);
    write_pid(w);
    call_tool("restart", out, sizeof(out));
    printf("F1: %s\n", out);
    llm_report_fails();
    assert(report_exists());
    unlink(REPORT);
    llm_report_fails();
    assert(!report_exists() && "F: second failure writes nothing");
    tool_recover_session_begin();
    tool_recover_reset(); /* nsh demo unlock: clear the needs_human
                           * latch so the next recovery can run */
    call_tool("restart", out, sizeof(out)); /* new recovery */
    printf("F2: %s\n", out);
    assert(strstr(out, "needs_human") != NULL
        || strstr(out, "recurred") != NULL);
    llm_report_fails();
    assert(report_exists() && "F: new recovery re-arms the fallback");
    kill(w, SIGKILL);
    waitpid(w, NULL, 0);

    printf("FALLBACK REPORT TESTS: ALL GREEN\n");
    return 0;
}
