from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.agents.extractor import extract_claims
from shared.schemas import ClaimExtractorInput


SHORT_ARTICLE = """
The city council met on Tuesday evening to discuss a proposed redesign of the
central bus depot. Officials said the project would add covered waiting areas,
improve lighting, and repaint the exterior walls. Several residents spoke
during public comment and raised concerns about noise and traffic near nearby
apartments. A transit manager said the depot currently serves six routes each
weekday and handles roughly 2,000 passenger boardings. The council did not
vote on the proposal and scheduled a follow-up meeting for next month.
""".strip()


def run_harness() -> None:
    payload = ClaimExtractorInput(
        article_id="test-article-1",
        text=SHORT_ARTICLE,
        source_url="https://example.com/article",
    )
    result = extract_claims(payload)
    print(result.model_dump_json(indent=2))


def test_extractor_harness() -> None:
    run_harness()


if __name__ == "__main__":
    run_harness()
