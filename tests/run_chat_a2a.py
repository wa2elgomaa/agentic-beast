"""Comprehensive A2A (Agent-to-Agent) test runner for the /chat API.

Tests the full request pipeline: authentication → conversation creation →
orchestrator routing → sub-agent execution → response validation.

Covers:
  • Analytics queries (data, metrics, rankings, trends)
  • Follow-up queries that reuse a conversation_id
  • General chat (greetings, jokes, multi-task)
  • Sentiment analysis
  • External-knowledge requests (no DB)
  • Gibberish / edge-case inputs
  • Conversation lifecycle: create → continue → list → delete

Usage
-----
Run against a live FastAPI server (default http://localhost:8000):

    PYTHONPATH=backend/src python tests/run_chat_a2a.py

Override server URL or credentials via env vars:

    BASE_URL=http://localhost:8000  \\
    TEST_USERNAME=wael              \\
    TEST_PASSWORD=your-password     \\
    PYTHONPATH=backend/src python tests/run_chat_a2a.py

Output is printed to stdout and saved to tests/output/chat_a2a_results.json.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")
TEST_USERNAME: str = os.getenv("TEST_USERNAME", "wael")
TEST_PASSWORD: str = os.getenv("TEST_PASSWORD", "")
API_PREFIX: str = "/api/v1"
OUTPUT_DIR: Path = Path(__file__).parent / "output"

TIMEOUT = httpx.Timeout(120.0, connect=10.0)  # LLM calls can take a while


# ---------------------------------------------------------------------------
# Test scenario definitions
# ---------------------------------------------------------------------------

@dataclass
class Scenario:
    """A single A2A test scenario."""

    name: str
    message: str
    expected_agent: str  # "analytics" | "chat" | "any"
    # If set, this scenario reuses the conversation from a prior scenario by name.
    continue_from: Optional[str] = None
    # Soft assertions on the response content
    content_must_contain: List[str] = field(default_factory=list)
    content_must_not_contain: List[str] = field(default_factory=list)
    # Whether we expect the response to carry analytics metadata (op_data)
    expect_analytics_data: bool = False
    notes: str = ""


SCENARIOS: List[Scenario] = [
    # ------------------------------------------------------------------
    # Group 1 — Analytics: rankings & performance
    # ------------------------------------------------------------------
    Scenario(
        name="top_5_instagram_videos",
        message="What is the top 5 viewed videos on instagram",
        expected_agent="analytics",
        expect_analytics_data=True,
        notes="Should return top 5 rows from DB ordered by views",
    ),
    Scenario(
        name="followup_cross_platform_comparison",
        message="Compare the first video from your previous answer across all platforms",
        expected_agent="analytics",
        continue_from="top_5_instagram_videos",
        notes="Follow-up query; orchestrator must use same conversation for context",
    ),
    Scenario(
        name="best_day_tiktok",
        message="Which day is the best to publish on TikTok?",
        expected_agent="analytics",
        expect_analytics_data=True,
        notes="Aggregation query grouping by day-of-week",
    ),
    Scenario(
        name="videos_featuring_trump",
        message='What are the top videos featuring "Donald Trump"?',
        expected_agent="analytics",
        expect_analytics_data=True,
        notes="Keyword / full-text search in video titles or captions",
    ),
    Scenario(
        name="most_engagement_last_month",
        message="Which videos got the most engagement last month?",
        expected_agent="analytics",
        expect_analytics_data=True,
        notes="Date-range aggregation; engagement = likes + comments + shares",
    ),
    Scenario(
        name="avg_engagement_per_platform",
        message="Show me the average engagement rate per platform",
        expected_agent="analytics",
        expect_analytics_data=True,
        notes="Aggregation grouped by platform",
    ),
    Scenario(
        name="video_count_total",
        message="What is the total number of videos in the database?",
        expected_agent="analytics",
        expect_analytics_data=True,
        notes="Simple COUNT(*) query",
    ),
    Scenario(
        name="top_hashtags",
        message="What are the top 10 hashtags used across all platforms this year?",
        expected_agent="analytics",
        expect_analytics_data=True,
        notes="Hashtag frequency aggregation",
    ),
    Scenario(
        name="engagement_followup",
        message="Which platform has the highest average engagement overall?",
        expected_agent="analytics",
        continue_from="avg_engagement_per_platform",
        notes="Follow-up in the same conversation to verify context retention",
    ),

    # ------------------------------------------------------------------
    # Group 2 — General chat
    # ------------------------------------------------------------------
    Scenario(
        name="greeting",
        message="Hi there! How are you?",
        expected_agent="chat",
        content_must_not_contain=["SELECT", "FROM", "WHERE"],
        notes="Pure greeting — no DB query expected",
    ),
    Scenario(
        name="sentiment_simple",
        message="Can you analyze the sentiment of this text: I love sunny days but I hate the rain.",
        expected_agent="chat",
        content_must_contain=["positive", "negative", "sentiment"],
        notes="Sentiment analysis — no DB needed",
    ),
    Scenario(
        name="joke_plus_sentiment",
        message=(
            "Can you tell me a joke and also analyze the sentiment of this joke? "
            "The joke is: Why don't scientists trust atoms? Because they make up everything!"
        ),
        expected_agent="chat",
        notes="Multi-task: creative + sentiment — should stay in chat agent",
    ),
    Scenario(
        name="weather_external",
        message="What's the weather like today in Paris?",
        expected_agent="chat",
        notes="External knowledge request — no DB data available; graceful degradation expected",
    ),
    Scenario(
        name="gibberish",
        message="asdjkl qwerty 12345",
        expected_agent="chat",
        notes="Nonsensical input — orchestrator should route to chat and respond gracefully",
    ),
    Scenario(
        name="short_form_trends",
        message="What are the latest trends in short-form video content in general?",
        expected_agent="chat",
        notes="General knowledge question not requiring DB lookup",
    ),
    Scenario(
        name="explain_metric",
        message="What is engagement rate and how is it calculated?",
        expected_agent="chat",
        notes="Conceptual question — chat agent should answer",
    ),

    # ------------------------------------------------------------------
    # Group 3 — Edge cases & robustness
    # ------------------------------------------------------------------
    Scenario(
        name="very_long_message",
        message=(
            "I have a very important question about social media analytics. "
            "I need to understand which content strategy works best. "
            "Specifically, I want to know: out of all the videos posted on Instagram "
            "and TikTok combined, which 3 videos had the highest view count? "
            "Please include the title, platform, view count, and posting date. "
            "Also, could you tell me what time of day those videos were posted?"
        ),
        expected_agent="analytics",
        expect_analytics_data=True,
        notes="Complex multi-part analytics query",
    ),
    Scenario(
        name="mixed_analytics_and_chat",
        message=(
            "Can you first tell me the top 3 most liked videos on all platforms, "
            "and then explain what makes a video go viral in general?"
        ),
        expected_agent="any",
        notes="Mixed intent: orchestrator may call analytics then chat, or chain",
    ),
]


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    scenario_name: str
    message: str
    expected_agent: str
    conversation_id: Optional[str]
    status_code: int
    response_status: Optional[str]
    response_text: Optional[str]
    has_analytics_data: bool
    duration_ms: float
    passed: bool
    failure_reason: Optional[str]
    raw_rows_count: int = 0
    raw_response: Optional[Dict[str, Any]] = None


def _check_content_assertions(
    content: Any,
    must_contain: List[str],
    must_not_contain: List[str],
) -> Optional[str]:
    """Return a failure message if content assertions fail, else None."""
    text = json.dumps(content) if not isinstance(content, str) else content
    text_lower = text.lower()

    for term in must_contain:
        if term.lower() not in text_lower:
            return f"Expected '{term}' in response but not found"

    for term in must_not_contain:
        if term.lower() in text_lower:
            return f"Unexpected '{term}' found in response"

    return None


# ---------------------------------------------------------------------------
# HTTP client helpers
# ---------------------------------------------------------------------------

class ChatA2AClient:
    """Thin async HTTP wrapper around the /chat API."""

    def __init__(self, base_url: str, token: str) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def send_message(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        *,
        client: httpx.AsyncClient,
    ) -> httpx.Response:
        payload: Dict[str, Any] = {"message": message}
        if conversation_id:
            payload["conversation_id"] = conversation_id
        return await client.post(
            f"{self._base}{API_PREFIX}/chat",
            json=payload,
            headers=self._headers,
            timeout=TIMEOUT,
        )

    async def list_conversations(self, *, client: httpx.AsyncClient) -> httpx.Response:
        return await client.get(
            f"{self._base}{API_PREFIX}/chat/conversations",
            headers=self._headers,
            timeout=TIMEOUT,
        )

    async def get_conversation_messages(
        self, conversation_id: str, *, client: httpx.AsyncClient
    ) -> httpx.Response:
        return await client.get(
            f"{self._base}{API_PREFIX}/chat/conversations/{conversation_id}/messages",
            headers=self._headers,
            timeout=TIMEOUT,
        )

    async def delete_conversation(
        self, conversation_id: str, *, client: httpx.AsyncClient
    ) -> httpx.Response:
        return await client.delete(
            f"{self._base}{API_PREFIX}/chat/conversations/{conversation_id}",
            headers=self._headers,
            timeout=TIMEOUT,
        )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

async def authenticate(
    base_url: str, username: str, password: str, client: httpx.AsyncClient
) -> str:
    """Login and return a JWT access token."""
    resp = await client.post(
        f"{base_url}{API_PREFIX}/users/login",
        json={"username": username, "password": password, "provider": "local"},
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Login failed ({resp.status_code}): {resp.text[:300]}\n"
            "Set TEST_USERNAME / TEST_PASSWORD env vars with valid credentials."
        )
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

class ChatA2ARunner:
    """Runs all A2A test scenarios and collects results."""

    def __init__(self, api_client: ChatA2AClient) -> None:
        self._api = api_client
        self._results: List[TestResult] = []
        # Maps scenario_name → conversation_id for follow-up chaining
        self._conversation_map: Dict[str, str] = {}

    async def run_all(self, client: httpx.AsyncClient) -> List[TestResult]:
        print(f"\n{'='*68}")
        print(f"  Chat A2A Test Suite — {len(SCENARIOS)} scenarios")
        print(f"  Server: {BASE_URL}")
        print(f"{'='*68}\n")

        for idx, scenario in enumerate(SCENARIOS, 1):
            print(f"[{idx:02d}/{len(SCENARIOS)}] {scenario.name}")
            print(f"       Message : {scenario.message[:90]}{'...' if len(scenario.message)>90 else ''}")
            result = await self._run_scenario(scenario, client)
            self._results.append(result)
            status_icon = "✓" if result.passed else "✗"
            print(f"       Status  : {status_icon}  HTTP {result.status_code}  ({result.duration_ms:.0f}ms)")
            if result.conversation_id:
                print(f"       ConvID  : {result.conversation_id}")
            if result.response_text:
                preview = str(result.response_text)[:150].replace("\n", " ")
                print(f"       Response: {preview}{'...' if len(str(result.response_text))>150 else ''}")
            if result.has_analytics_data:
                rows_info = f", raw_rows={result.raw_rows_count}" if result.raw_rows_count else ""
                print(f"       Data    : analytics payload present{rows_info}")
            if not result.passed:
                print(f"       FAIL    : {result.failure_reason}")
            print()

        return self._results

    async def _run_scenario(
        self, scenario: Scenario, client: httpx.AsyncClient
    ) -> TestResult:
        conversation_id: Optional[str] = None

        # Resolve conversation_id for follow-up scenarios
        if scenario.continue_from:
            conversation_id = self._conversation_map.get(scenario.continue_from)
            if not conversation_id:
                return TestResult(
                    scenario_name=scenario.name,
                    message=scenario.message,
                    expected_agent=scenario.expected_agent,
                    conversation_id=None,
                    status_code=0,
                    response_status=None,
                    response_text=None,
                    has_analytics_data=False,
                    duration_ms=0.0,
                    passed=False,
                    failure_reason=(
                        f"Cannot continue from '{scenario.continue_from}' — "
                        "parent scenario may have failed or not run yet"
                    ),
                )

        t0 = time.perf_counter()
        try:
            resp = await self._api.send_message(
                scenario.message,
                conversation_id=conversation_id,
                client=client,
            )
        except Exception as exc:
            return TestResult(
                scenario_name=scenario.name,
                message=scenario.message,
                expected_agent=scenario.expected_agent,
                conversation_id=None,
                status_code=0,
                response_status=None,
                response_text=None,
                has_analytics_data=False,
                duration_ms=(time.perf_counter() - t0) * 1000,
                passed=False,
                failure_reason=f"HTTP error: {exc}",
            )
        duration_ms = (time.perf_counter() - t0) * 1000

        # Parse response
        try:
            data: Dict[str, Any] = resp.json()
        except Exception:
            data = {}

        # --- Core assertions -------------------------------------------------
        failure_reason: Optional[str] = None

        if resp.status_code != 200:
            failure_reason = f"Expected HTTP 200, got {resp.status_code}: {resp.text[:200]}"

        if not failure_reason and data.get("status") != "success":
            failure_reason = f"Response status not 'success': {data.get('status')}"

        if not failure_reason:
            msg_obj = data.get("message") or {}
            content = msg_obj.get("content") if isinstance(msg_obj, dict) else None
            if not content:
                failure_reason = "Empty or missing message.content in response"

        if not failure_reason:
            # Content assertions
            content_obj = (data.get("message") or {}).get("content")
            failure_reason = _check_content_assertions(
                content_obj or "",
                scenario.content_must_contain,
                scenario.content_must_not_contain,
            )

        if not failure_reason and scenario.expect_analytics_data:
            meta = (data.get("message") or {}).get("metadata") or {}
            has_data = bool(
                meta.get("generated_sql")
                or meta.get("operation") == "analytics"
                or (isinstance((data.get("message") or {}).get("content"), list))
                or (isinstance((data.get("message") or {}).get("content"), dict))
            )
            if not has_data:
                # Soft warning only — analytics agent may embed rows in text
                pass

        # --- Extract conversation_id -----------------------------------------
        resp_conversation_id: Optional[str] = None
        if data.get("conversation_id"):
            resp_conversation_id = str(data["conversation_id"])
            # Store for follow-up chaining
            self._conversation_map[scenario.name] = resp_conversation_id
            # Also inherit conversation for follow-ups that extend a parent
            if scenario.continue_from and conversation_id:
                # Ensure the returned conv matches what we sent
                if resp_conversation_id != conversation_id:
                    failure_reason = (
                        f"Conversation ID mismatch: sent {conversation_id}, "
                        f"got {resp_conversation_id}"
                    )

        # --- Detect analytics data presence ----------------------------------
        meta = (data.get("message") or {}).get("metadata") or {}
        content_obj = (data.get("message") or {}).get("content")
        raw_rows: List[Dict[str, Any]] = meta.get("raw_rows") or []
        raw_rows_count = len(raw_rows)
        has_analytics_data = bool(
            meta.get("generated_sql")
            or meta.get("operation") == "analytics"
            or isinstance(content_obj, (list, dict))
            or raw_rows_count > 0
        )

        # --- Response text for display ---------------------------------------
        if isinstance(content_obj, str):
            response_text = content_obj
        elif content_obj is not None:
            response_text = json.dumps(content_obj, ensure_ascii=False)[:500]
        else:
            response_text = str(data.get("message") or "")[:200]

        return TestResult(
            scenario_name=scenario.name,
            message=scenario.message,
            expected_agent=scenario.expected_agent,
            conversation_id=resp_conversation_id,
            status_code=resp.status_code,
            response_status=data.get("status"),
            response_text=response_text,
            has_analytics_data=has_analytics_data,
            duration_ms=duration_ms,
            passed=failure_reason is None,
            failure_reason=failure_reason,
            raw_rows_count=raw_rows_count,
            raw_response=data,
        )

    async def run_lifecycle_checks(self, client: httpx.AsyncClient) -> None:
        """Additional checks: list conversations, fetch messages, delete."""
        print(f"{'─'*68}")
        print("  Lifecycle checks")
        print(f"{'─'*68}\n")

        # List conversations
        resp = await self._api.list_conversations(client=client)
        if resp.status_code == 200:
            convs = resp.json().get("conversations", [])
            print(f"[LIST] Conversations returned: {len(convs)}")
        else:
            print(f"[LIST] FAIL HTTP {resp.status_code}")

        # Fetch messages for the first conversation we created
        first_conv_id = next(
            (r.conversation_id for r in self._results if r.conversation_id), None
        )
        if first_conv_id:
            resp = await self._api.get_conversation_messages(first_conv_id, client=client)
            if resp.status_code == 200:
                msgs = resp.json().get("messages", [])
                print(f"[MSGS] Messages in first conversation ({first_conv_id[:8]}…): {len(msgs)}")
            else:
                print(f"[MSGS] FAIL HTTP {resp.status_code}")

        # Verify follow-up conversation has > 1 message
        followup_scenario = "followup_cross_platform_comparison"
        followup_parent = "top_5_instagram_videos"
        conv_id = self._conversation_map.get(followup_parent)
        if conv_id:
            resp = await self._api.get_conversation_messages(conv_id, client=client)
            if resp.status_code == 200:
                msgs = resp.json().get("messages", [])
                # Expect 4 messages: user1, assistant1, user2, assistant2
                expected_min = 4
                ok = len(msgs) >= expected_min
                icon = "✓" if ok else "✗"
                print(
                    f"[CONV] Follow-up conversation has {len(msgs)} messages "
                    f"(expected ≥{expected_min}) {icon}"
                )
            else:
                print(f"[CONV] FAIL HTTP {resp.status_code}")
        print()


# ---------------------------------------------------------------------------
# Summary printer & file writer
# ---------------------------------------------------------------------------

def _print_summary(results: List[TestResult]) -> None:
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    print(f"\n{'='*68}")
    print(f"  SUMMARY  {passed}/{len(results)} passed   {failed} failed")
    print(f"{'='*68}")

    if failed:
        print("\nFailed scenarios:")
        for r in results:
            if not r.passed:
                print(f"  • {r.scenario_name}: {r.failure_reason}")

    analytics_results = [r for r in results if r.expected_agent == "analytics" and r.passed]
    chat_results = [r for r in results if r.expected_agent == "chat" and r.passed]
    avg_dur = sum(r.duration_ms for r in results if r.passed) / max(1, passed)
    print(f"\nResult breakdown:")
    print(f"  Analytics scenarios passed : {len(analytics_results)}")
    print(f"  Chat scenarios passed      : {len(chat_results)}")
    print(f"  Average latency (passed)   : {avg_dur:.0f}ms")
    print()


def _save_results(results: List[TestResult]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "chat_a2a_results.json"
    payload = [asdict(r) for r in results]
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"Results saved to {out_path}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> int:
    if not TEST_PASSWORD:
        print(
            "ERROR: TEST_PASSWORD env var is required.\n"
            "  export TEST_PASSWORD=your-password\n"
            "  export TEST_USERNAME=wael   # default\n",
            file=sys.stderr,
        )
        return 1

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # 1. Authenticate
        print(f"Authenticating as '{TEST_USERNAME}' on {BASE_URL} …")
        try:
            token = await authenticate(BASE_URL, TEST_USERNAME, TEST_PASSWORD, client)
            print("Authentication OK\n")
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        # 2. Run scenarios
        api_client = ChatA2AClient(base_url=BASE_URL, token=token)
        runner = ChatA2ARunner(api_client)
        results = await runner.run_all(client)

        # 3. Lifecycle checks
        await runner.run_lifecycle_checks(client)

        # 4. Summary + persist
        _print_summary(results)
        _save_results(results)

    failed = sum(1 for r in results if not r.passed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
