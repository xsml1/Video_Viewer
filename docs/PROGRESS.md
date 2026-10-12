# 开发进度

## 2026-10-12–13：文件夹浏览、混合工作区与全屏

- 当前任务范围：文件夹浏览器替换右栏，图像/视频混合添加，画面拖拽对调，Space独占播放/暂停；用户另明确增加P2中的工作区全屏单项，含左右步进、Ctrl滚轮、Esc和右上×退出；其他P2不扩展。按用户最新要求，当前先同步原GitHub仓库，再执行剩余自检/验证。
- 当前里程碑：本次功能、最终234项回归、原生全屏、本机Windows包实际全屏/恢复及媒体自检均已验证；只保留原有外部设备/异机环境边界。
- 代码状态/分支/提交或未提交变更：功能e152d07、回归fdb68e9已先推送GitHub main，随后才进行最终验证。本机源48文件摘要8377BD7BD97CD17CC4C02FDB911E2328359B688A70832C99909D6730BDA7CA82；最终证据文档作为后续独立提交同步。输入素材和此前包保留。
- 本次已实现：目录导航/双击添加，统一6路及后台有序槽位，静图加入完整显示组，拖拽对调不重建decoder，Space独占，混合截图；同画布全屏隐藏其它UI，Esc/×恢复原窗口/侧栏，保留播放/步进/视图变换；SQLite连接及时关闭，首组GL失败软件回退保留混合组，异步导出时全屏隐藏栏按当前状态恢复。
- 实际验证及证据路径：同步后最终234 passed、2 deselected/47.19s（两项耗时循环在增加全屏前的本轮226通过中已执行，370.19s），reports/fullscreen_delivery_tests_20261013.log与workspace_release_tests_20261013.log。最终原生GL1920×1080、键鼠全屏/退出、混合固定截图、输入SHA均通过，reports/artifacts/fullscreen-native-gl-after-push-20261013/result.json。新包独立进程混合自检输出fullscreen=True normal_restore=True，reports/package_fullscreen_mixed_20261013.log；随包SDR/图像/PQ+HLG/16位图像四种实际程序自检均通过，reports/clean_windows_fullscreen_20261013.log。
- 发布产物：dist/VideoCompare.dist/main.exe，SHA256 B2F1A3113E98D864353FF79BE5DBE2530F329DA12C2C3BA6BD1F8DC4EC5B9E3D。旧混合包保留dist/VideoCompare.pre-fullscreen-20261013，原先包保留dist/VideoCompare.pre-folder-workspace-20261013；不上传视频/缓存/虚拟环境/本机发布目录。
- 仍失败/未验证：本轮不复测30分钟吞吐；高DPI/跨屏、另一台干净Windows和真实系统主题通知仍未验证，不作完整原计划通过声明。
- 下一步具体动作：直接双击dist/VideoCompare.dist/main.exe；选择工作文件夹、双击素材添加。顶部全屏/F11，Space播放暂停、左右步进、Ctrl滚轮缩放、Esc/右上×退出。后续设备验证按已准备的一键自检和验收记录进行。
- 当前启动/测试命令：源码 .venv/Scripts/python.exe -m video_compare --ffprobe <ffprobe.exe>；回归 .venv/Scripts/python.exe -m pytest -q --basetemp reports/artifacts/pytest-<唯一目录>；构建 scripts/build_windows.ps1 -FfmpegBin <bin>。

## 2026-10-01：格式兼容、HDR/BT.2020 与 GitHub 更新

