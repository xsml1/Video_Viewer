# 验收状态（A01–A23）

## 2026-10-13：追加工作区全屏

用户明确授权A20中的全屏单项，并要求先将当前功能同步原GitHub仓库，再执行剩余自检/验证。此前已执行的结果保留；以下不把尚未构建的全屏包宣称通过。

- 本机源码原生GL：reports/artifacts/fullscreen-native-gl-delivery-20261013/result.json，退出0；屏幕/画布/framebuffer1920×1080、DPR1，同canvas/transport/decoder/完整帧组保留。Space播放暂停、左右真实帧标识、Ctrl滚轮联动、Esc/F11/右上×退出与恢复通过，混合截图/导出及输入SHA不变。源48文件摘要8377BD7BD97CD17CC4C02FDB911E2328359B688A70832C99909D6730BDA7CA82；截图native-gl-fullscreen.png。
- 全屏GUI与相关21项通过/4.10s，reports/fullscreen_gui_tests_20261013.log，退出0；覆盖正常/最大化/隐藏侧栏恢复、模态隔离、ROI、关闭释放。新增动态标注完成后隐藏恢复的回归待同步后执行。
- 源码进程自检两种输入均含真实全屏/×恢复相位，输出fullscreen=True normal_restore=True；reports/fullscreen_source_mixed_selftest_20261013.log、fullscreen_source_image_selftest_20261013.log，退出0。
- 全屏最终Windows包及完整最终回归尚待同步后运行。下方226项/9702A6包是增加全屏前的已验证混合版本；M9其余P2仍范围外，高DPI/跨屏与异机继续未验证。

## 2026-10-12–13：文件夹浏览与混合工作区

本轮按用户新要求替换右侧操作栏、取消图像/视频模式分类、直接拖拽交换并使Space独占播放/暂停。Windows 11 x64（build26200）、CPython3.11.16、PySide6/Qt6.11.2、PyAV16.1.0、FFmpeg/ffprobe9.0.1。测试基于 `ca06178b7fd3131db677dc6223291ccb8dccbda0` 的未提交工作树；`src/**/*.py`48文件摘要 **CD901E5A2ABFEFF1B2EA739F8BB915B93CAEE7EB0CD8F8092E8B120B3B700259**。下方历史结果不代表本版。

| 项目 | 状态 | 本轮实际验证、预期及证据 |
|---|---|---|
| U13 文件夹浏览（A01/A02） | 已验证通过（本机） | 真实中文/空格目录：双击进入下级/媒体添加，上级/后退/前进/刷新/路径输入/选择取消；源文件只读，旧栏所有控件不可见。`tests/gui/test_file_browser.py`6项通过；原生鼠标操作见下列GL工具。目录操作为导航，不进行磁盘重命名/移动/删除。 |
| U14 混合工作区（A01–A07/A16） | 已验证通过（本机） | PNG+带帧ID的真实H.264 B帧视频混合，总计最多6路；后台完成顺序仍按导入顺序；视频播放/步进时图像对象和RGB不变，不缩短公共区间。移除最后视频保留图片并拒绝旧transport；首组GL失败后软件显示同一完整组。`tests/gui/test_mixed_workspace.py`6项通过，原生主流程退出0。 |
| U15 拖拽交换（A08/A09/A11/A16） | 已验证通过（本机） | 实际跨格鼠标拖放交换，仅改变排列，decoder、请求、帧、基准、视图不变。同格/中键平移保留，ROI/标注优先；阈值/Esc/返回原格/离开/布局变化取消。`tests/gui/test_pane_swap.py`11项通过，原生GL截图与行为断言退出0。 |
| U16 Space独占（A03/A06） | 已验证通过（本机） | 按钮/输入框/目录树焦点下只播放暂停，不触发按钮、不输入空格、不添加素材；autoRepeat忽略，模态窗口隔离。GUI及原生工具通过。纯图像播放禁用，方向键文字编辑保留。 |
| A14 混合截图/导出 | 已验证通过（本机） | 固定第18UI帧（source ID17）后截图再播放，PNG/JSON仍为固定组，视频PTS/帧身份与像素一致、图像标明static、media_kind=mixed。对比图1078×302/无JSON，输入SHA不变。`reports/artifacts/mixed-native-gl-delivery-20261013/frames/`、`view/`、`mixed-comparison.png`。 |
| A19 GL/软件回退 | 已验证通过（本机所测） | 原生单QOpenGLWidget，DPR1/framebuffer1080×678，角落标签1252绿色像素。模拟首次上传失败的软件回退保留完整真实帧/顺序/视图/decoder，截图可保存。Qt `QWidget.grab()`漏GL叠加，`window-qt-widget-grab.png`只证外壳/目录；画布证据用独立`native-gl-mixed-swapped.png`及实际产品截图。 |
| A18 索引关闭 | 已验证通过（专项） | SQLite每次连接独占并关闭，事务成功提交/异常回滚；保留强引用时仍能立即Windows rename/unlink；两个线程及真实H.264读写/reuse覆盖。连接/索引/运输22项专项通过。 |
| A01–A09/A11–A16/A18/A23 既有回归 | 最终完整集运行中 | Ruff检查/格式退出0（97文件），`reports/workspace_ruff_20261013.log`。审查前快速全回归216 passed、2 deselected/43.71s，`reports/workspace_regression_20261013.log`。最终源码226项含两个100次开闭/替换循环正在执行，完成后替换本状态。 |
| A22 新Windows包 | 本机包已验证，异机环境阻塞 | 构建退出0，`reports/build_workspace_20261013.log`；`dist/VideoCompare.dist/main.exe` SHA256 **9702A62658BC3F643033F22DEF0C67D4A6C9F6062D8F8F0A26F49EE64224AD99**。旧包保留`dist/VideoCompare.pre-folder-workspace-20261013/`。仅系统PATH独立进程实际PNG+H.264混合导入/定位/截图/导出退出0，`reports/package_mixed_workspace_20261013.log`和`reports/artifacts/package-mixed-workspace-20261013/`。随包自检实跑视频、图像、PQ/HLG、16位图像，退出0及CLEAN_WINDOWS_SELF_TEST_OK，`reports/clean_windows_workspace_20261013.log`。 |
| A10/A17/A20–A21/A23 边界 | 环境阻塞/未重测/范围外 | 真实高DPI/跨屏、第二台干净Windows、实际系统主题变化仍未测；本轮未重测30分钟吞吐/6路4K持续实时。M9/P2仍范围外；此处工作区是同窗会话，不增加Workspace持久化。 |

原生验收：`.venv/Scripts/python.exe tools/verify_mixed_workspace.py --ffprobe <ffprobe.exe> --output reports/artifacts/mixed-native-gl-delivery-20261013`，退出0，`reports/mixed_native_gl_delivery_20261013.log`及目录中的`result.json`。测试输入为本地生成PNG和带可识别帧ID的压缩视频，不读写用户原件；大型素材、缓存、报告日志和发布包按忽略规则只留本机。

