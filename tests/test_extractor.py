from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.agents.extractor import extract_claims
from shared.schemas import ClaimExtractorInput

def run_harness() -> None:
    article_path = ROOT / "fixtures" / "articles" / "article_001.txt"
    payload = ClaimExtractorInput(
        article_id="article-001",
        text=article_path.read_text(encoding="utf-8"),
        source_url="local-fixture",
    )
    result = extract_claims(payload)
    print(result.model_dump_json(indent=2))


def test_extractor_harness() -> None:
    run_harness()


if __name__ == "__main__":
    run_harness()
