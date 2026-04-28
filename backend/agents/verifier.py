from __future__ import annotations

import asyncio
import random

from backend.utils.logging import get_logger
from shared.schemas import VerificationSource, VerifierData, VerifierInput, VerifierSuccess

logger = get_logger(__name__)


async def verify_claim(payload: VerifierInput) -> VerifierSuccess:
    logger.info("Verifier started for claim_id=%s", payload.claim_id)

    delay = random.uniform(0.5, 3.0)
    await asyncio.sleep(delay)

    result = VerifierSuccess(
        status="ok",
        data=VerifierData(
            claim_id=payload.claim_id,
            verdict="supported",
            confidence=0.85,
            sources=[
                VerificationSource(
                    url="https://stub.example.com",
                    title="Stub Source",
                    evidence_quote="Stub evidence.",
                    supports=True,
                )
            ],
            reasoning="Stub verifier - real logic not yet implemented.",
        ),
    )

    logger.info("Verifier completed for claim_id=%s duration=%.2fs", payload.claim_id, delay)
    return result
