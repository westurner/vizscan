import pytest
import os
from vizscan.static import scan_file_full, RiskLevel

PRESETS_DIR = os.path.join(os.path.dirname(__file__), "presets")


def get_preset_path(filename):
    return os.path.join(PRESETS_DIR, filename)


def verify_preset(filename):
    path = get_preset_path(filename)
    events, metadata, _ = scan_file_full(path)

    if not metadata:
        # Fallback for safe.milk or files without metadata
        if filename == "safe.milk":
            assert len(events) == 0
        return

    # Check that we found the expected number of events for each rule
    found_counts = {}
    for e in events:
        found_counts[e.rule_id] = found_counts.get(e.rule_id, 0) + 1

    for rule_id, expected_count in metadata.items():
        assert (
            found_counts.get(rule_id, 0) == expected_count
        ), f"Expected {expected_count} events for {rule_id} in {filename}, found {found_counts.get(rule_id, 0)}"


def test_static_ban():
    verify_preset("static_ban.milk")


def test_static_critical_modulo():
    verify_preset("static_critical_modulo.milk")


def test_static_critical_tan_color():
    verify_preset("static_critical_tan_color.milk")


def test_static_warn_high_freq():
    verify_preset("static_warn_high_freq.milk")


def test_static_warn_tan_motion():
    verify_preset("static_warn_tan_motion.milk")


def test_static_warn_step():
    verify_preset("static_warn_step.milk")


def test_safe():
    verify_preset("safe.milk")