构建缺少dumpbin时跳过Qt依赖探测并警告，不影响本次构建；上述实际独立程序与随包自检证明本机所测流程可运行，不能替代另一台干净机器验收。

## 2026-10-01：视频/图像格式、HDR 与本机发布验证

本节更新本次受影响项；后文 9 月记录为历史版本。平台 Windows 11 x64、Python 3.11.16、PySide6 6.11.2、PyAV 16.1.0（wheel FFmpeg 库）、CLI FFmpeg/ffprobe 9.0.1；Pillow 12.3.0、pillow-heif 1.8.0、rawpy 0.27.1、imagecodecs 2026.3.6、tifffile 2025.5.10。Git 测试起点 `5ef2839`，实现和证据测试时为未提交变更。

- 完整回归对象：47 个 `src/**/*.py` 摘要 `9D84831E8FA857B2FFB9F78914DF610353E344433F0AC69EDB762A24344D8655`；`pytest -q --basetemp reports/artifacts/pytest-all2-20261001 -o cache_dir=reports/artifacts/pytest-cache-20261001`，**193 passed / 417.11s**，包含 100 次实际窗口开闭与 100 次替换/移除/重载、旧 worker 退出断言。日志 `reports/all_tests2_20261001.log`，退出 0。
- 此后修正发布自检的混合容器 PTS 预期、固定长提示导致的状态栏换行，并增加三个峰值元信息用例；最终源码摘要 **`04CE493FBF41D596AA397A3A0947A9BBAEA7F1A4D77E3B4FEE981B1E0E3390E7`**。最新非耗时回归、色彩专项和最终包结果见下表。媒体/同步算法在长测后仅调整无效及低亮度峰值的标记处理；长测输入真实 1000 nit 的处理不变。
- 静态检查：`ruff check src tests tools`、`ruff format --check src tests tools` 退出 0，`reports/ruff_delivery_20261001.log`。
- 生成视频/图像不是用户素材。所有输入按只读处理，内容哈希检查通过；大型测试素材、虚拟环境及包不提交 GitHub。生成命令：`tools/generate_format_fixtures.py --ffmpeg <ffmpeg.exe> --output tests/assets/generated/formats-20261001`、`tools/generate_hdr_fixtures.py --ffmpeg <ffmpeg.exe> --output tests/assets/generated/hdr-20261001`；日志分别在 `reports/format_fixtures_20261001.log`、`reports/hdr_fixtures_20261001.log`。

| 项目 | 状态 | 实际验证与证据（2026-10-01，退出码均为 0） |
|---|---|---|
| A01–A09、A11–A12、A15–A16 | 已验证通过（本机既有范围） | 完整 193 项回归及最终快速回归保留真实导入、VFR、Offset、模式切换、逐帧步进、公共区间、ROI、慢路/晚到隔离、循环和 Marker；不放宽帧号、PTS 或资源断言。 |
| A04 扩展编码/容器 | 已验证通过 | `tests/integration/test_format_compatibility.py` 对 30 组真实编码/容器各检查 107 个定位目标、首末/GOP/B 帧、独立 ffprobe PTS 和内嵌源帧 ID；含 H.264/HEVC/VP8/VP9/AV1/MPEG-2/MPEG-4/MJPEG/WMV2/ProRes/DNxHR/FFV1/HuffYUV/QTRLE/Theora。最终回归日志 `reports/complete_tests_20261001.log`。 |
| A10 | 进行中，实际设备环境阻塞 | 本版 `tools/verify_display_metadata.py` 在本机 DPR1 和 `QT_SCALE_FACTOR=1.5/2` 上，GL/软件旋转及 SAR 逐像素通过：`reports/artifacts/display-metadata-20261001/`、`display-metadata-dpr150-20261001/`、`display-metadata-dpr200-20261001/`；日志 `reports/display_metadata*_20261001.log`。模拟缩放不能替代实际高 DPI/跨屏验收。 |
| A13、A19 HDR/BT.2020/颜色 | 已验证通过（SDR 预览范围） | 9 组 PQ/HLG/BT.2020 SDR/P3、10/12 位、有限/全范围真实视频：整帧与独立 CLI swscale/zimg/Hable 对照最大 <=1 个 8 位灰阶，逐帧 ID、PTS、只读保护通过。`tests/integration/test_hdr_compatibility.py`。PQ 标准亮度、HLG 固定曝光、真实元信息、BT.2020 CL 和 Dolby Vision 基础层策略另测；`reports/color_delivery_tests_20261001.log`，27 passed。Dolby Vision 是策略注入测试，没有真实 DV 片验收。 |
| A14 | 已验证通过（本机） | HDR 实际解码 RGB8 与帧截图 PNG 逐像素一致，JSON 保留源矩阵/范围/原色/transfer/位深/峰值/推定及策略。混合 MKV/TS 自检按真实时间区间验收，不误要求相同 ordinal；`reports/selftest_mixed_pts_20261001.log` 和对应输出。最新包 35 个独立进程覆盖导入、定位、固定帧组截图及合成图导出。 |
| A17 | 已验证通过（本机所测负载） | 两路真实 1920×1080、30fps、HEVC 10-bit PQ、60s 同一生成文件的独立解码路；64 MiB 缓存、每2秒随机定位、原生可见 GL 每5秒采样 framebuffer。**1800.0s、12,981 组、899 次 seek、错误列表空**；359 个 RSS/缓存/队列采样，缓存峰值 62,208,000 B（预算 67,108,864 B），结果队列峰值4，worker pending峰值2，线程始终7；关闭后全部 worker 已退出。RSS 首/末/峰值 541,978,624 / 521,650,176 / 549,736,448 B，没有持续增长。WDDM 1536.524s、255样本，79,400,960–79,425,536 B。证据 `reports/benchmark_hdr_gui_30min_20261001.json/.log`、`reports/benchmark_hdr_gpu_20261001.json/.log`；输入 `tests/assets/generated/hdr-20261001/stress1080pq60s.mp4`。运行期间存在构建/测试负载，平均7.21组/s包含随机定位停顿，不能当独占吞吐量或30fps保证；GPU采样从长测中途开始。测试对象为前述193回归源码版本。 |
| A18 | 已验证通过（本机） | 两个100次循环用例包含在193通过完整回归；长测确认 decoder、视频/图像 loader、截图 worker 关闭退出。最终状态栏修改另以15个标注/布局/语言 GUI 用例通过，`reports/status_layout_tests_20261001.log`。 |
| A19 原生画布 | 已验证通过（本机） | 真实PQ/HLG两路再扩展六路，原生GL 100%裁切等于解码RGB，完整帧组截图、脱离/重入通过；`tools/verify_gl_canvas.py --ffprobe <ffprobe.exe> --output reports/artifacts/hdr-native-gl-release-20261001 <PQ.mp4> <HLG.ts>`，`reports/hdr_native_gl_release_20261001.log`。 |
| A20–A21 | 不在当前范围 | M9/P2 未实现，不声称通过。 |
| A22 | 本机包已验证，另一台干净机器环境阻塞 | 最终文件夹包用仅系统 PATH、无 PYTHONPATH/VIRTUAL_ENV 的独立进程验证 39 组视频、29个图像样本及源哈希，图像固定参考颜色在导出图中检查。随包一键自检实际生成普通视频、PQ/HLG、16位 PNG/TIFF 并运行程序。缺少第二台机器，不能据本机启动宣称干净机器通过。 |
| A23 | 部分通过，实际系统通知未验证 | 主题/语言/设置持久化相关 GUI 回归通过。尚未实际切换 Windows 系统主题验证通知链；固定状态栏后原生GL检查通过。 |
| I04 图像兼容 | 已验证通过（所列样本） | 29 个真实图像样本加16位方向/平面布局/Alpha/多页、改名读取、预算、失败后继续加载，以及真实LibRaw合成Bayer DNG/改名DNG显影。`tests/unit/test_image_readers.py`、`tests/integration/test_format_compatibility.py`。JXL/XR/LS 未校验全部ICC/HDR配置，厂商相机RAW与PSD分层等仍未验证；详细边界见 `docs/FORMAT_SUPPORT.zh-CN.md`。 |

