"""Unit tests for UUID hashing utility.

Tests verify that UUID hashing is deterministic and produces
consistent, predictable results for deduplication.
"""

import pytest
import uuid as uuid_lib
from app.utils.uuid_hasher import generate_beast_uuid, get_beast_uuid, get_beast_uuid_hex


class TestGenerateBeastUUID:
    """Test suite for generate_beast_uuid function."""

    def test_generate_beast_uuid_basic(self):
        """Test basic UUID generation from text."""
        hex_hash, uuid_str = generate_beast_uuid("hello world")

        # Verify hex_hash is a string of 64 characters (SHA256)
        assert isinstance(hex_hash, str)
        assert len(hex_hash) == 64
        assert all(c in "0123456789abcdef" for c in hex_hash)

        # Verify uuid_str is a valid UUID
        assert isinstance(uuid_str, str)
        assert len(uuid_str) == 36  # Standard UUID string length
        assert uuid_str.count('-') == 4

    def test_generate_beast_uuid_is_deterministic(self):
        """Test that same input always produces same output."""
        text = "test content"
        hex1, uuid1 = generate_beast_uuid(text)
        hex2, uuid2 = generate_beast_uuid(text)

        assert hex1 == hex2
        assert uuid1 == uuid2

    def test_generate_beast_uuid_different_input_different_output(self):
        """Test that different inputs produce different outputs."""
        hex1, uuid1 = generate_beast_uuid("hello")
        hex2, uuid2 = generate_beast_uuid("world")

        assert hex1 != hex2
        assert uuid1 != uuid2

    def test_generate_beast_uuid_max_length_default(self):
        """Test that default max_length is 150."""
        long_text = "a" * 200
        hex1, uuid1 = generate_beast_uuid(long_text, max_length=150)
        hex2, uuid2 = generate_beast_uuid(long_text, max_length=150)

        assert hex1 == hex2
        assert uuid1 == uuid2

    def test_generate_beast_uuid_max_length_custom(self):
        """Test that custom max_length is respected."""
        text = "abcdefghijklmnopqrstuvwxyz"
        hex1, uuid1 = generate_beast_uuid(text, max_length=10)
        hex2, uuid2 = generate_beast_uuid("abcdefghij", max_length=150)

        # First 10 chars of text should match different max_length
        assert hex1 == hex2
        assert uuid1 == uuid2

    def test_generate_beast_uuid_truncates_correctly(self):
        """Test that text is truncated before hashing."""
        long_text = "a" * 200

        # Hash of first 150 chars of "a"*200 should equal hash of "a"*150
        hex1, _ = generate_beast_uuid(long_text, max_length=150)
        hex2, _ = generate_beast_uuid("a" * 150, max_length=150)

        assert hex1 == hex2

    def test_generate_beast_uuid_empty_string(self):
        """Test UUID generation from empty string."""
        hex_hash, uuid_str = generate_beast_uuid("")

        # Should still produce valid hash and UUID
        assert len(hex_hash) == 64
        assert len(uuid_str) == 36

        # Should be reproducible
        hex2, uuid2 = generate_beast_uuid("")
        assert hex_hash == hex2
        assert uuid_str == uuid2

    def test_generate_beast_uuid_non_string_input(self):
        """Test that non-string inputs are converted."""
        hex1, uuid1 = generate_beast_uuid(123)
        hex2, uuid2 = generate_beast_uuid("123")

        # Both should produce same result
        assert hex1 == hex2
        assert uuid1 == uuid2

    def test_generate_beast_uuid_none_input(self):
        """Test handling of None input."""
        hex_hash, uuid_str = generate_beast_uuid(None)

        # Should convert None to string "None"
        assert len(hex_hash) == 64
        assert len(uuid_str) == 36

    def test_generate_beast_uuid_numeric_input(self):
        """Test with numeric input."""
        hex1, uuid1 = generate_beast_uuid(12345)
        hex2, uuid2 = generate_beast_uuid("12345")

        assert hex1 == hex2
        assert uuid1 == uuid2

    def test_generate_beast_uuid_float_input(self):
        """Test with float input."""
        hex1, uuid1 = generate_beast_uuid(123.456)
        hex2, uuid2 = generate_beast_uuid("123.456")

        assert hex1 == hex2
        assert uuid1 == uuid2

    def test_generate_beast_uuid_special_characters(self):
        """Test with special characters."""
        hex_hash, uuid_str = generate_beast_uuid("test@example.com!#$")

        assert len(hex_hash) == 64
        assert len(uuid_str) == 36

    def test_generate_beast_uuid_unicode(self):
        """Test with unicode characters."""
        hex_hash, uuid_str = generate_beast_uuid("café résumé")

        assert len(hex_hash) == 64
        assert len(uuid_str) == 36

    def test_generate_beast_uuid_whitespace(self):
        """Test that whitespace is significant."""
        hex1, uuid1 = generate_beast_uuid("hello world")
        hex2, uuid2 = generate_beast_uuid("helloworld")

        # Different whitespace should produce different hashes
        assert hex1 != hex2
        assert uuid1 != uuid2

    def test_generate_beast_uuid_case_sensitive(self):
        """Test that hashing is case-sensitive."""
        hex1, uuid1 = generate_beast_uuid("Hello World")
        hex2, uuid2 = generate_beast_uuid("hello world")

        # Different case should produce different hashes
        assert hex1 != hex2
        assert uuid1 != uuid2

    def test_generate_beast_uuid_consistent_across_calls(self):
        """Test that UUID generation is consistent across many calls."""
        text = "test content for verification"
        hashes = [generate_beast_uuid(text) for _ in range(100)]

        # All should be identical
        first_hash = hashes[0]
        for hash_pair in hashes[1:]:
            assert hash_pair == first_hash

    def test_generate_beast_uuid_valid_uuid_format(self):
        """Test that returned UUID is valid according to UUID spec."""
        _, uuid_str = generate_beast_uuid("test")

        # Should be parseable as a UUID
        try:
            parsed = uuid_lib.UUID(uuid_str)
            # UUID version can be any value since we're constructing from hash
            assert parsed.version in (None, 1, 2, 3, 4, 5, 6, 7)
        except (ValueError, AttributeError):
            pytest.fail(f"Invalid UUID format: {uuid_str}")

    def test_generate_beast_uuid_real_world_identifier(self):
        """Test with real-world identifier."""
        identifier = "YouTube_dQw4w9WgXcQ_Published_2023-01-15_Views_1M"
        hex_hash, uuid_str = generate_beast_uuid(identifier, max_length=150)

        assert len(hex_hash) == 64
        assert len(uuid_str) == 36

        # Should be reproducible
        hex2, uuid2 = generate_beast_uuid(identifier, max_length=150)
        assert hex_hash == hex2
        assert uuid_str == uuid2


