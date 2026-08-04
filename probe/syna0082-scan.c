#define _POSIX_C_SOURCE 200809L

#include <libusb.h>

#include "syna0082-protocol.h"

#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include <unistd.h>

#define SYNA0082_VENDOR_ID 0x06cb
#define SYNA0082_PRODUCT_ID 0x0082
#define SYNA0082_INTERFACE 0
#define SYNA0082_EP_OUT 0x01
#define SYNA0082_EP_IN 0x81
#define SYNA0082_EP_INTERRUPT 0x83
#define SYNA0082_BULK_TIMEOUT_MS 3000
#define SYNA0082_INTERRUPT_TIMEOUT_MS 30000
#define SYNA0082_CONFIG_06_LENGTH 10501U
#define SYNA0082_SCAN_02_LENGTH 18869U
#define SYNA0082_SCAN_RESPONSE_LENGTH 2154U
#define SYNA0082_IMAGE_RESPONSE_LENGTH 8082U

typedef struct
{
  const char *blob_dir;
  const char *output;
  bool omit_config_06;
  bool flip_config_06_last_bit;
  bool flip_config_06_header_bit;
  bool flip_config_06_envelope_bit;
  bool flip_config_06_body_bit;
} Options;

typedef struct
{
  int done;
  enum libusb_transfer_status status;
  int actual_length;
} BulkRead;

static bool
parse_options (int argc, char **argv, Options *options)
{
  bool acknowledged = false;

  memset (options, 0, sizeof (*options));
  for (int i = 1; i < argc; i++)
    {
      if (strcmp (argv[i], "--blob-dir") == 0 && i + 1 < argc)
        options->blob_dir = argv[++i];
      else if (strcmp (argv[i], "--output") == 0 && i + 1 < argc)
        options->output = argv[++i];
      else if (strcmp (argv[i],
                       "--i-understand-device-state-will-change") == 0)
        acknowledged = true;
      else if (strcmp (argv[i], "--experimental-omit-config-06") == 0)
        options->omit_config_06 = true;
      else if (strcmp (argv[i],
                       "--experimental-flip-config-06-last-bit") == 0)
        options->flip_config_06_last_bit = true;
      else if (strcmp (argv[i],
                       "--experimental-flip-config-06-header-bit") == 0)
        options->flip_config_06_header_bit = true;
      else if (strcmp (argv[i],
                       "--experimental-flip-config-06-envelope-bit") == 0)
        options->flip_config_06_envelope_bit = true;
      else if (strcmp (argv[i],
                       "--experimental-flip-config-06-body-bit") == 0)
        options->flip_config_06_body_bit = true;
      else
        return false;
    }

  unsigned int experiments = options->omit_config_06 +
                             options->flip_config_06_last_bit +
                             options->flip_config_06_header_bit +
                             options->flip_config_06_envelope_bit +
                             options->flip_config_06_body_bit;
  return acknowledged && options->blob_dir != NULL && options->output != NULL &&
         experiments <= 1;
}

static bool
load_blob (const char *directory,
           const char *name,
           uint8_t    *buffer,
           size_t      expected_length,
           uint8_t     expected_command)
{
  char path[4096];
  FILE *file;
  size_t length;
  int trailing;

  if (snprintf (path, sizeof (path), "%s/%s", directory, name) >=
      (int) sizeof (path))
    {
      fputs ("blob path is too long\n", stderr);
      return false;
    }

  file = fopen (path, "rb");
  if (file == NULL)
    {
      fprintf (stderr, "could not open %s: %s\n", path, strerror (errno));
      return false;
    }
  length = fread (buffer, 1, expected_length, file);
  trailing = fgetc (file);
  if (ferror (file))
    {
      fprintf (stderr, "could not read %s\n", path);
      fclose (file);
      return false;
    }
  fclose (file);

  if (length != expected_length || trailing != EOF)
    {
      fprintf (stderr,
               "%s has an unexpected length (read %zu, expected %zu)\n",
               path,
               length,
               expected_length);
      return false;
    }
  if (buffer[0] != expected_command)
    {
      fprintf (stderr,
               "%s begins with %02x, expected %02x\n",
               path,
               buffer[0],
               expected_command);
      return false;
    }
  return true;
}

