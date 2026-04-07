"""Unit tests for text cleaning utility.

Tests verify that text cleaning produces consistent, deterministic output
suitable for deduplication hashing.
"""

import pytest
from app.utils.text_cleaner import clean_text, clean_and_truncate


class TestCleanText:
    """Test suite for clean_text function."""

    def test_clean_text_basic(self):
        """Test basic text cleaning with mixed case and spaces."""
        result = clean_text("Hello  World")
        assert result == "hello world"

    def test_clean_text_removes_special_chars(self):
        """Test that special characters are removed."""
        result = clean_text("Hello@World#123!")
        assert result == "helloworld123"

    def test_clean_text_preserves_alphanumeric(self):
        """Test that alphanumeric characters are preserved."""
        result = clean_text("Test123ABC")
        assert result == "test123abc"

    def test_clean_text_preserves_spaces(self):
        """Test that spaces between words are preserved."""
        result = clean_text("hello world test")
        assert result == "hello world test"

    def test_clean_text_collapses_multiple_spaces(self):
        """Test that multiple consecutive spaces are collapsed."""
        result = clean_text("hello    world")
        assert result == "hello world"

    def test_clean_text_trims_leading_trailing(self):
        """Test that leading and trailing whitespace is removed."""
        result = clean_text("   hello world   ")
        assert result == "hello world"

    def test_clean_text_tabs_and_newlines(self):
        """Test that tabs and newlines are handled."""
        result = clean_text("hello\t\nworld")
        assert result == "hello world"

    def test_clean_text_unicode_normalization(self):
        """Test unicode normalization."""
        # Using combining characters that should be normalized
        result = clean_text("café")  # é as single character
        # Should handle unicode properly
        assert len(result) > 0
        assert "caf" in result

    def test_clean_text_urls_removed(self):
        """Test that URL special characters are removed."""
        result = clean_text("Check https://example.com/page")
        # URL protocol "https" is alphanumeric so it's preserved
        assert "https" in result
        assert "example" in result
        assert "com" in result
        # Slashes and colons removed (special chars)
        assert "/" not in result
        assert ":" not in result

    def test_clean_text_html_tags_removed(self):
        """Test that HTML tags and angle brackets are removed."""
        result = clean_text("<p>Hello World</p>")
        assert "<" not in result
        assert ">" not in result
        assert "hello world" in result

    def test_clean_text_empty_string(self):
        """Test handling of empty string."""
        result = clean_text("")
        assert result == ""

    def test_clean_text_only_whitespace(self):
        """Test handling of string with only whitespace."""
        result = clean_text("   \t\n  ")
        assert result == ""

    def test_clean_text_only_special_chars(self):
        """Test handling of string with only special characters."""
        result = clean_text("!@#$%^&*()")
        assert result == ""

    def test_clean_text_numbers_only(self):
        """Test that numbers are preserved."""
        result = clean_text("123 456 789")
        assert result == "123 456 789"

    def test_clean_text_mixed_special_chars(self):
        """Test various special characters."""
        result = clean_text("Hello-World_Test.123!")
        # Hyphens, underscores, periods removed (special chars)
        # This results in "helloworld test123" (without spaces between words since - and _ are removed)
        assert result == "helloworldtest123"
        assert "-" not in result
        assert "_" not in result
        assert "." not in result

    def test_clean_text_quotes(self):
        """Test that quotes are removed."""
        result = clean_text('Say "hello" and \'world\'')
        assert "\"" not in result
        assert "'" not in result
        assert "say hello and world" in result

    def test_clean_text_parentheses_brackets(self):
        """Test that brackets and parentheses are removed."""
        result = clean_text("test (content) [data] {value}")
        assert "(" not in result
        assert ")" not in result
        assert "[" not in result
        assert "]" not in result
        assert "{" not in result
        assert "}" not in result

    def test_clean_text_deterministic(self):
        """Test that cleaning is deterministic (same input = same output)."""
        input_text = "Hello!!!  World@@@123###"
        result1 = clean_text(input_text)
        result2 = clean_text(input_text)
        assert result1 == result2

    def test_clean_text_non_string_input(self):
        """Test that non-string inputs are converted."""
        result = clean_text(123)
        assert result == "123"

        result = clean_text(None)
        assert result == "none"

    def test_clean_text_real_world_content_id(self):
        """Test cleaning a real-world content identifier."""
        # Example: YouTube video ID with context
        result = clean_text("YouTube Video: dQw4w9WgXcQ - Published 2023-01-15")
        assert "youtube video" in result
        assert "dqw4w9wgxcq" in result
        assert "published" in result
        assert "2023" in result
        assert "01" in result
        assert "15" in result

    def test_clean_text_social_media_handle(self):
        """Test cleaning social media handle."""
        result = clean_text("@username_123-official!")
        assert "username" in result
        assert "123" in result
        assert "official" in result
        assert "@" not in result
        assert "_" not in result
        assert "-" not in result

    def test_clean_text_email_like_content(self):
        """Test cleaning email-like content."""
        result = clean_text("contact@example.com")
        assert "contact" in result
        assert "example" in result
        assert "com" in result
        assert "@" not in result
        assert "." not in result


class TestCleanAndTruncate:
    """Test suite for clean_and_truncate function."""

    def test_clean_and_truncate_basic(self):
        """Test basic cleaning and truncation."""
        result = clean_and_truncate("Hello World", max_length=5)
        assert result == "hello"

    def test_clean_and_truncate_no_truncation_needed(self):
        """Test when text is shorter than max_length."""
        result = clean_and_truncate("Hi", max_length=10)
        assert result == "hi"

    def test_clean_and_truncate_with_special_chars_and_length(self):
        """Test cleaning and truncation together."""
        result = clean_and_truncate("Hello!!!World@@@123", max_length=8)
        assert result == "hellowor"

    def test_clean_and_truncate_default_length(self):
        """Test that default max_length is 150."""
        long_text = "a" * 200
        result = clean_and_truncate(long_text)
        assert len(result) == 150

    def test_clean_and_truncate_custom_length(self):
        """Test custom max_length parameter."""
        text = "a" * 100
        result = clean_and_truncate(text, max_length=50)
        assert len(result) == 50

    def test_clean_and_truncate_empty_after_cleaning(self):
        """Test when text becomes empty after cleaning."""
        result = clean_and_truncate("!@#$%^", max_length=10)
        assert result == ""

    def test_clean_and_truncate_truncates_after_cleaning(self):
        """Test that truncation happens after cleaning, not before."""
        # "!!!hello!!!" cleans to "hello" (5 chars), truncate at 3
        result = clean_and_truncate("!!!hello!!!", max_length=3)
        assert result == "hel"

    def test_clean_and_truncate_preserves_truncation_boundary(self):
        """Test that text is truncated at exact boundary."""
        result = clean_and_truncate("abcdefghij", max_length=5)
        assert result == "abcde"
        assert len(result) == 5

    def test_clean_and_truncate_with_spaces_in_truncation(self):
        """Test truncation when it falls in the middle of a word."""
        # "hello world" cleaned remains "hello world" (11 chars), truncate at 7
        result = clean_and_truncate("hello world", max_length=7)
        assert result == "hello w"

    def test_clean_and_truncate_realworld_identifier(self):
        """Test cleaning and truncating a real-world identifier."""
        identifier = "YouTube_Video_dQw4w9WgXcQ_Published_Jan_15_2023_View_Count_10M_Likes_5K_Comments_1K"
        result = clean_and_truncate(identifier, max_length=50)
        assert len(result) <= 50
        assert "youtube" in result
        assert "video" in result
