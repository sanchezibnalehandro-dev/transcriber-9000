# Microsoft Visual C++ Redistributable provenance

- Upstream: `https://aka.ms/vs/17/release/vc_redist.x64.exe`
- Product: Microsoft Visual C++ 2015-2022 Redistributable (x64)
- Version: `14.44.35211.0`
- Installer SHA-256: `CC0FF0EB1DC3F5188AE6300FAEF32BF5BEEBA4BDD6E8E445A9184072096B713B`
- Authenticode signer: `Microsoft Corporation` (signature status `Valid` when prepared)
- Redistribution method: the four app-local DLLs below are extracted from the
  official signed package with WiX Toolset `dark.exe` and an administrative MSI
  extraction. They are used both at the application root and beside the CUDA
  helper. No file is copied from Windows `System32`.

| File | SHA-256 |
| --- | --- |
| `msvcp140.dll` | `0F885B509A685D2BBFA652FED26B5FB31D88FBDAB0A978C641D1C7B8AA460AA9` |
| `vcomp140.dll` | `55ABA23CDCD6484FBB06F4155B8CA75ADFCE7A881F10AFD0C49457165E677164` |
| `vcruntime140.dll` | `D5E4D9A3E835FA679450145D6A7D94E36573A509317111904D9B3712C30D9066` |
| `vcruntime140_1.dll` | `1F2D41C4AA5DB0BC33EBF7B66D72943A817D7CE6CBE880502A9403823633093F` |

Microsoft permits app-local deployment of files listed as redistributable for
licensed Visual Studio tooling. Preparation and build both fail closed on the
pinned hashes. See Microsoft's current redistribution documentation:
`https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files`.
