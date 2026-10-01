"""Deterministic HDR/wide-gamut conversion to the application's SDR RGB8 preview.

PQ uses ST 2084, HLG the zimg-compatible per-channel 1.2 OOTF at 1000 nits.
SDR video uses the BT.1886 display EOTF (gamma 2.4), matching zimg's display policy.
The reference white is 100 nits. Hable mapping uses a source/fallback peak and
does not vary with frame statistics. Working float buffers are limited to rows.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from video_compare.domain.models import ColorInfo

# D65 linear-light primary transforms, derived from the standard chromaticities.
_TO_709 = {
    "bt2020": np.array(
        [
            [1.660491, -0.587641, -0.072850],
            [-0.124550, 1.132900, -0.008349],
            [-0.018151, -0.100579, 1.118730],
        ],
        dtype=np.float32,
    ),
    "smpte432": np.array(
        [
            [1.224940, -0.224940, 0.0],
            [-0.042057, 1.042057, 0.0],
            [-0.019638, -0.078636, 1.098274],
        ],
        dtype=np.float32,
    ),
}


@lru_cache(maxsize=8)
def _linear_table(transfer: str) -> np.ndarray:
    values = np.arange(65536, dtype=np.float64) / 65535.0
    if transfer == "smpte2084":
        p = values ** (1 / 78.84375)
        linear = (np.maximum(p - 0.8359375, 0) / (18.8515625 - 18.6875 * p)) ** (
            1 / 0.1593017578125
        )
        linear *= 100.0  # 10000-nit PQ scaled by 100-nit SDR reference white.
    elif transfer == "arib-std-b67":
        scene = np.where(
            values <= 0.5,
            values * values / 3,
            (np.exp((values - 0.55991073) / 0.17883277) + 0.28466892) / 12,
        )
        linear = scene**1.2 * 10.0  # Explicit 1000-nit HLG display assumption.
    elif transfer in {"bt709", "bt2020-10", "bt2020-12", "smpte170m", "unspecified", ""}:
        linear = values**2.4
    elif transfer == "iec61966-2-1":
        linear = np.where(values <= 0.04045, values / 12.92, ((values + 0.055) / 1.055) ** 2.4)
    elif transfer == "linear":
        linear = values
    else:
        raise ValueError(f"尚未验证的广色域传递函数：{transfer}")
    result = linear.astype(np.float32)
    result.setflags(write=False)
    return result


def _hable(values):
    return (
        (values * (0.15 * values + 0.05) + 0.004) / (values * (0.15 * values + 0.5) + 0.06)
    ) - 0.02 / 0.3


def display_rgb16(encoded: np.ndarray, info: ColorInfo) -> np.ndarray:
    if encoded.dtype != np.uint16 or encoded.ndim != 3 or encoded.shape[2] != 3:
        raise ValueError("HDR 转换需要真实 RGB16 采样")
    hdr = info.transfer in {"smpte2084", "arib-std-b67"}
    primaries = info.primaries or ("bt2020" if hdr else "bt709")
    if primaries not in {"bt709", "bt2020", "smpte432"}:
        raise ValueError(f"尚未验证的 HDR/广色域原色：{primaries}")
    table = _linear_table(info.transfer or "")
    result = np.empty(encoded.shape, dtype=np.uint8)
    for top in range(0, encoded.shape[0], 64):
        linear = table[encoded[top : top + 64]]
        if primaries in _TO_709:
            linear = linear @ _TO_709[primaries].T
        np.maximum(linear, 0, out=linear)
        if hdr:
            signal = np.maximum(linear.max(axis=2), 1e-6)
            factor = _hable(signal) / (_hable(info.peak_nits / 100.0) * signal)
            linear *= factor[:, :, None]
        # Fixed BT.709 output transfer, full range; values outside SDR gamut clip visibly.
        encoded709 = linear ** (1 / 2.4)
        result[top : top + 64] = np.rint(np.clip(encoded709, 0, 1) * 255).astype(np.uint8)
    return result
