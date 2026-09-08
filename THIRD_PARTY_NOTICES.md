# Third-party notices — Transcriber 9000 1.0.0-rc.1

This index comes from the actual PyInstaller analysis and native files in the
frozen Windows payload. It is a minimum RC notice bundle, not an enterprise
SBOM. Paths are relative to the installed application directory. Upstream
licenses control if this index and a license text differ.

## Application and native runtime

| Component | Version | License | Bundled license path | Upstream/source |
| --- | --- | --- | --- | --- |
| Meetily helper adaptation | 0.4.0 | MIT | `LICENSES/Meetily-0.4.0/LICENSE.txt` | https://github.com/Zackriya-Solutions/meetily/tree/v0.4.0/llama-helper |
| llama-cpp-2 / llama-cpp-sys-2 | 0.1.156 | MIT OR Apache-2.0 | `LICENSES/Rust-helper-runtime/llama-cpp-rs-0.1.156/` | https://crates.io/crates/llama-cpp-2/0.1.156 |
| llama.cpp embedded by llama-cpp-sys-2 | crate 0.1.156 snapshot | MIT | `LICENSES/llama.cpp/LICENSE.txt` | https://github.com/utilityai/llama-cpp-rs/tree/0.1.156/llama-cpp-sys-2/llama.cpp |
| FFmpeg BtbN `win64-lgpl` static build | n8.1.2-51-g7ba069f4f1-20260907 | LGPL-3.0-or-later | `LICENSES/FFmpeg-BtbN-n8.1.2-51/LICENSE.txt`; provenance in `LICENSES/FFmpeg-BtbN-n8.1.2-51/VERSION.txt` | https://github.com/BtbN/FFmpeg-Builds/releases/tag/autobuild-2026-09-07-15-39 |
| Whisper code and bundled `base.pt` | 20250625 / `base` | MIT | `LICENSES/openai-whisper-20250625/licenses/LICENSE` | https://github.com/openai/whisper |
| Python | 3.12.14 | PSF-2.0 and included notices | `LICENSES/Python-3.12.14/LICENSE.txt` | https://www.python.org/downloads/release/python-31214/ |
| Tcl/Tk | 8.6.12 | Tcl/Tk terms | `LICENSES/Tcl-Tk-8.6.12/license.terms` | https://www.tcl-lang.org/software/tcltk/8.6.html |
| TkDND native extension | bundled by tkinterdnd2 0.6.2 | TkDND permissive terms | `LICENSES/TkDND/license.terms` | https://github.com/petasis/tkdnd |
| LLVM-MinGW UCRT runtime (`libc++`, `libunwind`, `libomp`) | 20260616 / LLVM 22 | Apache-2.0 WITH LLVM-exception and component terms | `LICENSES/LLVM-MinGW-20260616/LICENSE.TXT` | https://github.com/mstorsjo/llvm-mingw/releases |
| MinGW-w64 runtime portions | LLVM-MinGW 20260616 bundle | component-specific permissive terms | `LICENSES/MinGW-w64-runtime/mingw32/` | https://www.mingw-w64.org/ |
| Microsoft Visual C++ app-local runtime | 14.44.35211.0 | Microsoft redistribution terms | `LICENSES/MSVC-14.44.35211/license.rtf`; provenance: `packaging/MSVC_REDIST_PROVENANCE.md` in source release | https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files |
| NVIDIA CUDA runtime for accepted helper | 12.4 | NVIDIA CUDA EULA | `LICENSES/NVIDIA-CUDA-12.4/EULA.pdf` | https://docs.nvidia.com/cuda/archive/12.4.0/eula/ |
| NVIDIA CUDA libraries bundled by PyTorch | 12.8 | NVIDIA CUDA EULA | `LICENSES/NVIDIA-CUDA-12.8/EULA.pdf` | https://docs.nvidia.com/cuda/archive/12.8.1/eula/ |
| NVIDIA cuDNN runtime DLLs bundled by PyTorch | 9.19.0.56 | NVIDIA cuDNN EULA | `LICENSES/NVIDIA-cuDNN-9.19.0/EULA.html` | https://docs.nvidia.com/deeplearning/cudnn/backend/v9.19.0/reference/eula.html |
| OpenSSL runtime | 3.5.8 | Apache-2.0 | `LICENSES/OpenSSL-3.5.8/LICENSE.txt` | https://github.com/openssl/openssl/tree/openssl-3.5.8 |
| Roboto font files bundled by CustomTkinter | bundled with 6.0.0 | Apache-2.0 | `LICENSES/Roboto-font/LICENSE.txt` | https://github.com/googlefonts/roboto-2 |
| PyInstaller bootloader | 6.16.0 | GPL-2.0-or-later with Bootloader Exception; runtime-hook terms included | `LICENSES/PyInstaller-6.16.0/licenses/COPYING.txt` | https://github.com/pyinstaller/pyinstaller/tree/v6.16.0 |
| Inno Setup compiler/runtime | 6.7.3 | Inno Setup License | `LICENSES/Inno-Setup-6.7.3/license.txt` | https://jrsoftware.org/isinfo.php |

