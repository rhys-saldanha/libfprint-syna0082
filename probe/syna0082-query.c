#include <libusb.h>

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define SYNA0082_VENDOR_ID 0x06cb
#define SYNA0082_PRODUCT_ID 0x0082
#define SYNA0082_INTERFACE 0
#define SYNA0082_EP_OUT 0x01
#define SYNA0082_EP_IN 0x81
#define SYNA0082_TIMEOUT_MS 1000

typedef struct
{
  const char *name;
  uint8_t command;
  int expected_length;
  uint8_t expected_prefix[5];
  size_t expected_prefix_length;
  bool parse_flash_info;
} Query;

static const Query queries[] = {
  {
    .name = "device information",
    .command = 0x01,
    .expected_length = 38,
    .expected_prefix = { 0x00, 0x00, 0x10, 0xb6, 0x04 },
    .expected_prefix_length = 5,
  },
  {
    .name = "capabilities/status",
    .command = 0x19,
    .expected_length = 68,
    /* The status fields vary with device state; validate only the framing. */
    .expected_prefix_length = 0,
  },
  {
    .name = "flash information",
    .command = 0x3e,
    /* The vendor API reserves 0x88 bytes; the wire response is variable. */
    .expected_length = -1,
    .expected_prefix = { 0x00, 0x00 },
    .expected_prefix_length = 2,
    .parse_flash_info = true,
  },
};

static uint16_t
read_le16 (const uint8_t *value)
{
  return (uint16_t) value[0] | (uint16_t) value[1] << 8;
}

static uint32_t
read_le32 (const uint8_t *value)
{
  return (uint32_t) value[0] |
         (uint32_t) value[1] << 8 |
         (uint32_t) value[2] << 16 |
         (uint32_t) value[3] << 24;
}

static bool
print_flash_info (const uint8_t *response,
                  size_t         response_length)
{
  const size_t status_size = 2;
  const size_t header_size = 14;
  const size_t partition_size = 12;
  const uint8_t *header;
  const uint8_t *partitions;
  uint16_t partition_count;

  if (response_length < status_size + header_size)
    return false;
  header = response + status_size;
  partitions = header + header_size;
  partition_count = read_le16 (header + 12);
  if (partition_count > (response_length - status_size - header_size) /
                        partition_size)
    {
      fprintf (stderr,
               "flash information declares %u truncated partitions\n",
               partition_count);
      return false;
    }

  printf ("flash_jedec=%04x:%04x blocks=%u unknown0=%u block_size=%u "
          "unknown1=%u partitions=%u\n",
          read_le16 (header),
          read_le16 (header + 2),
          read_le16 (header + 4),
          read_le16 (header + 6),
          read_le16 (header + 8),
          read_le16 (header + 10),
          partition_count);
  for (uint16_t index = 0; index < partition_count; index++)
    {
      const uint8_t *partition = partitions + index * partition_size;
      printf ("flash_partition=%u id=%u type=%u access=0x%04x "
              "offset=0x%08x size=0x%08x\n",
              index,
              partition[0],
              partition[1],
              read_le16 (partition + 2),
              read_le32 (partition + 4),
              read_le32 (partition + 8));
    }
  return true;
}

static bool
run_query (libusb_device_handle *handle,
           const Query          *query)
{
  uint8_t response[4096];
  int transferred = 0;
  int result;

  result = libusb_bulk_transfer (handle,
                                 SYNA0082_EP_OUT,
                                 (unsigned char *) &query->command,
                                 1,
                                 &transferred,
                                 SYNA0082_TIMEOUT_MS);
  if (result != LIBUSB_SUCCESS || transferred != 1)
    {
      fprintf (stderr,
               "%s write failed: %s, transferred=%d\n",
               query->name,
               libusb_error_name (result),
               transferred);
      return false;
    }

  transferred = 0;
  result = libusb_bulk_transfer (handle,
                                 SYNA0082_EP_IN,
                                 response,
                                 sizeof (response),
                                 &transferred,
                                 SYNA0082_TIMEOUT_MS);
  if (result != LIBUSB_SUCCESS)
    {
      fprintf (stderr,
               "%s read failed: %s\n",
               query->name,
               libusb_error_name (result));
      return false;
    }

  printf ("query=%s command=%02x response_length=%d response=",
          query->name,
          query->command,
          transferred);
  for (size_t i = 0; i < (size_t) transferred; i++)
    printf ("%02x", response[i]);
  putchar ('\n');

  if (query->expected_length >= 0 && transferred != query->expected_length)
    {
      fprintf (stderr,
               "%s returned %d bytes; expected %d\n",
               query->name,
               transferred,
               query->expected_length);
      return false;
    }
  if (query->expected_prefix_length > 0 &&
      memcmp (response,
              query->expected_prefix,
              query->expected_prefix_length) != 0)
    {
      fprintf (stderr, "%s returned an unexpected prefix\n", query->name);
      return false;
    }
  if (query->parse_flash_info &&
      !print_flash_info (response, (size_t) transferred))
    {
      fprintf (stderr, "%s response is malformed\n", query->name);
      return false;
    }
  return true;
}

int
main (int argc, char **argv)
{
  libusb_context *context = NULL;
  libusb_device_handle *handle = NULL;
  bool claimed = false;
  int result;
  int exit_code = 1;

  if (argc != 2 ||
      strcmp (argv[1], "--i-understand-read-only-usb-query") != 0)
    {
      fprintf (stderr,
               "This probe sends the read-only 0x01, 0x19, and 0x3e "
               "information queries.\n"
               "It does not reset, reconfigure, detach a kernel driver, or "
               "write calibration.\n"
               "Run only after explicit approval:\n"
               "  %s --i-understand-read-only-usb-query\n",
               argv[0]);
      return 2;
    }

  result = libusb_init (&context);
  if (result != LIBUSB_SUCCESS)
    {
      fprintf (stderr, "libusb_init failed: %s\n", libusb_error_name (result));
      goto out;
    }

  handle = libusb_open_device_with_vid_pid (context,
                                            SYNA0082_VENDOR_ID,
                                            SYNA0082_PRODUCT_ID);
  if (handle == NULL)
    {
      fputs ("could not open 06cb:0082\n", stderr);
      goto out;
    }

  result = libusb_kernel_driver_active (handle, SYNA0082_INTERFACE);
  if (result != 0)
    {
      fprintf (stderr,
               "refusing to detach active kernel driver (result=%d)\n",
               result);
      goto out;
    }

  result = libusb_claim_interface (handle, SYNA0082_INTERFACE);
  if (result != LIBUSB_SUCCESS)
    {
      fprintf (stderr,
               "claim interface failed: %s\n",
               libusb_error_name (result));
      goto out;
    }
  claimed = true;

  for (size_t i = 0; i < sizeof (queries) / sizeof (queries[0]); i++)
    {
      if (!run_query (handle, &queries[i]))
        goto out;
    }

  exit_code = 0;

out:
  if (claimed)
    libusb_release_interface (handle, SYNA0082_INTERFACE);
  if (handle != NULL)
    libusb_close (handle);
  if (context != NULL)
    libusb_exit (context);
  return exit_code;
}
