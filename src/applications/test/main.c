#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "autoconf.h"

#include "mpi_connector_api.h"

int main(int argc, char **argv)
{
    k_connector_info info;

    kd_mpi_get_connector_info(0, &info);

    return 0;
}