- 当前任务范围：继续 M0–M8/P0/P1 的未完成项，尽可能扩展视频/图像格式；按用户新明确要求增加 HDR、BT.2020 的 SDR 预览，并提交现有 GitHub 仓库。M9/P2、音频、转码及视频导出不在范围。
- 当前里程碑：真实格式扩展、PQ/HLG/BT.2020/P3 预览、截图/标注、本机30分钟HDR资源验证和本机发布包已验证；A10实际高DPI/跨屏、A22第二台干净机器、A23真实系统主题通知仍受环境限制，原计划完整门槛未全部完成。
- 代码状态/分支/提交：基于 `main` 的 `5ef2839`；测试时实现未提交，源文件47个，最终摘要 `04CE493FBF41D596AA397A3A0947A9BBAEA7F1A4D77E3B4FEE981B1E0E3390E7`。本轮源码及记录提交进入 `main`，提交身份采用已核实的GitHub登录账号；具体提交/推送结果以本记录对应的Git日志为准。原先已有文件保留，生成视频/图像、环境及 `dist/` 不上传。
- 本次已实现：30组普通视频编码/容器、9组HDR/广色域真实兼容；PQ/HLG线性光Hable映射、BT.2020 NCL/P3转709、真实峰值及推定提示；保留RGB8/原色色彩信息与截图一致性；imagecodecs/tifffile增加JPEG XL/XR/LS及16位PNG/TIFF读取；RAW关闭自动提亮并验证合成Bayer DNG。修复真实全范围/高位深转换、首笔标注窗口变宽、长状态提示改变画布高度，以及混合容器自检误要求相同帧号的问题。
- 实际验证及证据路径：完整193测试通过，包含100次开闭及100次替换/删除/重载；后续最终194通过、2个已执行的耗时用例明确排除，`reports/complete_tests_20261001.log`；最后色彩专项27通过，Ruff检查/格式通过。原生GL两路/六路HDR、100%像素、截图、脱离/重入通过，`reports/artifacts/hdr-native-gl-release-20261001/`。两路1080p PQ运行1800s、12,981完整组、899次定位、错误空及资源有界，`reports/benchmark_hdr_gui_30min_20261001.json` 和GPU报告。完整细节及各版摘要见 `reports/ACCEPTANCE.md`。
- 发布产物：`dist/VideoCompare.dist/main.exe`，SHA-256 `8229DF06548040DFBEB5286CDBC6446613CDF9800B37B045A5A2E44A29BFD791`。35个独立进程验证39组视频/29图像样本和原件哈希，`reports/artifacts/package-format-complete-20261001/result.json`；随包一键自检在本机实跑普通视频/PQ/HLG/16位图像，通过 `CLEAN_WINDOWS_SELF_TEST_OK`。
- 仍失败/未验证：原生HDR屏幕输出、BT.2020 CL、非兼容Dolby Vision未实现；不应用DV/HDR10+动态元数据。JXL/XR/LS所有ICC变体、真实厂商相机RAW、分层PSD/浮点HDR图像、超大图像未全面验证。不同长片/六路HDR/4K实时性能未量化；长测期间还有其他构建/测试负载，不保证30fps。A10/A22/A23缺少真实外部设备/操作证据。
- 下一步具体动作：本机双击下列程序直接使用。另一台Windows可双击包内 `verify_clean_windows.cmd` 自动取得A22所需基本证据；有实际150/200%跨屏设备后验证A10，真实切换Windows系统主题时验证A23。测试素材和验证脚本已准备，用户无需修改源码或选择线程方案。
- 当前启动/测试命令：程序 `dist\VideoCompare.dist\main.exe`；源码 `& .\.venv\Scripts\python.exe -m video_compare --ffprobe <ffprobe.exe>`；图像模式加 `--mode image`。回归 `& .\.venv\Scripts\python.exe -m pytest -q --basetemp reports/artifacts/pytest-<新名字> -o cache_dir=reports/artifacts/pytest-cache-20261001`；生成素材/打包检查命令见验收报告和 `docs/FORMAT_SUPPORT.zh-CN.md`。

以下9月记录为历史版本；其包哈希和测试结果不代表本次新包。



## 2026-09-27：单路标注、八种界面语言与公开源码

- 当前任务范围：图像/视频导出标注可按笔选择联动全部画面或仅起笔画面；设置拆分主题与语言，语言名称始终按各自语言显示，增加繁体中文和六种常用外语；完成 README 并将项目源码推送到用户指定 GitHub 仓库。
- 当前里程碑：功能源码、本机真实显示器与 Windows 文件夹包已验证；公开仓库 `https://github.com/xsml1/Video_Viewer` 的 `main` 分支已推送。异机 A22、真实跨屏高 DPI A10 仍未验证。
- 代码状态/分支/提交或未提交变更：本机 `main` 与 `origin/main`；项目初始提交 `8d22f71` 已推送，文档更新见后续 Git 历史。`src/**/*.py` 43 文件摘要 `2DB84E77F33CA66A767B2782D53316F06C23120AB838B8FCA2F942E528951350`。新包 `dist/VideoCompare.dist/main.exe` SHA-256 `4C32DF23E409A4B32E146029B4403DE8E488076383857C6F83FF51CB0E6EE0B5`。
- 本次已实现：单路标注作用域随每笔保存，画布预览和导出按目标资产过滤；八种语言、固定自称语言列表、主题/语言设置页、即时切换和本地持久化；中英文安装快速说明、中文使用说明及公共仓库忽略规则。
- 实际验证及证据路径：`ruff check src tests tools` 和 `ruff format --check src tests tools` 退出 0；离屏全回归（排除耗时窗口循环）126 passed、1 deselected/41.10 秒，窗口打开关闭 100 次的独立用例 1 passed/283.11 秒。两路真实压缩视频的原生 OpenGL 单路标注检查退出 0，`reports/artifacts/annotation-scope-gl-20260927-final/result.json`；八种语言的本机原生窗口截图和固定语言名称验证退出 0，`reports/artifacts/languages-gl-20260927-final/result.json`。新 Windows 包本机 `verify_clean_windows.ps1` 使用包内 FFmpeg 和程序实测视频、图像两种模式，退出 0，显示 `CLEAN_WINDOWS_SELF_TEST_OK`，输出位于本机系统临时目录；详见 `reports/ACCEPTANCE.md`。
- 仍失败/未验证：另一台干净 Windows、真实 150/200% 与跨屏 DPI、所有图像编码变体及各语言的全部诊断文本尚未逐一人工验收。此前 30 分钟性能数字属于旧版。
- 下一步具体动作：用户可按 README 从 GitHub 克隆并启动源码，或运行本机 `dist/VideoCompare.dist/main.exe`。异机测试仍须在另一台 Windows 上运行包内 `verify_clean_windows.cmd`；高 DPI 与跨屏项目待实际设备验证。
- 当前启动/测试命令：源码 `& .\.venv\Scripts\python.exe -m video_compare`；Windows 包 `dist\VideoCompare.dist\main.exe`；测试 `$env:QT_QPA_PLATFORM='offscreen'; & .\.venv\Scripts\python.exe -m pytest tests\unit tests\integration tests\gui -q`。

