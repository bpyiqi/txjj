from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.fiber_splicing_analyzer import analyze_profile


def main() -> None:
    output_path = ROOT / "demo_air_blowing" / "output" / "fiber_splicing_evidence.json"
    evidence, metrics = analyze_profile(
        ROOT / "demo_air_blowing" / "fiber_splicing_profile.json", ROOT
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    metrics_path = output_path.with_name("fiber_splicing_metrics.json")
    metrics_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Generated: {output_path}")
    print(f"Samples: {metrics['sample_count']}")
    print(f"Stage accuracy: {metrics['stage_accuracy']:.2%}")


if __name__ == "__main__":
    main()

