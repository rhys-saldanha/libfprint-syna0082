# Windows reference driver

Collected on 2026-08-04 from Windows 11 IoT Enterprise LTSC
`10.0.26100`. Only hashes and metadata are retained; the proprietary binaries
remain in the Windows Driver Store and are not committed.

- Device: `Synaptics WBDI Fingerprint Reader - USB 052`
- USB ID: `06cb:0082`, revision `1.54`
- Provider: Synaptics Incorporated
- Driver: `5.5.4021.1052`, dated 2025-11-05
- Published INF: `oem40.inf`
- Original INF: `synawudfbiousbpqidongleprod.inf`
- Signer: Microsoft Windows Hardware Compatibility Publisher

| File | SHA-256 |
| --- | --- |
| `CheckFPDatabase.exe` | `C0662325D4765BB22D26619D6A701497EE6ED85D1036F9164F78BACD18D6F655` |
| `PQIFingerprintManager.exe` | `563F318BCB70A9AC76E7E3C3CB56DE4FEC9CCA22CFDDCB0102DB6754130D6257` |
| `synaBscAdapter52.dll` | `120A71174EE5E22C917E824498B5BCE3A5C85CCE7C40B5149E2752A17099231E` |
| `SynaCP52.dll` | `2CF085EC15CB5E0D900A27E4B7F20E11B71A92909034B568DE93324D67457F3F` |
| `SynaFPCoInstaller.dll` | `77A75124C92785A0A668FB7457CA57FD3C6729C1BF625E381105729059882920` |
| `synaUMDF.cat` | `9A24F6113D399BE1A3316CA1927FA2F55F30A5ED0E9090E93C990EA550BCD901` |
| `synaWudfBioUsb52.dll` | `50A9C36F9AFEFDE80921A17F92019877E5CFE083987C762F76398F9726C7029A` |
| `synaWudfBioUsbPQIDongleProd.inf` | `12E7B30F06A6FB3D4857BB97CBC42BB6F950B89C922042C7EBFFACD9E6E2EEAB` |
| `WudfUpdate_01011.dll` | `FCEEDF55343A78B4383B05D3E06B0B6F4F48CF4F6CF4406D4066FD388353E9FC` |

## Static capability inventory

`tools/syna0082_driver_inventory.py` reproduces a hash-only inventory from the
uncommitted DLL. The reference driver imports 16 CryptoAPI functions including
random generation, hashing, key import/export, encrypt/decrypt, signing, and
signature verification. It also imports nine BCrypt functions covering key
pairs, secret agreement, derivation, signing, and verification; 11 registry
functions; and `CreateFile`, `ReadFile`, and `WriteFile`.

Embedded diagnostic names include calibration backup, template-list updates,
database erase, ownership reset, and firmware update paths. This does not by
itself identify a USB opcode. It does show that the stable, high-entropy
10,501-byte `0x06` record must not be treated as an ordinary public constant
until its producer and security context are isolated.

The producer has since been narrowed further: captured `0x06` bytes 1 through
10,500 are a byte-identical contiguous `.rdata` table in this DLL. Run the
inventory with `--payload` to reproduce the offsets and hashes without dumping
the proprietary data. Its content semantics remain unresolved, so this finding
does not yet make the record suitable for inclusion in an open driver.

## Sensor-configuration descriptor catalog

The reference DLL contains a null-terminated catalog at RVA `0x161470`. It has
75 pointers to fixed-size `0x50`-byte descriptors. Each descriptor has a
16-byte zero/reserved prefix, 13 selection fields at offsets `0x10` through
`0x40`, a payload length at `0x44`, and a payload pointer at `0x48`.

The captured 10,500-byte `0x06` body is descriptor index 39. Its selector
fields are `6, 0x14, 0xffff, 0xffff, 0xe, 5, 4, 0x400080, 0, 3, 0xffff, 1,
0xffff`; its length is `0x2904`. A distinct 10,500-byte entry at index 66 has
different sensor-family selectors, so equal length alone is not sufficient to
select a table.

Static analysis identifies the catalog consumer in the vendor source unit
named `scsSensorConfig.c`. It walks the pointer array to its null terminator,
compares descriptor fields with sensor identity/capability fields, then copies
the selected payload using offsets `0x44` and `0x48`. This establishes a
static, hardware-variant selection mechanism rather than runtime generation.
Field semantics and the table's internal instruction format are still being
decoded.

All 75 catalog payloads begin with the same four-byte container header,
`02 00 00 01`. For every entry, the remaining length is an exact multiple of
16 bytes. Index 39's body has approximately 7.98 bits/byte of Shannon entropy
and no repeated aligned four-byte words. Together with the driver's separate
sensor-security/public-key path (`scsSSPubKey.c`), this is strong evidence for
a protected, block-oriented sensor-configuration container. It is not enough
to name a cipher or mode: the host-side path copies the prebuilt container and
does not decrypt it.

The older reference driver `5.5.4018.1052` places the same 75-entry catalog at
RVA `0x161370`, exactly `0x100` earlier. Its index-39 payload has the identical
SHA-256, `67f4a332d89f76fe12c57fa7f67b43a076f689e78267b888c694e26b05caacc1`.
Pass `--catalog-rva 0x161370` when inventorying that version; the tool's
default is deliberately tied to the documented current DLL.

`tools/syna0082_descriptor_catalog.py` reproduces the catalog inventory. Its
JSON contains only RVAs, lengths, selector values, and SHA-256 hashes. With
`--payload`, it identifies a capture (including a leading command byte) by
hash and exact comparison without printing proprietary bytes.
