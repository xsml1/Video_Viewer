# 第三方组件声明（随 Windows 文件夹式构建）

本工具本地使用 Python 3.11、PySide6/Qt 6.11.2、PyAV 16.1.0、NumPy 2.4.6、platformdirs 4.x 和 ffprobe/ffmpeg。具体版本以构建时 `uv.lock` 和 `ffprobe -version` 为准。PyAV wheel 内的 FFmpeg 库与随包命令行 FFmpeg 是两套构建，不能混为一谈。

- PySide6/Qt：LGPL-3.0-only 或 GPL-2.0-only/GPL-3.0-only，参见 [Qt for Python 许可](https://doc.qt.io/qtforpython-6/licenses.html)。
- PyAV：BSD-3-Clause，参见项目 wheel 的 `av-*.dist-info/licenses/LICENSE.txt`。
- NumPy：BSD-3-Clause，包含若干第三方组件许可，参见项目 wheel 的 `numpy-*.dist-info/licenses/`。
- platformdirs：MIT，参见项目 wheel 的许可文件。
- Pillow 12.3.0：MIT-CMU，用于常见静态图像、EXIF 方向与 ICC 转换。
- pillow-heif 1.8.0：BSD-3-Clause，用于 HEIC/HEIF 读取；其 libheif 等底层组件许可另见随 wheel 的许可文件。
- rawpy 0.27.1：MIT，用于相机 RAW 显影；底层 LibRaw 的许可另见随 wheel 的许可文件。
- tifffile 2025.5.10：BSD-3-Clause，用于高位深、方向与多种压缩 TIFF 读取。
- imagecodecs 2026.3.6：BSD-3-Clause，用于 JPEG XL、JPEG XR、JPEG-LS、16 位 PNG 及 TIFF 压缩解码；底层 libjxl、jxrlib、CharLS、libpng 等组件许可见 wheel 的 imagecodecs-*.dist-info/licenses/LICENSE。锁定此版本以保留 Python 3.11 支持。
- 构建时使用的 Nuitka：Apache-2.0，作为构建工具，不作为应用运行时导入。
- 本地开发所用命令行 FFmpeg：gyan.dev FFmpeg 9.0.1 essentials build，GPL v3；构建脚本将原构建的 `LICENSE` 和 `README.txt` 放入发布文件夹。上游源代码版本与构建选项见同目录 `FFmpeg-README.txt`。公开分发前须复核所有依赖许可义务。

- Microsoft Visual C++ v14 运行时：由 Nuitka 装配的 msvcp140/vcomp140/vcruntime140 等 DLL 用于 C++ 扩展；分发及许可说明参见 [Microsoft 部署文档](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files?view=msvc-170)。
