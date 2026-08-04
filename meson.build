project(
  'syna0082-research',
  'c',
  version: '0.1.0',
  default_options: ['c_std=c11', 'warning_level=3', 'werror=true'],
)

libusb = dependency('libusb-1.0', version: '>=1.0.26')

syna0082_protocol = static_library(
  'syna0082-protocol',
  'probe/syna0082-protocol.c',
)

executable(
  'syna0082-info',
  'probe/syna0082-info.c',
  dependencies: libusb,
  install: false,
)

test(
  'syna0082-protocol',
  executable(
    'test-syna0082-protocol',
    'probe/test-syna0082-protocol.c',
    link_with: syna0082_protocol,
  ),
)
