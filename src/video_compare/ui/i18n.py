"""Bundled offline interface translations."""

from __future__ import annotations

import re

from video_compare.ui.locale_catalog import LOCALES

LANGUAGE_OPTIONS = (
    ("zh_CN", "简体中文"),
    ("zh_TW", "繁體中文"),
    ("en_US", "English"),
    ("ja_JP", "日本語"),
    ("ko_KR", "한국어"),
    ("fr_FR", "Français"),
    ("de_DE", "Deutsch"),
    ("es_ES", "Español"),
)

_language = "zh_CN"

OVERRIDES: dict[str, dict[str, str]] = {
    "zh_TW": {
        "添加图像": "新增圖片",
        "图像对比": "圖片對比",
        "图像文件": "圖片檔案",
        "图像": "圖片",
        "保存视图": "儲存畫面",
        "视图联动": "畫面連動",
    },
    "ja_JP": {
        "导出对比图": "比較画像をエクスポート",
        "导出对比图…": "書き出し…",
        "视图联动": "連動",
        "同区域查看": "同じ領域",
        "跟随系统": "システム設定に合わせる",
        "适应": "全体表示",
        "帧": "フレーム",
        "按时间同步": "時刻",
        "按帧号同步": "フレーム",
        "原生像素 100%": "画素 100%",
    },
    "ko_KR": {
        "导出对比图": "비교 이미지 내보내기",
        "视图联动": "연동",
        "导出对比图…": "내보내기…",
        "跟随系统": "시스템 설정 따르기",
        "同区域查看": "동일 영역",
        "按时间同步": "시간",
        "按帧号同步": "프레임",
        "原生像素 100%": "픽셀 100%",
    },
    "fr_FR": {
        "导出对比图": "Exporter l’image comparée",
        "视图联动": "Lier",
        "导出对比图…": "Exporter…",
        "按时间同步": "Temps",
        "按帧号同步": "Image",
        "框选 ROI": "Zone ROI",
        "帧": "Image",
        "同区域查看": "Zone",
        "原生像素 100%": "Pixels 100%",
        "添加视频": "Ajouter",
        "添加图像": "Ajouter",
        "视频对比": "Vidéo",
        "图像对比": "Images",
        "保存原帧": "Images",
        "保存视图": "Vue PNG",
        "自动（按画面比例）": "Auto",
        "横向排列": "Lignes",
        "竖向排列": "Colonnes",
    },
    "de_DE": {
        "导出对比图": "Vergleichsbild exportieren",
        "导出对比图…": "Export…",
        "帧": "Frame",
        "播放": "Abspielen",
        "跟随系统": "Systemeinstellung verwenden",
        "同区域查看": "Bereich",
        "按时间同步": "Zeit",
        "按帧号同步": "Frame",
        "原生像素 100%": "Pixel 100%",
        "视频对比": "Video",
        "图像对比": "Bilder",
        "保存原帧": "Frames",
        "自动（按画面比例）": "Auto",
        "横向排列": "Zeilen",
        "竖向排列": "Spalten",
        "添加视频": "Datei +",
        "添加图像": "Datei +",
        "适应": "Fit",
        "框选 ROI": "ROI",
        "视图联动": "Link",
        "保存视图": "Ansicht",
        "设置": "Optionen",
        "侧栏": "Info",
        "移除选中": "Entfernen",
        "替换选中": "Ersetzen",
        "暂停选中路同步": "Sync pausieren",
    },
    "es_ES": {
        "导出对比图": "Exportar imagen comparativa",
        "视图联动": "Vincular",
        "导出对比图…": "Exportar…",
        "帧": "Fotograma",
        "播放": "Reproducir",
        "适应": "Ajustar",
        "同区域查看": "Zona",
        "按时间同步": "Tiempo",
        "按帧号同步": "Fotograma",
        "原生像素 100%": "Píxel 100%",
        "添加视频": "Añadir",
        "添加图像": "Añadir",
        "视频对比": "Vídeo",
        "图像对比": "Imágenes",
        "保存原帧": "Fotogramas",
        "保存视图": "Vista PNG",
        "自动（按画面比例）": "Auto",
        "横向排列": "Filas",
        "竖向排列": "Columnas",
        "框选 ROI": "ROI",
        "移除选中": "Eliminar",
        "替换选中": "Reemplazar",
    },
}