## 2026-09-27：视频 / 图像双模式

- 当前任务范围：在现有视频对比软件增加图像对比模式，尽量广泛读取本地图像；不扩大到 M9/P2。
- 当前里程碑：图像模式已实现并在本机源码与 Windows 文件夹包验证；原计划的异机 A22、真实高 DPI/跨屏 A10 等仍未完成。
- 代码状态/分支/提交或未提交变更：`master` 无提交，仓库文件全部未跟踪，未暂存用户素材。`src/**/*.py` 40 文件摘要 `5F1A929678E4F59271F5456ED38130CABB5C1EE5CA8A059BFBE57BD6C904B7EC`；最终包 `dist/VideoCompare.dist/main.exe` SHA-256 `978625DB21803FABFA6105E138AAE7A478CEB04F1A06AF65862878711E2B7DEF`。
- 本次已实现：顶部切换视频/图像；图像 1–6 路只读后台加载、替换、删除、排序；复用联动视图、原生像素、ROI、标注和导出；视频晚到帧不能覆盖图像模式。Pillow/pillow-heif、Qt、rawpy 按内容尝试读取，新增 `--mode image`，扩展随包一键自检。
- 实际验证及证据路径：`ruff check` 和 `ruff format --check` 通过；离屏回归 121 passed/1 deselected，另整套含 100 次窗口循环 122 passed；最终图像 GUI 用例 2 passed。真实 Windows OpenGL 源码与包内双图自检，以及 HEIC/AVIF 包内读取和真实 H.264 视频包内复测退出码均为 0，结果见 `reports/ACCEPTANCE.md` 新增 I01–I03、`reports/artifacts/image-mode-20260927/`。最终包内 `verify_clean_windows.ps1` 本机视频+图像自检退出 0，输出 `CLEAN_WINDOWS_SELF_TEST_OK`。
- 仍失败/未验证：真实相机 RAW 文件、PSD/PDF 变体和所有格式编码变体尚未逐一验证；另一台干净 Windows、高 DPI/跨屏验收仍需合适环境。30 分钟性能数据属于此前版本，未对新增模式复测。
- 下一步具体动作：用户可在最终包里用实际图像判断对比效果；若某种格式读取失败，保存文件类型和错误提示以便补测对应解码器。异机运行时双击包内 `verify_clean_windows.cmd` 完成 A22；高 DPI/跨屏设备到位后完成 A10。
- 当前启动/测试命令：`dist/VideoCompare.dist/main.exe`；源码 `& .\.venv\Scripts\python.exe -m video_compare --mode image <图像1> <图像2>`；测试先设 `$env:QT_QPA_PLATFORM='offscreen'`，再运行 `& .\.venv\Scripts\python.exe -m pytest tests/unit tests/integration tests/gui -q`。

以下为 2026-09-25 的视频阶段记录；其中构建哈希和性能数字是历史版本数据。

更新时间：2026-09-25，Windows 11 x64。

