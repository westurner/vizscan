from dataclasses import dataclass, field
from typing import List, Dict, Optional

from .constants import TOOL_ID, PES_URI
from .static import RiskEvent, QualityReport

@dataclass
class HybridReport:
    filepath: str
    static_events: List[RiskEvent] = field(default_factory=list)
    dynamic_events: List[RiskEvent] = field(default_factory=list)
    final_disposition: str = "PASS"  # PASS, WARN, FAIL
    render_stats: Dict = field(default_factory=dict)
    quality_report: Optional[QualityReport] = None


def generate_earl(reports: List[HybridReport]) -> Dict:
    graph = []

    # Tool Definition
    graph.append(
        {
            "@id": TOOL_ID,
            "@type": ["earl:Software", "earl:Assertor"],
            "dct:title": "PES Hybrid Scanner",
            "dct:hasVersion": "0.0.1",
        }
    )

    for r in reports:
        outcome = "earl:passed" if r.final_disposition == "PASS" else "earl:failed"

        assertion = {
            "@type": "earl:Assertion",
            "earl:assertedBy": TOOL_ID,
            "earl:subject": {"@id": f"file://{r.filepath}"},
            "earl:result": {
                "@type": "earl:TestResult",
                "earl:outcome": outcome,
                "pes:staticErrors": len(r.static_events),
                "pes:dynamicErrors": len(r.dynamic_events),
            },
        }
        graph.append(assertion)

    return {
        "@context": {
            "earl": "http://www.w3.org/ns/earl#",
            "pes": PES_URI,
        }, "@graph": graph}
