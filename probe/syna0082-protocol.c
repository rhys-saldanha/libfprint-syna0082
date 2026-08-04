#include "syna0082-protocol.h"

#include <string.h>

static uint16_t
read_le16 (const uint8_t *data)
{
  return (uint16_t) data[0] | ((uint16_t) data[1] << 8);
}

static uint32_t
read_le32 (const uint8_t *data)
{
  return (uint32_t) data[0] |
         ((uint32_t) data[1] << 8) |
         ((uint32_t) data[2] << 16) |
         ((uint32_t) data[3] << 24);
}

void
syna0082_build_scan_config_v1 (uint8_t output[SYNA0082_SCAN_CONFIG_SIZE])
{
  static const struct
  {
    uint8_t offset;
    uint8_t value;
  } fields[] = {
    { 0, 0x39 }, { 1, 0x20 }, { 2, 0xbf }, { 3, 0x02 },
    { 5, 0xff }, { 6, 0xff }, { 9, 0x01 }, { 10, 0xd1 },
    { 12, 0x20 }, { 17, 0xd1 }, { 18, 0xd1 }, { 32, 0x20 },
    { 45, 0xff }, { 46, 0xff }, { 50, 0xd1 }, { 52, 0x20 },
    { 72, 0x20 },
  };
  size_t i;

  memset (output, 0, SYNA0082_SCAN_CONFIG_SIZE);
  for (i = 0; i < sizeof (fields) / sizeof (fields[0]); i++)
    output[fields[i].offset] = fields[i].value;
}

Syna0082ParseResult
syna0082_parse_image (const uint8_t *data,
                      size_t         length,
                      Syna0082Image *image)
{
  uint16_t status;
  uint16_t width;
  uint16_t height;
  uint32_t declared_length;
  size_t pixels_len;

  if (data == NULL || image == NULL || length < SYNA0082_IMAGE_HEADER_SIZE)
    return SYNA0082_PARSE_TOO_SHORT;

  status = read_le16 (data);
  if (status != 0)
    return SYNA0082_PARSE_DEVICE_STATUS;

  declared_length = read_le32 (data + 2);
  if ((size_t) declared_length != length - 6)
    return SYNA0082_PARSE_LENGTH;

  width = read_le16 (data + 6);
  height = read_le16 (data + 8);
  pixels_len = length - SYNA0082_IMAGE_HEADER_SIZE;
  if (width == 0 || height == 0 || (size_t) width * height != pixels_len)
    return SYNA0082_PARSE_DIMENSIONS;

  image->width = width;
  image->height = height;
  memcpy (image->metadata, data + 10, sizeof (image->metadata));
  image->pixels = data + SYNA0082_IMAGE_HEADER_SIZE;
  image->pixels_len = pixels_len;

  return SYNA0082_PARSE_OK;
}
