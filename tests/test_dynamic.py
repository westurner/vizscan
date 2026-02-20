import pytest
from unittest.mock import patch, MagicMock
from vizscan.dynamic import (
    run_hybrid_scan,
    FlashDetector,
    MockProjectM,
    IRenderer,
    scan_dynamic,
)
from vizscan.static import RiskLevel


# Mock args class
class MockArgs:
    def __init__(self, enable_dynamic=False, duration=5, fps=60, score_quality=False):
        self.enable_dynamic = enable_dynamic
        self.duration = duration
        self.fps = fps
        self.score_quality = score_quality
        self.path = ""
        self.recursive = False
        self.help_scoring = False
        self.output = ""


def test_static_ban_aborts_dynamic(tmp_path):
    # Create a file that triggers a static ban
    p = tmp_path / "static_ban.milk"
    p.write_text("ob_r = 1 - ob_r;")  # InverterStrobe

    args = MockArgs(enable_dynamic=True)
    report = run_hybrid_scan(str(p), args)

    assert report.final_disposition == "FAIL"
    assert len(report.static_events) > 0
    assert report.static_events[0].risk_level == RiskLevel.BAN
    # Should NOT have run dynamic scan
    assert len(report.dynamic_events) == 0


def test_dynamic_fail(tmp_path):
    # Create a file that passes static but fails dynamic (mocked by filename)
    p = tmp_path / "dynamic_fail.milk"
    p.write_text("ob_r = 0.5;")  # Safe static code

    args = MockArgs(enable_dynamic=True)
    report = run_hybrid_scan(str(p), args)

    assert report.final_disposition == "FAIL"
    assert len(report.dynamic_events) > 0
    assert report.dynamic_events[0].rule_id == "DynamicStrobe"


def test_safe_file(tmp_path):
    p = tmp_path / "safe.milk"
    p.write_text("ob_r = 0.5;")

    args = MockArgs(enable_dynamic=True)
    report = run_hybrid_scan(str(p), args)

    assert report.final_disposition == "PASS"
    assert len(report.static_events) == 0
    assert len(report.dynamic_events) == 0


def test_static_warn_only(tmp_path):
    # Create a file that triggers a warning but not a ban
    p = tmp_path / "static_warn.milk"
    p.write_text("val = sin(time * 20);")  # HighFreqOsc (WARNING)

    args = MockArgs(enable_dynamic=False)
    report = run_hybrid_scan(str(p), args)

    assert report.final_disposition == "WARN"
    assert len(report.static_events) > 0
    assert report.static_events[0].risk_level == RiskLevel.WARNING


def test_flash_detector_limit():
    fd = FlashDetector(fps=60, limit=2)
    # Add 3 flashes in quick succession
    assert fd.process_frame(0, 0.0) is None
    assert fd.process_frame(1, 1.0) is None  # Flash 1
    assert fd.process_frame(2, 0.0) is None  # Flash 2
    assert fd.process_frame(3, 1.0) is not None  # Flash 3 (Limit exceeded)


def test_flash_detector_window_expiry():
    fd = FlashDetector(fps=10, limit=2)
    fd.process_frame(0, 0.0)
    fd.process_frame(1, 1.0)  # Flash 1 at frame 1

    # Advance time past window (10 frames)
    fd.process_frame(15, 0.0)  # Flash 2 at frame 15 (Frame 1 should expire)

    # Should have only 1 flash in window now
    assert len(fd.flash_timestamps) == 1


def test_mock_projectm_modes():
    mp = MockProjectM()

    mp.load_preset("dynamic_fail.milk")
    assert mp.render_frame() in [0.0, 1.0]

    mp.load_preset("dynamic_edge.milk")
    assert mp.render_frame() in [0.0, 1.0]

    mp.load_preset("safe.milk")
    val = mp.render_frame()
    assert 0.4 <= val <= 0.6


def test_irenderer_base():
    r = IRenderer()
    r.load_preset("foo")
    r.update_audio()
    with pytest.raises(NotImplementedError):
        r.render_frame()


def test_scan_dynamic_stats():
    # We need to mock MockProjectM to return specific values
    with patch("vizscan.dynamic.MockProjectM") as MockPM:
        instance = MockPM.return_value
        # Mock render_frame to return 0.0 then 1.0
        instance.render_frame.side_effect = [0.0, 1.0] * 30  # 60 frames

        events, stats = scan_dynamic("dummy.milk", duration_sec=1, fps=60)

        assert stats["min_lum"] == 0.0
        assert stats["max_lum"] == 1.0
        assert stats["avg_lum"] == 0.5
        assert stats["dark_ratio"] == 0.5
        assert stats["light_ratio"] == 0.5


def test_scan_dynamic_zero_frames():
    events, stats = scan_dynamic("dummy.milk", duration_sec=0, fps=60)
    assert stats["avg_lum"] == 0.0
    assert stats["dark_ratio"] == 0.0


def test_scan_dynamic_risk_event():
    # Mock FlashDetector to return an event
    with patch("vizscan.dynamic.FlashDetector") as MockFD:
        instance = MockFD.return_value
        instance.process_frame.return_value = "RiskEvent"

        events, stats = scan_dynamic("dummy.milk", duration_sec=1, fps=60)
        assert len(events) == 1
        assert events[0] == "RiskEvent"


def test_hybrid_scan_dynamic_fail(tmp_path):
    # Create a file that passes static but fails dynamic
    p = tmp_path / "dynamic_fail.milk"
    p.write_text("ob_r = 0.5;")

    # Mock scan_dynamic to return failure
    with patch("vizscan.dynamic.scan_dynamic") as mock_sd:
        mock_sd.return_value = ([MagicMock(risk_level="CRITICAL")], {})

        args = MockArgs(enable_dynamic=True)
        report = run_hybrid_scan(str(p), args)
        assert report.final_disposition == "FAIL"


def test_hybrid_scan_static_warn(tmp_path):
    # Create a file that triggers a warning
    p = tmp_path / "static_warn.milk"
    p.write_text("val = sin(time * 20);")  # HighFreqOsc

    args = MockArgs(enable_dynamic=False)
    report = run_hybrid_scan(str(p), args)
    assert report.final_disposition == "WARN"


def test_mock_projectm_unknown_mode():
    mp = MockProjectM()
    mp.mode = "unknown"
    assert mp.render_frame() == 0.0
