#include <stdio.h>

#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>

int main(int argc, char **argv)
{
    int fd;
    int flag = 0;

    printf("Test\n");

    if(0 > (fd = open("/dev/wlan_mgmt", O_RDWR))) {
        printf("wlan_mgmt device not exists\n");
        return -1;
    }

    if(0x00 != ioctl(fd, 1, &flag)) {
        printf("ioctl failed\n");
    }

    printf("flag 0x%x\n", flag);

    close(fd);

    return 0;
}