最终交付验证：

- 最终源码摘要 `04CE493FBF41D596AA397A3A0947A9BBAEA7F1A4D77E3B4FEE981B1E0E3390E7`，最新 `pytest -q -k 'not test_one_hundred_real_single_video_window_open_close_cycles and not test_hundred_real_replace_remove_reload_cycles_release_old_workers' --basetemp reports/artifacts/pytest-complete-20261001 -o cache_dir=reports/artifacts/pytest-cache-20261001`：**194 passed、2 deselected / 39.45s**，`reports/complete_tests_20261001.log`，退出0。两个耗时用例已在本次完整193通过回归中实际执行；本次定向复测保留其原断言并明确排除，无 skip/xfail。
- `scripts/build_windows.ps1 -FfmpegBin <本机bin>` 最终构建退出0，`reports/build_hdr_complete_20261001.log`；`dist/VideoCompare.dist/main.exe` SHA-256 **`8229DF06548040DFBEB5286CDBC6446613CDF9800B37B045A5A2E44A29BFD791`**。包内实际包含 ffprobe/ffmpeg、Qt 图像插件、imagecodecs 扩展以及 msvcp140/vcomp140/vcruntime140 等依赖。早期构建警告与中间包只作为诊断记录，不代替最终产物。
- `tools/verify_format_package.py --exe dist/VideoCompare.dist/main.exe --output reports/artifacts/package-format-complete-20261001`：35个实际独立程序进程，39组视频和29个图像样本，均完成真实导入、定位/对比、截图/导出；图像参考颜色与全部输入哈希通过。结果 `reports/artifacts/package-format-complete-20261001/result.json`，日志 `reports/package_format_complete_20261001.log`，退出0。
- `dist/VideoCompare.dist/verify_clean_windows.ps1` 在本机项目专用临时目录运行，普通视频、PQ/HLG与16位PNG/TIFF四组实际程序自检通过，`reports/clean_windows_selftest_complete_20261001.log`，退出0、`CLEAN_WINDOWS_SELF_TEST_OK`。该日志记录实际生成的输出目录。
- 上述产物与详细JSON/log保存在本机且实际存在；GitHub保留本报告和可复跑脚本，不上传生成素材、缓存、虚拟环境或发布文件夹。另一台干净机器、真实高DPI/跨屏、Windows系统主题实际变化仍未验证，完整M0–M8门槛尚未全部满足。





## 2026-09-27 标注作用域、语言与新版包

本节测试对象为 Windows 11 x64、CPython 3.11.16、PySide6 6.11.2、PyAV 16.1.0、Pillow 12.3.0、pillow-heif 1.8.0、rawpy 0.27.1，`src/**/*.py` 43 文件摘要 `2DB84E77F33CA66A767B2782D53316F06C23120AB838B8FCA2F942E528951350`。测试时 Git 尚无提交；测试对象为当前工作树。输入是本地生成图像和真实 H.264 压缩测试视频，不含上传的用户素材。

| 项目 | 状态 | 命令/操作、预期、实际与证据 |
|---|---|---|
| U12 单路标注 | 已验证通过（本机） | `tests/gui/test_annotation_scope.py` 对真实双路 H.264 和两张本地图像模拟矩形与自由画笔；关掉“标注联动到全部画面”后，画布和导出图的未选择路像素保持一致，选中路包含对应笔画。`tests/unit/test_comparison_export.py` 再检查混合全路与单路笔画。原生 Windows OpenGL 的 `tools/verify_annotation_scope_gl.py --ffprobe <ffprobe.exe> --output reports/artifacts/annotation-scope-gl-20260927-final` 退出 0，结果和截图在该目录。 |
| L01 八种语言与自称 | 已验证通过（本机） | `tests/gui/test_language_settings.py` 遍历简体中文、繁體中文、English、日本語、한국어、Français、Deutsch、Español，逐一验证语言选项名称固定、主题/语言页文案切换、设置持久化与重启恢复；真实双图保持同一完整组与像素。`tools/verify_language_ui.py --output reports/artifacts/languages-gl-20260927-final` 在原生 Windows 窗口采集八种语言的主窗及设置两页截图、输出 `result.json`，退出 0。语言诊断文本尚未逐条人工校对。 |
| L02 回归与构建 | 已验证通过（本机） | `ruff check src tests tools` 和 `ruff format --check src tests tools` 均退出 0；离屏 `pytest tests/unit tests/integration tests/gui -q -k 'not test_one_hundred_real_single_video_window_open_close_cycles'` 为 126 passed、1 deselected/41.10 秒，另该 100 次窗口循环测试 1 passed/283.11 秒。`scripts/build_windows.ps1` 退出 0，`dist/VideoCompare.dist/main.exe` SHA-256 `4C32DF23E409A4B32E146029B4403DE8E488076383857C6F83FF51CB0E6EE0B5`；包内 `verify_clean_windows.ps1` 在本机用随包 FFmpeg/程序生成并对比真实视频和图像，两个自检均退出 0，最终 `CLEAN_WINDOWS_SELF_TEST_OK`。异机 A22 仍未验证。 |

本节证据目录 `reports/artifacts/` 按 `.gitignore` 留在本机，不随公开源码仓库上传。下面旧版性能测量只作为历史记录，不代表本版重复测量。

## 2026-09-27 新增双模式与图像验收

