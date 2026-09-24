"""Thin async client for TypeSafe's System One endpoint (model Jev).

POST {TYPESAFE_BASE_URL}/v1/systemone  with  {"model", "state", "questions"}.
Answers: noul -> {"noul"}, choice -> {"choice","confidence","probabilities"},
score -> {"score","confidence","legend","probabilities"}.
Docs: https://docs.typesafe.ai/api.md
"""
import asyncio
import time

import httpx
from django.conf import settings

RETRYABLE = {429, 529}


class JevError(Exception):
    """Any failure talking to Jev: timeout, HTTP error, or malformed answer."""


async def system_one(client: httpx.AsyncClient, state, questions: dict, timeout: float | None = None) -> dict:
    if not settings.TYPESAFE_API_KEY:
        raise JevError("TYPESAFE_API_KEY is not set")
    timeout = timeout or settings.JEV_TIMEOUT_SECONDS
    body = {"model": settings.JEV_MODEL, "state": state, "questions": questions}
    headers = {"Authorization": f"Bearer {settings.TYPESAFE_API_KEY}"}
    url = f"{settings.TYPESAFE_BASE_URL.rstrip('/')}/v1/systemone"
    for attempt in range(2):
        started = time.perf_counter()
        try:
            resp = await client.post(url, json=body, headers=headers, timeout=timeout)
        except httpx.TimeoutException as exc:
            raise JevError(f"Jev timed out after {timeout:.1f}s") from exc
        except httpx.HTTPError as exc:
            raise JevError(f"Jev connection error: {exc}") from exc
        if resp.status_code in RETRYABLE and attempt == 0:
            await asyncio.sleep(0.25)
            continue
        if resp.status_code != 200:
            raise JevError(f"Jev HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        if "answers" not in data:
            raise JevError("Jev response has no 'answers'")
        data["_latency_ms"] = int((time.perf_counter() - started) * 1000)
        data["_request_id"] = resp.headers.get("x-typesafe-request-id")
        return data
    raise JevError("Jev rate-limited twice")


async def _run_many(state, question_sets: dict[str, dict]) -> dict[str, dict | JevError]:
    names = [name for name, qs in question_sets.items() if qs]
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *(system_one(client, state, question_sets[n]) for n in names), return_exceptions=True
        )
    out = {}
    for name, res in zip(names, results):
        out[name] = res if isinstance(res, (dict, JevError)) else JevError(repr(res))
    return out


def evaluate_concurrently(state, question_sets: dict[str, dict]) -> dict[str, dict | JevError]:
    """Send each named question set as its own Jev request, all at the same time.

    Returns {name: response_dict or JevError}. Empty question sets are skipped.
    """
    return asyncio.run(_run_many(state, question_sets))
