/*
 * Host test: recover_task guards & escalation logic (M2/M3, ASan/UBSan).
 * Compiles the REAL src/tools/tool_recover.c against the real headers.
 *
 *   A. healthy system (heartbeat advances): 20 tool calls must ALL be
 *      refused by the guards - the exact board-acceptance scenario.
 *   B. stall + SIGUSR1 resumes the worker: ladder L1 recovers and the
 *      recurrence watch passes -> "recovered".
 *   C. stall persists (SIGUSR1 has no effect): L1 fails, L2 respawn
 *      fails on host (no ELF) -> ladder exhausted -> "needs_human".
 *   D. L1 recovers but the fault returns inside the watch window
 *      -> "recurred" -> needs_human.
 */
#include <assert.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/prctl.h>
#include <sys/wait.h>
#include <pthread.h>
#include <unistd.h>

#include "tools/tool_recover.h"

#define DATA "/tmp/host-test-data"
#define HB   DATA "/evidence/heartbeat.txt"
#define PIDF DATA "/evidence/buggy_app.pid"
#define NEEDS DATA "/evidence/needs_human"

static void reset_env(void)
{
    mkdir(DATA, 0777);
    mkdir(DATA "/evidence", 0777);
    unlink(NEEDS);
    unlink(DATA "/evidence/actions.log");
    FILE *f = fopen(HB, "w");
    if (f) {
        fprintf(f, "0\n");
        fclose(f);
    }
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

/* worker child modes: 0 = healthy writer; 1 = stalled, SIGUSR1 resumes;
 * 2 = stalled, SIGUSR1 resumes for 2 writes then stalls (recurrence);
 * 3 = stalled, no SIGUSR1 handler (signal terminates it: the
 * fault clearly does not respond to L1) */
static volatile sig_atomic_t g_run;
static volatile sig_atomic_t g_budget = -1;

static void on_usr1(int sig)
{
    (void)sig;
    g_run = 1;
}

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
    if (mode == 1 || mode == 2) {
        signal(SIGUSR1, on_usr1);
    }
    if (mode == 2) {
        g_budget = 5; /* survives the post-check, relapses in the watch */
    }
    for (;;) {
        if (g_run && g_budget != 0) {
            bump_hb();
            if (g_budget > 0) {
                g_budget--;
            }
        }
        sleep(1);
    }
    return 0;
}

static void write_pid(pid_t pid)
{
    FILE *f = fopen(PIDF, "w");
    fprintf(f, "%d\n", (int)pid);
    fclose(f);
}

static int call_tool(const char *action, const char *target, char *out,
    size_t out_size);

static char g_thread_out[320];

static void *call_thread(void *arg)
{
    (void)arg;
    call_tool("resume", "buggy_app", g_thread_out, sizeof(g_thread_out));
    return NULL;
}

static int call_tool(const char *action, const char *target, char *out,
    size_t out_size)
{
    char input[128];
    snprintf(input, sizeof(input),
        "{\"action\":\"%s\",\"target\":\"%s\"}", action, target);
    out[0] = '\0';
    return tool_recover_execute(input, out, out_size);
}