当前新增范围为“视频对比 / 图像对比”切换及静态图像对比。Windows 11 x64、Python 3.11.16、PySide6 6.11.2、Pillow 12.3.0、pillow-heif 1.8.0、rawpy 0.27.1；图像输入均为本次本地生成，不含用户素材。

当前源码 `src/**/*.py` 共 40 文件，摘要 `5F1A929678E4F59271F5456ED38130CABB5C1EE5CA8A059BFBE57BD6C904B7EC`（`tools/source_digest.py`），Git `master` 无提交、全部文件未跟踪；未暂存用户素材。`ruff check src tests tools` 和 `ruff format --check src tests tools` 退出码 0。最终源码的离屏全回归（排除耗时的 100 次窗口测试）为 **121 passed、1 deselected/37.04 秒**；100 次窗口测试在此次改动中另跑，整套 **122 passed/244.51 秒**（其后只对图像读取和切回播放标签作小改动，图像用例再次 2 passed）。本机真实 OpenGL 源码自检 `IMAGE_SELF_TEST_OK`，输出 `reports/artifacts/image-mode-20260927/result/image_compare.png`。

| 项目 | 状态 | 实际验证与证据 |
|---|---|---|
| I01 双模式与操作 | 已验证通过 | `tests/gui/test_image_mode.py`：切换图像模式，真实两图导入、替换、保存各图 PNG/JSON、导出对比 PNG、切回视频再切回图像；原件 SHA-256 不变。图像无时间操作，播放控件隐藏。图像组联动区域在两路相同；以真实鼠标操作绘制图像标注，导出 PNG 中检出红色笔画，成功后清除标注。旧视频组信号无法覆盖当前图像。用户实际文件上的手感仍待体验验收。 |
| I02 格式读取 | 已验证通过（列出的样本） | `test_real_still_formats_orientation_and_alpha` 实读 PNG、JPEG、TIFF、WebP、AVIF、HEIC、BMP、GIF、SVG 的本地生成文件，核对真实 RGB、尺寸、EXIF 方向、透明白底、无 ICC 的 CMYK 默认转换及 16-bit 灰度高 8 位预览。`reports/artifacts/image-mode-20260927/` 的 PNG/WebP 和 HEIC/AVIF 双图又经真实 Windows OpenGL 源码与独立包导出；RAW、PSD/PDF 变体和所有格式的全部编码变体未验证。 |
| I03 包内图像与视频 | 已验证通过（本机） | `main.exe --mode image --self-test-image-output ...` 分别以 PNG/WebP、HEIC/AVIF 输入退出 0，生成 `package/image_compare.png`、`package-heif/image_compare.png`。`tools/verify_package.py` 使用包内程序和真实两路 H.264，输出 `SELF_TEST_OK`、退出 0，见 `package-video/`。另一台干净 Windows 仍未验证。 |

最终构建 `dist/VideoCompare.dist/main.exe` SHA-256 `978625DB21803FABFA6105E138AAE7A478CEB04F1A06AF65862878711E2B7DEF`。最终包再次在仅系统目录 PATH 的进程中读取 HEIC/AVIF 并导出，退出 0（`reports/artifacts/image-mode-20260927/final-package-heif/`）；`tools/verify_package.py` 的真实双路 H.264 再次退出 0（`final-package-video/`）。包内 `verify_clean_windows.ps1` 本机生成两段 H.264 与 PNG/WebP，两个自检分别输出 `SELF_TEST_OK`、`IMAGE_SELF_TEST_OK`，脚本最后输出 `CLEAN_WINDOWS_SELF_TEST_OK`，退出 0；结果目录 `C:/Users/XSML/AppData/Local/Temp/VideoViewerSelfTest-fc032ed3c9da49eebb21e40c9ae9104c/`。该临时目录属于本机，不是可移植交付路径；另一台干净 Windows 仍为 A22 未验证。

下面的 A01–A23 和性能数字是 2026-09-25 版本的逐项历史记录；本次源码的单元/集成/离屏 GUI 全量回归及本机包内视频自检另见本节。30 分钟资源数据尚未在本次新增版本重测，不把历史性能数字外推到本次版本。

最后实际复测：2026-09-25，Windows 11 10.0.26200 x64，AMD Ryzen 7 9800X3D、NVIDIA GeForce RTX 4070 SUPER；项目 CPython 3.11.16、PySide6 6.11.2、PyAV 16.1.0、NumPy 2.4.6，外部 FFmpeg/ffprobe 9.0.1。除注明外，全部输入均为本地生成视频。用户竖屏录制素材仅以只读方式打开。当前 `src/**/*.py` 共 39 文件，摘要 `DD9EB070D0D546463325EC783F249CBB888528CD1220B6DC95836EEAD15E2D58`（`tools/source_digest.py`）。仓库无提交，工作树全部未跟踪；逻辑变动后须重跑相关项。

本页所用命令/操作代号，退出码均为 0，除非条目另述：

