import pytest
from vizscan.reports import generate_earl, HybridReport
from vizscan.static import RiskEvent, RiskLevel


def test_generate_earl_pass():
    report = HybridReport(filepath="test.milk", final_disposition="PASS")
    earl = generate_earl([report])

    assert earl["@graph"][0]["@id"] == "urn:uuid:e8b2b7a0-0000-4000-8000-pes-hybrid-v1"
    assert earl["@graph"][1]["earl:result"]["earl:outcome"] == "earl:passed"


def test_generate_earl_fail():
    report = HybridReport(filepath="fail.milk", final_disposition="FAIL")
    report.static_events.append(RiskEvent("rule1", RiskLevel.BAN, 100, "ctx", 1, []))
    earl = generate_earl([report])

    assert earl["@graph"][1]["earl:result"]["earl:outcome"] == "earl:failed"
    assert earl["@graph"][1]["earl:result"]["pes:staticErrors"] == 1