def set_language(language: str) -> None:
    global _language
    if language not in dict(LANGUAGE_OPTIONS):
        raise ValueError(f"Unsupported language: {language}")
    _language = language


def language() -> str:
    return _language


EN: dict[str, str] = {
    "视频对比": "Video",
    "图像对比": "Images",
    "添加视频": "Add",
    "添加图像": "Add",
    "按时间同步": "Time",
    "按帧号同步": "Frame",
    "同区域查看": "Region",
    "原生像素 100%": "Pixels 100%",
    "自动（按画面比例）": "Auto",
    "网格排列": "Grid",
    "横向排列": "Rows",
    "竖向排列": "Columns",
    "与窗口一致": "As shown",
    "适应": "Fit",
    "框选 ROI": "Select ROI",
    "视图联动": "Link",
    "保存视图": "Save view",
    "保存原帧": "Frames",
    "保存各图": "Images",
    "导出对比图…": "Export…",
    "设置": "Settings",
    "侧栏": "Sidebar",
    "视频文件": "Video files",
    "图像文件": "Image files",
    "移除选中": "Remove selected",
    "替换选中": "Replace selected",
    "上移": "Move up",
    "下移": "Move down",
    "暂停选中路同步": "Exclude selected from sync",
    "重新加入时间同步": "Rejoin time sync",
    "选中路 Offset": "Selected source offset",
    "时间（秒）": "Time (seconds)",
    "帧": "Frame",
    "秒": "Seconds",
    "应用 Offset": "Apply offset",
    "Marker（仅本次会话）": "Markers (this session only)",
    "标题（可选）": "Title (optional)",
    "备注（可选）": "Note (optional)",
    "添加 Marker (M)": "Add marker (M)",
    "跳转选中 Marker": "Go to marker",
    "播放": "Play",
    "暂停": "Pause",
    "速度": "Speed",
    "区间循环": "Loop range",
    "时间 HH:MM:SS.mmm": "Time HH:MM:SS.mmm",
    "帧号（从 1 开始）": "Frame number (starts at 1)",
    "循环：未设置": "Loop: not set",
    "明暗模式": "Light/dark mode",
    "跟随系统": "Follow system",
    "浅色": "Light",
    "深色": "Dark",
    "整体色彩": "Color family",
    "颜色设置": "Color roles",
    "工作区": "Workspace",
    "功能区": "Controls",
    "强调色": "Accent",
    "视频信息": "Media information",
    "跟随色系": "Follow color family",
    "自定义": "Custom",
    "完成": "Done",
    "主题": "Theme",
    "语言": "Language",
    "简体中文": "Simplified Chinese",
    "英语": "English",
    "矩形": "Rectangle",
    "圆形/椭圆": "Circle/ellipse",
    "箭头": "Arrow",
    "直线": "Line",
    "自由画笔": "Freehand pen",
    "红": "Red",
    "橙": "Orange",
    "黄": "Yellow",
    "绿": "Green",
    "青": "Cyan",
    "蓝": "Blue",
    "紫": "Purple",
    "白": "White",
    "黑": "Black",
    "标注联动到全部画面": "Link annotations to all panes",
    "撤销上一笔": "Undo last stroke",
    "删除选中": "Delete selected",
    "删除全部": "Delete all",
    "取消": "Cancel",
    "完成并导出": "Finish and export",
    "全部画面": "All panes",
    "仅起笔画面": "Starting pane only",
    "导出对比图": "Export comparison",
    "排列方式": "Layout",
    "图片格式": "Image format",
    "JPEG 质量": "JPEG quality",
    "PNG（无损，推荐）": "PNG (lossless, recommended)",
    "JPEG/JPG（可调质量）": "JPEG/JPG (adjustable quality)",
    "选择保存位置…": "Choose save location…",
    "导出前先编辑标注（可选多画面联动）": "Edit annotations before export (optional pane linking)",
    "界面语言": "Interface language",
    "还没有可导出的画面。请先导入文件，等画面显示后再导出。": (
        "No image is ready to export. Add files and wait for the panes to appear."
    ),
    "Marker 仅在本次会话有效，退出后不会保留。仍要退出吗？": (
        "Markers last only for this session. Exit without saving them?"
    ),
    (
        "导出当前窗口里看到的画面区域（缩放的对比结果）：包含画面左上角的"
        "文件名、右下角的帧号信息与标注，不包含按钮、工具栏等界面元素；"
        "不再生成 JSON 文件。"
    ): (
        "Export the visible comparison, including filenames, frame details and annotations. "
        "Controls are excluded. No JSON file is created."
    ),
    (
        "整体色彩决定色系风格；工作区、功能区、强调色和视频信息四种颜色"
        "都用同一套色板选择：上方六行是所选色系的主题色及其由浅到深的深浅"
        "（右侧为原色），最下一行是标准色。"
    ): (
        "Choose a color family, then pick workspace, control, accent and media-label colors "
        "from its shades or the standard colors."
    ),
    "清爽极简": "Clean Minimal",
    "莫兰迪": "Morandi",
    "奶油风": "Cream",
    "复古": "Retro",
    "赛博朋克": "Cyberpunk",
    "马卡龙": "Macaron",
    "未知": "Unknown",
    "未知编码": "Unknown codec",
    "图像": "Image",
    "RGB8 预览": "RGB8 preview",
    "源文件只读": "Source file read-only",
    "等待画面": "Waiting for image",
    "色彩推定": "Color metadata inferred",
    "HDR/BT.2020 仅元信息": "HDR/BT.2020 metadata only",
    "导出成功": "Export succeeded",
    "导出失败": "Export failed",
    "暂时无法导出": "Cannot export yet",
    "部分视频未导入": "Some videos could not be loaded",
    "部分图像未导入": "Some images could not be loaded",
    "Marker 未保存": "Markers not saved",
    "选择截图保存目录": "Choose screenshot folder",
    "保存对比图": "Save comparison image",
    "替换图像": "Replace image",
    "替换视频": "Replace video",
    "JPEG 图片 (*.jpg *.jpeg)": "JPEG images (*.jpg *.jpeg)",
    "PNG 图片 (*.png)": "PNG images (*.png)",
    "所有文件 (*)": "All files (*)",
    "图像 (*.*)": "Images (*.*)",
    "已脱离同步": "Excluded from sync",
    "循环：未设置（时间轴变更后重置）": "Loop: cleared after timeline change",
    "添加本地图像；可比较 1–6 张": "Add local images; compare 1–6",
    "添加本地视频；当前按完整帧组同步显示": (
        "Add local videos; showing complete synchronized frame groups"
    ),
    "已移除全部视频；可添加本地视频": "All videos removed; add local videos",
    "已取消标注导出；本次标注已清除": "Annotation export cancelled; strokes cleared",
    "选中一路查看源信息与预览限制": "Select a source to see its information and preview limits",
    "双击画面单路查看 · Esc 返回网格": "Double-click a pane to focus; Esc returns to grid",
    "原生像素检查：忽略 SAR；Ctrl+滚轮调整像素倍率": (
        "Native pixel view: ignores SAR; Ctrl+wheel changes scale"
    ),
    "标注缩放后仍跟随源位置": "Annotations stay anchored when zooming",
    "选择要删除的标注": "Choose an annotation to delete",
    "视频窗口的背景、画面框与画布文字底色": (
        "Video area background, pane borders and canvas label backgrounds"
    ),
    "工具栏、播放条、侧栏与控件的底色": "Toolbar, transport, sidebar and control backgrounds",
    "选中状态、进度条与画布高亮": "Selection, progress bar and canvas highlights",
    "画面上文件名称与帧信息的文字颜色（默认绿色）": (
        "Filename and frame text on panes (green by default)"
    ),
    "整体色彩：色系风格，决定色板的主题颜色": "Color family determines the palette's theme colors",
    "该颜色使用所选色系的主色": "Use the selected color family's main color",
    "标准颜色：点击任意色块即把该颜色用于当前角色": (
        "Standard colors: choose a swatch for the current role"
    ),
    "添加本地视频（最多 6 路，Ctrl+O）": "Add local videos (up to 6, Ctrl+O)",
    "添加本地图像（最多 6 路，Ctrl+O）": "Add local images (up to 6, Ctrl+O)",
    "同步方式：按真实 PTS 或显示帧号": "Sync by real PTS or displayed frame number",
    "基准视频（与列表选中项独立）": "Reference video (independent of list selection)",
    "原生像素以 framebuffer 物理像素为准，忽略视频 SAR": (
        "Native pixels use physical framebuffer pixels and ignore video SAR"
    ),
    "画面排列方式；自动会按导入视频的比例选择": "Pane layout; Auto uses the source aspect ratios",
    "适应画面：恢复完整画面（F）": "Fit the full image (F)",
    "在画面内拖出区域，其他路定位到相同相对区域": (
        "Drag a region in a pane to align the other panes"
    ),
    "缩放、平移、ROI 是否联动所有画面": "Link zoom, pan and ROI across panes",
    "保存整个画布 PNG，含文件名与帧号标注": "Save the canvas as PNG with filename and frame labels",
    "保存各路源采样帧 PNG 与帧身份 JSON": "Save source frames as PNG and frame metadata as JSON",
    "保存各路 RGB8 预览 PNG 与图像来源 JSON": "Save RGB8 images as PNG and source metadata as JSON",
    "导出当前窗口看到的画面（不含界面元素）": "Export visible pane content without controls",
    "色系、明暗模式与强调色": "Theme and language settings",
    "显示或隐藏右侧信息栏": "Show or hide the right sidebar",
    "隐藏侧栏": "Hide sidebar",
    "播放或暂停（空格）": "Play or pause (Space)",
    "后退一步（左方向键）": "Step backward (Left arrow)",
    "前进一步（右方向键）": "Step forward (Right arrow)",
    "步进量：帧为正整数；秒最多精确到毫秒": (
        "Step amount: positive frames or seconds to milliseconds"
    ),
    "把当前完整组设为循环起点": "Set loop start at the displayed frame group",
    "把当前完整组设为循环终点": "Set loop end at the displayed frame group",
    "输入全局时间并回车定位": "Enter global time and press Enter to seek",
    "输入基准视频帧号并回车定位": "Enter reference frame number and press Enter to seek",
    "JPEG 质量，数值越高文件越大": "JPEG quality; higher values make larger files",
    "勾选后先在画面上框选或画箭头，点“完成并导出”才写文件": (
        "Draw on the panes before the file is saved"
    ),
    "关闭后，新画的矩形和自由画笔等标注只作用于起笔所在画面；已画标注保持原范围": (
        "When off, new strokes stay on the starting pane; existing strokes keep their scope"
    ),
    "HDR/BT.2020 暂不显示画面\n仅可查看元信息": "HDR/BT.2020 image unavailable\nMetadata only",
    "把本地视频或图像拖入窗口，或点击“添加文件”开始对比": (
        "Drop local videos or images here, or click Add files"
    ),
}

PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^第 (\d+) 笔 · (.+) · (全部画面|仅起笔画面)$"), r"Stroke \1 · \2 · \3"),
    (
        re.compile(r"^正在对比 (\d+) 张图像 · RGB8 预览 · 源文件只读$"),
        r"Comparing \1 images · RGB8 preview · source files read-only",
    ),
    (re.compile(r"^正在读取 (\d+) 张图像$"), r"Loading \1 images"),
    (
        re.compile(r"^正在后台探测/索引 (\d+) 路；窗口仍可操作$"),
        r"Probing/indexing \1 sources in the background; the window remains usable",
    ),
    (
        re.compile(r"^(\d+) 路参与同步，等待完整帧组$"),
        r"\1 sources participating; waiting for a complete frame group",
    ),
    (
        re.compile(r"^已同步显示 (\d+) 路(?: · (\d+) 路脱离同步)?"),
        r"Displaying \1 synchronized sources",
    ),
    (re.compile(r"^帧 (\d+) · PTS (.+)$"), r"Frame \1 · PTS \2"),
    (re.compile(r"^错误：(.*)$"), r"Error: \1"),
    (re.compile(r"^正在保存截图 · 完整组 (.*)$"), r"Saving screenshots · group \1"),
    (
        re.compile(r"^已在完整组 (.*) 添加 Marker（仅本次会话）$"),
        r"Marker added to group \1 (this session only)",
    ),
    (
        re.compile(r"^循环起点 (.*)；请定位终点后按 O$"),
        r"Loop starts at \1; seek to the end and press O",
    ),
    (re.compile(r"^循环 \[(.*)\)；点击开启$"), r"Loop [\1); click to enable"),
    (
        re.compile(r"^正在读取替换图像 (.*)，原画面保持显示$"),
        r"Loading replacement image \1; keeping current view",
    ),
    (
        re.compile(r"^正在后台索引替换文件 (.*)，原画面保持显示$"),
        r"Indexing replacement file \1; keeping current view",
    ),
    (re.compile(r"^(.+)：索引完成$"), r"\1: indexing complete"),
)