- T：`$env:QT_QPA_PLATFORM = 'offscreen'; & .\.venv\Scripts\python.exe -m pytest tests\unit tests\integration tests\gui -q -k 'not test_one_hundred_real_single_video_window_open_close_cycles'` → 最新复测 **119 passed、1 deselected/37.85 秒**。另以同版源码单独运行 `test_one_hundred_real_single_video_window_open_close_cycles` → **1 passed、205.39 秒**；共覆盖 120 项。离屏 GUI 不能证明真实显示器 OpenGL/DPI。
- L：`& .\.venv\Scripts\ruff.exe check src tests tools` 与 `ruff format --check src tests tools`，均通过；69 文件格式符合约定。
- U：`& .\.venv\Scripts\python.exe tools\verify_ui_and_export.py --ffprobe <项目 ffprobe.exe> --portrait "test_data\VID_20260722_223022.mp4" "test_data\VID_20260722_223022 - 副本.mp4"`，真实显示器的原生 GL 窗口上验证自适应排列、拖拽方向、对比图导出与导出对话框，退出码 0；证据 `reports/artifacts/ui/`。省略 `--portrait` 时使用生成的竖屏旋转素材。
- G：`& .\.venv\Scripts\python.exe tools\verify_gl_canvas.py --ffprobe .\.codex-tools\ffmpeg\ffmpeg-9.0.1-essentials_build\bin\ffprobe.exe --output reports\artifacts\monotonic-gl-20260925`，本轮源码在实际 Windows 显示器上的 2/6 路 OpenGL 画布、真实解码 RGB 原生像素裁切、六路脱离/重入及截图均通过，退出码 0；当前显示器 DPR 1.0。以前 `QT_SCALE_FACTOR=1.5`、`2.0` 的模拟缩放通过，但不等于多显示器实测。
- N：`& .\.venv\Scripts\python.exe tools\verify_annotation_gl.py`，最新源码在实际 Windows 显示器、原生 `QOpenGLWidget`、两路真实压缩视频上执行自由画笔、缩放定位和对比图导出，退出码 0；画布 framebuffer 1080×678、DPR 1.0，源定位附近命中 30 个紫色像素，导出 1078×302 中有 1494 个紫色像素，未产生 JSON；圆角蒙版排除左上 (0,0)。`reports/artifacts/annotation-gl-20260925/result.json`、`native-gl-pen.png` 与导出 PNG。
- U2：`& .\.venv\Scripts\python.exe tools\verify_ui_and_export.py --ffprobe <项目 ffprobe.exe> --output reports/artifacts/ui-annotation-20260925 --portrait <本机两路竖屏视频>`，最新源码真实 OpenGL + 用户竖屏素材上，侧栏 330→260px、隐藏/呼出均检测到中间宽度并完成 220ms 动画；窗口、设置对话框及标注导出截图实际生成。新设置截图显示“清爽极简”；蓝色矩形导出 4810 像素，无 JSON，成功后画布标注清除；退出码 0。
- D：`tools/verify_display_metadata.py --ffprobe <本项目 ffprobe.exe> --output reports/artifacts`，真实 F07 旋转 90/180/270° 与 SAR4:3 素材在软件和原生 GL 上对照源 RGB/FFmpeg 自动旋转；DPR 1、模拟 1.5/2.0 均通过。图片在 `reports/artifacts/f07_gl_*.png` 及 `dpr150`、`dpr200`。
- C：`& .\.venv\Scripts\python.exe tools\verify_long_cancel.py --ffmpeg <本项目 ffmpeg.exe> --ffprobe <本项目 ffprobe.exe> --output reports\artifacts\long-cancel-progressive-20260925`，本轮源码在 5 分钟/9000 帧 H.264 的 256 帧块后取消；loader 退出、关闭 0.010 秒、索引状态 partial、原件 SHA-256 `5ba119cc5544571254ff1dddaddfa253982b0a9ac8c1c19cd4fe9ceadf3be089` 未变化。
- P：本版源码经 `scripts/build_windows.ps1` 重建，日志 `reports/build_annotation_2026-09-25.log`；`dist/VideoCompare.dist/main.exe` 为 25 134 080 字节，SHA-256 `3331F24495384E8CA6844BECC3BD618C68684004B5DA3AE131858436976026D1`。`tools/verify_package.py` 在同一 Windows 主机用仅含系统目录的 PATH、无 PYTHONPATH/VIRTUAL_ENV/VIDEO_COMPARE_FFPROBE 的独立进程实际启动：生成两路（`reports/artifacts/selftest-annotation-generated/`，`SELF_TEST_OK ... layout_gap=8.0 export=1078x302 icon=True notices=1`）与用户竖屏两路（`reports/artifacts/selftest-annotation-portrait/`，`... export=768x678 ...`）均导入、seek UI 第 2 帧、保存视图 PNG/JSON、导出对比图且不写 JSON，退出码 0。包内 ffprobe.exe/ffmpeg.exe 存在。另新增随包 `verify_clean_windows.cmd/.ps1`，仅用包内 FFmpeg 在临时目录生成两段测试视频并调用 `main.exe` 自检；本机脚本退出码 0、显示 `CLEAN_WINDOWS_SELF_TEST_OK`，日志 `reports/clean_windows_selftest_local_20260925.log`。包内新增标注交互未单独自动操作；N 是同版源码的原生 GL 验证。此项没有覆盖另一台干净机器。

“已验证通过”只表示条目所写的可观察条件在上述条件下实际通过；“进行中”表示仍缺该项部分条件。条目中的测试位置可作为复跑和日志来源，产物图片被 `.gitignore` 排除。P2 条目不在当前范围。

