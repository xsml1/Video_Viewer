# 技术决策

## D001：运行时与依赖管理

- 日期：2026-09-23
- 决定：使用项目专用 CPython 3.11.16；用 uv 0.12.18 生成 `uv.lock` 并安装 `.venv`，不修改全局 Python。
- 原因：遵守规格的 Python 3.11 约束，并让依赖可复现。
- 当前证据：项目专用解释器位于 `.python/cpython-3.11-windows-x86_64-none`；最初因 README 缺失的同步失败已修复，现 `.venv` 和锁定版本可用，43 项测试已在此环境运行。

## D002：时间计算与帧号约定

- 日期：2026-09-23
- 决定：内部时间使用 `fractions.Fraction`；界面帧号 1-based、内部 ordinal 0-based；时间模式采用 PTS floor，重复 PTS 选择该时刻最后一个显示顺序帧。
- 原因：避免浮点累计和 VFR 的平均帧率误映射，直接落实实施计划第 4 节。

## D003：视图坐标

- 日期：2026-09-23
- 决定：联动状态只保存归一化内容区域，标题与黑边不参与命中；每个 pane 独立计算显示变换。
- 原因：不同分辨率和宽高比下仍能查看同一内容区域，不复制屏幕像素位移。

## D004：PyAV 16.1.0 色彩转换实测

2026-10-01 更新：本条“不传 dst_colorspace”的早期选择已由 D039 的实际全范围/高位深实验替代；历史实验只覆盖未标记矩阵的 8 位人工帧，不能代表带真实色彩标记的解码帧。

- 日期：2026-09-23
- 决定：SDR YUV→RGB8 显式指定源矩阵与源 full/limited 范围；不传 `dst_colorspace`。GBR/RGB 格式直接做 RGB24 通道格式转换。
- 依据：构造 Y=16、U=V=128 灰阶，`src_color_range=JPEG` 得到 (16,16,16)，`MPEG` 得到 (0,0,0)；同时传 `dst_colorspace` 时 JPEG 也错误得到 (0,0,0)。已加固定参考断言。
- 版本：PyAV 16.1.0；wheel 内 libswscale 9.1.100。CLI FFmpeg 9.0.1，仅供素材生成与 ffprobe，不等同于 PyAV 链接版本。

## D005：M0 渲染验证范围

- 日期：2026-09-23
- 决定：主线使用单个 QOpenGLWidget 绘制整个快照，软件回退使用同一绘制函数和 QWidget。此处是 2026-09-23 M0 时的状态；2026-09-24 已实现显式 GL front/staging 纹理，见 D016。
- 依据：本机 GL context 有效，2/6 路 framebuffer 均成功抓取；对应证据在 `reports/M0_CAPABILITIES.md`。

## D006：主题设置的存储与刷新

- 日期：2026-09-24
- 决定：使用用户配置目录的 `settings.toml`，以同目录临时文件加 `os.replace` 原子保存；外观和强调色独立切换，视频 RGB 帧与视图模型不改动。
- 依据：1/3/6 路 GUI 测试覆盖三种外观、四种强调色，切换和重新实例化后分别检查帧组身份、像素内容、视图区域及配置。当前“跟随系统”只在窗口初始化或用户手动重新选择时读取系统配色，运行时系统主题变化自动刷新待实现。

## D007：文件替换语义

- 日期：2026-09-24
- 决定：先在后台探测和建立替代文件索引，成功后才在原位置更换新的 `asset_id`；失败保留原资产。删除与替换后重建运输控制器，使旧 worker/result 不能参与新帧组，并尽量以当前全局时间定位。
- 依据：GUI 测试覆盖拖入顺序、替换失败保留、同路径替换新身份、删除后的帧组一致性与第 7 路限制。

## D008：索引任务与 UI 生命周期

- 日期：2026-09-24
- 决定：单个后台 loader 顺序执行最多 6 个排队任务；ffprobe 子进程可按取消令牌终止，PyAV 索引逐帧检查取消；结果经容量 6 的队列由 Qt 主线程轮询并提交。替换结果凭任务身份核对，旧请求不能覆盖新资产；关闭时停止轮询并取消、等待工作线程。
- 依据：模拟慢探测的 GUI 测试确认 `load_files` 立即返回、Qt timer 继续运行且关闭后 worker 退出；真实 H.264/FFV1 及 6 路导入测试通过。真实长片取消延迟仍待实测。

## D009：重复素材索引复用与版本签名

- 日期：2026-09-24
- 决定：不同 `asset_id` 若媒体指纹与 schema 均相同，可在 SQLite 事务中复制完成的帧元数据；每路仍有独立身份和解码 worker。指纹纳入 PyAV 与 libavcodec 版本，版本变化会失效旧索引。
- 依据：真实 H.264 文件建立第一份索引后，第二路在禁止 `av.open` 的测试中仍成功取得相同 PTS/ordinal/end_time。

## D010：Offset/基准及前向预取

- 日期：2026-09-24
- 决定：GUI 输入有符号毫秒时间 Offset 和有符号整数帧 Offset，分别保留；基准切换减去新基准的 Offset 并以当前已提交帧组锚定。无公共范围禁用播放且清空旧画面。播放只预取下一完整事件，每路最多一个执行和一个可替换待办；预取结果入有界缓存，不进入提交屏障。
- 依据：真实两路 GUI 验证 +0.200 秒选 B 第 7 UI 帧、帧模式 +5、基准重定向、空范围恢复；真实多路播放校验所提交 PTS 为参与路事件并集的严格递增前缀。预取性能收益尚未量化。

