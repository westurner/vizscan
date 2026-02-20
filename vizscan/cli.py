"""
vizscan.cli
"""
import os
import sys
import json
import argparse
from typing import List

# --- IMPORTS ---
from .static import REGISTRY
from .dynamic import run_hybrid_scan
from .reports import generate_earl, HybridReport


def main():
    parser = argparse.ArgumentParser(
        description="Hybrid Static/Dynamic Epilepsy Scanner"
    )
    parser.add_argument("path", nargs="?", help="File or directory to scan")
    parser.add_argument(
        "--enable-dynamic", action="store_true", help="Enable rendering test"
    )
    parser.add_argument(
        "--duration", type=int, default=5, help="Render duration in seconds"
    )
    parser.add_argument("--fps", type=int, default=60, help="Simulation FPS")
    parser.add_argument("-o", "--output", default="hybrid_report.jsonld")
    parser.add_argument(
        "--recursive", action="store_true", help="Recursively scan directories"
    )
    parser.add_argument(
        "--help-scoring", action="store_true", help="Print the full rules ontology."
    )
    parser.add_argument(
        "--score-quality", action="store_true", help="Include quality scoring in output"
    )

    args = parser.parse_args()

    if args.help_scoring:
        print(json.dumps(REGISTRY.export_ontology(), indent=2))
        sys.exit(0)

    if not args.path:
        parser.print_help()
        sys.exit(1)

    # Collect files
    files_to_scan = []
    if os.path.isfile(args.path):
        files_to_scan.append(args.path)
    elif os.path.isdir(args.path):
        if args.recursive:
            for root, _, files in os.walk(args.path):
                for f in files:
                    if f.endswith((".milk", ".json")):  # Basic filter
                        files_to_scan.append(os.path.join(root, f))
        else:
            for f in os.listdir(args.path):
                full_p = os.path.join(args.path, f)
                if os.path.isfile(full_p) and f.endswith((".milk", ".json")):
                    files_to_scan.append(full_p)

    print(f"Scanning {len(files_to_scan)} files...")

    reports: List[HybridReport] = []
    for f in files_to_scan:
        try:
            rep = run_hybrid_scan(f, args)
            reports.append(rep)
            print(f"[{rep.final_disposition}] {os.path.basename(f)}")
            if args.score_quality and rep.quality_report:
                print(f"  Quality (Static): {rep.quality_report.background_type}")
        except Exception as e:
            print(f"  -> ERROR: {e}")

    # Generate Output
    earl_report = generate_earl(reports)
    with open(args.output, "w") as f:
        json.dump(earl_report, f, indent=2)

    print(f"\nReport written to {args.output}")

    # Exit code based on failures
    if any(r.final_disposition == "FAIL" for r in reports):
        sys.exit(1)


if __name__ == "__main__":
    main()