FFmpeg binary, archive, exact source commit and exact BtbN recipe commit are
recorded in `packaging/FFMPEG_PROVENANCE.md`. The corresponding source/reference
package must be published beside every distributed Setup artifact.

## Frozen Python packages

| Component | Version | License | Bundled license path | Upstream/source |
| --- | --- | --- | --- | --- |
| certifi | 2026.6.17 | MPL-2.0 | `LICENSES/certifi-2026.6.17/licenses/LICENSE` | https://github.com/certifi/python-certifi |
| charset-normalizer | 3.4.9 | MIT | `LICENSES/charset-normalizer-3.4.9/licenses/LICENSE` | https://github.com/jawah/charset_normalizer |
| colorama | 0.4.6 | BSD-3-Clause | `LICENSES/colorama-0.4.6/licenses/LICENSE.txt` | https://github.com/tartley/colorama |
| CustomTkinter | 6.0.0 | MIT | `LICENSES/customtkinter-6.0.0/licenses/LICENSE` | https://github.com/TomSchimansky/CustomTkinter |
| darkdetect | 0.8.0 | BSD-3-Clause | `LICENSES/darkdetect-0.8.0/LICENSE` | https://github.com/albertosottile/darkdetect |
| filelock | 3.29.0 | MIT | `LICENSES/filelock-3.29.0/licenses/LICENSE` | https://github.com/tox-dev/py-filelock |
| fsspec | 2026.4.0 | BSD-3-Clause | `LICENSES/fsspec-2026.4.0/licenses/LICENSE` | https://github.com/fsspec/filesystem_spec |
| idna | 3.18 | BSD-3-Clause | `LICENSES/idna-3.18/licenses/LICENSE.md` | https://github.com/kjd/idna |
| Jinja2 | 3.1.6 | BSD-3-Clause | `LICENSES/Jinja2-3.1.6/licenses/LICENSE.txt` | https://github.com/pallets/jinja |
| llvmlite | 0.48.0 | BSD-2-Clause and Apache-2.0 WITH LLVM-exception | `LICENSES/llvmlite-0.48.0/licenses/` | https://github.com/numba/llvmlite |
| MarkupSafe | 3.0.3 | BSD-3-Clause | `LICENSES/MarkupSafe-3.0.3/licenses/LICENSE.txt` | https://github.com/pallets/markupsafe |
| more-itertools | 11.1.0 | MIT | `LICENSES/more-itertools-11.1.0/licenses/LICENSE` | https://github.com/more-itertools/more-itertools |
| mpmath | 1.3.0 | BSD-3-Clause | `LICENSES/mpmath-1.3.0/LICENSE` | https://github.com/mpmath/mpmath |
| networkx | 3.6.1 | BSD-3-Clause | `LICENSES/networkx-3.6.1/licenses/LICENSE.txt` | https://github.com/networkx/networkx |
| numba | 0.66.0 | BSD-2-Clause and bundled third-party terms | `LICENSES/numba-0.66.0/licenses/` | https://github.com/numba/numba |
| NumPy | 2.4.6 | BSD-3-Clause and bundled third-party terms | `LICENSES/numpy-2.4.6/licenses/` | https://github.com/numpy/numpy/tree/v2.4.6 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | `LICENSES/packaging-26.3/licenses/` | https://github.com/pypa/packaging |
| regex | 2026.6.28 | Apache-2.0 AND CNRI-Python | `LICENSES/regex-2026.6.28/licenses/LICENSE.txt` | https://github.com/mrabarnett/mrab-regex |
| requests | 2.34.2 | Apache-2.0 | `LICENSES/requests-2.34.2/licenses/` | https://github.com/psf/requests |
| setuptools | 84.0.0 | MIT | `LICENSES/setuptools-84.0.0/licenses/LICENSE` | https://github.com/pypa/setuptools |
| SymPy | 1.14.0 | BSD-3-Clause | `LICENSES/sympy-1.14.0/licenses/LICENSE` | https://github.com/sympy/sympy |
| tiktoken | 0.13.0 | MIT | `LICENSES/tiktoken-0.13.0/licenses/LICENSE` | https://github.com/openai/tiktoken |
| tkinterdnd2 Python wrapper | 0.6.2 | MIT | `LICENSES/tkinterdnd2-0.6.2/licenses/LICENSE` | https://github.com/pmgagne/tkinterdnd2 |
| PyTorch | 2.11.0+cu128 | BSD-3-Clause and bundled third-party notices | `LICENSES/torch-2.11.0+cu128/torch-2.11.0+cu128.dist-info/LICENSE`, `NOTICE` | https://github.com/pytorch/pytorch |
| tqdm | 4.68.4 | MPL-2.0 AND MIT | `LICENSES/tqdm-4.68.4/licenses/LICENCE` | https://github.com/tqdm/tqdm |
| typing-extensions | 4.15.0 | PSF-2.0 | `LICENSES/typing-extensions-4.15.0/licenses/LICENSE` | https://github.com/python/typing_extensions |
| urllib3 | 2.7.0 | MIT | `LICENSES/urllib3-2.7.0/licenses/LICENSE.txt` | https://github.com/urllib3/urllib3 |
| wheel | 0.47.0 | MIT | `LICENSES/wheel-0.47.0/licenses/LICENSE.txt` | https://github.com/pypa/wheel |

