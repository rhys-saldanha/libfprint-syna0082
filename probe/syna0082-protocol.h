#pragma once

#include <stddef.h>
#include <stdint.h>

#define SYNA0082_IMAGE_HEADER_SIZE 18U
#define SYNA0082_SCAN_CONFIG_SIZE 125U

typedef enum
{
  SYNA0082_PARSE_OK = 0,
  SYNA0082_PARSE_TOO_SHORT,
  SYNA0082_PARSE_DEVICE_STATUS,
  SYNA0082_PARSE_LENGTH,
  SYNA0082_PARSE_DIMENSIONS,
} Syna0082ParseResult;

typedef struct
{
  uint16_t width;
  uint16_t height;
  uint8_t metadata[8];
  const uint8_t *pixels;
  size_t pixels_len;
} Syna0082Image;

Syna0082ParseResult syna0082_parse_image (const uint8_t *data,
                                           size_t         length,
                                           Syna0082Image *image);

void syna0082_build_scan_config_v1 (uint8_t output[SYNA0082_SCAN_CONFIG_SIZE]);
