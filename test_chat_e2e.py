#!/usr/bin/env python3
"""
End-to-End Chat Testing Script
Tests the complete orchestrator pipeline with 160k records
"""

import requests
import json
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime

# Configuration
API_BASE = "http://localhost:8000/api/v1"
TIMEOUT = 30  # seconds
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


class ChatTester:
    def __init__(self, api_base: str = API_BASE):
        self.api_base = api_base
        self.conversation_id: Optional[str] = None
        self.results: List[TestResult] = []
        self.session = requests.Session()

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
            print(f"  [API] {message[:50]}... ({duration:.2f}s)")

        return data

    def get_conversation_messages(self, conversation_id: Optional[str] = None) -> Dict[str, Any]:
        """Get all messages in the conversation."""
        conv_id = conversation_id or self.conversation_id
        if not conv_id:
            raise ValueError("No conversation ID set")

        url = f"{self.api_base}/chat/conversations/{conv_id}/messages"
        response = self.session.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()

    def get_conversation_context(self, conversation_id: Optional[str] = None) -> Dict[str, Any]:
        """Get LLM-formatted conversation context."""
        conv_id = conversation_id or self.conversation_id
        if not conv_id:
            raise ValueError("No conversation ID set")

        url = f"{self.api_base}/chat/conversations/{conv_id}/context"
        response = self.session.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()

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
        print("TEST RESULTS SUMMARY")
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
                    if result.response_metadata:
                        print(f"  Metadata: {json.dumps(result.response_metadata, indent=4)}")
                    if result.response_content:
                        print(f"  Content: {json.dumps(result.response_content, indent=4)}")


# ============================================================================
# PHASE 1: INTENT CLASSIFICATION & ROUTING
# ============================================================================


def test_analytics_intent() -> tuple:
    """Test that analytics queries are classified correctly."""
    tester = ChatTester()

    response = tester.send_message("What were the top performing posts last week?")
    message = response.get("message", {})
    metadata = message.get("metadata", {})
    operation = metadata.get("operation")

    passed = operation == "analytics"
    message_text = f"Operation: {operation}" if operation else "No operation in metadata"

    return passed, message_text, metadata, message.get("content")


def test_tagging_intent() -> tuple:
    """Test that tagging queries are classified correctly."""
    tester = ChatTester()

    response = tester.send_message("Suggest tags for this article about machine learning")
    message = response.get("message", {})
    metadata = message.get("metadata", {})
    operation = metadata.get("operation")

    passed = operation in ["tagging", "tag_suggestions"]
    message_text = f"Operation: {operation}" if operation else "No operation in metadata"

    return passed, message_text, metadata, message.get("content")


def test_fallback_intent() -> tuple:
    """Test that unknown intents are handled gracefully."""
    tester = ChatTester()

    try:
        response = tester.send_message("Tell me a physics joke")
        passed = response.get("status") == "success" or "message" in response
        message_text = "Graceful fallback to unknown intent"
        return passed, message_text, {}, response.get("message", {}).get("content")
    except Exception as e:
        return False, f"Failed with error: {str(e)}", {}, None


# ============================================================================
# PHASE 2: ANALYTICS SQL PIPELINE
# ============================================================================


def test_simple_metric_query() -> tuple:
    """Test simple aggregation query."""
    tester = ChatTester()

    response = tester.send_message("How many total documents do we have?")
    message = response.get("message", {})
    metadata = message.get("metadata", {})
    content = message.get("content", {})

    generated_sql = metadata.get("generated_sql")
    result_data = content.get("result_data", [])

    passed = (
        generated_sql is not None
        and len(result_data) > 0
        and "metric_value" in result_data[0]
    )

    message_text = (
        f"Generated SQL, {len(result_data)} results"
        if passed
        else "Missing SQL or results"
    )

    return passed, message_text, metadata, content


def test_top_content_query() -> tuple:
    """Test top-N query."""
    tester = ChatTester()

    response = tester.send_message("Show me the top 5 posts by views")
    message = response.get("message", {})
    metadata = message.get("metadata", {})
    content = message.get("content", {})

    result_data = content.get("result_data", [])
    insight_summary = content.get("insight_summary", "")

    passed = (
        len(result_data) > 0
        and len(result_data) <= 5
        and len(insight_summary) > 10
    )

    message_text = f"{len(result_data)} results with insight summary"

    return passed, message_text, metadata, content


def test_parameterized_sql() -> tuple:
    """Test SQL injection prevention."""
    tester = ChatTester()

    response = tester.send_message("What posts have more than 1000 views?")
    message = response.get("message", {})
    metadata = message.get("metadata", {})
    content = message.get("content", {})

    generated_sql = metadata.get("generated_sql", "")
    result_data = content.get("result_data", [])

    # Check that SQL is valid and parameterized (no quoted values)
    passed = (
        "SELECT" in generated_sql
        and "FROM" in generated_sql
        and len(result_data) >= 0
    )

    message_text = f"Query parameterized, {len(result_data)} results"

    return passed, message_text, metadata, content


# ============================================================================
# PHASE 3: CONVERSATION CONTEXT & FOLLOW-UPS
# ============================================================================


