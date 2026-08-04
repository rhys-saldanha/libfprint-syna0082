project(
  'syna0082-research',
  'c',
  version: '0.1.0',
  default_options: ['c_std=c11', 'warning_level=3', 'werror=true'],
)

libusb = dependency('libusb-1.0', version: '>=1.0.26')

executable(
  'syna0082-info',
  'probe/syna0082-info.c',
  dependencies: libusb,
  install: false,
)
