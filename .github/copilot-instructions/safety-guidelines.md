# Photo-Epilepsy Safety Guidelines

When writing, reviewing, or documenting code related to photo-epilepsy safety criteria in the `vizscan` codebase, always ensure that the appropriate medical and accessibility guidelines are cited in docstrings, comments, and rule descriptions.

## Relevant Guidelines to Cite

1. **W3C WCAG 2.1 (Guideline 2.3 Seizures and Physical Reactions):** 
   Specifically the "General Flash and Red Flash Thresholds" (no more than 3 general flashes and/or 3 red flashes within any 1-second period).
2. **ITU-R BT.1702:** 
   "Guidance for the reduction of photosensitive epileptic seizures caused by television." Covers flash rates, alternating spatial patterns, and high-contrast transitions.
3. **Harding FPA (Flash and Pattern Analyzer):** 
   The industry-standard algorithm for measuring luminance changes and spatial patterns in video.

## Mapping Criteria to Guidelines

When documenting specific rules, read the implementation of each rule and map it to the appropriate guideline. You can find the implementation of the static rules in `vizscan/static.py` inside the `SafetyAnalyzer.visit` and `SafetyAnalyzer.visit_Assignment` methods. Dynamic rules are implemented in `vizscan/dynamic.py` inside the `FlashDetector.process_frame` method:

- **InverterStrobe (`val = 1 - val`):** This creates a guaranteed 30Hz strobe (at 60fps). Cite **ITU-R BT.1702** regarding rapid alternating light/dark frames exceeding the safe flash threshold.
- **FrameModulo (`frame % N` where N < 4):** Creates rapid flickering. Cite **ITU-R BT.1702** and **WCAG 2.1 General Flash Threshold** (exceeds 3Hz).
- **HighFreqOsc (`sin(freq > 18.0)`):** 18 rad/s is ~2.86 Hz, approaching the 3Hz limit. Cite **WCAG 2.1 General Flash Threshold** and **ITU-R BT.1702**.
- **TanColor (`tan()` on color variables):** Tangent functions approach infinity, causing sudden, extreme high-contrast whiteouts. Cite **ITU-R BT.1702** regarding high-contrast luminance transitions and **WCAG 2.1**.
- **TanMotion (`tan()` on geometry/motion variables):** Causes extreme, sudden spatial jumps. Cite **ITU-R BT.1702** regarding provocative spatial patterns and disorientation.
- **StepFunction (`step`, `fract`, `ceil`, `floor` on time):** Creates instant on/off hard edges in time, leading to infinite-contrast flashes. Cite **ITU-R BT.1702** regarding high-contrast luminance transitions.
- **DynamicStrobe (in `dynamic.py`):** Ensure it references **Harding FPA** and **WCAG 2.1 General Flash Threshold** (> 3 flashes / 6 transitions per second).

## Constraints
- Do NOT change rule IDs, base scores, or risk levels when updating documentation.
- Risk level changes must be justified by cited guidelines.
- Ensure citations are concise and clearly explain the medical/accessibility justification for the rule.
