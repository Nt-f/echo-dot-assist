/* The other side's picture on this screen: see video.h.
 *
 * One writer thread: records wait in a queue (QMAX records, QBYTES bytes; a key frame of 720p is some 60 KB) and go to
 * the player's stdin in order.  The player is started by the first key frame or codec config of a call (deltas before
 * it are useless to a decoder), and goes with video_stop: its stdin closed (cam.c hides the picture and exits), killed
 * if it is still there after STOP_MS.  A player that died mid-call (its write failed) is started again at the next key
 * frame, at most once every RESTART_MS.  Behind (the queue full): what waits is dropped and the queue takes only a key
 * frame again, so the picture skips ahead rather than falls behind the call's sound.
 *
 * The picture must never outlive its call (a frozen face on someone's Show): video_stop for every end of a call
 * (dropin.c's end_call) kills the player at once, whatever the writer is doing; a new call's records end the old one's
 * player first, and cam.c ends by itself after 3 s without frames (PLAY_IDLE_MS). */
#include "video.h"
#include "board.h"
#include "camera.h"
#include "screen.h"
#include <errno.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define QMAX       64
#define QBYTES     (2 << 20)
#define STOP_MS    1500
#define RESTART_MS 3000

struct rec { int type; long long pts; uint8_t *d; size_t n; };
static pthread_mutex_t lk = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cv = PTHREAD_COND_INITIALIZER;
static struct rec q[QMAX]; static unsigned qh, qt; static size_t qbytes;
static int cur_gen = -1, need_key = 1, stop_req, started;
/* The player's pid, for video_stop to kill it itself: a player that stops reading without dying (a decoder hung in the
 * driver) would hold the writer in write() on a full pipe, where it never sees stop_req, and the picture would stay on
 * the screen after the call.  Killed, its pipe's read end goes, the write fails, and the writer reaps it */
static pid_t player = -1;
static long long last_start;
static int shown_n;

static long long now_ms(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec * 1000LL + t.tv_nsec / 1000000; }

int video_present(void)
{
    if (getenv("HASSMIC_FAKE_VIDEO")) return 1;
    return camera_present() && !getenv("HASSMIC_FAKE_CAMERA") && screen_present();
}

int video_shown(void) { pthread_mutex_lock(&lk); int n = shown_n; pthread_mutex_unlock(&lk); return n; }

static void drop_all(void)                      /* lk held */
{
    while (qt != qh) { free(q[qt % QMAX].d); qt++; }
    qbytes = 0;
}

static void *writer(void *arg);

void video_show(int gen, int type, long long pts_us, const uint8_t *data, size_t len)
{
    if (!video_present() || !len || len > QBYTES) return;
    pthread_mutex_lock(&lk);
    if (!started) { pthread_t t; if (!pthread_create(&t, NULL, writer, NULL)) { pthread_detach(t); started = 1; } }
    if (gen != cur_gen) { drop_all(); cur_gen = gen; need_key = 1; stop_req = 1; if (player > 0) kill(player, SIGKILL); }   /* the last call's player goes */
    if (type == CAM_FRAME && need_key) { pthread_mutex_unlock(&lk); return; }
    if (qh - qt >= QMAX || qbytes + len > QBYTES) {                                   /* behind: skip to a key frame */
        drop_all(); need_key = 1;
        if (type == CAM_FRAME) { pthread_mutex_unlock(&lk); return; }
    }
    uint8_t *d = malloc(len);
    if (d) {
        memcpy(d, data, len);
        q[qh % QMAX] = (struct rec){ type, pts_us, d, len }; qh++; qbytes += len;
        if (type != CAM_FRAME) need_key = 0;
        pthread_cond_signal(&cv);
    }
    pthread_mutex_unlock(&lk);
}

void video_stop(int gen)
{
    pthread_mutex_lock(&lk);
    if (gen == cur_gen) { drop_all(); need_key = 1; stop_req = 1; cur_gen = -1; if (player > 0) kill(player, SIGKILL); pthread_cond_signal(&cv); }
    pthread_mutex_unlock(&lk);
}

static int write_all(int fd, const void *p, size_t n)
{
    const uint8_t *c = p;
    while (n) { ssize_t w = write(fd, c, n); if (w < 0 && errno == EINTR) continue; if (w <= 0) return -1; c += w; n -= (size_t)w; }
    return 0;
}

static void end_player(pid_t *pid, int *fd)
{
    if (*fd >= 0) { close(*fd); *fd = -1; }
    if (*pid <= 0) return;
    long long t0 = now_ms(); int st;
    while (waitpid(*pid, &st, WNOHANG) == 0) {
        if (now_ms() - t0 > STOP_MS) { kill(*pid, SIGKILL); waitpid(*pid, &st, 0); break; }
        usleep(20000);
    }
    fprintf(stderr, "video: the other side's picture ended\n");
    pthread_mutex_lock(&lk); if (player == *pid) player = -1; pthread_mutex_unlock(&lk);
    *pid = -1;
}

static void *writer(void *arg)
{
    (void)arg; pid_t pid = -1; int fd = -1;
    signal(SIGPIPE, SIG_IGN);                   /* a player that died: write() fails, it is started again */
    for (;;) {
        pthread_mutex_lock(&lk);
        while (qt == qh && !stop_req) pthread_cond_wait(&cv, &lk);
        int stop = stop_req; stop_req = 0;
        struct rec r = { 0 };
        if (!stop && qt != qh) { r = q[qt % QMAX]; qt++; qbytes -= r.n; }
        pthread_mutex_unlock(&lk);
        if (stop) { end_player(&pid, &fd); if (!r.d) continue; }
        if (pid < 0 && r.type != CAM_FRAME && now_ms() - last_start >= RESTART_MS) {
            last_start = now_ms();
            if ((pid = camera_player(&fd)) < 0) fprintf(stderr, "video: no player for the other side's picture\n");
            else {
                fprintf(stderr, "video: the other side's picture on the screen\n");
                pthread_mutex_lock(&lk);
                player = pid;
                int gone = stop_req;                    /* stopped while it started: the kill above found no pid */
                pthread_mutex_unlock(&lk);
                if (gone) kill(pid, SIGKILL);
            }
        }
        if (pid > 0 && fd >= 0) {
            uint8_t h[20] = { 'H', 'M', 'C', 'V', (uint8_t)r.type };
            for (int i = 0; i < 4; i++) h[8 + i] = (uint8_t)(r.n >> (8 * i));
            for (int i = 0; i < 8; i++) h[12 + i] = (uint8_t)((unsigned long long)r.pts >> (8 * i));
            if (write_all(fd, h, sizeof h) || write_all(fd, r.d, r.n)) {
                fprintf(stderr, "video: the player went\n");
                end_player(&pid, &fd);
                pthread_mutex_lock(&lk); need_key = 1; pthread_mutex_unlock(&lk);
            } else { pthread_mutex_lock(&lk); shown_n++; pthread_mutex_unlock(&lk); }
        }
        free(r.d);
    }
    return NULL;
}