- 当前任务范围：继续实施计划 M0–M8/P0/P1，并修复用户本轮反馈的五项编辑与界面问题；M9/P2 不在当前范围。
- 当前里程碑：核心真实视频链路及本轮五项修复已验证；M7 的本机 30 分钟资源测量已完成，M8 另一台干净机器发布验收仍待环境。原计划尚未全部验收完成。
- 代码状态/分支/提交或未提交变更：Git master 无提交、工作树全部未跟踪，未暂存或提交用户素材。当前 `src/**/*.py` 共 39 文件，`tools/source_digest.py` 摘要 `DD9EB070D0D546463325EC783F249CBB888528CD1220B6DC95836EEAD15E2D58`。当前 Windows 包 `dist/VideoCompare.dist/main.exe` SHA-256 `3331F24495384E8CA6844BECC3BD618C68684004B5DA3AE131858436976026D1`，旧包保存在 `dist/VideoCompare.pre-annotation-20260925/`。
- 本次已实现：标注仅在当前编辑会话显示，取消或保存成功后清除，失败保留重试；新增自由画笔和删除选中项；标注锚定源坐标，缩放/平移后画布与导出一致；侧栏 220ms 宽度动画；播放画布 12px 圆角；旧“Codex 极简”用户可见名称改为“清爽极简”，旧设置键继续兼容。
- 实际验证及证据路径：
  - `ruff check src tests tools`、`ruff format --check src tests tools` 通过，69 文件。
  - 离屏 `pytest tests/unit tests/integration tests/gui -q -k 'not test_one_hundred_real_single_video_window_open_close_cycles'`：最新复测 119 passed、1 deselected，37.85 秒；本版 100 次真实窗口开闭单独通过，205.39 秒。标注、缩放导出、侧栏动画、圆角和新色系名称有针对性断言。
  - 原生 Windows 显示器/OpenGL/真实压缩视频：`tools/verify_annotation_gl.py` 退出码 0，`reports/artifacts/annotation-gl-20260925/result.json` 和 `native-gl-pen.png`；DPR 1.0、画布 1080×678、导出 1078×302，画笔像素和圆角蒙版验证通过。`tools/verify_ui_and_export.py` 用用户两路竖屏素材确认侧栏连续动画、新设置名称、标注导出后清除，退出码 0，截图见 `reports/artifacts/ui-annotation-20260925/`。
  - `scripts/build_windows.ps1` 重新构建，日志 `reports/build_annotation_2026-09-25.log`。`tools/verify_package.py` 在去掉开发 PATH 的独立进程中以生成两路及用户竖屏两路实际启动，导入/定位/截图/导出均退出码 0；证据目录 `reports/artifacts/selftest-annotation-generated/` 和 `selftest-annotation-portrait/`。随包新增 `verify_clean_windows.cmd/.ps1` 一键自检，本机使用包内 FFmpeg 生成素材并启动程序，退出码 0、`CLEAN_WINDOWS_SELF_TEST_OK`，见 `reports/clean_windows_selftest_local_20260925.log`。
  - 本版原生 GL/两路 1080p/64 MiB/每 2 秒随机 seek 的 30 分钟运行退出码 0：39,432 完整组、899 次 seek、错误列表空；缓存峰值 62.2 MB、结果队列峰值 2，RSS 首/末约 335/343 MB；WDDM 显存约 79–82 MB，见 `reports/benchmark_gui_30min_annotation_20260925.json` 与 `benchmark_gpu_30min_annotation_20260925.json`。60 秒生成视频上的原生 GL 两路 30 秒 899 组、六路 15 秒 449 组，均接近 30fps；条件与局限见 `reports/ACCEPTANCE.md` A17。
- 仍失败/未验证：A10 实际 150/200% 与跨屏 DPR，A22 另一台干净 Windows 10/11 x64 解压运行，A23 真实 Windows 系统主题运行中切换。六路不同长片同时索引、4K 持续播放和冷磁盘性能未实测，不能外推本机短素材结果。原计划完整完成门槛尚未达到。
- 下一步具体动作：在另一台干净 Windows 10/11 x64 机器解压发布包并双击 `verify_clean_windows.cmd` 取得 A22 证据；在可用的高 DPI/跨屏环境完成 A10，实际切换 Windows 系统主题验收 A23。若要扩大性能支持边界，再以不同长片及 4K 素材复测。
- 当前启动命令：`dist/VideoCompare.dist/main.exe`；源码运行 `.venv\Scripts\python.exe -m video_compare --ffprobe .codex-tools\ffmpeg\ffmpeg-9.0.1-essentials_build\bin\ffprobe.exe`。
- 当前测试命令：设置 `QT_QPA_PLATFORM=offscreen` 后运行 `.venv\Scripts\python.exe -m pytest tests/unit tests/integration tests/gui -q`；原生显示器验证运行 `.venv\Scripts\python.exe tools/verify_annotation_gl.py --ffprobe <项目 ffprobe.exe> --output <新目录>`。