## D011：P1 循环、截图与 Marker 的组身份

- 日期：2026-09-24
- 决定：倍速只作用于统一运输时钟；区间循环采用 `[A,B)`，边界以已经提交的组设置，循环跳转使旧在途结果失效。两种 PNG 截图和会话 Marker 均固定已经显示的完整帧组，不采用尚在解码的请求位置；PNG 默认不覆盖已有文件，Marker 退出前提醒会话性质。
- 依据：真实两路 4× 循环 100 次的帧序列、播放中/暂停时的 PNG 像素和 JSON group_id、Marker 切基准后跳回真实源帧测试通过；不同 DPI 与完整错误注入仍待验证。

## D012：文件侧栏与布局身份

- 日期：2026-09-24
- 决定：文件和 Marker 操作放入固定宽度侧栏；上移/下移仅改变稳定 asset_id 的显示顺序，双击单路最大化仅改变单画布当前显示集合，不改变运输控制器或完整帧组。视图区域按所有已导入资产保留，隐藏路线恢复后不丢失 Pan/ROI。
- 依据：两路软件 GUI 断言 transport 与 snapshot 身份不变；六路原生 GL 最大化/恢复保留完整组六帧并成功出图。时间参与开关另作同步语义实现，不混同布局隐藏。

## D013：原生像素查看与联动源

- 日期：2026-09-24
- 决定：同区域视图沿用归一化 ROI 与 SAR；原生像素模式用源存储采样尺寸、旋转后尺寸和当前 framebuffer DPR 算逻辑缩放，默认倍率 1×，忽略 SAR 并明示。裁切对齐整数源像素，目标起点对齐物理像素；倍率不小于 1 时默认最近邻。两种查看模式保留各自区域宽高，切回时沿用当前中心。视图联动重新开启时使用列表选中路作为共享源。
- 依据：模型在 DPR 1/1.5/2 下验证缩放与整数裁切；真实 H.264 帧在 DPR 1 的软件与原生 GL framebuffer 裁切后逐像素相等。实际高 DPI/跨屏动态变化仍待实机验证。

## D014：源限制提示与生命周期回归

- 日期：2026-09-24
- 决定：选中路侧栏始终显示源尺寸/编码与 RGB8 预览，色彩推定、HDR 不支持、旋转及 SAR 在有对应元信息时显式呈现；画布对高影响的色彩推定/HDR/高位深显示短提醒，长文件名自动省略但保留列表 tooltip。M7 首轮使用真实压缩素材执行 100 次替换、移除、重新导入，并检查每轮旧解码 worker 退出。
- 依据：本机六路窗口截图显示色彩推定，相关 GUI 测试通过；100 轮测试通过，耗时约 13 秒。真实长片、中断子进程和 30 分钟资源测试仍待执行。

## D015：时间参与开关与保留帧

- 日期：2026-09-24
- 决定：基准路必须参加运输组，需先切基准才可脱离；非基准路退出时固定其已显示的不可变真实帧，退出路不进入下一完整组的屏障。画布合成完整参与组与明确标为“已脱离同步”的保留帧，不用同一时间标签冒充同步。重入按当前组重新 seek，保留时间/帧 Offset；若当前请求超出新的公共区间，整组夹到最近有效边界并提示。截图 sidecar 保存每路参与状态及各路真实 PTS。移除最后参与路时自动使剩余一路重新参加，以维持有效基准。
- 依据：真实两路播放中脱离/重入、三路切基准与 Offset 的独立帧序号 30/36/33、末端重入、六路原生 GL 出图及脱离帧截图标签测试通过；长片与全部布局组合尚待验证。

## D016：单画布 OpenGL 原子纹理组

- 日期：2026-09-24
- 决定：每个参与路维持 front/staging 两个 `QOpenGLTexture` 槽；新帧只上传到非显示槽，只有完整帧组到齐才一起换 front。未变化帧复用已有纹理，缩放/平移只变换显示，不触发解码或重复上传。元数据不一致、上下文/纹理失败时通过 UI 线程切换同一语义的软件画布。
- 依据：`tools/verify_gl_canvas.py` 在真实 Windows 显示器上验证 2/6 路 framebuffer、原生像素与真实 RGB 逐像素相同；DPR 1.5/2.0 通过 `QT_SCALE_FACTOR` 模拟验证。GUI 慢路/晚到/单路解码错误测试断言不出现混时刻画面。仅有一台实际 DPR 1.0 显示器，跨屏物理切换未测。

## D017：旋转、SAR 与不可信 HDR 的显示边界

- 日期：2026-09-24
- 决定：ffprobe 的正 display rotation 以逆向 Qt 变换应用到画面和截图；同区域视图采纳 SAR，原生像素检查忽略 SAR 并显式说明。缺少 HDR 可信显示链路时，PQ/HLG/BT.2020 输入在导入时拒绝且保留已有组；10-bit SDR 只以 RGB8 预览并标注，不冒称原位深。
- 依据：F07 旋转 90/180/270 与 SAR4:3、F09 10-bit SDR/HDR 真实素材；独立 FFmpeg 自动旋转参考、原生 GL 与软件画布像素检查和 GUI HDR 拒绝测试。DPR 1/1.5/2.0 的后两者是模拟比例，不是三台显示器。

