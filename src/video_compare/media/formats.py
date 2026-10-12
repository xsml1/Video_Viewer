"""File-dialog hints only: readers identify the actual contents."""

from pathlib import Path

VIDEO_SUFFIXES = [
    "mp4",
    "m4v",
    "mov",
    "qt",
    "mkv",
    "webm",
    "avi",
    "wmv",
    "asf",
    "flv",
    "f4v",
    "ts",
    "mts",
    "m2ts",
    "m2t",
    "mpg",
    "mpeg",
    "mpe",
    "m2v",
    "vob",
    "ogv",
    "ogg",
    "3gp",
    "3g2",
    "mxf",
    "nut",
    "ivf",
]
RAW_SUFFIXES = frozenset(
    f".{suffix}"
    for suffix in [
        "3fr",
        "arw",
        "cr2",
        "cr3",
        "dng",
        "erf",
        "k25",
        "kdc",
        "mef",
        "mos",
        "mrw",
        "nef",
        "nrw",
        "orf",
        "pef",
        "raf",
        "raw",
        "rw2",
        "sr2",
        "srf",
        "x3f",
    ]
)
IMAGE_SUFFIXES = [
    "png",
    "apng",
    "jpg",
    "jpeg",
    "jfif",
    "mpo",
    "bmp",
    "dib",
    "gif",
    "tif",
    "tiff",
    "webp",
    "avif",
    "heic",
    "heif",
    "jxl",
    "jxr",
    "wdp",
    "hdp",
    "jp2",
    "j2k",
    "j2c",
    "jpc",
    "jpf",
    "jpx",
    "jls",
    "qoi",
    "svg",
    "svgz",
    "pdf",
    "psd",
    "tga",
    "ico",
    "cur",
    "icns",
    "dds",
    "pcx",
    "dcx",
    "pbm",
    "pgm",
    "ppm",
    "pnm",
    "pam",
    "sgi",
    "rgb",
    "rgba",
    "bw",
    "ras",
    "xbm",
    "xpm",
    "wbmp",
] + [suffix.lstrip(".") for suffix in sorted(RAW_SUFFIXES)]


def media_file_filter(media_kind: str) -> str:
    suffixes = (
        IMAGE_SUFFIXES
        if media_kind == "image"
        else VIDEO_SUFFIXES
        if media_kind == "video"
        else IMAGE_SUFFIXES + VIDEO_SUFFIXES
    )
    label = {"image": "图像", "video": "视频"}.get(media_kind, "图像与视频")
    return f"{label} ({' '.join(f'*.{suffix}' for suffix in suffixes)});;所有文件 (*)"


def infer_media_kind(path: Path) -> str:
    """Route common content signatures before suffix hints; decoders validate contents."""
    hint = "image" if path.suffix.lower().lstrip(".") in IMAGE_SUFFIXES else "video"
    if not path.is_file():
        # Missing files are reported by the background reader, like decode failures.
        return hint
    with path.open("rb") as source:
        header = source.read(512)
    if header.startswith(
        (
            b"\x89PNG\r\n\x1a\n",
            b"\xff\xd8",
            b"GIF87a",
            b"GIF89a",
            b"BM",
            b"II*\0",
            b"MM\0*",
            b"II+\0",
            b"MM\0+",
            b"II\xbc\x01",
            b"qoif",
            b"\xff\x0a",
            b"\0\0\0\x0cJXL ",
            b"\0\0\0\x0cjP  ",
            b"%PDF",
            b"8BPS",
        )
    ) or (header.startswith(b"RIFF") and header[8:12] == b"WEBP"):
        return "image"
    if b"<svg" in header.lstrip(b"\xef\xbb\xbf \r\n\t"):
        return "image"
    if header[4:8] == b"ftyp":
        brands = {header[i : i + 4] for i in range(8, min(len(header), 64), 4)}
        if path.suffix.lower() == ".cr3" and b"crx " in brands:
            return "image"
        return (
            "image" if brands & {b"avif", b"avis", b"heic", b"heix", b"mif1", b"msf1"} else "video"
        )
    if header.startswith((b"\x1aE\xdf\xa3", b"OggS", b"FLV")) or (
        header.startswith(b"RIFF") and header[8:12] == b"AVI "
    ):
        return "video"
    return hint
