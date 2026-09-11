from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.air_blowing_analyzer import analyze_profiles


def main() -> None:
    profile_path = PROJECT_ROOT / "demo_air_blowing" / "video_profiles.json"
    output_path = PROJECT_ROOT / "demo_air_blowing" / "output" / "construction_evidence.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = analyze_profiles(profile_path, PROJECT_ROOT)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated: {output_path}")
    print(f"Videos: {result['summary']['video_count']}")
    print(f"Samples: {result['summary']['sample_count']}")
    print(f"Stage accuracy: {result['summary']['stage_accuracy']:.2%}")


if __name__ == "__main__":
    main()