## D018：Windows 文件夹发布

- 日期：2026-09-24
- 决定：遵循计划使用 `pyside6-deploy`/Nuitka 4.1.1 文件夹式构建，随包附带 ffprobe、ffmpeg、使用说明和第三方声明；构建脚本遇到非空旧输出停止。PyAV 作为扩展模块由其导入链带入，不使用 Nuitka `--include-package=av` 强制编译源 `.py`，否则在发布包中会触发缺失 Cython 模块错误。
- 依据：本机 `dist/VideoCompare.dist/main.exe` 实际构建并在清理 PATH/PYTHONPATH、无开发环境变量的进程中启动，导入两路真实视频、定位第 2 UI 帧、导出 PNG/JSON、退出码 0。干净独立 Windows 机器尚未具备，A22 仍为部分验证。

## D019：长片索引开放时机

- 日期：2026-09-24
- 决定：当前后台 loader 完成整段帧索引后才将资产交给运输控制器；期间窗口可交互、任务可取消，SQLite 分块写入并标记 `partial`，但不能把部分索引误报为完整或允许越界帧号。此决定是当前实现边界，不等同于计划要求的“首帧后可播放已覆盖区域”，因此保持为未完成项。
- 依据：5 分钟/9000 帧真实 H.264 索引扫描在 256 帧后取消，loader 退出、数据库为 `partial`、输入文件 SHA-256 不变；完整测试步骤在 `tools/verify_long_cancel.py`。后续需设计增量 timeline/运输控制器更新与待索引目标排队，不能用平均 FPS 伪造帧身份。

## D020：拖拽平移方向（垂直方向按用户要求反转）

- 日期：2026-09-25
- 决定：水平方向保持实施计划 7.2 的“画面跟随指针”（`center_u -= Δx/(s*Dw)`）；垂直方向改为“拖动视图”语义（`center_v += Δy/(s*Dh)`），即向下拖动时视图下移、画面向上移动。
- 原因：用户 2026-09-25 明确反馈“上下平移的逻辑反了”。复核显示原实现与计划公式一致，且原生 GL 与软件画布在缩放子区域上逐像素一致（本次再次用同一区域对比确认差值 0.000），因此这不是渲染错误，而是用户要求的行为变更；按用户最新指令覆盖计划默认值。
- 影响：两个轴的方向语义不再相同。若希望恢复“画面跟随指针”，把 `domain/viewport.py` 中 `pan()` 的第二行改回 `-=` 即可；`tests/unit/test_viewport.py::test_pan_direction_per_axis_is_explicit` 固定了当前约定，`tools/verify_ui_and_export.py` 在真实视频上打印两个方向。

## D021：排列随导入视频自适应

- 日期：2026-09-25
- 决定：单画布按参与视频“显示后的宽高比”（含旋转与 SAR；原生像素模式忽略 SAR）分行。在全部连续行划分中取“同一缩放尺度下画面最大”的方案，并且多一行必须至少带来 15% 放大（`AUTO_ROW_GAIN = 1.15`）才采用，避免无谓重排。行内画面按各自比例紧密排列，只保留 8 逻辑像素间距，剩余空间留在外侧；同一排列内所有画面共用一个缩放尺度，使“同区域”比较更公平。
- 原因：用户导入两路竖屏视频时，中间出现大片空隙——旧实现把每路固定在等分格子里再各自 Fit。
- 依据：`ui/layout.py`、`tests/unit/test_layout.py`、`tests/gui/test_export_and_layout.py`；真实 1080×1920（rotation 元数据）双路原生 GL 验证中间空隙 8.0px、外侧留白 145.3px，见 `reports/artifacts/ui/`。
- 补充：排列只由视频本身比例决定，不随缩放或 ROI 变化。开发中曾按“当前可见区域比例”排列，结果缩放后窗格会跳到另一行（现有 GUI 用例捕获），因此明确固定在视频比例上。阈值定在 15% 是因为画面标题条移入画面内部后（D023），两路同比例视频在常规窗口比例下若用 10% 会把并排改成上下两行，实测渲染与旧用例都会变化；15% 保持“两路并排、三路 2+1、六路 3+3”的直观结果。另有“网格/横排/竖排”手动模式，选择写入 `settings.toml`。

## D022：对比图导出（不含界面）

- 日期：2026-09-25
- 决定：新增“导出对比图…”，可选排列（与窗口一致/横排/竖排/网格）与格式（PNG/JPEG，JPEG 质量可调）。导出内容为“当前窗口每一路实际显示的区域”，按设备像素等比合成；按用户 2026-09-25 的要求，**导出图包含画面左上角的文件名与右下角的帧号/PTS/提醒文字（含标注图形）**，但不包含按钮、工具栏、侧栏等界面元素；**不再生成 JSON 文件**。用户选择的路径允许覆盖（先写临时文件再原子替换）。成功与失败都用弹窗显示结果与路径（成功提示里带组 ID，便于追溯帧身份）。
- 依据：`services/comparison_export.py`、`tests/unit/test_comparison_export.py`（角落文字与标注像素）、`tests/gui/test_export_and_layout.py`（原生像素 100% 下中部区域与源帧裁切逐像素一致、导出不写 JSON）；真实双路证据 `reports/artifacts/ui/对比图_与窗口一致.png`、`对比图_竖向排列.jpg`、`对比图_带标注.png`。
- 边界：HDR/BT.2020 路没有可信 RGB8 画面，导出时自动跳过并在弹窗与状态栏说明；“保存对比视图”与“保存原帧”仍各写 PNG + 帧身份 JSON（只有对比图导出取消了 JSON）。

