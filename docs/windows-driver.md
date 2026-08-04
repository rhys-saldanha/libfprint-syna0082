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