| 编号 | 状态 | 输入/操作、预期与实际、证据 |
|---|---|---|
| A01 | 已验证通过 | T/G：F05 H.264 逐路导入 1–6，逐次检查网格与完整真实帧组；第 7 路提示“最多导入 6 路”且保留原组。单路播放/暂停/帧定位、两路替换失败保留与成功替换、移除均有 GUI 断言。`tests/gui/test_m0_canvas.py`。 |
| A02 | 已验证通过 | T：同一真实 H.264 文件以六个独立 `asset_id`/decoder 导入并同步播放，每个提交组均有 6 张与基准同源 ordinal 的帧，暂停后 100ms 无新组；两路异格式事件并集前缀也通过。`tests/integration/test_transport.py`。 |
| A03 | 已验证通过 | T：GUI 连续 100 次确定随机滑杆请求，最终第 72 UI 帧且 100ms 后无旧画面覆盖；另以慢路 200ms、旧请求晚到验证完整组屏障，结果队列不超过容量。`tests/gui/test_m0_canvas.py`。 |
| A04 | 已验证通过 | T：F05 H.264 B 帧、FFV1、F04 VFR、非零起点、中文特殊路径各 100 次随机 seek 加首末/GOP/后退；目标 ordinal、原 PTS、图中 16-bit ID 全相同，ffprobe PTS 列表独立比对一致。`tests/integration/test_precise_decode.py`。 |
| A05 | 已验证通过 | T：真实 H.264 的 1/5 帧步进、10 次连续右键到第 11 UI 帧、10 次连续左键回第 1 UI 帧，以及 10 个 Qt 自动重复按键事件再次到第 11 UI 帧；每次最终已显示组两路源 ordinal 精确相同，无 ±1 容差。首帧索引尚未完成时连续三次步进也会累计到目标第 4 UI 帧。`tests/gui/test_m0_canvas.py`。 |
| A06 | 已验证通过 | T：0.01 秒连续 5 次累计位置精确、1 秒 GUI 步进到第 31 UI 帧；时间输入框内按方向键不触发视频步进。`tests/gui/test_m0_canvas.py`。 |
| A07 | 已验证通过 | T：真实 F02 24fps、F03 60fps、F04 VFR 三路在 GUI 中同时导入，施加正负时间/帧 Offset、切时间/帧模式与基准；时间模式的每路实际 ordinal 对照独立 ffprobe PTS 与二分结果，帧模式精确满足 K+q_i，切基准后当前各路真实帧不变。公共区间、三路脱离/重入及空范围恢复另有真实 GUI 与纯模型回归。`tests/unit/test_timeline.py`、`tests/gui/test_m0_canvas.py`。 |
| A08 | 已验证通过 | T：F06 480p/1080p/4K 同归一化十分格与红色中央区域真实编码素材，RGB 识别源标记；GUI 在 480p 路框选 ROI 后三路 `ViewRegion` 完全相等，屏幕整像素输入定位与预期内容坐标相符。归一化源像素量化误差模型见 `tests/unit/test_viewport.py`；GUI 见 `tests/gui/test_m0_canvas.py`。 |
| A09 | 已验证通过 | T：内容区 Ctrl+滚轮缩放、无 Ctrl 滚轮和黑边滚轮不缩放；黑边起始框选不改变视图，2px 无效 ROI 被拒绝，画面右下角 5px 有效 ROI 被钳制在归一化内容范围内并联动两路；Fit 恢复两路完整画面，缩放后的 Pan 通过。`tests/gui/test_m0_canvas.py::test_ctrl_wheel_links_view_and_black_bar_does_not_zoom`。 |
| A10 | 进行中 | G/D/T：原生 100% 裁切在本机 DPR 1 逐像素等于真实解码 RGB，模拟 DPR 1.5/2.0 的 GL/软件及旋转/SAR 通过；实际 150/200% 显示器与跨屏 DPR 动态更新无法在当前单显示器环境验证。`tests/unit/test_pixel_inspect.py`。 |
| A11 | 已验证通过 | T/G：最大化/Esc/重排不更改 `asset_id`、基准、Offset 或完整组；非基准路退出时间同步保留已显示帧并标注，重入对齐当前组，六路原生画布出图；末端重入夹到公共有效边界并提示。`tests/gui/test_m0_canvas.py`、`reports/artifacts/m5_gl_detached.png`。 |
| A12 | 已验证通过 | T：真实两路 H.264 在时间/帧两种同步模式下实测 0.25× 与 2× 的连续完整组间隔，源 PTS 为 1/30 秒、慢放约对应 133ms、快放约对应 17ms 目标；定时测试验证两者明显分离且组 ordinal 连续。运输时钟已改为累计单调截止时间，解码延迟不再逐帧叠加。真实两路 4× `[A,B)` 循环至少 100 次，循环末帧包含且没有 B 外帧闪现；GUI 速度控件各倍率有效。`tests/integration/test_transport.py`、`tests/gui/test_m0_canvas.py`。重负载达不到设定倍率时仍受硬件性能限制。 |
| A13 | 已验证通过 | T/D：真实 90/180/270°、SAR4:3、10-bit SDR、HDR/PQ/BT.2020；旋转画面/截图对照 FFmpeg 自动旋转，色彩 limited/full 与 601/709 固定参考块通过；缺失元信息显示“色彩推定”，10-bit SDR 标注 RGB8，HDR 路拒绝且已有组不变。`tests/integration/test_display_metadata.py`、`tests/unit/test_color.py`。 |
| A14 | 已验证通过 | T/G/P：暂停与播放中对两路真实帧组保存合成视图和各路原帧 PNG/JSON；播放中点击后冻结的组 ID、PTS/帧号和源 RGB 均对应同一快照，无混时刻。ROI 后保存的合成 PNG 逐像素等于当时软件画布，sidecar 记录两路 ROI；旋转原帧截图另与独立 FFmpeg 自动旋转结果匹配。已有路径不覆盖，写失败提示且原文件与旧组保留；脱离路在 JSON 标 `detached`。本机原生 GL 合成截图与发布包自检均通过，真实跨屏 DPR 仍归 A10。`tests/gui/test_m0_canvas.py`、`tests/integration/test_display_metadata.py`、`tests/unit/test_screenshots.py`。 |
| A15 | 已验证通过 | T：真实完整组建立会话 Marker，添加标题/备注、切基准后跳回同一源帧；退出提醒只保留本会话。`tests/gui/test_m0_canvas.py`、`tests/unit/test_markers.py`。 |
| A16 | 已验证通过 | T：屏障纯模型拒绝缺路、错 ordinal、旧 generation；真实 GUI 注入一路 200ms 延迟、过期返回及解码错误，画布只在整组完成后变化，错误时保持上一组并进 ERROR，后续定位恢复。`tests/unit/test_barrier_cache.py`、`tests/gui/test_m0_canvas.py`。 |
| A17 | 已验证通过 | T：8 MiB 小缓存播放及缓存 pin/逐出、有限任务/结果队列已测；六路 1080p、64 MiB 缓存下下一完整组能提交且旧快照像素不变。本版原生 GL/两路 1080p/64 MiB/每 2 秒随机 seek 的 1800 秒测试退出码 0，39,432 组、899 次 seek、359 个样本、错误列表空；缓存峰值 62,208,000 B < 64 MiB、结果队列峰值 2、线程峰值 6，关闭后 worker 均退出。RSS 首/末/峰值 334.95/343.27/343.40 MB，后 10 分钟中位数约 326.3→327.2 MiB，增长放缓；WDDM 显存 293 个样本、79.40–81.52 MB。`reports/benchmark_gui_30min_annotation_20260925.json`、`benchmark_gpu_30min_annotation_20260925.json`。条件为 4 秒生成短片循环、DPR1；不推断长片或六路 4K 持续实时。 |
| A18 | 已验证通过 | T/C：真实两路 100 次替换/删除/重导入且每轮旧 worker 退出；真实长片索引中取消无死锁、partial 状态与原件哈希未变；模拟慢 ffprobe 关闭可取消。本版单路真实窗口独立打开关闭 100 次通过（205.39 秒）；100 次快速 seek 后第 101 次在途关闭的测试在本版 T 中通过。`tools/verify_long_cancel.py`、`tests/gui/test_m0_canvas.py`。 |
| A19 | 已验证通过 | G/D/T：同一源 RGB 已知颜色块经软件/原生 GL 及合成/原帧 PNG 对照，原生像素裁切在 DPR1 完全相同；旋转源的方向和色块位置与 FFmpeg 参考吻合，未加额外 gamma。`tools/verify_gl_canvas.py`、`tools/verify_display_metadata.py`、`tests/unit/test_color.py`。 |
| A20 | 不在当前范围 | M9/P2 的 A/B、分割、冻结、ROI 导出、全屏未实现或验收。 |
| A21 | 不在当前范围 | M9/P2 Workspace 未实现或验收。 |
| A22 | 进行中 | P：本版发布包在本机无 Python/ffprobe PATH 环境中实际两路导入、seek、截图、对比图导出并退出 0；包内 `bin/ffprobe.exe`、`bin/ffmpeg.exe` 存在。随包一键自检脚本本机运行通过，输出记录见 `reports/clean_windows_selftest_local_20260925.log`；另一台干净 Windows 10/11 x64 机器解压启动仍未验证，不能称 A22 全通过。`scripts/build_windows.ps1`、`tools/verify_package.py`、`reports/artifacts/selftest-annotation-generated/` 与 `selftest-annotation-portrait/`。 |
| A23 | 进行中 | T：1/3/6 路暂停的真实视频遍历 system/light/dark 与 blue/green/purple/orange，组对象、RGB、视图区域不变，TOML 重启持久化；三路播放中切换仍继续提交完整组。现已订阅 `colorSchemeChanged`，测试注入 Qt 系统外观变化信号后“跟随系统”刷新样式且保留帧组/RGB/ROI，手动深色不响应；真实 Windows 运行中改变系统主题的通知链尚未验证。`tests/gui/test_m0_canvas.py`、`tests/unit/test_settings.py`。 |