## D028a：导出前编辑标注（多窗口同步）

- 日期：2026-09-25
- 决定：导出对话框提供“导出前先编辑标注”；在任意画面上拖拽绘制矩形、圆形/椭圆、箭头、直线或自由画笔，线条颜色从 9 色中选择。标注按归一化**源画面**坐标保存，缩放、平移后仍锚定源内容，并同步显示在所有画面上。工具栏提供撤销、删除选中、删除全部、取消与“完成并导出”；成功保存或取消后清除，写入失败时保留以便重试。
- 依据：`ui/annotations.py`（形状与绘制）、`ui/annotation_bar.py`（工具条）、`ui/canvas_interaction.py`（拖拽生成/预览）、`services/comparison_export.py`（导出时按同一归一化坐标绘制）；`tests/unit/test_comparison_export.py` 断言导出图含角落文字与红色标注像素；`tests/gui/test_export_and_layout.py::test_annotated_export_syncs_shapes_and_colours` 走完整流程（进入标注模式 → 拖拽生成 1 个标注 → 完成导出 → 导出图命中蓝色标注像素且无 JSON）。真实窗口证据 `reports/artifacts/ui/canvas_annotated.png`、`对比图_带标注.png`（蓝色矩形像素 4860）。
- 边界：标注只在本次编辑期间存在，不写入源视频；导出图不含标注工具条本身。各路使用相同归一化源坐标，屏幕投影随各路当前视图与比例变化。

## D023：现代简约外观

- 日期：2026-09-25
- 决定：用扁平卡片式 QSS 重做外壳（卡片、圆角、轻边框、强调色、下拉箭头、细滑块与滚动条），侧栏与工具条分组。画面信息按用户 2026-09-25 要求直接叠在画面上：**文件名在画面左上角，帧号/PTS/提醒在右下角**；文字用半透明深色底衬保证在任意画面上可读，文字颜色取“视频信息”颜色（默认绿色 `#00b050`，可在设置里改）。原先每行上方的 22px 标题条因此取消，视频可用面积增大。
- 依据：真实窗口截图 `reports/artifacts/ui/canvas_light.png`、`window_light.png`、`window_dark.png`；`tests/gui/test_shell_layout.py::test_overlay_labels_sit_in_the_picture_corners` 用像素计数验证“左上角与右下角有该颜色的文字像素、另外两个角没有”，并验证改色后立即生效；`tools/verify_ui_and_export.py` 在真实 GL 窗口打印两角像素数（默认绿色 #00b050：左上 219、右下 124）。
- 边界：叠加文字会覆盖画面角落像素（这是用户要求的位置）。因此原生像素 1:1 与旋转/SAR 的**逐像素**验证在比对前调用 `canvas.set_overlay_visible(False)` 隐藏叠加层（`tests/gui/test_m0_canvas.py`、`tools/verify_gl_canvas.py`、`tools/verify_display_metadata.py`）；按用户后续要求，对比图导出保留这些文字。

## D024：图标与桌面快捷方式

- 日期：2026-09-25
- 决定：用 `tools/prepare_logo.py` 从 `logo/` 图片生成透明背景的 `src/video_compare/assets/app.png` 与多尺寸 `app.ico`。工具按输入自动选路径：已带透明通道的图（当前使用的 `logo/logo2.png`，透明像素 63.9%）原样保留 alpha，只做裁剪与缩放；白底不透明的图只移除与图像边缘连通的白色（画面内部白色细节保留），边缘像素按“反预乘 a=255-min(r,g,b)”去掉白边。窗口与应用图标取自该 `app.ico`；`pysidedeploy.spec` 与 `scripts/build_windows.ps1` 使用同一文件，构建前重新生成。`scripts/create_desktop_shortcut.ps1` 在桌面创建 `Video Viewer` 快捷方式，`scripts/run_video_compare.cmd` 用项目虚拟环境运行当前源码；PowerShell 脚本保存为 UTF-8 with BOM，避免 Windows PowerShell 5.1 按 ANSI 读取中文名。
- 依据：`reports/artifacts/logo/logo_preview.png`（棋盘/白/深色三种背景）、`reports/artifacts/logo/logo_transparent.png`；快捷方式已创建并实际启动（进程命令行确认使用项目 venv 与随包 ffprobe）。

## D025：顶部单行工具栏、底部播放条与右侧可调信息栏

- 日期：2026-09-25（用户第二轮界面要求）
- 决定：窗口改为「顶部单行工具栏 + 中间工作区 + 画面下方播放条」结构：顶部一行放置应用名 `Video Viewer`、添加视频、同步方式、基准、查看模式、排列、适应、框选 ROI、视图联动、保存视图、保存原帧、导出对比图、设置与侧栏开关；播放/暂停、前后步进、步进量、速度、循环边界与区间循环、进度条、时间与帧号定位、状态文字统一放在视频窗口下方的播放条；文件列表、Offset 与 Marker 移到右侧信息栏。
- 依据：用户 2026-09-25 截图要求「红框内容放到顶部且只有一行并包含设置」「播放相关内容放到视频窗口底部」「蓝框部分放到右侧」。测试 `tests/gui/test_shell_layout.py` 断言顶部控件中心同一行、播放控件位于画布下方、侧栏位于 `QSplitter` 右侧且宽度可拖拽、隐藏与恢复按钮有效；真实窗口截图见 `reports/artifacts/ui/window_light.png`、`window_sidebar_hidden.png`、`settings_dialog.png`。
- 补充：侧栏宽度由 `QSplitter` 控制（220–620 逻辑像素），`»` 小按钮隐藏，顶栏「侧栏」按钮可恢复；排列方式仍按 D021 自适应视频比例，时间/帧号输入移到播放条后仍按回车定位，`Ctrl+O`、方向键、空格、`F`、`I/O`、`M`、`Esc` 快捷键不变。