static bool
bulk_write (libusb_device_handle *handle,
            const uint8_t        *data,
            size_t                length,
            const char           *name)
{
  int transferred = 0;
  int result;

  if (length > (size_t) INT32_MAX)
    return false;
  result = libusb_bulk_transfer (handle,
                                 SYNA0082_EP_OUT,
                                 (unsigned char *) data,
                                 (int) length,
                                 &transferred,
                                 SYNA0082_BULK_TIMEOUT_MS);
  if (result != LIBUSB_SUCCESS || transferred != (int) length)
    {
      fprintf (stderr,
               "%s write failed: %s, transferred=%d/%zu\n",
               name,
               libusb_error_name (result),
               transferred,
               length);
      return false;
    }
  return true;
}

static bool
bulk_read_exact (libusb_device_handle *handle,
                 uint8_t              *data,
                 size_t                expected_length,
                 const char           *name)
{
  int transferred = 0;
  int result;

  if (expected_length > (size_t) INT32_MAX)
    return false;
  result = libusb_bulk_transfer (handle,
                                 SYNA0082_EP_IN,
                                 data,
                                 (int) expected_length,
                                 &transferred,
                                 SYNA0082_BULK_TIMEOUT_MS);
  if (result != LIBUSB_SUCCESS || transferred != (int) expected_length)
    {
      fprintf (stderr,
               "%s read failed: %s, transferred=%d/%zu\n",
               name,
               libusb_error_name (result),
               transferred,
               expected_length);
      return false;
    }
  return true;
}

static bool
exchange (libusb_device_handle *handle,
          const uint8_t        *request,
          size_t                request_length,
          uint8_t              *response,
          size_t                response_length,
          const char           *name)
{
  if (!bulk_write (handle, request, request_length, name) ||
      !bulk_read_exact (handle, response, response_length, name))
    return false;
  printf ("stage=%s response_length=%zu\n", name, response_length);
  fflush (stdout);
  return true;
}

static bool
operation_control_start (libusb_device_handle *handle)
{
  uint8_t response[2];
  int transferred = libusb_control_transfer (handle,
                                             0xc0,
                                             0x14,
                                             0,
                                             0,
                                             response,
                                             sizeof (response),
                                             SYNA0082_BULK_TIMEOUT_MS);

  if (transferred != 2)
    {
      fprintf (stderr,
               "operation control transfer failed: %s, transferred=%d/2\n",
               transferred < 0 ? libusb_error_name (transferred) : "short read",
               transferred);
      return false;
    }
  if (response[0] != 0 || response[1] != 0)
    {
      fprintf (stderr,
               "operation control transfer returned %02x%02x\n",
               response[0],
               response[1]);
      return false;
    }
  puts ("stage=operation-control response_length=2");
  fflush (stdout);
  return true;
}

static bool
wait_for_capture_event (libusb_device_handle *handle)
{
  uint8_t event[16];

  puts ("Place a finger on the external reader.");
  fflush (stdout);
  for (unsigned int attempt = 0; attempt < 20; attempt++)
    {
      int transferred = 0;
      int result = libusb_interrupt_transfer (handle,
                                              SYNA0082_EP_INTERRUPT,
                                              event,
                                              sizeof (event),
                                              &transferred,
                                              SYNA0082_INTERRUPT_TIMEOUT_MS);
      if (result == LIBUSB_ERROR_TIMEOUT)
        continue;
      if (result != LIBUSB_SUCCESS)
        {
          fprintf (stderr,
                   "interrupt read failed: %s\n",
                   libusb_error_name (result));
          return false;
        }

      printf ("event=");
      for (int i = 0; i < transferred; i++)
        printf ("%02x", event[i]);
      putchar ('\n');
      fflush (stdout);

      if (transferred == 5 && event[0] == 0x03 &&
          (event[1] == 0x42 || event[1] == 0x43) && event[2] == 0x04)
        return true;
    }

  fputs ("timed out waiting for a capture-ready event\n", stderr);
  return false;
}