## A17 当前版本资源与速度实测

测试机：Windows 11 专业版 10.0.26200 x64、Ryzen 7 9800X3D（8 核）、GeForce RTX 4070 SUPER、约 31.6 GiB RAM、本地 Predator GM7 SSD、显示器 DPR 1.0；CPython 3.11.16、PyAV 16.1.0、PySide6 6.11.2、FFmpeg/ffprobe 9.0.1。被测应用源码摘要为 `DD9EB070D0D546463325EC783F249CBB888528CD1220B6DC95836EEAD15E2D58`。输入是本地生成、8-bit yuv420p、H.264、1920×1080、30 fps、GOP 60、2 个 B 帧的真实压缩素材；两路/六路均用同一文件作为**独立解码路**，不代表不同磁盘文件同时读取。索引建立完成后才开始计时，属于热文件缓存条件。

- `tools/verify_gui_stability.py --duration-s 1800 --seek-every-s 2 --cache-mib 64 --routes 2` 使用 4 秒素材重复定位以维持 30 分钟负载。原生可见 `QOpenGLWidget` 每 5 秒抓取 framebuffer 并检查真实 PTS。脚本退出码 0、`status=measured`、错误列表空；1800.0 秒内提交 39,432 组、899 次随机 seek，359 个采样。缓存峰值 62,208,000 B（预算 67,108,864 B）、结果队列峰值 2、worker pending 峰值 0、线程峰值 6，关闭后 decoder/loader/screenshot worker 均退出。RSS 首/末/峰值 334,954,496 / 343,273,472 / 343,396,352 B；最后两个 3 分钟区间的中位数约 327.02/327.22 MiB，增长明显放缓。本次没有看到持续快速线性增长，但一次 30 分钟运行不等于无限期无泄漏。实际组数平均 21.91/s，包含每 2 秒主动 seek 的间歇，不作为持续播放帧率。证据 `reports/benchmark_gui_30min_annotation_20260925.json`。
- `tools/sample_gpu_process.ps1` 对同一进程的 WDDM 专用显存采样从长测启动后开始、进程退出时结束：1763.0 秒、293 样本、79,396,864–81,518,592 B，首/末 81,518,592/79,425,536 B，未见持续增加；证据 `reports/benchmark_gpu_30min_annotation_20260925.json`。
- 为测持续播放速度，另生成 60 秒同规格 H.264 素材，避免 4 秒片到片尾后空等。原生 GL 两路 30.0 秒提交 899 组（29.97/s、一次末段 seek、64 MiB 缓存），六路 15.0 秒提交 449 组（29.93/s、一次末段 seek、512 MiB 缓存）；均退出码 0、错误列表空、缓存未超限。六路峰值 RSS 948,482,048 B，缓存峰值 534,988,800 B。对应 `reports/benchmark_gui_steady_60s_source_20260925.json`、`benchmark_gui_six_1080p_15s_annotation_20260925.json`。无渲染 10 秒补测两路/六路均约 29.8 组/s，见 `reports/benchmark_annotation_1080p_2routes_10s.json`、`benchmark_annotation_1080p_6routes_10s.json`。
- 这些结果证明本机上述工况的资源上限和近 1× 播放；没有验证六路不同长片同时索引、六路 4K 持续实时、冷磁盘缓存或高 DPI 跨屏性能。旧 `reports/benchmark.json` 和 `reports/benchmark_progressive_*.json` 属于此前源码或短测，不能替代本段最新实测。

## 本轮长片增量索引验证（E01/E02，2026-09-25）

以下长片增量索引验证在较早源码摘要 `77576AF2C8E8D8C3FCD52AB13B5EDC00A0D5747AD622B6D1D4ED1EC9F289738A` 下完成；最新源码的相关单元/集成/离屏 GUI 用例见 T：

- 真实 H.264 B 帧首次导入时，完整索引被测试门闩停在第 1 帧；软件画布仍显示源 ordinal 0，连续三次前进请求累计为 ordinal 3，索引释放后显示真实 PTS 对应的第 4 UI 帧。未覆盖时间定位同样先保留请求。`tests/gui/test_m0_canvas.py::test_long_import_opens_real_first_frame_and_queues_steps`，退出码 0。
- 600 帧真实 H.264 索引停在第一批 256 帧后，UI 只开放已确认的 255 帧；播放到 ordinal 254 等待，下一批索引到达后继续到 ordinal 255，未把临时前沿当作 EOF。`test_playback_waits_at_real_index_frontier_and_resumes`，退出码 0。
- 第一条视频完整索引暂停期间，第二条真实 H.264 仍独立探测并显示首帧；两路首帧组同时出现且两条完整索引都未结束。索引中移除该路会取消工作并阻止旧结果重新出现；Offset 暂无公共区间时索引增长后自动恢复。对应 GUI 用例均通过。
- `tests/integration/test_precise_decode.py::test_incremental_timelines_expose_only_real_covered_frames` 用真实 H.264 + B 帧逐批对照完整索引前缀，并解码每批最后一张可见帧的 16-bit 源 ID；没有用平均 FPS 伪造 ordinal。
- 5 分钟/9000 帧取消结果见 C；2/6 路真实显示器 GL 结果见 G。最新版本 30 分钟 GUI/随机 seek 资源验证已通过，见 A17；4/6 路长片同时加载和高 DPI 跨屏压力数据仍未取得，A10 保持进行中。A18 的 100 次窗口开闭已在本版单独复测，见 T。

## 用户新增需求（2026-09-25，超出实施计划原条目）

用户此前提出的界面及导出改动使用上述证据代号；新标注、缩放定位、侧栏动画、圆角和色系名称的源码验证见 T/L/N。旧截图 U 仅证明当时画面；本版发布包状态以 P 项新证据为准。