## Rust helper dependency notices

The helper's locked normal dependency graph is in `llama-helper/Cargo.lock`.
License files for these exact crates are under the corresponding versioned
subdirectories of `LICENSES/Rust-helper-runtime/`: `anyhow 1.0.104`,
`encoding_rs 0.8.35`, `cfg-if 1.0.4`, `enumflags2 0.7.12`,
`enumflags2_derive 0.7.12`, `proc-macro2 1.0.107`, `unicode-ident 1.0.24`,
`quote 1.0.47`, `syn 2.0.119`, `syn 3.0.5`, `thiserror 2.0.20`,
`thiserror-impl 2.0.20`, `tracing 0.1.44`, `tracing-attributes 0.1.31`,
`tracing-core 0.1.36`, `pin-project-lite 0.2.17`, `once_cell 1.21.4`,
`serde 1.0.229`, `serde_core 1.0.229`, `serde_derive 1.0.229`,
`serde_json 1.0.151`, `itoa 1.0.18`, `memchr 2.8.3`, and `zmij 1.0.23`.
Upstream records are at `https://crates.io/crates/<crate>/<version>`.

## Not bundled

Qwen 3.5 9B Q4_K_M and Qwen 3.5 4B Q4_K_M GGUF files are downloaded
separately by the model manager and are not installer content.