## D026：色系、工作区与功能区分离的颜色设置

- 日期：2026-09-25（用户第二轮与后续补充要求）
- 决定：外观模型为「整体色彩 = 色系风格」+「四个颜色角色各自选色」+「明暗模式」。整体色彩只选择色系风格（`清爽极简`、`莫兰迪`、`奶油风`、`复古`、`赛博朋克`、`马卡龙`），它决定色板中的主题颜色；**工作区、功能区、强调色、视频信息**四种颜色彼此独立，每个角色都可取“跟随色系”或任意具体颜色。为兼容已有设置，`清爽极简` 的内部键仍为 `codex`，界面不显示该键。
- 颜色选择器做成 PPT/Visio 填充色样式：主题色行（该色系 8 个颜色）+ **5 档深浅**（0.8、0.6、0.4 变浅，0.25、0.5 变深，`SHADE_STEPS`），下方另有一行 15 个标准色（黑白灰与红橙黄绿青蓝紫）。对话框把四个角色做成按钮组，右侧色板始终作用于当前角色，并显示该角色当前颜色与十六进制值。设置写入 `settings.toml` 的 `workspace_color`/`function_color`/`accent`/`overlay_color`（`follow` 或 `#rrggbb`）。
- 依据：`tests/gui/test_shell_layout.py` 断言 5 套指定色系存在、不同色系配色互不相同、功能区选色决定界面底色、四个角色可分别设置并持久化、颜色网格色块数量 = 色系颜色数×6 + 15、点选与“跟随色系”都即时生效；`tests/unit/test_settings.py` 覆盖四个颜色字段的读写、默认“视频信息”为绿色 `#00b050`、非法值逐项回退；`tests/gui/test_m0_canvas.py` 覆盖 3 种明暗模式 × 5 个强调色（含 `follow`）下真实帧组与视图区域不变。截图证据 `reports/artifacts/ui/settings_dialog.png`、`scheme_*.png`。
- 边界：这些颜色只影响界面与画布装饰色（含画面叠加文字颜色），不改变视频像素、色彩转换策略、截图/导出内容与帧身份；组合很多，未逐一人工审美检查。

## D027：测试隔离用户设置文件

- 日期：2026-09-25
- 决定：`tests/conftest.py` 用 autouse fixture 把 `user_config_path` 指到测试临时目录，测试不再读写开发者真实 `settings.toml`；需要持久化的用例显式传入 `settings_path`。GUI 用例在计算 `pane_transform` 时显式传入 `canvas.layout_mode`，避免依赖默认排列。
- 原因：一次全量测试失败暴露出用例通过 `MainWindow` 默认路径读到了本机真实配置（其中含 `layout = "horizontal"`），导致测试计算出的画面框与画布实际布局不一致；这既是测试脆弱性，也会污染真实配置。
- 依据：修复前 `test_real_480p_1080p_4k_grid_shares_normalized_roi` 失败、修复后全量 103 项通过；本机配置文件已恢复默认值（`theme=system/accent=blue/layout=auto/scheme=codex/follow/follow`）。

## D028b：PowerShell 中文乱码的永久修复（统一 UTF-8 输出）

- 日期：2026-09-25
- 现象：在 PowerShell 里运行本项目脚本时中文变乱码。证据：`reports/_build_2026-09-25c.log` 中记成了 `source logo\ChatGPT Image 2026��9��24�� 22_53_41.png`。
- 根因：中文版 Windows 控制台默认代码页是 936(GBK)，Python 输出到管道/重定向时按 GBK 编码（`sys.stdout.encoding=gbk`），而 PowerShell 7（以及已设成 UTF-8 的控制台）按 UTF-8 解码，两侧编码不一致。同一命令对照实测：不设 `PYTHONIOENCODING` 时输出 `���Ĳ��� ��9��24��`，设为 `utf-8` 后输出 `中文测试 年9月24日`（`python stdout encoding=utf-8`）。
- 决定：新增可重复执行的 `scripts/setup_powershell_utf8.ps1`，把当前用户环境统一为 UTF-8 输出：
  1. 写入 `%USERPROFILE%\Documents\WindowsPowerShell\profile.ps1` 与 `Documents\PowerShell\profile.ps1`（UTF-8 with BOM）：控制台输出代码页 65001、`$OutputEncoding` 为 UTF-8、`PYTHONIOENCODING=utf-8`；5.1 下再把 `Out-File`/`Tee-Object` 的默认编码从 UTF-16 改为 UTF-8。
  2. 用户环境变量 `PYTHONIOENCODING=utf-8`，使 `-NoProfile` 或非 PowerShell 宿主启动的 Python 也按 UTF-8 输出。
  3. 执行策略 `CurrentUser=RemoteSigned`：本机原为 `Restricted`，profile 与仓库内 .ps1 都无法加载/运行（首次执行本脚本需 `-ExecutionPolicy Bypass`，脚本自己会修好这一点）。