def translate(text: str) -> str:
    if _language == "zh_CN" or not text:
        return text
    override = OVERRIDES.get(_language, {}).get(text)
    if override is not None:
        return override
    localized = LOCALES.get(_language, {}).get(text)
    if localized is not None:
        return localized.replace("影象", "影像") if _language == "zh_TW" else localized
    if text in EN:
        return EN[text]
    if text.startswith("● ") and text[2:] in EN:
        return f"● {translate(text[2:])}"
    stroke = re.fullmatch(r"第 (\d+) 笔 · (.+) · (全部画面|仅起笔画面)", text)
    if stroke:
        label = {
            "zh_TW": "第 {} 筆",
            "en_US": "Stroke {}",
            "ja_JP": "描画 {}",
            "ko_KR": "표시 {}",
            "fr_FR": "Trait {}",
            "de_DE": "Strich {}",
            "es_ES": "Trazo {}",
        }[_language].format(stroke.group(1))
        return f"{label} · {translate(stroke.group(2))} · {translate(stroke.group(3))}"
    image_count = re.fullmatch(r"正在对比 (\d+) 张图像 · RGB8 预览 · 源文件只读", text)
    if image_count:
        template = {
            "zh_TW": "正在對比 {} 張圖片 · RGB8 預覽 · 原始檔唯讀",
            "en_US": "Comparing {} images · RGB8 preview · source files read-only",
            "ja_JP": "{} 枚の画像を比較中 · RGB8 プレビュー · 元ファイルは読み取り専用",
            "ko_KR": "이미지 {}개 비교 중 · RGB8 미리보기 · 원본 파일 읽기 전용",
            "fr_FR": "Comparaison de {} images · aperçu RGB8 · fichiers source en lecture seule",
            "de_DE": "Vergleich von {} Bildern · RGB8-Vorschau · Quelldateien schreibgeschützt",
            "es_ES": "Comparando {} imágenes · RGB8 · originales de solo lectura",
        }[_language]
        return template.format(image_count.group(1))
    if ";;所有文件 (*)" in text:
        return (
            text.replace("图像 (", "Images (")
            .replace("视频 (", "Videos (")
            .replace(";;所有文件 (*)", ";;All files (*)")
        )
    for pattern, replacement in PATTERNS:
        if pattern.fullmatch(text):
            result = pattern.sub(replacement, text)
            if pattern.pattern.startswith("^第 "):
                for source, target in EN.items():
                    if source in (
                        "矩形",
                        "圆形/椭圆",
                        "箭头",
                        "直线",
                        "自由画笔",
                        "全部画面",
                        "仅起笔画面",
                    ):
                        result = result.replace(source, target)
            return result
    return text
