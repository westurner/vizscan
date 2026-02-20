# vizscan: Photo-Epilepsy Safety Scanner

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Standard: W3C EARL](https://img.shields.io/badge/Standard-W3C%20EARL-green)](https://www.w3.org/TR/EARL10-Schema/)

vizscan (visualization scanner)
is a specialized analysis tool for
**PES (Photo-Epilepsy Safety)** with
 `projectM` and MilkDrop music visualizations.
It tries to detect patterns, frequencies, and render outputs that pose a high risk of triggering photosensitive seizures.

It utilizes static, taint, and dynamic analysis methods to try to predict risk:

1.  **Static Taint Analysis (AST):** Parses CPU (NSEL) and GPU (Shader) code to detect dangerous logic (e.g., hard strobes, high-frequency math).
2.  **Dynamic Render Analysis:** Simulates the rendering pipeline to detect flash rates exceeding **3 Hz** (Harding FPA standard).

## 📦 Installation

```bash
# Install dependencies
pip install .

# Or for development (includes pytest)
pip install .[dev]
```

## 🚀 Usage

### Basic Scan (Static Only)

Quickly scans files for banned code patterns. Useful for CI/CD pipelines.

```bash
vizscan ./presets/ --recursive
```

### Full Hybrid Scan (Recommended)

Runs static analysis first. If no immediate bans are found, it performs a
simulated render test to check for visual strobing.

```bash
vizscan ./presets/ --enable-dynamic --fps 60 --duration 5
```

### Quality Scoring

In addition to safety checks, PES can analyze the aesthetic quality of presets, such as background brightness and dynamic range.

```bash
vizscan ./presets/ --score-quality
```

This will output:
- **Static Quality:** Background type (Dark/Light/Dynamic) and estimated brightness.
- **Dynamic Quality:** Average luminance, dark/light ratios, and contrast statistics.

### Options

| Option | Description | Default |
| :--- | :--- | :--- |
| `path` | File or directory to scan. | (Required) |
| `-r, --recursive` | Recursively search directories. | False |
| `--enable-dynamic` | Enable the render-based flash detector. | False |
| `--fps <int>` | Simulation framerate for dynamic testing. | 60 |
| `--duration <int>` | Seconds of video to simulate per file. | 5 |
| `-o <file>` | Output path for the JSON-LD report. | hybrid_report.jsonld |
| `--help-scoring` | Print the full rules ontology. | False |
| `--score-quality` | Include quality scoring in output. | False |

## 🛡️ Detection Logic

### 1. Static Analysis (The "Gatekeeper")

We use a custom Abstract Syntax Tree (AST) parser to analyze both NSEL (MilkDrop
math) and GLSL (Shaders). We perform Taint Propagation to track dangerous values (like `time`) as they move through variables.

| Rule ID | Level | Description |
| :--- | :--- | :--- |
| InverterStrobe | BAN | Detects val = 1 - val logic. Creates a guaranteed 30Hz strobe. |
| FrameModulo | CRITICAL | Detects frame % N where N < 4. Creates rapid flickering. |
| TanColor | CRITICAL | Detects tan() driving color variables. Causes infinite-contrast whiteouts. |
| StepFunction | WARNING | Detects step(), fract() on GPU. Creates infinite-contrast hard edges. |
| HighFreqOsc | WARNING | Detects sin(time * N) where N > 18.0 rad/s (> 3 Hz). |

### 2. Dynamic Analysis (The "Validator")

If a preset passes static checks, the Dynamic Engine simulates a render loop
(Mock or Headless ProjectM).

• Algorithm: Harding-Lite Sliding Window.
• Threshold: >10% Luminance change between frames.
• Limit: Max 3 flashes per rolling 1-second window.

## 🔧 Customizing Criteria

### Adding Safety Rules

Safety rules are defined in the `SafetyRegistry` within `vizscan/shader_scanner.py`. To add a new rule, register it using the `REGISTRY.register` method:

```python
REGISTRY.register(
    "MyNewRule",          # Rule ID
    "My Rule Name",       # Human-readable name
    "Description of risk",# Description
    50,                   # Base score (higher = riskier)
    RiskLevel.WARNING     # Risk Level (INFO, WARNING, CRITICAL, BAN)
)
```

Then, implement the detection logic in the `SafetyAnalyzer.visit_*` methods (e.g., `visit_BinaryOp`, `visit_FunctionCall`) to trigger the event:

```python
if condition_met:
    self.events.append(
        REGISTRY.create_event("MyNewRule", "Context info", node.line, [node.target])
    )
```

### Adding Quality Criteria

Quality metrics are handled by the `QualityAnalyzer` class in `vizscan/shader_scanner.py`. To add new criteria:

1.  Modify `QualityReport` dataclass to include the new metric field.
2.  Update `QualityAnalyzer.visit_*` methods to track relevant AST nodes (e.g., specific function calls or variable assignments).
3.  Update `QualityAnalyzer.generate_report()` to calculate the metric based on the collected data.

## 📊 Reporting (JSON-LD / EARL)

The tool generates machine-readable reports compliant with the W3C Evaluation and Report Language (EARL).

Example Output (`hybrid_report.jsonld`):

```json
{
  "@type": "earl:Assertion",
  "earl:subject": { "@id": "file://presets/dangerous.milk" },
  "earl:test": "pes:DynamicStrobe",
  "earl:result": {
    "earl:outcome": "earl:failed",
    "pes:staticErrors": 0,
    "pes:dynamicErrors": 1,
    "dct:description": "Measured 15 flashes/sec (Limit 3)"
  }
}
```

## 🧪 Development & Testing

Run the test suite to verify AST parsing and Taint logic:

```bash
pytest -v
```

## 🤖 GitHub Actions Integration

You can automate safety scanning in your repository using GitHub Actions. This ensures no unsafe presets are merged into your main branch.

0. Copy `run-vizscan.yml` to `.github/workflows/` to automatically scan your `.milk` files.
1. Update the `paths` trigger in the yaml to match your preset folder location (e.g., `presets/**.milk`).
2. The workflow will **fail** if `vizscan` detects any BAN or CRITICAL issues, preventing the merge.
3. A full **EARL JSON-LD report** is uploaded as a workflow artifact for debugging.

**Example YAML Snippet:**
```yaml
- name: Run vizscan
  run: vizscan ./my_presets --recursive --enable-dynamic --output report.jsonld
```

## 📄 License

This project is licensed under the [MIT License](LICENSE).

## ⚠️ Medical Disclaimer & Liability

**This software is NOT a medical device and is NOT intended to be used as a medical therapy.**

`vizscan` is an analysis tool designed to detect visual patterns commonly associated with photosensitive epilepsy triggers (such as Harding FPA guidelines). However, it cannot guarantee safety.

*   **No Warranty of Fitness:** As stated in the MIT License, this software is provided "AS IS", without warranty of any kind, express or implied, including but not limited to the warranties of merchantability or fitness for a particular purpose.
*   **Limitation of Liability:** By using this software, you agree that the authors and copyright holders shall not be liable for any claim, damages, or other liability, whether in an action of contract, tort, or otherwise, arising from, out of, or in connection with the software or the use or other dealings in the software.

This tool may help content creators reduce risk, but it does not replace professional medical advice or certification.