- 有意不改：控制台**输入**代码页保持系统默认（5.1 自带 PSReadLine 2.0 在 65001 输入代码页下有已知中文/韩文输入缺陷，见 PowerShell/PSReadLine#1326）；系统 ANSI 代码页保持 936；`cmd.exe` 与批处理保持 GBK；不启用“Beta: UTF-8 全球语言支持”。
- 验证（2026-09-25，Windows 11 26200，zh-CN）：从 936 控制台新开的 5.1 与 PowerShell 7 读回 `InputCP=936 / OutputCP=65001 / $OutputEncoding=utf-8 / PYTHONIOENCODING=utf-8 / ExecutionPolicy=RemoteSigned`；5.1 会话内运行项目 venv Python 打印 `中文测试 年9月24日`；模拟构建日志路径（`Python | Tee-Object 日志`）得到 `source logo 2026年9月24日 22_53_41.png`，日志字节头由旧的 `FF-FE`(UTF-16) 变为 `EF-BB-BF`(UTF-8 BOM)，`rg "年9月24日"` 可直接命中；把策略临时改回 Restricted 并放入自定义 profile 后重跑，脚本正确恢复 RemoteSigned 并先备份自定义 profile 为 `.bak-<时间戳>`。
- 回退方式：删除两个 `profile.ps1`、删除用户环境变量 `PYTHONIOENCODING`、执行 `Set-ExecutionPolicy -Scope CurrentUser Undefined`。
- 边界：直接输出 GBK 字节的旧程序在 UTF-8 控制台下仍可能乱码，可在该会话临时 `chcp 936`；`reports/_build_2026-09-25c.log` 等修复前的历史日志保持原样，不追改。

## D029：长片首帧预览与增量索引

- 日期：2026-09-25
- 决定：导入使用一个快速探测线程顺序取得各路真实首帧，另由一个后台索引线程顺序建立各路完整 PTS/显示顺序索引。首帧可先显示；每 256 帧提交一批 SQLite 索引，并向 UI 发送只覆盖已确定时间边界的不可变时间轴。多路完整帧组仍由同一运输控制器与屏障提交。播放到临时索引前沿进入等待状态，索引增长后继续；尚未覆盖的时间/帧定位保留精确目标，不用平均 FPS 估算。设置 Offset 导致临时公共区间为空时等待覆盖增加，不把临时前沿误报为文件结束。
- 正确性边界：每批对比新旧索引前缀，解码 worker 仅在自身线程切换索引及容器；首帧预览与后续完整索引的帧身份必须相同，否则显式报错。移除正在索引的路会取消对应任务，过期结果由任务身份隔离。先显示的首帧时间预览仅开放一个原始 time-base tick；后续帧须待下一个不同 PTS 界定时间区间。重复 PTS 的最终时间选帧在更多索引到来后可能更新，因此帧号与实际 PTS 始终显示真实值。
- 依据：`tests/gui/test_m0_canvas.py` 的首帧三次累计步进、两路首帧并行、256 帧前沿等待/恢复、索引中移除和 Offset 自动恢复；`tests/integration/test_precise_decode.py` 的真实 H.264 索引前缀/帧 ID；`tools/verify_long_cancel.py` 在 9000 帧长片的取消与原件哈希；真实 Windows 原生 GL 2/6 路验证。多路长片性能与新版 30 分钟资源测试仍待执行。

## D030：提交下一帧组前释放旧组的缓存 pin

- 日期：2026-09-25
- 决定：运输控制器发起新完整帧组请求时，释放上一已显示组在 LRU 缓存上的 pin；画布和不可变已显示快照继续持有真实 RGB buffer，因此旧画面仍可显示和截图。待提交组的缓存 pin 保留到原子提交或取消。缓存预算始终由 FrameCache 执行，预算不足以装下一组时明确报错。
- 原因：64 MiB 缓存下六路 1080p 的旧组和新组各约 36 MiB，同时 pin 会使第二组无法插入，即使旧组仍由已显示快照安全持有。修复后同条件的真实两组定位和旧快照像素不变测试通过；短测从“0 组、缓存错误”变为 8 秒 55 组。512 MiB 下六路 1080p 的 8 秒短测为 160 组，六路 4K 的 8 秒短测为 163 组；均为无 GUI 渲染的短循环，不宣称实时播放或持续稳定。
- 依据：`tests/integration/test_transport.py::test_six_1080p_routes_fit_small_cache_without_overwriting_display`、`reports/benchmark_progressive_*.json`。完整 30 分钟 GUI/随机 seek、GPU 内存和更长真实素材仍待测。

## D031：变速播放使用累计单调时钟截止时间

- 日期：2026-09-25
- 决定：播放定时器使用 `time.monotonic_ns()` 锚点累计下一帧组的截止时间，`QTimer` 只负责唤醒。每组真实 PTS 间隔按当前倍率换算；解码晚到时缩短下一次等待，但不跳过帧或提交不完整帧组。暂停、主动 seek、切换倍率及索引前沿缓冲恢复时重新锚定。
- 原因：原实现总是在完整组解码提交之后才开始计下一段 PTS 间隔，解码耗时逐组累加，真实两路 2× 测试出现快放明显偏慢。累计截止时间使可恢复的延迟在后续组内补回；持续解码瓶颈仍可能达不到设定倍率，不能伪称实时。
- 依据：`tests/integration/test_transport.py::test_real_two_route_playback_rates_follow_pts_intervals` 在真实双路 H.264 的时间/帧同步模式实测 0.25×、2× 提交节奏；既有 4× 两路 100 次循环与索引前沿等待/恢复回归通过。

