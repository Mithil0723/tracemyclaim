from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.agents.extractor import extract_claims
from backend.orchestrator import run_verifier_fanout
from shared.schemas import ClaimExtractorInput, ClaimExtractorSuccess, VerifierError, VerifierSuccess


def _print_result(claim_id: str, result: VerifierSuccess | VerifierError, duration: float) -> None:
    verdict = result.data.verdict if isinstance(result, VerifierSuccess) else "error"
    print(f"{claim_id}: {verdict} ({duration:.2f}s)")


async def run_harness() -> None:
    article_path = ROOT / "fixtures" / "articles" / "article_001.txt"
    payload = ClaimExtractorInput(
        article_id="article-001",
        text=article_path.read_text(encoding="utf-8"),
        source_url="local-fixture",
    )

    extractor_result = extract_claims(payload)
    if not isinstance(extractor_result, ClaimExtractorSuccess):
        print(extractor_result.model_dump_json(indent=2))
        return

    results = await run_verifier_fanout(extractor_result, on_result=_print_result)

    supported = sum(
        1 for result in results if isinstance(result, VerifierSuccess) and result.data.verdict == "supported"
    )
    contested = sum(
        1 for result in results if isinstance(result, VerifierSuccess) and result.data.verdict == "contested"
    )
    unsupported = sum(
        1 for result in results if isinstance(result, VerifierSuccess) and result.data.verdict == "unsupported"
    )
    errors = sum(1 for result in results if isinstance(result, VerifierError))

    print(
        "Summary: "
        f"total claims={len(results)}, "
        f"supported={supported}, "
        f"contested={contested}, "
        f"unsupported={unsupported}, "
        f"errors={errors}"
    )


def test_orchestrator_harness() -> None:
    asyncio.run(run_harness())


if __name__ == "__main__":
    asyncio.run(run_harness())
