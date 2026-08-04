// SPDX-License-Identifier: LGPL-2.1-or-later
// Descriptor-only inventory. This program never opens the USB device.

#include <libusb.h>
#include <stdint.h>
#include <stdio.h>

#define SYNA_VENDOR_ID 0x06cb
#define SYNA_PRODUCT_ID 0x0082

static const char *
transfer_type_name(uint8_t attributes)
{
  switch (attributes & LIBUSB_TRANSFER_TYPE_MASK)
    {
    case LIBUSB_TRANSFER_TYPE_CONTROL:
      return "control";
    case LIBUSB_TRANSFER_TYPE_ISOCHRONOUS:
      return "isochronous";
    case LIBUSB_TRANSFER_TYPE_BULK:
      return "bulk";
    case LIBUSB_TRANSFER_TYPE_INTERRUPT:
      return "interrupt";
    case LIBUSB_TRANSFER_TYPE_BULK_STREAM:
      return "bulk-stream";
    default:
      return "unknown";
    }
}

static void
print_configuration(const struct libusb_config_descriptor *config)
{
  printf("configuration=%u interfaces=%u attributes=0x%02x max_power_ma=%u\n",
         config->bConfigurationValue,
         config->bNumInterfaces,
         config->bmAttributes,
         config->MaxPower * 2U);

  for (uint8_t interface_index = 0;
       interface_index < config->bNumInterfaces;
       interface_index++)
    {
      const struct libusb_interface *interface = &config->interface[interface_index];

      for (int alt_index = 0; alt_index < interface->num_altsetting; alt_index++)
        {
          const struct libusb_interface_descriptor *alt =
            &interface->altsetting[alt_index];

          printf("interface=%u alternate=%u class=0x%02x subclass=0x%02x "
                 "protocol=0x%02x endpoints=%u\n",
                 alt->bInterfaceNumber,
                 alt->bAlternateSetting,
                 alt->bInterfaceClass,
                 alt->bInterfaceSubClass,
                 alt->bInterfaceProtocol,
                 alt->bNumEndpoints);

          for (uint8_t endpoint_index = 0;
               endpoint_index < alt->bNumEndpoints;
               endpoint_index++)
            {
              const struct libusb_endpoint_descriptor *endpoint =
                &alt->endpoint[endpoint_index];
              const char *direction =
                (endpoint->bEndpointAddress & LIBUSB_ENDPOINT_DIR_MASK) ==
                    LIBUSB_ENDPOINT_IN
                  ? "in"
                  : "out";

              printf("endpoint=0x%02x direction=%s type=%s max_packet=%u "
                     "interval=%u\n",
                     endpoint->bEndpointAddress,
                     direction,
                     transfer_type_name(endpoint->bmAttributes),
                     endpoint->wMaxPacketSize,
                     endpoint->bInterval);
            }
        }
    }
}

int
main(void)
{
  libusb_context *context = NULL;
  libusb_device **devices = NULL;
  ssize_t count;
  int result = libusb_init_context(&context, NULL, 0);

  if (result != LIBUSB_SUCCESS)
    {
      fprintf(stderr, "libusb initialization failed: %s\n",
              libusb_error_name(result));
      return 1;
    }

  count = libusb_get_device_list(context, &devices);
  if (count < 0)
    {
      fprintf(stderr, "USB enumeration failed: %s\n",
              libusb_error_name((int) count));
      libusb_exit(context);
      return 1;
    }

  for (ssize_t index = 0; index < count; index++)
    {
      struct libusb_device_descriptor descriptor;
      struct libusb_config_descriptor *config = NULL;

      result = libusb_get_device_descriptor(devices[index], &descriptor);
      if (result != LIBUSB_SUCCESS || descriptor.idVendor != SYNA_VENDOR_ID ||
          descriptor.idProduct != SYNA_PRODUCT_ID)
        continue;

      printf("device=%04x:%04x revision=%x.%02x bus=%u address=%u\n",
             descriptor.idVendor,
             descriptor.idProduct,
             descriptor.bcdDevice >> 8,
             descriptor.bcdDevice & 0xff,
             libusb_get_bus_number(devices[index]),
             libusb_get_device_address(devices[index]));

      result = libusb_get_active_config_descriptor(devices[index], &config);
      if (result != LIBUSB_SUCCESS)
        {
          fprintf(stderr, "Reading the active descriptor failed: %s\n",
                  libusb_error_name(result));
          libusb_free_device_list(devices, 1);
          libusb_exit(context);
          return 1;
        }

      print_configuration(config);
      libusb_free_config_descriptor(config);
      libusb_free_device_list(devices, 1);
      libusb_exit(context);
      return 0;
    }

  fprintf(stderr, "Synaptics 06cb:0082 was not found.\n");
  libusb_free_device_list(devices, 1);
  libusb_exit(context);
  return 2;
}