static void LIBUSB_CALL
bulk_read_callback (struct libusb_transfer *transfer)
{
  BulkRead *read = transfer->user_data;

  read->status = transfer->status;
  read->actual_length = transfer->actual_length;
  read->done = 1;
}

static bool
capture_image (libusb_context       *context,
               libusb_device_handle *handle,
               const uint8_t        *command,
               size_t                command_length,
               uint8_t              *response,
               size_t                response_length)
{
  struct timeval timeout = { .tv_sec = 1, .tv_usec = 0 };
  struct libusb_transfer *transfer = NULL;
  BulkRead read = { 0 };
  bool ok = false;
  int result;

  transfer = libusb_alloc_transfer (0);
  if (transfer == NULL)
    {
      fputs ("could not allocate image transfer\n", stderr);
      return false;
    }
  libusb_fill_bulk_transfer (transfer,
                             handle,
                             SYNA0082_EP_IN,
                             response,
                             (int) response_length,
                             bulk_read_callback,
                             &read,
                             5000);
  puts ("stage=image-read-submit-start");
  fflush (stdout);
  result = libusb_submit_transfer (transfer);
  if (result != LIBUSB_SUCCESS)
    {
      fprintf (stderr,
               "could not submit image transfer: %s\n",
               libusb_error_name (result));
      goto out;
    }
  puts ("stage=image-read-submit-complete");
  fflush (stdout);

  puts ("stage=image-command-write-start");
  fflush (stdout);
  if (!bulk_write (handle, command, command_length, "capture-image"))
    goto cancel;
  puts ("stage=image-command-write-complete");
  fflush (stdout);

  while (!read.done)
    {
      result = libusb_handle_events_timeout_completed (context,
                                                       &timeout,
                                                       &read.done);
      if (result != LIBUSB_SUCCESS && result != LIBUSB_ERROR_INTERRUPTED)
        {
          fprintf (stderr,
                   "image event handling failed: %s\n",
                   libusb_error_name (result));
          goto cancel;
        }
    }
  if (read.status != LIBUSB_TRANSFER_COMPLETED ||
      read.actual_length != (int) response_length)
    {
      fprintf (stderr,
               "image transfer failed: status=%d, transferred=%d/%zu\n",
               read.status,
               read.actual_length,
               response_length);
      goto out;
    }

  printf ("stage=capture-image response_length=%zu\n", response_length);
  fflush (stdout);
  ok = true;
  goto out;

cancel:
  if (!read.done)
    {
      result = libusb_cancel_transfer (transfer);
      if (result == LIBUSB_SUCCESS)
        while (!read.done)
          libusb_handle_events_timeout_completed (context,
                                                  &timeout,
                                                  &read.done);
    }

out:
  libusb_free_transfer (transfer);
  return ok;
}

static bool
write_pgm (const char *path, const Syna0082Image *image)
{
  int descriptor = open (path, O_WRONLY | O_CREAT | O_EXCL, 0600);
  FILE *file;
  bool ok = false;

  if (descriptor < 0)
    {
      fprintf (stderr, "could not create %s: %s\n", path, strerror (errno));
      return false;
    }
  file = fdopen (descriptor, "wb");
  if (file == NULL)
    {
      fprintf (stderr, "fdopen failed: %s\n", strerror (errno));
      close (descriptor);
      return false;
    }

  if (fprintf (file, "P5\n%u %u\n255\n", image->width, image->height) < 0 ||
      fwrite (image->pixels, 1, image->pixels_len, file) != image->pixels_len)
    fprintf (stderr, "could not write %s\n", path);
  else
    ok = true;

  if (fclose (file) != 0)
    {
      fprintf (stderr, "could not close %s: %s\n", path, strerror (errno));
      ok = false;
    }
  return ok;
}