## D032：系统外观变化时刷新“跟随系统”配色

- 日期：2026-09-25
- 决定：主窗口订阅 Qt `QStyleHints.colorSchemeChanged`；仅当前明暗模式为“跟随系统”时重新应用界面与画布装饰色，关闭窗口时断开连接。手动指定浅色/深色不受系统主题切换影响。
- 依据：离屏 GUI 测试注入该 Qt 信号并模拟颜色方案变化，样式更新且当前真实帧组对象、RGB 与 ROI 保持不变；真实操作系统运行中主题切换仍需独立验证。

## D033：标注编辑生命周期、视图定位与界面过渡

- 日期：2026-09-25；响应用户对标注残留、缩放错位、侧栏突变和画布直角的反馈。
- 决定：标注点记录归一化源坐标，渲染及导出时按每路当前 `ViewRegion` 映射；导出裁切使用实际取整后的源区域。自由画笔收集同一画面拖拽轨迹。编辑开始清除前次标注；取消立即清除；异步写入成功后才清除，失败时保留可重试。工具条列出每个标注并可删除选中项。侧栏使用 220ms OutCubic 的 `QSplitter` 宽度动画，画布外轮廓用 12px 圆角蒙版；更改尺寸时重算蒙版。
- 依据：`tests/gui/test_export_and_layout.py` 覆盖自由画笔、单项删除、取消/成功/失败、缩放后 GUI 与导出定位；`tests/gui/test_shell_layout.py` 覆盖动画中间宽度、快速反向操作和圆角蒙版；原生 OpenGL 的 `tools/verify_annotation_gl.py` 在真实压缩视频上生成 `reports/artifacts/annotation-gl-20260925/`，验证画面及导出中的自由画笔像素与角落裁切。

## D034：独立 Windows 包的一键自检

- 日期：2026-09-25。
- 决定：发布文件夹附带 `verify_clean_windows.cmd/.ps1`。脚本只调用包内 FFmpeg，在唯一系统临时目录生成两段 320×180 H.264 测试视频，再调用包内程序的 `--self-test-output`，检查真实两路导入、定位和 PNG/JSON 产物；结束后保留结果目录便于诊断。它不需要 Python，不读取用户视频，也不覆盖已有文件。
- 依据：同一 Windows 主机上从发布文件夹运行 PowerShell 脚本，退出码 0，输出 `CLEAN_WINDOWS_SELF_TEST_OK`，日志 `reports/clean_windows_selftest_local_20260925.log`。另一台干净 Windows 机器尚未执行，A22 保持进行中。

## D035：视频与静态图像共用对比画布

- 日期：2026-09-27；用户新增“视频对比 / 图像对比”两种模式，尽可能广泛支持图像格式。
- 决定：保留视频的真实 PTS 时间轴和解码链；图像独立为静态资产组，通过同一个画布、视图坐标、标注和导出链显示。切到图像时暂停视频播放并隔离晚到视频组，切回时恢复原视频位置。图像无时间轴，隐藏播放、步进、Offset 和 Marker；两种模式分别保留已导入文件。
- 图像读取用 Pillow 12.3.0 处理常见栅格、EXIF 与 ICC，pillow-heif 1.8.0 补充 HEIC/HEIF，Qt 6.11.2 图像插件补充 SVG 等，rawpy 0.27.1 尝试相机 RAW；不按后缀限制最终识别。单个读取 worker、有界队列、每路 RGB 缓冲 512 MiB 和整组 1 GiB 上限；替换成功才更换旧图，重复文件有独立资产 ID。RGB8 显示对透明区域使用白底，缺少 ICC 时按 sRGB 推定并标记；多页/动画取首页，RAW 经显影。源文件只读。
- 依据：`tests/gui/test_image_mode.py` 使用真实 PNG/JPEG/TIFF/WebP/AVIF/HEIC/BMP/GIF/SVG、EXIF 方向及透明图；同一测试检查模式切换、替换、截图、导出和原件哈希。真实 Windows OpenGL 源码/独立包自检见 `reports/artifacts/image-mode-20260927/`。RAW 的实际相机文件未得到验证，不能将库的格式覆盖范围等同于本机验收。

## D036：标注范围按笔保存

- 日期：2026-09-27；用户要求框选和自由绘画可选择仅在单独图像或视频区域操作。
- 决定：编辑工具条新增“标注联动到全部画面”，默认开启，保留原有同步标注行为。关闭后，每笔标注记录鼠标按下时的 `asset_id`；同一笔的预览、完成后的画布绘制和对比图导出均按此 ID 过滤。切换开关只影响新笔画，避免已画内容突然变更。顶部“视图联动”继续独立控制视图区域。
- 依据：`tests/gui/test_annotation_scope.py` 在真实压缩视频与本地图像中分别模拟矩形、自由画笔操作，比较两路画布和导出图像的像素；`tests/unit/test_comparison_export.py` 验证混合联动与单路笔画；真实 Windows OpenGL 视频画布验证见 `reports/artifacts/annotation-scope-gl-20260927-final/result.json`。