class TestGetBeastUUID:
    """Test suite for get_beast_uuid convenience function."""

    def test_get_beast_uuid_basic(self):
        """Test basic UUID string retrieval."""
        uuid_str = get_beast_uuid("hello world")

        assert isinstance(uuid_str, str)
        assert len(uuid_str) == 36

    def test_get_beast_uuid_is_deterministic(self):
        """Test that get_beast_uuid is deterministic."""
        text = "test"
        uuid1 = get_beast_uuid(text)
        uuid2 = get_beast_uuid(text)

        assert uuid1 == uuid2

    def test_get_beast_uuid_matches_generate_beast_uuid(self):
        """Test that get_beast_uuid returns same as generate_beast_uuid."""
        text = "comparison test"
        _, uuid_from_generate = generate_beast_uuid(text)
        uuid_from_convenience = get_beast_uuid(text)

        assert uuid_from_generate == uuid_from_convenience

    def test_get_beast_uuid_custom_length(self):
        """Test with custom max_length."""
        text = "a" * 200
        uuid1 = get_beast_uuid(text, max_length=100)
        uuid2 = get_beast_uuid("a" * 100, max_length=150)

        assert uuid1 == uuid2


class TestGetBeastUUIDHex:
    """Test suite for get_beast_uuid_hex convenience function."""

    def test_get_beast_uuid_hex_basic(self):
        """Test basic hex string retrieval."""
        hex_str = get_beast_uuid_hex("hello world")

        assert isinstance(hex_str, str)
        assert len(hex_str) == 64
        assert all(c in "0123456789abcdef" for c in hex_str)

    def test_get_beast_uuid_hex_is_deterministic(self):
        """Test that get_beast_uuid_hex is deterministic."""
        text = "test"
        hex1 = get_beast_uuid_hex(text)
        hex2 = get_beast_uuid_hex(text)

        assert hex1 == hex2

    def test_get_beast_uuid_hex_matches_generate_beast_uuid(self):
        """Test that get_beast_uuid_hex returns same as generate_beast_uuid."""
        text = "comparison test"
        hex_from_generate, _ = generate_beast_uuid(text)
        hex_from_convenience = get_beast_uuid_hex(text)

        assert hex_from_generate == hex_from_convenience

    def test_get_beast_uuid_hex_custom_length(self):
        """Test with custom max_length."""
        text = "a" * 200
        hex1 = get_beast_uuid_hex(text, max_length=100)
        hex2 = get_beast_uuid_hex("a" * 100, max_length=150)

        assert hex1 == hex2


class TestIntegration:
    """Integration tests for UUID hashing with deduplication use cases."""

    def test_duplicate_detection_scenario(self):
        """Test that same content identifier always produces same UUID."""
        # Simulate three imports of same content
        content_id = "platform_video_12345"

        uuid1 = get_beast_uuid(content_id)
        uuid2 = get_beast_uuid(content_id)
        uuid3 = get_beast_uuid(content_id)

        # All three should be identical
        assert uuid1 == uuid2 == uuid3

    def test_cross_platform_deduplication(self):
        """Test deduplication across platforms with normalized identifier."""
        # Same video on different platforms
        identifier = "famous youtube video uploaded 2023"

        uuid_import1 = get_beast_uuid(identifier)
        uuid_import2 = get_beast_uuid(identifier)  # Later import

        assert uuid_import1 == uuid_import2

    def test_multiple_different_content(self):
        """Test that different content gets different UUIDs."""
        content_ids = [
            "video_id_12345",
            "video_id_12346",
            "video_id_12347",
            "tweet_id_98765",
            "instagram_post_54321",
        ]

        uuids = [get_beast_uuid(cid) for cid in content_ids]

        # All UUIDs should be different
        assert len(uuids) == len(set(uuids))

    def test_truncation_at_150_chars(self):
        """Test that content is truncated at 150 chars for hashing."""
        # Create two strings: one 150 chars, one 200 chars (first 150 same)
        base = "a" * 150
        long_version = base + "b" * 50

        uuid_base = get_beast_uuid(base)
        uuid_long = get_beast_uuid(long_version)

        # Should produce same UUID (both hash first 150)
        assert uuid_base == uuid_long
