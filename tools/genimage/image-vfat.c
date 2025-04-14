/*
 * Copyright (c) 2012 Michael Olbrich <m.olbrich@pengutronix.de>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2
 * as published by the Free Software Foundation.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

#include <confuse.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>

#include <sys/stat.h>

#include "genimage.h"

#define FAT32_MASK 0x0FFFFFFF

uint32_t read_le32(FILE *fp, long offset) {
    uint8_t b[4];
    fseek(fp, offset, SEEK_SET);
    fread(b, 1, 4, fp);
    return b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24);
}

uint16_t read_le16(FILE *fp, long offset) {
    uint8_t b[2];
    fseek(fp, offset, SEEK_SET);
    fread(b, 1, 2, fp);
    return b[0] | (b[1] << 8);
}

static long long find_last_valid_pos(struct image *image) {
    FILE *fp = fopen(imageoutfile(image), "rb");
    if (!fp) {
		image_error(image, "open image output file (%s) failed.\n", imageoutfile(image));
        return -1;
    }

    // --- Read boot sector ---
    fseek(fp, 11, SEEK_SET);
    uint16_t bytes_per_sector = read_le16(fp, 11);
    uint8_t sectors_per_cluster;
    fread(&sectors_per_cluster, 1, 1, fp);
    uint16_t reserved_sectors = read_le16(fp, 14);
    uint8_t num_fats;
    fread(&num_fats, 1, 1, fp);
    uint16_t root_entry_count = read_le16(fp, 17);
    uint16_t total_sectors_16 = read_le16(fp, 19);
    uint32_t sectors_per_fat_32 = read_le32(fp, 36); // FAT32 location
    uint32_t total_sectors_32 = read_le32(fp, 32);
    uint32_t root_cluster = read_le32(fp, 44); // Usually cluster 2

    // FAT size
    uint32_t sectors_per_fat = sectors_per_fat_32;
    uint32_t total_sectors = total_sectors_16 ? total_sectors_16 : total_sectors_32;

    uint32_t fat_offset = reserved_sectors * bytes_per_sector;
    uint32_t fat_size_bytes = sectors_per_fat * bytes_per_sector;
    uint32_t cluster_size_bytes = sectors_per_cluster * bytes_per_sector;

    // Data region offset (FAT32: root dir is in data region)
    uint32_t data_region_offset = (reserved_sectors + num_fats * sectors_per_fat) * bytes_per_sector;

    // Number of FAT entries = fat size / 4
    uint32_t num_entries = fat_size_bytes / 4;

    uint32_t last_used_cluster = 0;

    for (uint32_t cluster = 2; cluster < num_entries; cluster++) {
        uint32_t fat_entry = read_le32(fp, fat_offset + cluster * 4) & FAT32_MASK;
        if (fat_entry != 0x00000000 && fat_entry < 0x0FFFFFF8) {
            last_used_cluster = cluster;
        }
    }

	fclose(fp);

    if (0x00 == last_used_cluster) {
		image_error(image, "No used clusters found.\n");
        return -1;
    }

	return data_region_offset + last_used_cluster * cluster_size_bytes;
}

static int vfat_generate(struct image *image)
{
	int ret;
	struct partition *part;
	char *extraargs = cfg_getstr(image->imagesec, "extraargs");
	char *label = cfg_getstr(image->imagesec, "label");
	cfg_bool_t minimize = cfg_getbool(image->imagesec, "minimize");

	if (label && label[0] != '\0')
		xasprintf(&label, "-n '%s'", label);
	else
		label = "";

	ret = prepare_image(image, image->size);
	if (ret)
		return ret;

	ret = systemp(image, "%s %s %s '%s'", get_opt("mkdosfs"),
			extraargs, label, imageoutfile(image));
	if (ret)
		return ret;

	list_for_each_entry(part, &image->partitions, list) {
		struct image *child = image_get(part->image);
		const char *file = imageoutfile(child);
		const char *target = part->name;
		char *path = strdupa(target);
		char *next = path;

		while ((next = strchr(next, '/')) != NULL) {
			*next = '\0';
			/* ignore the error: mdd fails if the target exists. */
			systemp(image, "MTOOLS_SKIP_CHECK=1 %s -DsS -i %s '::%s'",
				get_opt("mmd"), imageoutfile(image), path);
			*next = '/';
			++next;
		}

		image_info(image, "adding file '%s' as '%s' ...\n",
				child->file, *target ? target : child->file);
		ret = systemp(image, "MTOOLS_SKIP_CHECK=1 %s -sp -i '%s' '%s' '::%s'",
				get_opt("mcopy"), imageoutfile(image),
				file, target);
		if (ret)
			return ret;
	}
	if (!list_empty(&image->partitions))
		return 0;

	if (!image->empty)
		ret = systemp(image, "MTOOLS_SKIP_CHECK=1 %s -sp -i '%s' '%s'/* ::",
				get_opt("mcopy"), imageoutfile(image), mountpath(image));

	if(minimize) {
		long long offset = find_last_valid_pos(image);

		struct stat s;
		stat(imageoutfile(image), &s);
	
		if(0 < offset) {
			image_info(image, "minimize image size %lu to %llu\n", s.st_size, offset);
			image->size = offset;
		}
	}

	return ret;
}

static int vfat_setup(struct image *image, cfg_t *cfg)
{
	char *label = cfg_getstr(image->imagesec, "label");

	if (!image->size) {
		image_error(image, "no size given or must not be zero\n");
		return -EINVAL;
	}

	if (label && strlen(label) > 11) {
		image_error(image, "vfat volume name cannot be longer than 11 characters\n");
		return -EINVAL;
	}

	return 0;
}

static int vfat_parse(struct image *image, cfg_t *cfg)
{
	unsigned int i;
	unsigned int num_files;
	struct partition *part;

	num_files = cfg_size(cfg, "file");
	for (i = 0; i < num_files; i++) {
		cfg_t *filesec = cfg_getnsec(cfg, "file", i);
		part = xzalloc(sizeof *part);
		part->name = cfg_title(filesec);
		part->image = cfg_getstr(filesec, "image");
		list_add_tail(&part->list, &image->partitions);
	}

	for(i = 0; i < cfg_size(cfg, "files"); i++) {
		part = xzalloc(sizeof *part);
		part->image = cfg_getnstr(cfg, "files", i);
		part->name = "";
		list_add_tail(&part->list, &image->partitions);
	}

	return 0;
}

static cfg_opt_t file_opts[] = {
	CFG_STR("image", NULL, CFGF_NONE),
	CFG_END()
};

static cfg_opt_t vfat_opts[] = {
	CFG_STR("extraargs", "", CFGF_NONE),
	CFG_STR("label", "", CFGF_NONE),
	CFG_STR_LIST("files", NULL, CFGF_NONE),
	CFG_SEC("file", file_opts, CFGF_MULTI | CFGF_TITLE),
	CFG_BOOL("minimize", 0, CFGF_NONE),
	CFG_END()
};

struct image_handler vfat_handler = {
	.type = "vfat",
	.generate = vfat_generate,
	.setup = vfat_setup,
	.parse = vfat_parse,
	.opts = vfat_opts,
};