int
main (int argc, char **argv)
{
  static const uint8_t command_1a[] = { 0x1a };
  static const uint8_t command_01[] = { 0x01 };
  static const uint8_t command_19[] = { 0x19 };
  static const uint8_t command_75[] = { 0x75 };
  static const uint8_t command_51[] = { 0x51, 0x00, 0x20, 0x00, 0x00 };
  Options options;
  uint8_t config_39[SYNA0082_SCAN_CONFIG_SIZE];
  uint8_t config_06[SYNA0082_CONFIG_06_LENGTH];
  uint8_t scan_02[SYNA0082_SCAN_02_LENGTH];
  uint8_t response[SYNA0082_IMAGE_RESPONSE_LENGTH];
  libusb_context *context = NULL;
  libusb_device_handle *handle = NULL;
  Syna0082Image image;
  bool claimed = false;
  int result;
  int exit_code = 1;

  if (!parse_options (argc, argv, &options))
    {
      fprintf (stderr,
               "usage: %s --blob-dir DIR --output IMAGE.pgm "
               "[--experimental-omit-config-06] "
               "[--experimental-flip-config-06-last-bit] "
               "[--experimental-flip-config-06-header-bit] "
               "[--experimental-flip-config-06-envelope-bit] "
               "[--experimental-flip-config-06-body-bit] "
               "--i-understand-device-state-will-change\n",
               argv[0]);
      return 2;
    }
  syna0082_build_scan_config_v1 (config_39);
  if ((!options.omit_config_06 &&
       !load_blob (options.blob_dir,
                   "config-06.bin",
                   config_06,
                   sizeof (config_06),
                   0x06)) ||
      !load_blob (options.blob_dir,
                  "scan-matrix-02.bin",
                  scan_02,
                  sizeof (scan_02),
                  0x02))
    return 1;

  if (options.flip_config_06_last_bit)
    {
      config_06[sizeof (config_06) - 1] ^= 0x01;
      fputs ("experiment=flip-config-06-last-bit offset=10500 mask=01\n",
             stderr);
    }
  else if (options.flip_config_06_header_bit)
    {
      config_06[4] ^= 0x01;
      fputs ("experiment=flip-config-06-header-bit message-offset=4 "
             "payload-offset=3 mask=01\n", stderr);
    }
  else if (options.flip_config_06_envelope_bit)
    {
      config_06[5] ^= 0x01;
      fputs ("experiment=flip-config-06-envelope-bit message-offset=5 "
             "payload-offset=4 mask=01\n", stderr);
    }
  else if (options.flip_config_06_body_bit)
    {
      config_06[261] ^= 0x01;
      fputs ("experiment=flip-config-06-body-bit message-offset=261 "
             "payload-offset=260 mask=01\n", stderr);
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

  if (!operation_control_start (handle) ||
      !exchange (handle,
                 command_1a,
                 sizeof (command_1a),
                 response,
                 2,
                 "operation-start") ||
      !exchange (handle,
                 command_01,
                 sizeof (command_01),
                 response,
                 38,
                 "device-information") ||
      !exchange (handle,
                 command_19,
                 sizeof (command_19),
                 response,
                 68,
                 "capabilities-status") ||
      !exchange (handle,
                 command_75,
                 sizeof (command_75),
                 response,
                 10,
                 "sensor-status") ||
      !exchange (handle,
                 config_39,
                 sizeof (config_39),
                 response,
                 2,
                 "config-39") ||
      (!options.omit_config_06 &&
       !exchange (handle,
                  config_06,
                  sizeof (config_06),
                  response,
                  2,
                  "config-06")))
    goto out;

  if (!exchange (handle,
                 scan_02,
                 sizeof (scan_02),
                 response,
                 SYNA0082_SCAN_RESPONSE_LENGTH,
                 "scan-matrix-02") ||
      !wait_for_capture_event (handle))
    goto out;

  if (!capture_image (context,
                      handle,
                      command_51,
                      sizeof (command_51),
                      response,
                      SYNA0082_IMAGE_RESPONSE_LENGTH))
    goto out;

  result = syna0082_parse_image (response, sizeof (response), &image);
  if (result != SYNA0082_PARSE_OK)
    {
      fprintf (stderr, "image parse failed: result=%d\n", result);
      goto out;
    }
  if (!write_pgm (options.output, &image))
    goto out;

  printf ("saved=%s width=%u height=%u pixels=%zu metadata=",
          options.output,
          image.width,
          image.height,
          image.pixels_len);
  for (size_t i = 0; i < sizeof (image.metadata); i++)
    printf ("%02x", image.metadata[i]);
  putchar ('\n');
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
