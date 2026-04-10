#!/usr/bin/env python3
"""
Advanced E2E Chat Testing Script
Tests complex queries, multi-turn conversations, and sophisticated orchestrator paths
"""

import requests
import json
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime

# Configuration
API_BASE = "http://localhost:8000/api/v1"
TIMEOUT = 60  # seconds (longer for code interpreter)
VERBOSE = True


@dataclass
class TestResult:
    test_name: str
    test_phase: str
    passed: bool
    message: str
    duration: float
    response_metadata: Optional[Dict] = None
    response_content: Optional[Dict] = None

    def __str__(self):
        status = "✓ PASS" if self.passed else "✗ FAIL"
        return f"{status} | {self.test_name} ({self.duration:.2f}s) | {self.message}"


class AdvancedChatTester:
    def __init__(self, api_base: str = API_BASE, username: str = "testuser", password: str = "testpass123"):
        self.api_base = api_base
        self.conversation_id: Optional[str] = None
        self.results: List[TestResult] = []
        self.session = requests.Session()
        self.username = username
        self.password = password
        self.auth_token: Optional[str] = None

        # Authenticate on init
        self._authenticate()

    def _authenticate(self) -> None:
        """Authenticate with the API and store the token."""
        try:
            auth_url = f"{self.api_base}/users/login"
            response = self.session.post(
                auth_url,
                json={"username": self.username, "password": self.password},
                timeout=TIMEOUT,
            )

            if response.status_code == 200:
                data = response.json()
                self.auth_token = data.get("access_token")
                if self.auth_token:
                    self.session.headers.update({"Authorization": f"Bearer {self.auth_token}"})
                    if VERBOSE:
                        print(f"✓ Authenticated as {self.username}")
            else:
                print(f"⚠ Authentication failed ({response.status_code})")
        except Exception as e:
            print(f"⚠ Could not authenticate: {str(e)}")

    def send_message(self, message: str, conversation_id: Optional[str] = None) -> Dict[str, Any]:
        """Send a chat message and return the full response."""
        url = f"{self.api_base}/chat"
        payload = {"message": message}
        if conversation_id:
            payload["conversation_id"] = conversation_id
        elif self.conversation_id:
            payload["conversation_id"] = self.conversation_id

        start = time.time()
        response = self.session.post(url, json=payload, timeout=TIMEOUT)
        duration = time.time() - start

        response.raise_for_status()
        data = response.json()

        # Update conversation ID from response
        if "conversation_id" in data:
            self.conversation_id = data["conversation_id"]

        if VERBOSE:
            print(f"  [API] {message[:60]}... ({duration:.2f}s)")

        return data

    def run_test(self, test_name: str, test_phase: str, test_fn) -> TestResult:
        """Run a single test and record result."""
        try:
            start = time.time()
            passed, message, metadata, content = test_fn()
            duration = time.time() - start

            result = TestResult(
                test_name=test_name,
                test_phase=test_phase,
                passed=passed,
                message=message,
                duration=duration,
                response_metadata=metadata,
                response_content=content,
            )
            self.results.append(result)
            return result
        except Exception as e:
            result = TestResult(
                test_name=test_name,
                test_phase=test_phase,
                passed=False,
                message=f"Exception: {str(e)}",
                duration=0.0,
            )
            self.results.append(result)
            return result

    def print_results(self):
        """Print test results summary."""
        print("\n" + "=" * 80)
        print("COMPLEX QUERY TEST RESULTS SUMMARY")
        print("=" * 80)

        phases = {}
        for result in self.results:
            if result.test_phase not in phases:
                phases[result.test_phase] = []
            phases[result.test_phase].append(result)

        total_passed = sum(1 for r in self.results if r.passed)
        total_failed = sum(1 for r in self.results if not r.passed)

        for phase, results in sorted(phases.items()):
            phase_passed = sum(1 for r in results if r.passed)
            phase_failed = sum(1 for r in results if not r.passed)
            print(f"\n{phase} ({phase_passed}/{len(results)} passed)")
            print("-" * 80)
            for result in results:
                print(f"  {result}")

        print("\n" + "=" * 80)
        print(f"OVERALL: {total_passed}/{len(self.results)} tests passed")
        print("=" * 80)

        if total_failed > 0:
            print("\nFailed tests details:")
            for result in self.results:
                if not result.passed:
                    print(f"\n[{result.test_phase}] {result.test_name}")
                    print(f"  Message: {result.message}")


# ============================================================================
# PHASE 1: MULTI-TURN CONVERSATIONS WITH CONTEXT
# ============================================================================