## D037：语言选项使用各自语言的名称

- 日期：2026-09-27；用户要求统一语言选项显示逻辑，并增加繁体中文和常用语言。
- 决定：设置窗口分“主题”和“语言”两页；主题保留原外观控件。语言列表固定显示 `简体中文 / 繁體中文 / English / 日本語 / 한국어 / Français / Deutsch / Español`，不会因当前界面语言重新翻译这些名称。选择后立即更新当前窗口、设置和导出界面的主要文案，并写入本地设置；语言目录随程序离线打包。默认仍为简体中文。
- 依据：`tests/gui/test_language_settings.py` 遍历八种语言并检查自称、切换和重启持久化；原生 Windows 窗口截图及结果见 `reports/artifacts/languages-gl-20260927-final/`。


## D038：扩展图像解码与真实格式矩阵

- 日期：2026-10-01；用户要求尽可能兼容视频和图像格式。
- 决定：新增 imagecodecs 2026.3.6、tifffile 2025.5.10，仅安装项目环境并锁定依赖。JPEG XL/XR/LS 与 16 位 PNG/TIFF 采用真实整数解码；保留 EXIF/ICC、方向、Alpha 和明确的 RGB8 转换提醒。RAW/DNG 按内容转入 LibRaw，不把嵌入缩略图当作传感器显影；RAW 关闭自动提亮。不同格式共用已有静态资产/画布链，不增加平行应用。
- 边界：JXL/XR/LS 的全部 ICC/HDR 配置未验证，显示未校色提醒；浮点/HDR 静态图像失败可见。PSD 首次打开已位于合成图，移除不必要的 seek(0)，避免 Pillow 对无图层合成图返回 EOFError。
- 验证：30 组真实视频通过嵌入源帧 ID、独立 ffprobe PTS、107 个定位目标和源文件哈希检查；29 个图像样本通过固定色块、源位深/方向/透明与只读检查。JPEG-LS 锁定版本的 check() 返回 None，改读有界 JPEG 标记头并跳过 APP 内容；AVI 最后缺失 PTS 的独立 CLI 对照显式启用 genpts，不改时间容差。

## D039：用户明确授权 HDR 与 BT.2020 的 SDR 预览

- 日期：2026-10-01；用户明确新增“HDR、BT.2020 等”兼容，更新实施计划 7.6 的早期拒绝策略；音频、转码、视频输出与 M9/P2 范围不变。
- 决定：PyAV 真实源帧转 RGB16，按 PQ ST 2084 或 HLG 1000 nit/gamma 1.2 的逐通道显示模型解线性，D65 原色转换至 BT.709，固定 Hable 曲线按 MaxCLL/mastering display 或明确推定的 1000 nit 归一。有效源峰值（含低于 100 nit 的值）原样保留，无效/非有限/超出 PQ 范围的峰值明确改用推定值。BT.1886 gamma 2.4 编码输出 RGB8；BT.2020/P3 SDR 只转色域。工作浮点缓冲以 64 行分块，LUT 有界；不使用每帧自动曝光。窗口、原帧截图及合成导出用同一不可变像素，提醒明确显示 SDR 色调映射。
- 边界：不实现 HDR 显示器输出；不应用 Dolby Vision/HDR10+ 动态元数据。兼容基础层可预览，非兼容 Dolby Vision、BT.2020 CL 明确拒绝。HLG 为逐通道近似显示模型，不承诺校准参考监视器精度。
- 实际 API 修复：PyAV 16.1.0 仅在 src/dst 矩阵或范围不同才配置 swscale；源真实标记等于请求值且 full->full 时会跳过设置并错误使用默认 limited/601。RGB 目标的 YUV 矩阵无意义，显式传 dst_colorspace=0 触发正确源设置。该 wheel 的 bilinear YUV420p10->RGB48 色度路径在彩色块上明显损坏，改用 bicubic 色度重建路径；与独立 FFmpeg 9 CLI/zimg/Hable 输出按整帧比较，最终 9 组样本最大误差 <=1/255，无扩大容差。BT.1886 输出采用显示 EOTF，与 zimg 的 display-referred 行为一致。
- 资料：[PyAV 16.1.0 reformatter 源码](https://github.com/PyAV-Org/PyAV/blob/v16.1.0/av/video/reformatter.pyx)、[FFmpeg Hable 实现](https://ffmpeg.org/doxygen/8.0/vf__tonemap_8c_source.html)、[zimg gamma](https://github.com/sekrit-twc/zimg/blob/master/src/zimg/colorspace/gamma.cpp)。公式独立实现，未复用被测函数生成预期。

## D040：进度式索引与标注尺寸回归

- 日期：2026-10-01。
- 决定：标注选择框固定最小内容长度，避免第一笔增加长名称后窗口强制扩宽；保持画布和导出像素验证标准。真实窗口 100 次替换/删除/重载测试等待完整索引完成后再断言 pending_add=0；两个完整预览帧出现不等于后台索引完成，此行为与原有进度式索引规格一致。保留每轮旧 worker 已退出及帧组资产一致的断言，不放宽时间、身份或资源上限。异步导出结果的长路径提示采用单行状态栏与完整 tooltip，避免换行在标注手势中改变画布高度。发布自检按真实 PTS 区间计算各路目标，修正 MKV 33ms 与 TS 1/30s 混合时间轴时误要求各路相同 ordinal 的旧假设。