| 编号 | 状态 | 输入/操作、预期与实际、证据 |
|---|---|---|
| U01 垂直拖拽平移方向 | 已验证通过 | T/U：先复核旧实现与实施计划 7.2 公式一致，且原生 GL 与软件画布在同一缩放子区域逐像素相同（差值 0.000），确认原实现不是渲染反向；按用户要求把垂直方向改为“拖动视图”（`center_v += Δy/(s*Dh)`），水平保持“画面跟随指针”。真实 GL 上 Ctrl+滚轮缩小到 0.6575 后拖拽 (+30,+40)：center_u 0.5004→0.4381、center_v 0.5003→0.5470，方向与约定一致；`tests/unit/test_viewport.py`（含钳制方向）与 `tests/gui/test_export_and_layout.py` 覆盖。原始参数证据：画布 932×585，用户竖屏素材。 |
| U02 画面窗口随导入视频变化 | 已验证通过 | T/U：排列按各路“显示后宽高比”（含旋转/SAR；原生像素忽略 SAR）计算，行划分取同尺度下画面最大且需提升 ≥15% 才增行；行内紧密排列只留 8 逻辑像素，剩余空间移到外侧。用户两路 1080×1920 真实素材中间空隙 8.0px；生成双竖屏旋转素材同样通过。`tests/unit/test_layout.py`、`tests/gui/test_export_and_layout.py`、`reports/artifacts/ui/`。 |
| U03 导出当前缩放对比视图 | 已验证通过 | T/U：新增“导出对比图…”，排列（与窗口一致/横排/竖排/网格）× 格式（PNG/JPEG + 质量），导出为“当前窗口每路可见区域”按设备像素合成；按 2026-09-25 后续要求，导出图**包含画面左上角文件名与右下角帧号/PTS/提醒**，**不再写 JSON**。原生像素 100% 下导出中部区域与源帧裁切逐像素相同、且不产生 JSON（`tests/gui/test_export_and_layout.py`）；角落文字与标注像素、排列尺寸见 `tests/unit/test_comparison_export.py`；写入语义（允许覆盖用户选定路径、不触碰其他文件、编码失败清理）见 `tests/unit/test_screenshots.py`。真实双路导出：PNG 702×618（与理论尺寸一致）、JPEG 348×1242 且为上下两行，证据 `reports/artifacts/ui/对比图_与窗口一致.png`、`对比图_竖向排列.jpg`，对话框截图 `export_dialog_png.png`、`export_dialog_jpeg.png`。 |
| U11 导出前编辑标注（多窗口同步） | 已验证通过 | T/N：真实视频画面可绘制矩形/椭圆/箭头/直线/自由画笔，9 色可选；标注按归一化源坐标锚定，缩放、平移后在画布和导出图中位置一致。工具条可撤销、删除选中项及全部；取消立即清除且不写文件，异步保存成功后清除，写入失败时保留重试。`tests/gui/test_export_and_layout.py::test_annotated_export_syncs_shapes_and_colours` 和 `test_annotation_tracks_source_through_zoom_and_export` 验证两路真实压缩视频、缩放定位、自由画笔像素、删除、取消/成功/失败与无 JSON；N 在真实 OpenGL 上复核紫色轨迹。旧 U 截图仅作原界面历史参考。 |
| U04 现代简约界面 | 已验证通过 | L/T/U：QSS 改为卡片式扁平外观（圆角、轻边框、强调色、下拉箭头、细滑块与滚动条）；按用户后续要求取消独立标题条，文件名直接叠在画面左上角，帧号/PTS/提醒在右下角。真实窗口截图 `reports/artifacts/ui/window_light.png`、`window_dark.png`、`canvas_light.png`；隐藏叠加文字后原生像素 1:1 与 GL 子区域裁切仍逐像素通过。 |
| U05 logo 图标与桌面快捷方式 | 已验证通过 | 当前 logo 为用户提供的 `logo/logo2.png`（已带透明通道，透明像素 63.9%）：`tools/prepare_logo.py` 检测到透明通道后原样保留 alpha，只做裁剪与缩放，生成 `src/video_compare/assets/app.png`（512×512）与多尺寸 `app.ico` 并作为窗口/应用图标（U 打印“窗口图标已设置：True”）；白底不透明的图仍走“只移除边缘连通白色 + 反预乘去白边”的路径。预览 `reports/artifacts/logo/logo_preview.png`。桌面快捷方式 `C:\Users\XSML\Desktop\Video Viewer.lnk`，目标 `scripts\run_video_compare.cmd`，图标为 `app.ico`；实际启动验证命令行使用项目 venv 与随包 ffprobe（验证后关闭测试进程）。局限：快捷方式依赖本机开发环境；发布版入口为 `dist\VideoCompare.dist\main.exe`。 |
| U06 顶部单行工具栏 / 底部播放条 / 右侧可调信息栏 | 已验证通过 | T/U2：`tests/gui/test_shell_layout.py` 验证顶部单行、播放条下置、侧栏宽度可拖拽；本版侧栏隐藏/呼出以 220ms OutCubic 过渡，测试检查中间宽度与快速反向操作，U2 在真实 OpenGL 窗口确认连续宽度动画；播放画布 12px 圆角蒙版测试检查外角不在可见区而内点在可见区，N 在原生 GL 上复核。 |
| U07 整体色系与四角色颜色 | 已验证通过 | T/U2：6 套色系（清爽极简/莫兰迪/奶油风/复古/赛博朋克/马卡龙）决定主题色板；工作区、功能区、强调色和视频信息四个角色分别自由选色或跟随色系，并写入 `settings.toml`。`tests/gui/test_shell_layout.py` 验证新名称及即时生效；`tests/unit/test_settings.py` 验证旧内部键保持兼容；`tests/gui/test_m0_canvas.py` 验证切换后真实帧组与视图不变。U2 的 `settings_dialog.png` 显示新名称。 |
| U09 PPT 式颜色选择器（四角色共用） | 已验证通过 | T/U：设置对话框把工作区/功能区/强调色/视频信息做成角色按钮，右侧色板始终作用于当前角色：主题色行（色系 8 色）+ 5 档深浅（`SHADE_STEPS` 0.8/0.6/0.4 变浅，0.25/0.5 变深）+ 一行 15 个标准色，另有“跟随色系”。`tests/gui/test_shell_layout.py` 断言色块总数 = 色系颜色数×6 + 15，四个角色分别点选颜色后各自写入 `settings.toml` 且画布立即生效，“跟随色系”回到色系主色；`tests/unit/test_settings.py` 覆盖四字段读写、默认视频信息色 `#00b050` 与非法值逐项回退。对话框截图 `reports/artifacts/ui/settings_dialog.png`。 |
| U10 画面内信息位置与颜色 | 已验证通过 | T/U：文件名在画面左上角、帧号/PTS/提醒在右下角，文字带半透明底衬，颜色取“视频信息”角色（默认绿色 `#00b050`，可改）。`tests/gui/test_shell_layout.py::test_overlay_labels_sit_in_the_picture_corners` 与真实 GL 窗口像素计数验证位置及改色；逐像素的 1:1 与旋转/SAR 验证在比对前隐藏叠加层。按后续要求，对比图导出**包含**这些角落文字；证据 `reports/artifacts/ui/canvas_light.png`、`canvas_overlays.png`、`对比图_与窗口一致.png`。 |
| U08 测试与真实配置隔离 | 已验证通过 | T：`tests/conftest.py` 把 `user_config_path` 指向临时目录，GUI 用例显式传 `settings_path` 并在计算 `pane_transform` 时传 `canvas.layout_mode`。修复前 `test_real_480p_1080p_4k_grid_shares_normalized_roi` 因读到本机真实配置（`layout = "horizontal"`）失败；修复后全量 103 项通过，本机配置文件已恢复默认值，见 DECISIONS D027。 |