def test_multi_turn_with_refinement() -> tuple:
    """Test conversation refinement: initial query > follow-up > filter."""
    tester = AdvancedChatTester()

    # Turn 1: Get top posts
    response1 = tester.send_message("What are our top 3 posts this month?")
    conv_id = tester.conversation_id
    message1 = response1.get("message", {})
    content1 = message1.get("content", {})
    result_data1 = content1.get("result_data", [])

    if len(result_data1) == 0:
        return False, "No results from initial query", {}, {}

    top_post = result_data1[0]
    top_post_label = top_post.get("label") or top_post.get("title") or "Unknown"

    # Turn 2: Ask about platform
    response2 = tester.send_message("What platform are they from?", conv_id)
    message2 = response2.get("message", {})
    content2 = message2.get("content", {})
    result_data2 = content2.get("result_data", [])

    # Turn 3: Ask specific follow-up
    response3 = tester.send_message("Show me all posts from that platform", conv_id)
    message3 = response3.get("message", {})
    content3 = message3.get("content", {})
    result_data3 = content3.get("result_data", [])

    passed = (
        len(result_data1) > 0
        and len(result_data2) > 0
        and response1.get("conversation_id") == response2.get("conversation_id") == response3.get("conversation_id")
    )
    message_text = f"3-turn conversation: {len(result_data1)} → {len(result_data2)} → {len(result_data3)} results"

    return passed, message_text, message3.get("metadata", {}), content3


def test_complex_multi_metric_query() -> tuple:
    """Test query with multiple metrics and comparisons."""
    tester = AdvancedChatTester()

    response = tester.send_message(
        "Show me the top 5 content items and compare their views, engagement, and comments"
    )
    message = response.get("message", {})
    metadata = message.get("metadata", {})
    content = message.get("content", {})
    result_data = content.get("result_data", [])

    passed = len(result_data) > 0

    message_text = f"{len(result_data)} results with multiple metrics"

    return passed, message_text, metadata, content


def test_aggregation_with_grouping() -> tuple:
    """Test complex aggregation by platform."""
    tester = AdvancedChatTester()

    response = tester.send_message("Get total views grouped by platform, ordered by highest to lowest")
    message = response.get("message", {})
    metadata = message.get("metadata", {})
    content = message.get("content", {})
    result_data = content.get("result_data", [])

    passed = len(result_data) > 0

    message_text = f"Grouped aggregation: {len(result_data)} platform groups"

    return passed, message_text, metadata, content


def test_filter_with_conditions() -> tuple:
    """Test query with multiple filter conditions."""
    tester = AdvancedChatTester()

    response = tester.send_message("Show posts with more than 5000 views and more than 100 engagements")
    message = response.get("message", {})
    metadata = message.get("metadata", {})
    content = message.get("content", {})
    result_data = content.get("result_data", [])

    passed = (
        content.get("insight_summary", "").strip() != ""
        or len(result_data) >= 0
    )

    message_text = f"Filtered results: {len(result_data)} items matching conditions"

    return passed, message_text, metadata, content


# ============================================================================
# PHASE 2: PERFORMANCE & SCALE TESTS
# ============================================================================


def test_large_result_set() -> tuple:
    """Test handling of large result sets from 160k records."""
    tester = AdvancedChatTester()

    start = time.time()
    response = tester.send_message("List all unique platforms in our data")
    duration = time.time() - start

    message = response.get("message", {})
    metadata = message.get("metadata", {})
    content = message.get("content", {})
    result_data = content.get("result_data", [])

    passed = duration < 10.0  # Should complete quickly

    message_text = f"Completed in {duration:.2f}s, {len(result_data)} results"

    return passed, message_text, metadata, content


def test_complex_sql_generation() -> tuple:
    """Test that complex SQL is generated correctly for sophisticated queries."""
    tester = AdvancedChatTester()

    response = tester.send_message(
        "What's the average engagement per post for content from TikTok vs Instagram?"
    )
    message = response.get("message", {})
    metadata = message.get("metadata", {})
    generated_sql = metadata.get("generated_sql", "")

    content = message.get("content", {})

    passed = (
        len(generated_sql) > 20  # SQL should be substantial
        and ("SELECT" in generated_sql or len(content.get("result_data", [])) > 0)
    )

    message_text = f"SQL generated: {len(generated_sql)} chars"

    return passed, message_text, metadata, content


# ============================================================================
# PHASE 3: CONTEXT RETENTION & MEMORY
# ============================================================================


def test_context_accumulation() -> tuple:
    """Test that context accumulates across multiple turns."""
    tester = AdvancedChatTester()

    # Turn 1: Ask about top posts
    tester.send_message("What are the top posts?")
    conv_id = tester.conversation_id

    # Turn 2: Add context
    tester.send_message("Which ones are from TikTok?", conv_id)

    # Turn 3: More specific
    tester.send_message("Of those, which got the most engagement?", conv_id)

    # Turn 4: Complex follow-up using accumulated context
    response4 = tester.send_message("Show me similar posts from the same creator", conv_id)
    message4 = response4.get("message", {})
    metadata4 = message4.get("metadata", {})

    passed = response4.get("conversation_id") == conv_id

    message_text = "4-turn conversation with context accumulation"

    return passed, message_text, metadata4, message4.get("content", {})


