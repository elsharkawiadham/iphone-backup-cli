#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr, "Usage: launcher FD EXECUTABLE [ARGS...]\n");
        return 64;
    }

    errno = 0;
    char *end = NULL;
    long parsed = strtol(argv[1], &end, 10);

    if (
        errno != 0 ||
        end == argv[1] ||
        *end != '\0' ||
        parsed < 0 ||
        parsed > INT_MAX
    ) {
        fprintf(stderr, "Invalid directory descriptor\n");
        return 65;
    }

    int fd = (int)parsed;
    struct stat info;

    if (fstat(fd, &info) != 0 || !S_ISDIR(info.st_mode)) {
        fprintf(stderr, "Descriptor is not an open directory\n");
        return 66;
    }

    if (fchdir(fd) != 0) {
        perror("fchdir");
        return 72;
    }

    if (close(fd) != 0) {
        perror("close");
        return 74;
    }

    if (argv[2][0] != '/') {
        fprintf(stderr, "Executable path must be absolute\n");
        return 67;
    }

    execv(argv[2], &argv[2]);

    perror("execv");
    return 73;
}
