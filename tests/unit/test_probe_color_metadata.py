from __future__ import annotations

import json

import pytest

from video_compare.media import probe


def metadata_asset(tmp_path, monkeypatch, side_data, *, frame_data=(), matrix="bt2020nc"):
    path = tmp_path / "header.bin"
    path.write_bytes(b"non-user metadata test")
    binary = tmp_path / "ffprobe.exe"
    binary.write_bytes(b"probe stub")
    payload = {
        "streams": [
            {
                "index": 5,
                "codec_type": "video",
                "width": 320,
                "height": 180,
                "time_base": "1/30000",
                "pix_fmt": "yuv420p10le",
                "color_space": matrix,
                "color_range": "tv",
                "color_transfer": "smpte2084",
                "color_primaries": "bt2020",
                "side_data_list": side_data,
            }
        ],
        "frames": frame_data,
    }

    class MetadataProcess:
        returncode = 0

        def __init__(self, command, **kwargs):
            assert command[-1] == str(path)
            assert "frame=stream_index,side_data_list" in command

        def poll(self):
            return 0

        def communicate(self, **kwargs):
            return json.dumps(payload).encode(), b""

    monkeypatch.setattr(probe.subprocess, "Popen", MetadataProcess)
    return probe.probe_video(path, ffprobe_path=binary)


def test_actual_first_frame_maxcll_precedes_mastering_peak(tmp_path, monkeypatch):
    frames = [
        {"stream_index": 0, "side_data_list": [{"max_content": 9999}]},
        {"stream_index": 5, "side_data_list": [{"max_luminance": "1000/1"}, {"max_content": 1500}]},
    ]
    info = metadata_asset(tmp_path, monkeypatch, [], frame_data=frames).color_info
    assert info.peak_nits == 1500 and not info.peak_inferred


@pytest.mark.parametrize(
    "peak,expected,inferred", [(50, 50, False), (float("inf"), 1000, True), (20000, 1000, True)]
)
def test_peak_metadata_is_preserved_or_explicitly_inferred(
    tmp_path, monkeypatch, peak, expected, inferred
):
    info = metadata_asset(tmp_path, monkeypatch, [{"max_content": peak}]).color_info
    assert info.peak_nits == expected and info.peak_inferred is inferred


@pytest.mark.parametrize(
    "profile,compatibility,unsupported", [(5, 0, True), (8, 1, False), (8, 2, False), (8, 4, False)]
)
def test_dolby_vision_requires_compatible_base_layer(
    tmp_path, monkeypatch, profile, compatibility, unsupported
):
    side = [{"dv_profile": profile, "dv_bl_signal_compatibility_id": compatibility}]
    info = metadata_asset(tmp_path, monkeypatch, side).color_info
    assert info.dolby_vision
    assert info.hdr_unsupported is unsupported


def test_bt2020_constant_luminance_is_not_treated_as_ncl(tmp_path, monkeypatch):
    info = metadata_asset(tmp_path, monkeypatch, [], matrix="bt2020c").color_info
    assert info.hdr_unsupported
