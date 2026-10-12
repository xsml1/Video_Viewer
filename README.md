# Video Viewer（视频与图像对比工具）

本地 Windows 桌面应用，图像和视频共用一个工作区，可混合添加 1–6 路。选择工作文件夹后，在右侧双击文件添加；双击文件夹进入下一级，可返回上一级、后退、前进和刷新。视频按真实 PTS 或显示帧号同步，图像保持静止。**原计划 P0/P1 和干净机器发布验收仍以实际报告为准**，状态见 [进度](docs/PROGRESS.md)和[验收](reports/ACCEPTANCE.md)。输入文件只读，不上传、不转码。操作细节见 [中文使用说明](docs/USER_GUIDE.zh-CN.md)。

## 安装与启动（Windows 10/11 x64）

仓库保存源码和构建脚本，不把可再生成的 `dist/`、虚拟环境或测试视频提交到 Git。准备 [Git](https://git-scm.com/download/win)、[uv](https://docs.astral.sh/uv/getting-started/installation/) 和一个含 `ffmpeg.exe`、`ffprobe.exe` 的 Windows FFmpeg 构建（下载入口见 [FFmpeg 官网](https://ffmpeg.org/download.html#build-windows)）。在 PowerShell 中执行：

```powershell
git clone https://github.com/xsml1/Video_Viewer.git
cd Video_Viewer
uv sync --locked --extra dev
& .\.venv\Scripts\python.exe -m video_compare --ffprobe 'C:\path\to\ffmpeg\bin\ffprobe.exe'
```

请把示例中的 FFmpeg 路径改成实际文件路径。`uv` 会按 `uv.lock` 建立项目环境并使用 Python 3.11；之后可双击项目中的 `scripts\run_video_compare.cmd` 启动（播放视频需把 FFmpeg 的 `bin` 加入 PATH，或在命令行继续传 `--ffprobe`）。可直接打开图像，也可同时传入视频：

```powershell
& .\.venv\Scripts\python.exe -m video_compare 'C:\path\to\first.png' 'C:\path\to\second.heic'
```

想生成无需 Python 的 Windows 程序文件夹，执行 `uv sync --locked --extra dev --extra build`，再运行 `powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -FfmpegBin 'C:\path\to\ffmpeg\bin'`。构建结果位于 `dist\VideoCompare.dist\main.exe`；复制或压缩时应保留整个 `VideoCompare.dist` 文件夹。构建后的本机自检可双击文件夹内的 `verify_clean_windows.cmd`。另一台干净 Windows 机器尚未实测，详见[验收报告](reports/ACCEPTANCE.md)。

窗口结构：顶部单行工具栏、中间对比画布、画面下方播放条、右侧可调文件夹浏览器（“»”隐藏）。左键把画面拖到另一格，松手即可交换位置；同格拖动或中键拖动平移，ROI/标注模式仍用于框选和绘画。空格在主窗口中只控制播放/暂停，不触发当前焦点按钮或添加文件；仅图像时播放控件禁用。右键画面可从工作区移除或替换，不删除源文件。每路画面的左上角显示文件名，右下角显示帧号/PTS或图像信息，文字颜色可在设置里修改。设置中的主题、八种语言及颜色角色仍保持即时切换与本地保存。

## 当前状态

顶部“全屏”或 F11 进入工作区全屏，只显示画面和右上角 ×。空格播放/暂停，左右键按当前设置步进，Ctrl+滚轮缩放，Esc 或 × 退出并恢复原窗口与侧栏。图像保持静止。全屏与普通窗口共用同一画布和视频解码器。

图像和视频可以在同一工作区同步查看、联动缩放/平移/ROI、原生像素查看、保存各路预览和标注导出。图像不参与视频时间轴，也不缩短视频公共播放区间。图片由 Pillow、pillow-heif、imagecodecs、tifffile 和 Qt 插件读取，相机 RAW 由 LibRaw 显影。此前验证的格式样本与未验证变体见 [格式支持说明](docs/FORMAT_SUPPORT.zh-CN.md)。多页/动画只看首页，透明区域按白底预览，原件只读。旧 `--mode image/video` 参数继续兼容启动脚本，不再切换工作区。完整边界见 [已知问题](KNOWN_ISSUES.md)。

视频真实解码、统一帧组和 GUI 已接通；各路真实首帧由快速探测线程取得，完整索引在另一个后台线程逐段建立。已索引区间可播放，超出覆盖区的定位会等待索引追上。普通视频的30组编码/容器、9组HDR/广色域样本保留回归覆盖，PQ、HLG、BT.2020 SDR/P3以明确标注的SDR RGB8预览显示。2026-10-01版本的两路1080p PQ有30分钟资源实测，本轮不重复此吞吐测量。当前版已通过234项最终回归、本机1920×1080全屏原生GL及独立Windows包自检；完整证据和未验证设备边界见 [验收](reports/ACCEPTANCE.md)与 [已知问题](KNOWN_ISSUES.md)。

## 开发环境

要求：

- Windows 10/11 x64
- Python 3.11
- FFmpeg/ffprobe（最终查找顺序为用户配置、随程序附带目录、PATH）

项目使用 `uv.lock` 固定完整依赖。仓库内开发环境的安装与启动：

```powershell
uv sync --locked --extra dev
& .\.venv\Scripts\python.exe -m video_compare --ffprobe 'C:\path\to\ffprobe.exe'
```

直接打开本地图像（也可以混合视频路径）：

```powershell
& .\.venv\Scripts\python.exe -m video_compare --mode image 'C:\path\to\first.png' 'C:\path\to\second.heic'
```

PowerShell 里若出现中文乱码（Python/git/ffmpeg 输出变成 `��`、重定向日志里搜不到中文），执行一次
`powershell -ExecutionPolicy Bypass -File scripts\setup_powershell_utf8.ps1`：它把当前用户的控制台输出编码、
`$OutputEncoding` 与 `PYTHONIOENCODING` 统一为 UTF-8，并让 Windows PowerShell 5.1 的日志重定向写 UTF-8。
原因、边界与回退方式见 `docs/DECISIONS.md` D028b。

可在命令尾部附加 1–6 个本地视频路径。若本机 OpenGL 不可用，会自动切到软件画布；也可显式加 `--software`。长片首帧显示后可播放已索引区间；播放到索引前沿会等待下一批真实帧，精确定位到未覆盖位置会排队。

在窗口中可添加或拖入视频、选中一路移除/替换/上移/下移、播放/暂停、输入时间或基准帧号定位、拖动进度条、配置帧/秒步进、切换基准并设置选中路的时间/帧 Offset、Ctrl+滚轮缩放、拖拽平移、框选 ROI、Fit，以及切换主题和强调色。双击画布中的一路可单路查看，再双击或按 Esc 返回网格；其他路仍留在同步组。正时间 Offset 表示该路向后取内容，正帧 Offset 表示该路帧号领先基准；两种数值分别保存，不用 FPS 互换。拖拽平移时水平方向画面跟随指针，垂直方向按用户要求为“视图跟随指针”（向下拖动时视图下移）。

画面排列会随导入视频变化：默认“自动（按画面比例）”会按各路视频显示后的宽高比选择行划分，行内紧密排列并只留 8 逻辑像素间距，多余空间留在外侧，因此两路竖屏视频不会在中间留下大片空白；也可在工具条切到“网格/横向/竖向排列”，选择会记忆到 `settings.toml`。

“导出对比图…”把当前窗口里看到的画面区域导出为一张对比图：排列可选“与窗口一致/横向排列/竖向排列/网格排列”，格式可选 PNG 或 JPEG（可调质量）；导出图包含画面左上角文件名与右下角帧号/PTS/提醒，不含按钮与工具栏，且不再生成 JSON。勾选“导出前先编辑标注”可在画面上画**矩形/椭圆/箭头/直线/自由画笔**（九种线条颜色）。编辑工具条的“标注联动到全部画面”默认勾选；取消勾选后，新画的框选和自由画笔等标注只显示并导出在起笔的那一路图像或视频上。此开关只影响新标注，已有笔画保持原范围；顶部“视图联动”仍单独控制缩放/平移/ROI。标注锚定源画面位置，缩放后仍与内容对齐。工具条可撤销、删除选中项或全部删除；成功保存或取消编辑后，本次标注从画面消失，保存失败则保留以便重试。支持的 HDR/BT.2020 路会按实际 SDR 预览导出，并保留色调映射提醒；非兼容 Dolby Vision 与 BT.2020 CL 会明确拒绝。

应用图标来自 `logo/` 中的用户 logo（白底已处理为透明，见 `tools/prepare_logo.py`）。桌面快捷方式 `Video Viewer` 由 `scripts/create_desktop_shortcut.ps1` 创建，默认指向 `scripts/run_video_compare.cmd`，用项目虚拟环境运行当前源码。

速度可选 0.25–4×；在已经显示的画面分别按 I、O（或对应按钮）设置循环区间边界，再开启区间循环。可从当前完整帧组保存对比视图 PNG 或各路原帧 PNG，旁边会生成记录时间/帧身份的 JSON。Marker 可为当前完整组添加标题和备注并跳回，但只在本次会话有效，退出后不保存。查看模式可切换“同区域”和“原生像素 100%”；后者每个源采样像素对应一个 framebuffer 物理像素，忽略 SAR，Ctrl+滚轮可调整倍率；实际高 DPI/跨屏验证尚未完成。选中视频的侧栏显示源尺寸、编码、色彩范围及 RGB8/推定/HDR 限制；画布也标出对应提醒。

侧栏的“暂停选中路同步”可让非基准路保留当前帧，其余路继续按统一时钟运行；重新加入时对齐当前组。基准路不能脱离，需先切换基准。若重入位置已超出新的公共范围，整组会定位到最近有效边界并提示。截图 JSON 会将保留帧标为 `detached`，不冒称它与参与路同一时刻。

测试素材生成与验证命令：

```powershell
& .\.venv\Scripts\python.exe tools\generate_fixtures.py --output tests\assets\generated --ffmpeg 'C:\path\to\ffmpeg.exe'
$env:QT_QPA_PLATFORM = 'offscreen'
& .\.venv\Scripts\python.exe -m pytest tests\unit tests\integration tests\gui -q
& .\.venv\Scripts\ruff.exe check src tests tools
# 真实窗口验证（自适应排列、拖拽方向、对比图导出、导出对话框）
& .\.venv\Scripts\python.exe tools\verify_ui_and_export.py --ffprobe 'C:\path\to\ffmpeg\bin\ffprobe.exe'
# 应用图标（白底转透明 + 多尺寸 ico），构建脚本会先自动执行
& .\.venv\Scripts\python.exe tools\prepare_logo.py
# 桌面快捷方式
powershell -ExecutionPolicy Bypass -File scripts\create_desktop_shortcut.ps1
```

软件回退的离屏测试不等于真实显示器、DPI 或 Windows 发布包验收。

## Windows 文件夹式构建

在 64 位 Windows、Python 3.11 和 [uv](https://docs.astral.sh/uv/) 可用的环境中，先同步锁定依赖，再指定一个同时含有 `ffprobe.exe`、`ffmpeg.exe` 的 FFmpeg 目录：

```powershell
uv sync --locked --extra dev --extra build
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -FfmpegBin 'C:\path\to\ffmpeg\bin'
```

成功后产物是 `dist\VideoCompare.dist\main.exe`，同目录 `bin` 含命令行 FFmpeg；正常启动无需 Python 或额外设置 FFmpeg PATH。脚本遇到已有非空发布目录会停止，避免混入旧文件；请先移动旧目录。构建工具为 `pyside6-deploy`/Nuitka 4.1.1。文件夹内会附带第三方声明及本次 FFmpeg 构建的许可文本；公开分发前应复核许可义务。产物只有通过实际启动和导入验证才可标为可运行；当前结果见验收报告。

在另一台 Windows 10/11 x64 机器验收时，解压整个文件夹，双击其中的 `verify_clean_windows.cmd`。它会用包内 FFmpeg 在系统临时目录生成两段小测试视频和两张图像，再启动 `main.exe` 自动执行视频导入/定位/截图和图像导入/导出；窗口最后显示 `CLEAN_WINDOWS_SELF_TEST_OK` 及结果目录即为通过。若失败，保留窗口全文和结果目录用于排查。此脚本不会读取或上传用户素材。本机已实跑含图像的新版脚本，另一台干净机器仍待实际验证。

## 产品边界

- 输入视频只读；索引、缓存和截图使用独立位置。
- 已支持的 PQ/HLG、BT.2020 NCL 和 P3 转为明确标注的 SDR RGB8 预览；不输出原生 HDR，不应用动态元数据。BT.2020 CL 与非兼容 Dolby Vision 拒绝导入。
- P0/P1 不包含音频、转码、视频导出或客观质量指标。
- P2 的 Workspace、A/B、分割线、冻结、ROI 导出、自定义快捷键和全屏不在本轮默认范围。

## Quick start (English)

Video Viewer is an offline Windows 10/11 x64 desktop app for comparing 1–6 videos or images. Video comparison uses source timestamps or display frame numbers; image comparison supports common raster formats, HEIC/AVIF and some RAW files where the bundled readers can decode them. Source files are read-only.

Install [Git](https://git-scm.com/download/win), [uv](https://docs.astral.sh/uv/getting-started/installation/) and a Windows [FFmpeg build](https://ffmpeg.org/download.html#build-windows) containing `ffprobe.exe`. In PowerShell:

```powershell
git clone https://github.com/xsml1/Video_Viewer.git
cd Video_Viewer
uv sync --locked --extra dev
& .\.venv\Scripts\python.exe -m video_compare --ffprobe 'C:\path\to\ffmpeg\bin\ffprobe.exe'
```

Choose a working folder, then double-click images or videos in the right sidebar to add them to one shared workspace. Double-click folders to enter them; use the up, back, forward and refresh buttons to navigate. Drag a pane onto another pane to swap positions. Space only toggles video playback/pause throughout the main window; still images remain unchanged. The toolbar controls linked zoom, pan, ROI and comparison image export. During annotation export, clear **Link annotations to all panes** to keep new strokes in their starting pane. **Settings → Language** retains eight languages. To build a standalone folder, run `uv sync --locked --extra dev --extra build` followed by `powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -FfmpegBin 'C:\path\to\ffmpeg\bin'`; keep the whole `dist\VideoCompare.dist` folder together. See the [Chinese user guide](docs/USER_GUIDE.zh-CN.md) and [known limitations](KNOWN_ISSUES.md) for details.