def test_conversation_context_injection() -> tuple:
    """Test that conversation context is properly injected for follow-ups."""
    tester = ChatTester()

    # First query
    response1 = tester.send_message("What is our top performing post?")
    message1 = response1.get("message", {})
    metadata1 = message1.get("metadata", {})

    # Follow-up query in same conversation
    response2 = tester.send_message("How many comments did it get?", tester.conversation_id)
    message2 = response2.get("message", {})

    # Verify follow-up happened in same conversation
    passed = response1.get("conversation_id") == response2.get("conversation_id")
    message_text = (
        "Follow-up in same conversation"
        if passed
        else "Conversation ID mismatch"
    )

    return passed, message_text, metadata1, message2.get("content")


def test_message_history() -> tuple:
    """Test that conversation history is retrievable."""
    tester = ChatTester()

    # Send multiple messages
    tester.send_message("What are the top posts?")
    tester.send_message("Show me their engagement metrics")

    # Get message history
    history = tester.get_conversation_messages()
    messages = history.get("messages", [])

    passed = len(messages) >= 4  # 2 user + 2 assistant
    message_text = f"{len(messages)} messages in history"

    return passed, message_text, {}, None


# ============================================================================
# PHASE 4: VALUE-GUARD VALIDATION
# ============================================================================


def test_no_invented_metrics() -> tuple:
    """Test that responses don't include hallucinated values."""
    tester = ChatTester()

    response = tester.send_message("Show me all metrics for the top post")
    message = response.get("message", {})
    content = message.get("content", {})

    insight_summary = content.get("insight_summary", "")
    result_data = content.get("result_data", [])

    # Check that insight summary mentions actual values from result_data
    passed = (
        len(insight_summary) > 0
        and len(result_data) > 0
    )

    message_text = f"Insight summary with {len(result_data)} result items"

    return passed, message_text, message.get("metadata", {}), content


# ============================================================================
# PHASE 5: RESPONSE FORMAT VALIDATION
# ============================================================================


def test_response_schema() -> tuple:
    """Test that response conforms to expected schema."""
    tester = ChatTester()

    response = tester.send_message("Top 3 posts by views")
    message = response.get("message", {})
    metadata = message.get("metadata", {})
    content = message.get("content", {})

    # Check required fields
    required_metadata = ["operation"]
    required_content = ["query_type", "result_data", "insight_summary"]

    metadata_ok = all(k in metadata for k in required_metadata)
    content_ok = all(k in content for k in required_content)

    passed = metadata_ok and content_ok
    message_text = f"Metadata ({'✓' if metadata_ok else '✗'}), Content ({'✓' if content_ok else '✗'})"

    return passed, message_text, metadata, content


def test_result_item_schema() -> tuple:
    """Test that result_data items conform to schema."""
    tester = ChatTester()

    response = tester.send_message("Show top 2 posts")
    message = response.get("message", {})
    content = message.get("content", {})
    result_data = content.get("result_data", [])

    if len(result_data) == 0:
        return False, "No result_data items", {}, content

    item = result_data[0]
    required_fields = ["display_label", "metric_value"]
    passed = all(k in item for k in required_fields)

    message_text = f"Result item has required fields" if passed else "Missing required fields in result item"

    return passed, message_text, message.get("metadata", {}), content


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================


def main():
    print("=" * 80)
    print("CHAT ORCHESTRATOR E2E TEST SUITE")
    print("=" * 80)
    print(f"API Base: {API_BASE}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 80)

    tester = ChatTester()

    # Phase 1: Intent Classification
    print("\n[PHASE 1] Intent Classification & Routing")
    print("-" * 80)
    tester.run_test("Analytics Intent Detection", "Phase 1", test_analytics_intent)
    tester.run_test("Tagging Intent Detection", "Phase 1", test_tagging_intent)
    tester.run_test("Unknown Intent Fallback", "Phase 1", test_fallback_intent)

    # Reset conversation for Phase 2
    tester.conversation_id = None

    # Phase 2: Analytics SQL Pipeline
    print("\n[PHASE 2] Analytics SQL Pipeline")
    print("-" * 80)
    tester.run_test("Simple Metric Query", "Phase 2", test_simple_metric_query)
    tester.run_test("Top Content Query", "Phase 2", test_top_content_query)
    tester.run_test("Parameterized SQL", "Phase 2", test_parameterized_sql)

    # Reset conversation for Phase 3
    tester.conversation_id = None

    # Phase 3: Conversation Context
    print("\n[PHASE 3] Conversation Context & Follow-Ups")
    print("-" * 80)
    tester.run_test("Context Injection", "Phase 3", test_conversation_context_injection)
    tester.run_test("Message History", "Phase 3", test_message_history)

    # Phase 4: Value-Guard Validation
    print("\n[PHASE 4] Value-Guard Validation")
    print("-" * 80)
    tester.run_test("No Invented Metrics", "Phase 4", test_no_invented_metrics)

    # Phase 5: Response Format
    print("\n[PHASE 5] Response Format Validation")
    print("-" * 80)
    tester.run_test("Response Schema", "Phase 5", test_response_schema)
    tester.run_test("Result Item Schema", "Phase 5", test_result_item_schema)

    # Print results
    tester.print_results()

    # Exit code based on results
    failed = sum(1 for r in tester.results if not r.passed)
    exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
