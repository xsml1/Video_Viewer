# M0 能力验证（阶段记录）

> 本文记录 2026-09-23 的 M0 当时快照，不代表当前功能缺失。2026-09-24 已扩展至真实播放、统一帧组、GUI 手势、主题和文件管理；最新状态与验证以 `docs/PROGRESS.md`、`reports/ACCEPTANCE.md` 为准。最近一次原生 GL 复测为 2/6 路 framebuffer 1182×506、DPR 1.0，退出码 0。

日期：2026-09-23；平台：Windows 11 x64 10.0.26200。工作树尚无提交；本报告对应当前未提交代码，关键文件 SHA-256 见文末。

## 运行环境

- CPU：AMD Ryzen 7 9800X3D，8 核/8 逻辑处理器；GPU：NVIDIA GeForce RTX 4070 SUPER。
- 项目专用 Python 3.11.16、PyAV 16.1.0、PySide6 6.11.2、NumPy 2.4.6。
- PyAV wheel 内 FFmpeg 库：libavcodec 62.11.100、libavformat 62.3.100、libavutil 60.8.100、libswscale 9.1.100。
- 外部 CLI：Gyan FFmpeg/ffprobe 9.0.1 essentials build，下载自 winget 的 `Gyan.FFmpeg.Essentials`，仅存放于忽略的 `.codex-tools/ffmpeg/`，未写入全局 PATH。其版本与 PyAV wheel 内 FFmpeg 版本不同。

## 实际执行与观察

| 项目 | 输入/操作 | 实际结果 | 状态 |
|---|---|---|---|
| Python 依赖 | `uv sync --python .python/cpython-3.11-windows-x86_64-none/python.exe --extra dev` | 17 个包安装成功，生成 `uv.lock` | 已验证通过 |
| 探测 | `ffprobe -show_format -show_streams -of json`；H.264 文件 | 真实 stream index 0、time_base 1/15360、72 帧、320×180；矩阵/范围缺失时显示推定字段 | 已验证通过（旋转源未测） |
| 顺序索引 | PyAV 解码 H.264/FFV1/VFR/非零起点素材并写 SQLite | H.264 72 帧，最后有效端 12/5 秒；VFR 间距不等；非零源首 PTS 2000 而本地首时间 0 | 已验证通过 |
| 精确取帧 | 5 种真实素材各 100 次随机目标及边界/后退；源图嵌入 16-bit 大块帧 ID | 目标 ordinal、实际 PTS 和像素 ID 全部相等；H.264 含 B 帧，跨 48 帧 GOP 正确 | 已验证通过 |
| 独立 PTS 对照 | ffprobe frame PTS 列表与 PyAV 索引逐项比对 | 72 项完全相等 | 已验证通过 |
| 色彩 API | YUV420P 灰阶 Y=16、U=V=128；601/709 色块 | limited→RGB(0,0,0)，full→RGB(16,16,16)；601→(253,0,0)，709→(255,23,0) | 已验证通过（更全面 F09 素材未测） |
| 软件画布 | `QT_QPA_PLATFORM=offscreen` 的 GUI 测试导入 2/6 路 | 真实解码快照被单画布绘制；测试通过 | 已验证通过（不代表真实显示器） |
| OpenGL 画布 | 本机真实显示环境，运行 `tools/verify_gl_canvas.py`，导入 2/6 路 | QOpenGLWidget 有有效 context，2/6 路 framebuffer 均 1182×670、DPR 1.0；截图目视可见真实帧 ID | 已验证通过（只验证 Qt OpenGL 画布；显式纹理 staging 尚未实现） |
| 中文路径 | `f11_中文 空格 [样例].mp4` | ffprobe、索引和 100 次随机取帧通过 | 已验证通过 |
| 部署 smoke build | `pyside6-deploy` 已存在，`--help` 可执行 | 尚未真正构建或启动部署产物 | 未验证 |

测试命令：

```powershell
.\.venv\Scripts\python.exe tools\generate_fixtures.py --output tests\assets\generated --ffmpeg .\.codex-tools\ffmpeg\ffmpeg-9.0.1-essentials_build\bin\ffmpeg.exe
.\.venv\Scripts\python.exe -m pytest tests\unit tests\integration -q
$env:QT_QPA_PLATFORM = 'offscreen'; .\.venv\Scripts\python.exe -m pytest tests\gui -q
.\.venv\Scripts\python.exe tools\verify_gl_canvas.py --ffprobe .\.codex-tools\ffmpeg\ffmpeg-9.0.1-essentials_build\bin\ffprobe.exe --output reports\artifacts
```

上述测试计数是 M0 当时记录；2026-09-24 的当前全量复测为 49 项通过，`ruff` 通过。GL 命令退出码 0；实际截图为 `reports/artifacts/m0_gl_two.png` 和 `reports/artifacts/m0_gl_six.png`（本机生成，按忽略规则不提交）。

## 差异与限制

- 锁定 PyAV 16.1.0 的 reformatter 接口支持显式源矩阵与色彩范围。实验发现同时传入 `dst_colorspace` 时全范围灰阶错转为黑位，因此生产转换不传该参数；将其作为回归测试。RGB/GBR 无损源直接做通道格式转换。
- 当前主窗口只显示已解码首帧。文件导入时同步建立完整索引，长视频可能卡住 UI。播放、原子同步帧组、异步取消、视图手势和 P1 功能还没接入。M0 窗口实验不能代表 M4 或最终产品验收。
- 尚未验证 90/180/270 度、SAR、HDR、10-bit、跨屏 DPR 或软件与 GL 逐像素一致性。

## 测试对象摘要

- `media/decoder.py`: `271AC3B71CAD76D6311A2E87B168045782BD1249C9EF47B8B2280BA97A677528`
- `media/index.py`: `174AC305C8B67EA566CE606AA60299852EEB405C9301E3A8961808E6233D82EF`（后续 M1 lookup 编辑后已变化；以后续复测和 Git diff 为准）
- `media/color.py`: `8FD6391707F7C6E283247A9B9497D04BFAB6AC4F4DEB2C93AA76C4DC69C47588`（随后修复 RGB/GBR 和 dst 参数，已变化）
- `ui/canvas_gl.py`: `D666CB7E42C5B9660C29BAC3A2FE6A573F228E2B0EF57201369DFF8E4CE9DDA2`
