from __future__ import annotations

import json
import os
import re
from collections.abc import Sequence
from pathlib import Path

from backend.utils.logging import get_logger
from backend.utils.prompts import EXTRACTOR_SYSTEM_PROMPT
from shared.schemas import (
    ClaimExtractorData,
    ClaimExtractorError,
    ClaimExtractorInput,
    ClaimExtractorSuccess,
    ExtractedClaim,
)

logger = get_logger(__name__)

MODEL_NAME = "gpt-4o"
MAX_CLAIMS = 25
MIN_WORD_COUNT = 200
MAX_TEXT_CHARS = 50_000

CONTEXT_DEPENDENT_PATTERN = re.compile(
    r"\b(this|that|these|those|they|them|their|the author)\b",
    re.IGNORECASE,
)
SUBJECTIVE_OR_PREDICTIVE_PATTERN = re.compile(
    r"\b("
    r"should|shouldn't|must|ought|best|worst|good|bad|better|worse|"
    r"believe|think|feel|seem|appears?|probably|likely|unlikely|may|might|"
    r"could|would|will|going to|expect|predict|forecast|hope|fear"
    r")\b",
    re.IGNORECASE,
)
MULTI_CLAUSE_PATTERN = re.compile(
    r"(;)|\b(because|therefore|however|although|while|whereas)\b",
    re.IGNORECASE,
)
WORD_PATTERN = re.compile(r"\b[\w'-]+\b")


def extract_claims(
    payload: ClaimExtractorInput,
) -> ClaimExtractorSuccess | ClaimExtractorError:
    word_count = _count_words(payload.text)
    logger.info("Extractor started for article_id=%s words=%s", payload.article_id, word_count)

    if word_count < MIN_WORD_COUNT:
        logger.info("Extractor rejected article_id=%s for insufficient text", payload.article_id)
        return ClaimExtractorError(
            status="error",
            error_code="INSUFFICIENT_TEXT",
            message=f"Article must contain at least {MIN_WORD_COUNT} words.",
        )

    prompt = _build_user_prompt(payload)
    try:
        raw_response = _call_openai(prompt)
        extracted = _parse_claims_response(raw_response)
    except Exception as exc:
        logger.exception("Extractor upstream failure for article_id=%s", payload.article_id)
        return ClaimExtractorError(
            status="error",
            error_code="UPSTREAM",
            message=str(exc),
        )

    filtered_claims = _enforce_claim_rules(extracted.data.claims, payload.article_id)

    logger.info(
        "Extractor completed for article_id=%s raw_claims=%s kept_claims=%s",
        payload.article_id,
        len(extracted.data.claims),
        len(filtered_claims),
    )

    return ClaimExtractorSuccess(
        status="ok",
        data=ClaimExtractorData(claims=filtered_claims),
    )


def _count_words(text: str) -> int:
    return len(WORD_PATTERN.findall(text))


def _build_user_prompt(payload: ClaimExtractorInput) -> str:
    trimmed_text = payload.text[:MAX_TEXT_CHARS]
    source_url = payload.source_url or "None"
    return (
        f"article_id: {payload.article_id}\n"
        f"source_url: {source_url}\n"
        f"article_text:\n{trimmed_text}"
    )


def _call_openai(user_prompt: str) -> str:
    _load_env_file()

    try:
        from openai import OpenAI
    except ImportError as exc:
        logger.exception("OpenAI SDK is not installed")
        raise RuntimeError("OpenAI SDK is not installed.") from exc

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": EXTRACTOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("OpenAI returned an empty response.")

    return content


def _parse_claims_response(raw_response: str) -> ClaimExtractorSuccess:
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        logger.exception("Extractor response was not valid JSON")
        raise RuntimeError("Extractor response was not valid JSON.") from exc

    return ClaimExtractorSuccess.model_validate(payload)


def _enforce_claim_rules(
    claims: Sequence[ExtractedClaim],
    article_id: str,
) -> list[ExtractedClaim]:
    normalized: list[ExtractedClaim] = []

    for index, claim in enumerate(claims, start=1):
        if not _is_verifiable(claim.text):
            continue
        if not _is_decontextualized(claim.text):
            continue
        if not _is_atomic(claim.text):
            continue

        normalized.append(
            ExtractedClaim(
                claim_id=claim.claim_id or f"{article_id}-claim-{index}",
                text=claim.text.strip(),
                original_quote=claim.original_quote.strip(),
                importance=_clamp_score(claim.importance),
                controversy=_clamp_score(claim.controversy),
                topic_tags=[tag.strip() for tag in claim.topic_tags if tag.strip()],
            )
        )

    normalized.sort(key=lambda item: item.importance, reverse=True)
    return normalized[:MAX_CLAIMS]


def _load_env_file() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if os.getenv("OPENAI_API_KEY") or not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()

        value = value.strip()
        if " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        value = value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value


def _is_verifiable(text: str) -> bool:
    return not SUBJECTIVE_OR_PREDICTIVE_PATTERN.search(text)


def _is_decontextualized(text: str) -> bool:
    return not CONTEXT_DEPENDENT_PATTERN.search(text)


def _is_atomic(text: str) -> bool:
    return not MULTI_CLAUSE_PATTERN.search(text)


def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
