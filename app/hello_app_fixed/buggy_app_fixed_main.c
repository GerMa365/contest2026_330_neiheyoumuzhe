/****************************************************************************
 * SiliconLoop - buggy_app_fixed (L3 hotfix payload, M4)
 *
 * Recovery-ladder L3 payload: the corrected build of buggy_app, deployed
 * to /data/patches/buggy_app_fixed and exec'd by recover_task when the
 * bug-mode fault survives L1/L2 (docs/m4-design.md).
 *
 * SiliconLoop: this is deliberately the SAME source as
 * app/hello_app/buggy_app_main.c with exactly one behavioural change -
 * the drain path decrements unconditionally, repairing the missing
 * counter release that made the FIFO report full forever. Keeping the
 * diff to one line is the demo's core claim: the fix is small, targeted,
 * and loaded while the system runs. Debug subcommands (pmp/md) are
 * dropped to keep the payload small, and fault-injection arguments are
 * accepted (so the task identity/mode files behave identically) but
 * ignored - a fixed build must not be able to re-inject the fault.
 ****************************************************************************/

#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <pthread.h>
#include <sched.h>

#define FIFO_SIZE      64
#define HEARTBEAT_PATH "/data/ai_agent/evidence/heartbeat.txt"
#define PID_FILE       "/data/ai_agent/evidence/buggy_app.pid"
#define MODE_FILE      "/data/ai_agent/evidence/buggy_app.mode"

static unsigned char g_fifo[FIFO_SIZE];
static int g_head;
static int g_tail;
static int g_count;
static volatile int g_consumer_on = 1;
static unsigned long g_produced;
static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;

static int fifo_has_space(void)
{
    int has;

    pthread_mutex_lock(&g_lock);
    has = (g_count < FIFO_SIZE);
    pthread_mutex_unlock(&g_lock);
    return has;
}

static void fifo_put(unsigned char c)
{
    pthread_mutex_lock(&g_lock);
    g_fifo[g_head] = c;
    g_head = (g_head + 1) % FIFO_SIZE;
    g_count++;
    g_produced++;
    pthread_mutex_unlock(&g_lock);
}

/* L1 soft-recovery hook, kept identical to the buggy build so the fixed
 * task stays manageable by the same ladder after the hotfix. */
static void on_usr1(int sig)
{
    (void)sig;
    g_consumer_on = 1;
}

static void publish_identity(const char *mode)
{
    FILE *f = fopen(PID_FILE, "w");

    if (f) {
        fprintf(f, "%d\n", (int)getpid());
        fclose(f);
    }
    f = fopen(MODE_FILE, "w");
    if (f) {
        fprintf(f, "%s\n", mode ? mode : "normal");
        fclose(f);
    }
}

static void *consumer_thread(void *arg)
{
    (void)arg;

    for (;;) {
        pthread_mutex_lock(&g_lock);
        if (g_consumer_on && g_count > 0) {
            g_tail = (g_tail + 1) % FIFO_SIZE;
            /* SiliconLoop: THE fix (vs app/hello_app). The buggy build
             * skips this decrement in bug mode, so the count only ever
             * grows, the FIFO reports full forever and the producer
             * deadlocks. The drain path must release the slot
             * unconditionally. */
            g_count--;
        }
        pthread_mutex_unlock(&g_lock);
        usleep(20000);
    }

    return NULL;
}

static void write_heartbeat(void)
{
    FILE *f = fopen(HEARTBEAT_PATH, "w");

    if (f) {
        fprintf(f, "%lu\n", g_produced);
        fclose(f);
    }
}

int main(int argc, char *argv[])
{
    pthread_t tid;

    /* Run below the agent so a spinning producer cannot starve the
     * diagnostic path. Same priority as the buggy build. */
    {
        struct sched_param sp;

        if (sched_getparam(0, &sp) == 0) {
            sp.sched_priority = 50;
            sched_setparam(0, &sp);
        }
    }

    /* Fault-injection arguments are accepted so recover_task can respawn
     * "the same workload" identically, but a fixed build ignores them -
     * re-injecting the fault from the payload would defeat the ladder. */
    if (argc > 1 && strcmp(argv[1], "bug") == 0) {
        printf("buggy_app_fixed: fault injection disabled in fixed build\n");
    }

    signal(SIGUSR1, on_usr1);
    publish_identity(argc > 1 ? argv[1] : "normal");

    pthread_create(&tid, NULL, consumer_thread, NULL);

    printf("buggy_app_fixed: producing, heartbeat at %s\n", HEARTBEAT_PATH);

    /* Wait for the agent to create the evidence directory, then publish
     * one heartbeat and the identity files - same startup handshake as
     * the buggy build (recover_task targets pid/mode files). */
    {
        int tries;

        for (tries = 0; tries < 300; tries++) {
            FILE *probe = fopen(HEARTBEAT_PATH, "w");

            if (probe) {
                fprintf(probe, "0\n");
                fclose(probe);
                publish_identity(argc > 1 ? argv[1] : "normal");
                break;
            }

            sleep(1);
        }
    }

    for (;;) {
        while (!fifo_has_space())
            usleep(1000);

        fifo_put((unsigned char)(g_produced & 0xff));

        if ((g_produced % 50) == 0) {
            write_heartbeat();
        }

        usleep(10000);
    }

    return 0;
}
