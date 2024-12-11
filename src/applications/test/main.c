#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/vfs.h>

#include <fcntl.h>
#include <sys/ioctl.h>

void test_statfs(const char *path) {
#define MISC_DEV_CMD_GET_FS_STAT (0x1024 + 9)
#define FS_STAT_PATH_LENGTH 32

  struct statfs_wrap {
    char path[FS_STAT_PATH_LENGTH];
    struct statfs stat;
  };

  int fd = -1;
  struct statfs_wrap wrap;

  strncpy(&wrap.path[0], path, FS_STAT_PATH_LENGTH);

  if (0 < (fd = open("/dev/canmv_misc", O_RDWR))) {
    if (0x00 != ioctl(fd, MISC_DEV_CMD_GET_FS_STAT, &wrap)) {
      printf("ioctl failed.\n");
      return;
    }

    printf("Filesystem statistics for path: %s\n", path);
    printf("====================================\n");
    printf("Filesystem type: 0x%lX\n", (unsigned long)wrap.stat.f_type);
    printf("Block size: %lu bytes\n", (unsigned long)wrap.stat.f_bsize);
    printf("Total blocks: %lu\n", (unsigned long)wrap.stat.f_blocks);
    printf("Free blocks: %lu\n", (unsigned long)wrap.stat.f_bfree);
    printf("Available blocks: %lu\n", (unsigned long)wrap.stat.f_bavail);
    printf("Total file nodes: %lu\n", (unsigned long)wrap.stat.f_files);
    printf("Free file nodes: %lu\n", (unsigned long)wrap.stat.f_ffree);
    printf("Maximum length of filenames: %lu\n",
           (unsigned long)wrap.stat.f_namelen);
  }
}

int main(int argc, char *argv[]) {
  if (argc != 2) {
    fprintf(stderr, "Usage: %s <path>\n", argv[0]);
    return 1;
  }

  const char *path = argv[1];
  test_statfs(path);

  return 0;
}
