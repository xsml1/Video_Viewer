# 格式与色彩支持

更新时间：2026-10-01。文件按实际内容识别，后缀用于选择窗口的提示；同一种后缀可能包含不同编码。下表列出本机真实素材验证范围，不等于任意文件或所有编码变体保证可用。

## 视频

| 编码 | 已验证容器或变体 |
|---|---|
| H.264/AVC | MP4、MOV、MKV、TS、M2TS、FLV，含 B 帧 |
| H.265/HEVC | MP4、MOV、MKV，8/10 位 SDR；10 位 PQ/HLG、有限/全范围 |
| VP8 / VP9 | WebM；VP9 另含 MKV、10 位 HLG |
| AV1 | MP4、MKV；MKV 另含 10 位 PQ |
| MPEG-4 Part 2 / MPEG-2 | AVI、MP4 / MPEG-PS、TS，含 B 帧 |
| Motion JPEG / WMV2 | AVI、MOV / WMV |
| ProRes / DNxHR | 10 位 MOV / MOV、MXF |
| FFV1 / HuffYUV / QTRLE / Theora | MKV、AVI / AVI / MOV / OGV；FFV1 另含 12 位 PQ、10/12 位 BT.2020 SDR、P3 |

30 组普通视频加 9 组 HDR/广色域视频均以嵌入的源帧编号验证随机定位、前后跳转、首末帧与真实 PTS。原有 VFR、24/60fps、旋转及 SAR 验证继续保留。

### HDR 与广色域预览

- PQ/ST 2084、HLG/ARIB STD-B67 会先按源矩阵及范围转换为 RGB16，再在浮点线性光中转换原色、执行固定 Hable 色调映射，输出 BT.709/BT.1886 的 RGB8 SDR 预览。
- 峰值优先采用首帧 MaxCLL，再采用 mastering display 最大亮度；缺失时推定为 1000 nit，并在画面和信息栏明确显示。HLG 按 1000 nit 显示器、系统 gamma 1.2 的逐通道 OOTF 预览。不会按每帧亮度自动改变曝光。
- BT.2020 非恒定亮度（NCL）SDR 与 Display P3 转为 BT.709；超出目标色域的值裁切。不额外锐化、不用低分辨率代理、不修改输入文件。
- 帧截图保存实际已显示的 SDR 像素；JSON 保留源原色、传递函数、矩阵、范围、位深、峰值及推定状态、显示策略。对比图保留色调映射提醒。
- 当前窗口和截图均是 SDR，不能用于评价原生 HDR 屏幕的绝对亮度。Dolby Vision 仅允许兼容 HDR10/SDR/HLG 的基础层，不应用其动态元数据；非兼容基础层及 BT.2020 恒定亮度（CL）明确拒绝。HDR10+ 的动态元数据未应用，使用固定静态曲线。未验证的广色域原色或传递函数会显示失败原因。

## 图像

| 类别 | 已验证样本 |
|---|---|
| 常见格式 | PNG、JPEG、BMP、GIF、WebP、AVIF、HEIC、TIFF |
| 扩展格式 | JPEG XL/JXL、JPEG XR/JXR、JPEG-LS/JLS、JPEG 2000/JP2/J2K、QOI |
| 其他图像 | TGA、PCX、PPM、DDS、SGI、ICO、ICNS、PSD 合成图、SVG、SVGZ |
| 高位深 | 16 位 RGB PNG；16 位 RGB TIFF 未压缩、Deflate、LZW、Zstd；16 位 Alpha PNG、TIFF 方向/平面布局与多页 |

共 29 个格式样本，加方向、Alpha、损坏输入、大小限制等专门用例。16 位整数图像明确按高 8 位预览，不保证原始高位深比较。透明区域按白底合成，动画/多页只显示首页。有效 ICC 尝试转至 sRGB；未嵌入或无效 ICC 明确标为推定。JPEG XL/XR/LS 当前没有校验全部色彩配置，按解码数值预览并显示提醒。

RAW 通过 LibRaw 读取并按相机白平衡显影，关闭自动提亮；不能把相机原始传感器采样当作显示 RGB。合成 Bayer DNG 用于验证真实 LibRaw 链路；不同厂商/机型 RAW、分层 PSD、PDF、浮点/HDR 静态图像和超大图像不属于已验证范围。图像解码失败会保留原画面并提示原因。

## 使用与诊断

直接将文件拖入对应模式，或使用“添加视频 / 添加图像”。色彩提醒显示在右下角，详细源信息在侧栏。比较颜色时，各路都应考虑预览转换的影响。

发布文件夹内的 `verify_clean_windows.cmd` 使用随包组件生成普通视频、PQ、HLG 和 16 位图像并实际启动程序自检。当前本机验证与另一台干净机器验证分别记录在 `reports/ACCEPTANCE.md`，真实高 DPI/跨屏仍需相应设备。
