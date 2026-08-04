#include "syna0082-protocol.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

#define IMAGE_WIDTH 56U
#define IMAGE_HEIGHT 144U
#define IMAGE_PIXELS (IMAGE_WIDTH * IMAGE_HEIGHT)
#define RESPONSE_SIZE (SYNA0082_IMAGE_HEADER_SIZE + IMAGE_PIXELS)

static void
make_valid_response (uint8_t response[RESPONSE_SIZE])
{
  const uint32_t declared_length = RESPONSE_SIZE - 6U;

  memset (response, 0, RESPONSE_SIZE);
  response[2] = (uint8_t) declared_length;
  response[3] = (uint8_t) (declared_length >> 8);
  response[4] = (uint8_t) (declared_length >> 16);
  response[5] = (uint8_t) (declared_length >> 24);
  response[6] = (uint8_t) IMAGE_WIDTH;
  response[7] = (uint8_t) (IMAGE_WIDTH >> 8);
  response[8] = (uint8_t) IMAGE_HEIGHT;
  response[9] = (uint8_t) (IMAGE_HEIGHT >> 8);
  response[10] = 0x4d;
  response[11] = 0x01;
  response[12] = 0x08;
  response[16] = 0x20;
  response[17] = 0x80;
  response[SYNA0082_IMAGE_HEADER_SIZE] = 0x12;
  response[RESPONSE_SIZE - 1] = 0x34;
}

int
main (void)
{
  uint8_t response[RESPONSE_SIZE];
  uint8_t config[SYNA0082_SCAN_CONFIG_SIZE];
  Syna0082Image image = { 0 };

  syna0082_build_scan_config_v1 (config);
  assert (config[0] == 0x39);
  assert (config[1] == 0x20);
  assert (config[2] == 0xbf);
  assert (config[3] == 0x02);
  assert (config[5] == 0xff && config[6] == 0xff);
  assert (config[10] == 0xd1);
  assert (config[72] == 0x20);
  assert (config[124] == 0);

  make_valid_response (response);
  assert (syna0082_parse_image (response, sizeof (response), &image) ==
          SYNA0082_PARSE_OK);
  assert (image.width == IMAGE_WIDTH);
  assert (image.height == IMAGE_HEIGHT);
  assert (image.pixels_len == IMAGE_PIXELS);
  assert (image.metadata[0] == 0x4d);
  assert (image.metadata[6] == 0x20);
  assert (image.metadata[7] == 0x80);
  assert (image.pixels[0] == 0x12);
  assert (image.pixels[IMAGE_PIXELS - 1] == 0x34);

  assert (syna0082_parse_image (response, SYNA0082_IMAGE_HEADER_SIZE - 1,
                                &image) == SYNA0082_PARSE_TOO_SHORT);

  response[0] = 1;
  assert (syna0082_parse_image (response, sizeof (response), &image) ==
          SYNA0082_PARSE_DEVICE_STATUS);
  response[0] = 0;

  response[2]--;
  assert (syna0082_parse_image (response, sizeof (response), &image) ==
          SYNA0082_PARSE_LENGTH);
  response[2]++;

  response[6]--;
  assert (syna0082_parse_image (response, sizeof (response), &image) ==
          SYNA0082_PARSE_DIMENSIONS);

  return 0;
}