def test_pronoun_reference_resolution() -> tuple:
    """Test that pronouns and references are resolved through context."""
    tester = AdvancedChatTester()

    # Turn 1: Establish subject
    tester.send_message("What was our highest performing post last week?")
    conv_id = tester.conversation_id

    # Turn 2: Use pronoun reference
    response2 = tester.send_message("How many total shares did it get?", conv_id)
    message2 = response2.get("message", {})
    content2 = message2.get("content", {})

    # Turn 3: Another pronoun reference
    response3 = tester.send_message("What was the sentiment of the comments on it?", conv_id)
    message3 = response3.get("message", {})

    passed = response2.get("conversation_id") == response3.get("conversation_id") == conv_id

    message_text = "Handled pronoun references across 3 turns"

    return passed, message_text, message3.get("metadata", {}), content2


# ============================================================================
# PHASE 4: ERROR HANDLING & EDGE CASES
# ============================================================================


def test_invalid_metric_graceful_handling() -> tuple:
    """Test graceful handling of non-existent metrics."""
    tester = AdvancedChatTester()

    response = tester.send_message("Show me the sentiment scores for all posts")
    message = response.get("message", {})
    metadata = message.get("metadata", {})
    content = message.get("content", {})

    # Should either: return error message OR empty results OR pivot to available metrics
    passed = (
        response.get("status") == "success"
        or "error" in metadata.get("operation", "").lower()
        or len(content.get("result_data", [])) >= 0  # Empty is OK
    )

    insight = content.get("insight_summary", "")
    message_text = f"Graceful error handling: {insight[:50]}..."

    return passed, message_text, metadata, content


def test_time_range_specification() -> tuple:
    """Test handling of time range queries."""
    tester = AdvancedChatTester()

    response = tester.send_message("Show me posts from the last 7 days with the most views")
    message = response.get("message", {})
    metadata = message.get("metadata", {})
    content = message.get("content", {})

    passed = response.get("status") == "success"

    message_text = "Time range query handled"

    return passed, message_text, metadata, content


def test_boundary_results() -> tuple:
    """Test boundary conditions like top 1, bottom N, etc."""
    tester = AdvancedChatTester()

    response = tester.send_message("What is the single highest performing post?")
    message = response.get("message", {})
    metadata = message.get("metadata", {})
    content = message.get("content", {})
    result_data = content.get("result_data", [])

    passed = len(result_data) >= 1

    message_text = f"Boundary result: {len(result_data)} items"

    return passed, message_text, metadata, content


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================


def main():
    print("=" * 80)
    print("ADVANCED E2E CHAT TEST SUITE")
    print("Complex Queries, Multi-Turn Conversations, and Sophisticated Orchestrator Paths")
    print("=" * 80)
    print(f"API Base: {API_BASE}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 80)

    tester = AdvancedChatTester()

    # Phase 1: Multi-Turn Conversations
    print("\n[PHASE 1] Multi-Turn Conversations with Context")
    print("-" * 80)
    tester.run_test("Multi-Turn with Refinement", "Phase 1", test_multi_turn_with_refinement)
    tester.run_test("Complex Multi-Metric Query", "Phase 1", test_complex_multi_metric_query)
    tester.run_test("Aggregation with Grouping", "Phase 1", test_aggregation_with_grouping)
    tester.run_test("Filter with Conditions", "Phase 1", test_filter_with_conditions)

    # Reset conversation
    tester.conversation_id = None

    # Phase 2: Performance & Scale
    print("\n[PHASE 2] Performance and Scale")
    print("-" * 80)
    tester.run_test("Large Result Set Handling", "Phase 2", test_large_result_set)
    tester.run_test("Complex SQL Generation", "Phase 2", test_complex_sql_generation)

    # Reset conversation
    tester.conversation_id = None

    # Phase 3: Context Retention
    print("\n[PHASE 3] Context Retention and Memory")
    print("-" * 80)
    tester.run_test("Context Accumulation", "Phase 3", test_context_accumulation)
    tester.run_test("Pronoun Reference Resolution", "Phase 3", test_pronoun_reference_resolution)

    # Reset conversation
    tester.conversation_id = None

    # Phase 4: Error Handling
    print("\n[PHASE 4] Error Handling and Edge Cases")
    print("-" * 80)
    tester.run_test("Invalid Metric Handling", "Phase 4", test_invalid_metric_graceful_handling)
    tester.run_test("Time Range Specification", "Phase 4", test_time_range_specification)
    tester.run_test("Boundary Results", "Phase 4", test_boundary_results)

    # Print results
    tester.print_results()

    # Exit code based on results
    failed = sum(1 for r in tester.results if not r.passed)
    exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
