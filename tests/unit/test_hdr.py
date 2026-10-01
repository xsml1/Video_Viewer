from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from video_compare.domain.models import ColorInfo
from video_compare.media.color import ColorError, conversion_parameters, display_notice
from video_compare.media.hdr import _linear_table, display_rgb16


@pytest.mark.parametrize(
    "signal,nits", [(0, 0), (0.508078421517399, 100), (0.751827096247041, 1000), (1, 10000)]
)
def test_pq_standard_reference_luminance(signal, nits):
    value = _linear_table("smpte2084")[round(signal * 65535)] * 100
    assert value == pytest.approx(nits, rel=0.0002, abs=0.01)


def test_hlg_1000_nit_assumption_and_fixed_exposure():
    table = _linear_table("arib-std-b67")
    assert table[0] == 0
    assert table[32768] == pytest.approx(0.5069702849, abs=0.0001)
    assert table[-1] == pytest.approx(10, abs=0.0001)
    info = ColorInfo(primaries="bt2020", transfer="arib-std-b67")
    ramp = np.arange(65536, dtype=np.uint16)[None, :, None].repeat(3, axis=2)
    result = display_rgb16(ramp, info)
    assert result[0, 0, 0] == 0 and result[0, -1, 0] == 255
    assert np.all(np.diff(result[0, :, 0].astype(int)) >= 0)
    isolated = display_rgb16(ramp[:, 32768:32769], info)
    assert np.array_equal(isolated, result[:, 32768:32769])
    assert "推定峰值 1000" in display_notice(info)


def test_invalid_color_paths_fail_explicitly():
    info = ColorInfo(matrix="bt2020c", primaries="bt2020", hdr_unsupported=True)
    with pytest.raises(ColorError, match="BT.2020 CL"):
        conversion_parameters(info)
    pixels = np.zeros((2, 2, 3), np.uint16)
    with pytest.raises(ValueError, match="传递函数"):
        display_rgb16(pixels, replace(info, transfer="unknown"))
    with pytest.raises(ValueError, match="原色"):
        display_rgb16(pixels, ColorInfo(primaries="smpte431", transfer="smpte2084"))
