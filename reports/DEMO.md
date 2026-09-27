# 演示记录

日期：2026-09-24 至 2026-09-25；Windows 11 x64。本页是已经实际执行的本机操作/自动 GUI 复现记录。旧条目使用 `tools/generate_fixtures.py` 生成素材；新增标注条目还以本机用户竖屏素材只读验证，素材本身不进入报告或发布包。代码版本与复跑命令见 `reports/ACCEPTANCE.md`。

| 场景 | 实际输入与操作 | 可核对的实际结果 |
|---|---|---|
| 两路与六路 | F05 H.264、FFV1 两路导入；相同素材再加到六路；运行 `tools/verify_gl_canvas.py` | 单个原生 QOpenGLWidget 的 2/6 路完整帧组、实际 framebuffer 分别留在 `reports/artifacts/m0_gl_two.png`、`m0_gl_six.png`，命令退出 0。真实六路同 PTS 独立 decoder 播放时逐组 frame ordinal 相同，暂停后不再提交；测试在 `tests/integration/test_transport.py`。 |
| 拖动与步进 | 两路导入，GUI 连续 100 次确定随机滑杆请求并最终到第 72 UI 帧；连续右键 10 次，再做 1 秒步进 | 最终帧 ID 71（内部从 0 起），晚到旧请求不能覆盖；右键到内部 ordinal 10，1 秒从首帧到 ordinal 30。`tests/gui/test_m0_canvas.py` 通过。 |
| ROI 与不同分辨率 | 真实 F06 480p/1080p/4K 带相同归一化网格和红色中央区的压缩视频导入；在 480p 格框选 ROI | 三路视图 `ViewRegion` 完全相等，源红区落在对应归一化位置；`tests/gui/test_m0_canvas.py` 通过。该测试使用 Qt 离屏软件画布，不代表 4K 实时播放性能。 |
| 原生像素与方向 | F05/F07 真实帧在本机原生 GL、软件画布及模拟 1.5/2.0 DPR 下查看；F07 旋转 90/180/270°、SAR4:3 | DPR1 的原生像素 framebuffer 裁切逐像素匹配源 RGB；旋转方向与 FFmpeg 自动旋转一致。图片在 `reports/artifacts/m5_gl_pixel_100.png`、`f07_gl_*.png`、`dpr150`、`dpr200`。实际跨屏未验。 |
| 截图与异常 | 运行中的两路保存对比视图与各路原帧 PNG/JSON；另模拟已有文件占用输出路径 | 导出组 ID、真实 PTS/帧号和像素一致；失败时状态提示“截图失败”，已有文件和已显示组不变。产物示例 `reports/artifacts/selftest-package/compare_20260924_231601_f000002_1a630b0ffac2_view.png/.json`。 |
| 发布包 | `dist/VideoCompare.dist/main.exe` 从无 Python/ffprobe PATH 的本机进程启动，导入两路、seek UI 第 2 帧并截图 | 进程退出 0，以上 PNG/JSON 存在且记录两路源 PTS。未在独立干净 Windows 机器验证。 |
| 标注编辑与缩放（2026-09-25） | 两路真实压缩视频在原生 OpenGL 画布上进入导出前编辑，缩放后用自由画笔画线，保存 PNG；另以用户竖屏视频验证侧栏隐藏/呼出与设置界面 | `reports/artifacts/annotation-gl-20260925/result.json` 记录画布源定位和导出紫色画笔像素、圆角蒙版；`reports/artifacts/ui-annotation-20260925/` 保存侧栏动画验证、显示“清爽极简”的设置截图和标注导出 PNG。成功导出后画布标注清除，测试进程均退出 0。 |
