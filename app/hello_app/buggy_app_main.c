/****************************************************************************
 * SiliconLoop - buggy producer/consumer demo
 *
 * Reproduces the failure class that a mock test cannot catch: a producer
 * that waits on a bounded FIFO with no exit condition. On real hardware
 * the FIFO fills up and the loop never terminates; in a mock the
 * "has space" predicate always returns true and the test passes.
 *
 * The FIFO here is simulated in RAM so that killing it does not take the
 * console down with it.
 *
 * Usage:
 *   buggy_app          run normally (consumer drains the FIFO)
 *   buggy_app stall    inject the fault (consumer stops draining)
 ****************************************************************************/

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <pthread.h>
#include <sched.h>

#define FIFO_SIZE      64
#define HEARTBEAT_PATH "/data/ai_agent/evidence/heartbeat.txt"

static unsigned char g_fifo[FIFO_SIZE];
static int g_head;
static int g_tail;
static int g_count;
static int g_consumer_on = 1;
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

static void *consumer_thread(void *arg)
{
    (void)arg;

    for (;;) {
        pthread_mutex_lock(&g_lock);
        if (g_consumer_on && g_count > 0) {
            g_tail = (g_tail + 1) % FIFO_SIZE;
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
     * diagnostic path. The scheduler class stays SCHED_RR.
     */
    {
        struct sched_param sp;

        if (sched_getparam(0, &sp) == 0) {
            sp.sched_priority = 50;
            sched_setparam(0, &sp);
        }
    }

    if (argc > 1 && strcmp(argv[1], "stall") == 0) {
        g_consumer_on = 0;
        printf("buggy_app: consumer disabled, FIFO will fill up\n");
    }

    pthread_create(&tid, NULL, consumer_thread, NULL);

    printf("buggy_app: producing, heartbeat at %s\n", HEARTBEAT_PATH);

    /* Wait for the agent to create the evidence directory, then publish
     * one heartbeat before the FIFO can fill. Without this the stalled
     * run leaves no heartbeat at all, and "file missing" is weaker
     * evidence than "value never changed".
     */
    {
        int tries;

        for (tries = 0; tries < 300; tries++) {
            FILE *probe = fopen(HEARTBEAT_PATH, "w");

            if (probe) {
                fprintf(probe, "0\n");
                fclose(probe);
                break;
            }

            sleep(1);
        }
    }

    for (;;) {
        /* The bug: no exit condition, no timeout, no error path.
         * The usleep() is a concession to demonstrability, not part of
         * the fault. A bare spin here starves every lower-priority
         * thread on this single-core board, including the agent's own
         * CLI, so the diagnostic system never gets to run. That was
         * reproduced first; the sleep was added afterwards so the
         * fault stays observable. The loop still never terminates and
         * the task still never makes progress.
         */
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
