#include <confuse.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>

#include <sys/stat.h>

#include "genimage.h"

/**
Usage: ../mkuffs [options]
  -h  --help                                show usage
  -c  --command-line                        command line mode
  -v  --verbose                             verbose mode
  -f  --file           <file>               uffs image file
  -p  --page-size      <n>                  page data size, default=2048
  -s  --spare-size     <n>                  page spare size, default=64
  -o  --status-offset  <n>                  status byte offset, default=0
  -b  --block-pages    <n>                  pages per block, default=64
  -t  --total-blocks   <n>                  total blocks
  -m  --mount          <mount_point,start,end> , for example: -m /,0,-1
  -x  --ecc-option     <none|soft|hw|auto>  ECC option, default=auto
  -z  --ecc-size       <n>                  ECC size, default=0 (auto)
  -e  --exec           <file>               execute a script file
*/
static int uffs_generate(struct image *image)
{
    int ret;
	struct stat s;
	char *extraargs = cfg_getstr(image->imagesec, "extraargs");
    const char *ecc_opt[] = {"none", "soft", "hw", "auto"};

    unsigned long long part_size = cfg_getint_suffix(image->imagesec, "size");

    if(part_size % (image->flash_type->page_size * image->flash_type->block_pages)) {
        image_error(image, "image size (%lld) is invalid, should align to (%d)\n", 
            part_size, image->flash_type->page_size * image->flash_type->block_pages);
        return -EINVAL;
    }

    remove(imageoutfile(image));

    ret = systemp(image, "%s -f %s -p %d -s %d -b %d -t %lld -x %s -o 0 -d %s %s",
            get_opt("mkuffs"),
            imageoutfile(image),
            image->flash_type->page_size,
            image->flash_type->spare_size,
            image->flash_type->block_pages,
            part_size / (image->flash_type->page_size * image->flash_type->block_pages),
            ecc_opt[image->flash_type->ecc_option],
            mountpath(image),
            extraargs);

    image_info(image, "Generate %s (%d)\n", (0x00 == ret) ? "success" : "failed", ret);

	if(0x00 == stat(imageoutfile(image), &s)) {
		image->size = s.st_size;
	}

    return ret;
}

static int uffs_setup(struct image *image, cfg_t *cfg)
{
    if (!image->flash_type) {
        image_error(image, "no flash type given\n");
        return -EINVAL;
    }

    if(!image->flash_type->is_uffs) {
        image_error(image, "not uffs flash type given\n");
        return -EINVAL;
    }

    if((0x00 == image->flash_type->page_size) || \
        (0x00 == image->flash_type->block_pages) || \
        (0x00 == image->flash_type->total_blocks))
    {
        image_error(image, "invalid page-size (%d) or block-pages (%d) or total-blocks (%d) in %s\n",
            image->flash_type->page_size, image->flash_type->block_pages,
            image->flash_type->total_blocks, image->flash_type->name);
        return -EINVAL;
    }

    if(3 < image->flash_type->ecc_option) {
        image_error(image, "invalid uffs flash ecc option given\n");
        return -EINVAL;
    }

    return 0;
}

static cfg_opt_t uffs_opts[] = {
	CFG_STR("extraargs", "", CFGF_NONE),
	CFG_STR("size", "", CFGF_NONE),
    CFG_END()
};

struct image_handler uffs_handler = {
    .type = "uffs",
    .generate = uffs_generate,
    .setup = uffs_setup,
    .opts = uffs_opts,
};
