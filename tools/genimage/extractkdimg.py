import struct
import binascii
import os

# Define constants from C code
KDIMG_HADER_MAGIC = 0x27CB8F93
KDIMG_PART_MAGIC = 0x91DF6DA4
KDIMG_CONTENT_STAT_OFFSET = 64 * 1024

# Define structure formats for `kd_img_part_t` and `kd_img_hdr_t`
KD_IMG_PART_FMT = '7I32B32s'  # 4 uint32_t and 32-char part_name
KD_IMG_HDR_FMT = '5I32s32s64s'  # 4 uint32_t and 32-char image_info, chip_info, board_info

# Sizes based on the C code's ct_assert checks
KD_IMG_PART_SIZE = 256
KD_IMG_HDR_SIZE = 512

# Helper function to extract the part information
def extract_parts(image_data):
    # Read the header
    header = struct.unpack_from(KD_IMG_HDR_FMT, image_data, 0)

    img_hdr_magic, img_hdr_crc32, img_hdr_flag, part_tbl_num, part_tbl_crc32, image_info, chip_info, board_info = header
    assert img_hdr_magic == KDIMG_HADER_MAGIC, "Invalid image header magic"

    print(f"Image Info: {image_info.decode('utf-8').strip()}")
    print(f"Chip Info: {chip_info.decode('utf-8').strip()}")
    print(f"Board Info: {board_info.decode('utf-8').strip()}")

    # Parse the parts table (part_tbl_num parts)
    parts = []
    offset = KD_IMG_HDR_SIZE
    for i in range(part_tbl_num):
        part_data = image_data[offset:offset + KD_IMG_PART_SIZE]
        part = struct.unpack_from(KD_IMG_PART_FMT, part_data)

        # Unpack the fields correctly:
        part_magic = part[0]
        assert part_magic == KDIMG_PART_MAGIC, f"Invalid part magic for part {i}"

        part_offset = part[1]
        part_size = part[2]
        part_max_size = part[3]
        part_flag = part[4]
        part_content_offset = part[5]
        part_content_size = part[6]

        # Extract the 32-byte SHA-256 and part name
        part_content_sha256 = part[7 : 7 + 32]  # 32 bytes for SHA-256 hash
        part_name = part[39].rstrip(b'\x00').decode('utf-8')  # Remove trailing null bytes and decode

        print(f"Extracting part: {part_name}")
        print(f"  Offset: {part_offset}, Size: {part_size}, Content Offset: 0x{part_content_offset:x}({part_content_offset}), Content Size: {part_content_size}, Content Sha256: {binascii.hexlify(bytes(part_content_sha256))}")

        # Extract part content from the image data
        part_content = image_data[part_content_offset:part_content_offset + part_content_size]
        parts.append((part_name, part_content))

        offset += KD_IMG_PART_SIZE

    return parts

# Function to save extracted files
def save_extracted_parts(parts, output_dir='extracted_parts'):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    for part_name, part_content in parts:
        output_file = os.path.join(output_dir, f"{part_name}.bin")
        with open(output_file, 'wb') as f:
            f.write(part_content)
        print(f"Saved {part_name} to {output_file}")

# Function to decode the image and extract the files
def decode_image(image_path):
    with open(image_path, 'rb') as img_file:
        image_data = img_file.read()

    parts = extract_parts(image_data)
    save_extracted_parts(parts)

# Run the script
if __name__ == '__main__':
    import sys
    decode_image(sys.argv[1])
