from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from backend.agents.verifier import verify_claim
from backend.utils.logging import get_logger
from shared.schemas import ClaimExtractorSuccess, VerifierError, VerifierInput, VerifierSuccess

logger = get_logger(__name__)

VerifierResult = VerifierSuccess | VerifierError
VerifierResultCallback = Callable[[str, VerifierResult, float], None]
VERIFIER_TIMEOUT_SECONDS = 15


async def run_verifier_fanout(
    extractor_output: ClaimExtractorSuccess,
    on_result: VerifierResultCallback | None = None,
) -> list[VerifierResult]:
    claims = extractor_output.data.claims
    logger.info("Dispatching verifier fan-out for claims=%s", len(claims))

    tasks = [
        asyncio.create_task(_run_single_verifier(claim.claim_id, claim.text, claim.topic_tags, on_result))
        for claim in claims
    ]
    entries = await asyncio.gather(*tasks)

    completed = sum(1 for _, result, _ in entries if isinstance(result, VerifierSuccess))
    failed = len(entries) - completed
    logger.info(
        "Verifier fan-out completed dispatched=%s completed=%s failed=%s",
        len(claims),
        completed,
        failed,
    )

    return [result for _, result, _ in entries]


async def _run_single_verifier(
    claim_id: str,
    claim_text: str,
    topic_tags: list[str],
    on_result: VerifierResultCallback | None,
) -> tuple[str, VerifierResult, float]:
    started_at = time.perf_counter()
    payload = VerifierInput(
        claim_id=claim_id,
        claim_text=claim_text,
        topic_tags=topic_tags,
    )

    try:
        result: VerifierResult = await asyncio.wait_for(
            verify_claim(payload),
            timeout=VERIFIER_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("Verifier timed out for claim_id=%s", claim_id)
        result = VerifierError(
            status="error",
            error_code="TIMEOUT",
            message=f"Verifier timed out for claim_id={claim_id}.",
        )
    except Exception as exc:
        logger.exception("Verifier failed for claim_id=%s", claim_id)
        result = VerifierError(
            status="error",
            error_code="UPSTREAM",
            message=f"Verifier failed for claim_id={claim_id}: {exc}",
        )

    duration = time.perf_counter() - started_at
    if on_result is not None:
        on_result(claim_id, result, duration)

    return claim_id, result, duration
