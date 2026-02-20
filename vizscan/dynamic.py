import math
from typing import List, Dict, Optional, Deque, Tuple
from collections import deque

from .static import (
    scan_file_full,
    RiskEvent,
    RiskLevel,
)
from .reports import HybridReport


class IRenderer:
    """Interface for the ProjectM Renderer."""

    def load_preset(self, path: str):
        pass

    def render_frame(self) -> float:
        raise NotImplementedError()
        #  return 0.0  # Returns average luminance (0.0 - 1.0)

    def update_audio(self):
        pass


class MockProjectM(IRenderer):
    """
    Simulates ProjectM for testing the pipeline without a GPU.
    It generates luminance values based on the filename to test safety logic.
    """

    def __init__(self):
        self.frame_count = 0
        self.mode = "safe"

    def load_preset(self, path: str):
        self.frame_count = 0
        if "dynamic_fail" in path:
            self.mode = "strobe"
        elif "dynamic_edge" in path:
            self.mode = "edge"  # 2.9 Hz (Safe but close)
        else:
            self.mode = "safe"

    def update_audio(self):
        pass

    def render_frame(self) -> float:
        self.frame_count += 1
        t = self.frame_count / 60.0

        if self.mode == "safe":
            return 0.5 + 0.1 * math.sin(t)
        elif self.mode == "strobe":
            # 15 Hz Strobe (Flash every 4 frames at 60fps)
            return 1.0 if (self.frame_count % 4) < 2 else 0.0
        elif self.mode == "edge":
            # 2.9 Hz Flash
            return 1.0 if (math.sin(t * 2.9 * 2 * math.pi) > 0) else 0.0
        return 0.0


class FlashDetector:
    """
    Harding-Lite Algorithm:
    Detects if luminance changes > 10% more than 3 times in 1 second.
    """

    def __init__(self, fps=60, limit=3):
        self.fps = fps
        self.limit = limit
        self.history: Deque[float] = deque(maxlen=fps)  # 1 second window
        self.flashes_in_window = 0
        self.last_lum = 0.0
        self.flash_timestamps: Deque[int] = (
            deque()
        )  # Frame numbers where flash occurred

    def process_frame(self, frame_idx: int, lum: float) -> Optional[RiskEvent]:
        # 1. Detect Transition
        delta = abs(lum - self.last_lum)
        self.last_lum = lum

        is_flash = delta > 0.10  # 10% luminance jump

        # 2. Update Window
        # Remove flashes older than 1 second (fps frames ago)
        while self.flash_timestamps and (
            frame_idx - self.flash_timestamps[0] > self.fps
        ):
            self.flash_timestamps.popleft()

        if is_flash:
            self.flash_timestamps.append(frame_idx)

        # 3. Check Limit
        current_rate = len(self.flash_timestamps)
        # Note: Harding is 3 flashes (6 transitions) per second.
        # Simplified here to 3 transitions > 10% for demo.

        if current_rate > self.limit:
            return RiskEvent(
                rule_id="DynamicStrobe",
                risk_level=RiskLevel.CRITICAL,
                score=100,
                context=f"Measured {current_rate} flashes/sec (Limit {self.limit})",
                line=0,
                variables=["screen_luminance"],
                source_type="Dynamic",
            )
        return None


def scan_dynamic(
    filepath: str, duration_sec: int, fps: int
) -> Tuple[List[RiskEvent], Dict]:
    """
    Runs the dynamic rendering pass.
    """
    # 1. Setup
    renderer = MockProjectM()  # Swap for real libprojectm wrapper in prod
    detector = FlashDetector(fps=fps)
    renderer.load_preset(filepath)

    events = []
    failed = False

    # Stats
    total_lum = 0.0
    min_lum = 1.0
    max_lum = 0.0
    dark_frames = 0
    light_frames = 0

    total_frames = duration_sec * fps

    # 2. Render Loop
    for i in range(total_frames):
        renderer.update_audio()
        lum = renderer.render_frame()

        # Stats Update
        total_lum += lum
        min_lum = min(min_lum, lum)
        max_lum = max(max_lum, lum)
        if lum < 0.1:
            dark_frames += 1
        elif lum > 0.9:
            light_frames += 1

        risk = detector.process_frame(i, lum)

        if risk and not failed:
            events.append(risk)
            failed = True  # Stop adding events after first failure, but finish stats?
            # Optimization: break early if we want speed over full stats
            # break # Don't break if we want stats

    stats = {
        "avg_lum": total_lum / total_frames if total_frames > 0 else 0.0,
        "min_lum": min_lum,
        "max_lum": max_lum,
        "dark_ratio": dark_frames / total_frames if total_frames > 0 else 0.0,
        "light_ratio": light_frames / total_frames if total_frames > 0 else 0.0,
    }

    return events, stats


def run_hybrid_scan(filepath: str, args) -> HybridReport:
    report = HybridReport(filepath=filepath)

    # --- PHASE 1: STATIC ANALYSIS ---
    events, _, quality = scan_file_full(filepath)
    report.static_events = events
    report.quality_report = quality

    # Check if we should ABORT dynamic scan
    # Policy: If Static Analysis finds a BAN-level threat (e.g. hard strobe logic),
    # we trust it and skip the expensive render.
    should_render = True
    for e in report.static_events:
        if e.risk_level == RiskLevel.BAN:
            report.final_disposition = "FAIL"
            should_render = False
            break

    # --- PHASE 2: DYNAMIC ANALYSIS ---
    if should_render and args.enable_dynamic:
        events, stats = scan_dynamic(filepath, args.duration, args.fps)
        report.dynamic_events = events
        report.render_stats = stats
        if report.dynamic_events:
            report.final_disposition = "FAIL"

    if report.final_disposition == "PASS" and (
        report.static_events or report.dynamic_events
    ):
        # If we have warnings but no failures
        report.final_disposition = "WARN"

    return report