int main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    char out[320];
    reset_env();

    /* ── A. healthy: 20 calls, all refused ─────────────────────── */
    pid_t w = spawn_worker(0); /* running=1 -> heartbeat advances */
    sleep(2);
    write_pid(w);
    int refused = 0;
    for (int i = 0; i < 20; i++) {
        call_tool("resume", "buggy_app", out, sizeof(out));
        printf("[A%02d] %s\n", i, out);
        if (strstr(out, "refused")) {
            refused++;
        }
    }
    kill(w, SIGTERM);
    waitpid(w, NULL, 0);
    printf("A: 20 healthy calls -> refused=%d\n", refused);
    assert(refused == 20 && "healthy system must never be touched");
    assert(access(NEEDS, F_OK) != 0 && "healthy must not set needs_human");

    /* ── B. stall -> L1 SIGUSR1 recovers -> recovered ──────────── */
    reset_env();
    w = spawn_worker(1); /* stalled until SIGUSR1 */
    write_pid(w);
    call_tool("resume", "buggy_app", out, sizeof(out));
    printf("B: %s\n", out);
    assert(strstr(out, "\"result\":\"recovered\"") != NULL);
    assert(strstr(out, "\"level\":1") != NULL);
    kill(w, SIGTERM);
    waitpid(w, NULL, 0);
    sleep(2); /* let the cooldown window (COOLDOWN_S=1 in tests) pass */

    /* ── C. stall persists -> L1 no-op, L2 respawn fails
     *    (no ELF on host) -> needs_human ───────────────────────── */
    reset_env();
    w = spawn_worker(3); /* stalled; SIGUSR1 keeps it stalled */
    write_pid(w);
    call_tool("restart", "buggy_app", out, sizeof(out));
    printf("C: %s\n", out);
    assert(strstr(out, "needs_human") != NULL || strstr(out, "recurred") != NULL);
    assert(access(NEEDS, F_OK) == 0 && "exhausted ladder must flag human");
    kill(w, SIGKILL);
    waitpid(w, NULL, 0);

    /* ── D. L1 recovers, fault recurs in the watch window -> recurred */
    reset_env();
    w = spawn_worker(2); /* resumes for 2 writes then stalls again */
    write_pid(w);
    call_tool("resume", "buggy_app", out, sizeof(out));
    printf("D: %s\n", out);
    assert(strstr(out, "\"result\":\"recurred\"") != NULL
        || strstr(out, "needs_human") != NULL);
    assert(access(NEEDS, F_OK) == 0 && "recurrence must flag human");
    kill(w, SIGKILL);
    waitpid(w, NULL, 0);

    /* ── E. stale PID file whose number was reused: the pid lives
     *    but is NOT buggy_app -> refused, audited ───────────────── */
    reset_env();
    w = spawn_worker(3); /* stalled */
    write_pid(getpid()); /* reuse: ours, wrong name */
    call_tool("resume", "buggy_app", out, sizeof(out));
    printf("E: %s\n", out);
    assert(strstr(out, "pid_mismatch") != NULL);
    kill(w, SIGKILL);
    waitpid(w, NULL, 0);

    /* ── F. second call while a recovery is in flight -> busy ──── */
    reset_env();
    w = spawn_worker(2); /* L1 recovers, recurrence watch spans ~2 s */
    write_pid(w);
    pthread_t th;
    pthread_create(&th, NULL, call_thread, NULL);
    sleep(3); /* first call is inside its ladder/watch window */
    call_tool("resume", "buggy_app", out, sizeof(out));
    printf("F: %s\n", out);
    assert(strstr(out, "busy") != NULL);
    pthread_join(th, NULL);
    kill(w, SIGKILL);
    waitpid(w, NULL, 0);

    /* ── G. reset/test are human-only CLI verbs: the LLM tool entry
     *    must refuse them outright ─────────────────────────────── */
    call_tool("reset", "buggy_app", out, sizeof(out));
    printf("G1: %s\n", out);
    assert(strstr(out, "cli_only") != NULL);
    call_tool("test", "buggy_app", out, sizeof(out));
    printf("G2: %s\n", out);
    assert(strstr(out, "cli_only") != NULL);

    /* ── H. L3 hotfix (M4): with the payload absent (host has no
     *    exec_spawn at all - compiled out), the ladder must walk
     *    L1 -> L2 -> L3 and exhaust to needs_human with the level:2
     *    terminal verdict. action=hotfix must be accepted as a valid
     *    level (not m4_deferred, not whitelist-refused). ──────────── */
    reset_env();
    w = spawn_worker(3); /* stalled; L1 can't help, L2 respawn fails */
    write_pid(w);
    call_tool("hotfix", "buggy_app", out, sizeof(out));
    printf("H: %s\n", out);
    assert(strstr(out, "needs_human") != NULL
        || strstr(out, "recurred") != NULL);
    assert(strstr(out, "\"level\":2") != NULL
        || strstr(out, "\"level\":3") != NULL);
    assert(access(NEEDS, F_OK) == 0 && "exhausted ladder must flag human");
    kill(w, SIGKILL);
    waitpid(w, NULL, 0);

    printf("RECOVER GUARD TESTS: ALL GREEN\n");
    return 0;
}
