#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static double milliseconds(struct timeval value)
{
    return value.tv_sec * 1000.0 + value.tv_usec / 1000.0;
}

int main(int argc, char **argv)
{
    struct timespec start, end;
    struct rusage usage;
    int status;
    if (argc < 4) {
        fputs("usage: bench-timer STDERR EXECUTABLE ARGV0 [ARGS...]\n", stderr);
        return 2;
    }
    int err = open(argv[1], O_WRONLY | O_CREAT | O_APPEND, 0644);
    int null = open("/dev/null", O_WRONLY);
    if (err < 0 || null < 0 || clock_gettime(CLOCK_MONOTONIC, &start) < 0) {
        perror("bench-timer setup");
        return 2;
    }
    pid_t child = fork();
    if (child == 0) {
        if (dup2(null, STDOUT_FILENO) < 0 || dup2(err, STDERR_FILENO) < 0)
            _exit(126);
        close(err);
        close(null);
        execv(argv[2], &argv[3]);
        perror("execv");
        _exit(127);
    }
    close(err);
    close(null);
    if (child < 0) {
        perror("fork");
        return 2;
    }
    pid_t reaped;
    do {
        reaped = wait4(child, &status, 0, &usage);
    } while (reaped < 0 && errno == EINTR);
    if (reaped != child || clock_gettime(CLOCK_MONOTONIC, &end) < 0) {
        perror("bench-timer wait");
        return 2;
    }
    int exit_code = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
    double wall = (end.tv_sec - start.tv_sec) * 1000.0 + (end.tv_nsec - start.tv_nsec) / 1000000.0;
    printf("%.6f %.3f %.3f %ld %ld %ld %d\n", wall, milliseconds(usage.ru_utime),
           milliseconds(usage.ru_stime), usage.ru_maxrss, usage.ru_majflt, usage.ru_minflt, exit_code);
    return 0;
}
