"""Tests for deduplication strategy application during ingestion."""

import pytest
from app.services.ingestion_service import IngestionService


@pytest.fixture
def ingestion_service():
    """Create ingestion service instance without database."""
    # Create a minimal service instance for testing strategy logic
    # This doesn't require database access for unit tests
    service = object.__new__(IngestionService)
    return service


class TestApplyDedupStrategies:
    """Test deduplication strategy application."""

    def test_apply_strategy_subtract_delta_calculation(self, ingestion_service):
        """Test subtract strategy calculates delta: new - prev."""
        dedup_config = {
            "default_strategy": "subtract",
            "field_strategies": {},
            "is_metric": {
                "video_views": True,
                "total_reach": True,
            }
        }

        existing_data = {
            "video_views": 100,
            "total_reach": 500,
            "title": "Test Post"
        }

        row_data = {
            "video_views": 150,  # new value
            "total_reach": 600,  # new value
            "title": "Test Post Updated"
        }

        result = ingestion_service._apply_dedup_strategies(row_data, existing_data, dedup_config)

        # Should calculate delta
        assert result["video_views"] == 50  # 150 - 100
        assert result["total_reach"] == 100  # 600 - 500
        assert result["title"] == "Test Post Updated"  # unchanged

    def test_apply_strategy_keep_replaces_with_new_value(self, ingestion_service):
        """Test keep strategy uses new value only."""
        dedup_config = {
            "default_strategy": "keep",
            "field_strategies": {},
            "is_metric": {
                "total_followers": True,
            }
        }

        existing_data = {
            "total_followers": 1000,
        }

        row_data = {
            "total_followers": 1050,  # new value
        }

        result = ingestion_service._apply_dedup_strategies(row_data, existing_data, dedup_config)

        # Should keep new value
        assert result["total_followers"] == 1050

    def test_apply_strategy_add_cumulative_sum(self, ingestion_service):
        """Test add strategy sums values: new + prev."""
        dedup_config = {
            "default_strategy": "add",
            "field_strategies": {},
            "is_metric": {
                "total_impressions": True,
            }
        }

        existing_data = {
            "total_impressions": 5000,
        }

        row_data = {
            "total_impressions": 3000,
        }

        result = ingestion_service._apply_dedup_strategies(row_data, existing_data, dedup_config)

        # Should sum values
        assert result["total_impressions"] == 8000  # 5000 + 3000

    def test_apply_strategy_sum_same_as_add(self, ingestion_service):
        """Test sum strategy works same as add."""
        dedup_config = {
            "default_strategy": "sum",
            "field_strategies": {},
            "is_metric": {
                "comments": True,
            }
        }

        existing_data = {
            "comments": 50,
        }

        row_data = {
            "comments": 30,
        }

        result = ingestion_service._apply_dedup_strategies(row_data, existing_data, dedup_config)

        # Should sum values (same as add)
        assert result["comments"] == 80  # 50 + 30

    def test_apply_strategy_skip_removes_field(self, ingestion_service):
        """Test skip strategy removes field from row_data."""
        dedup_config = {
            "default_strategy": "skip",
            "field_strategies": {},
            "is_metric": {
                "engagements": True,
            }
        }

        existing_data = {
            "engagements": 200,
            "title": "Post"
        }

        row_data = {
            "engagements": 250,
            "title": "Post Title"
        }

        result = ingestion_service._apply_dedup_strategies(row_data, existing_data, dedup_config)

        # Should remove field
        assert "engagements" not in result
        assert result["title"] == "Post Title"

    def test_apply_strategy_field_override(self, ingestion_service):
        """Test per-field strategy override."""
        dedup_config = {
            "default_strategy": "subtract",
            "field_strategies": {
                "video_views": "keep",  # override: keep instead of subtract
                "total_followers": "add",  # override: add instead of subtract
            },
            "is_metric": {
                "video_views": True,
                "total_followers": True,
                "comments": True,
            }
        }

        existing_data = {
            "video_views": 100,
            "total_followers": 1000,
            "comments": 50,
        }

        row_data = {
            "video_views": 150,
            "total_followers": 1100,
            "comments": 60,
        }

        result = ingestion_service._apply_dedup_strategies(row_data, existing_data, dedup_config)

        # Field overrides should apply
        assert result["video_views"] == 150  # keep: use new value
        assert result["total_followers"] == 2100  # add: 1000 + 1100
        assert result["comments"] == 10  # subtract (default): 60 - 50

    def test_apply_strategy_non_metric_fields_unchanged(self, ingestion_service):
        """Test non-metric fields are not affected by strategies."""
        dedup_config = {
            "default_strategy": "subtract",
            "field_strategies": {},
            "is_metric": {
                "video_views": True,
            }
        }

        existing_data = {
            "video_views": 100,
            "title": "Old Title",
            "description": "Old Description",
        }

        row_data = {
            "video_views": 150,
            "title": "New Title",
            "description": "New Description",
        }

        result = ingestion_service._apply_dedup_strategies(row_data, existing_data, dedup_config)

        # Only metric field affected
        assert result["video_views"] == 50  # subtract applied
        assert result["title"] == "New Title"  # unchanged
        assert result["description"] == "New Description"  # unchanged

    def test_apply_strategy_missing_field_in_existing(self, ingestion_service):
        """Test strategy when field missing in existing data."""
        dedup_config = {
            "default_strategy": "add",
            "field_strategies": {},
            "is_metric": {
                "shares": True,
            }
        }

        existing_data = {
            # shares not in existing
        }

        row_data = {
            "shares": 100,
        }

        result = ingestion_service._apply_dedup_strategies(row_data, existing_data, dedup_config)

        # Should skip if not in existing
        assert "shares" in row_data
        assert row_data["shares"] == 100

    def test_apply_strategy_non_numeric_values_skipped(self, ingestion_service):
        """Test non-numeric metric values are skipped."""
        dedup_config = {
            "default_strategy": "subtract",
            "field_strategies": {},
            "is_metric": {
                "video_views": True,
            }
        }

        existing_data = {
            "video_views": "100 views",  # non-numeric
        }

        row_data = {
            "video_views": "150 views",  # non-numeric
        }

        result = ingestion_service._apply_dedup_strategies(row_data, existing_data, dedup_config)

        # Should skip non-numeric values
        assert result["video_views"] == "150 views"

    def test_apply_strategy_zero_values(self, ingestion_service):
        """Test strategy application with zero values."""
        dedup_config = {
            "default_strategy": "subtract",
            "field_strategies": {},
            "is_metric": {
                "comments": True,
            }
        }

        existing_data = {
            "comments": 0,  # no previous comments
        }

        row_data = {
            "comments": 50,  # 50 new comments
        }

        result = ingestion_service._apply_dedup_strategies(row_data, existing_data, dedup_config)

        # Should calculate correctly with zeros
        assert result["comments"] == 50  # 50 - 0

    def test_apply_strategy_no_config_returns_unchanged(self, ingestion_service):
        """Test no dedup config returns row_data unchanged."""
        existing_data = {
            "video_views": 100,
        }

        row_data = {
            "video_views": 150,
        }

        result = ingestion_service._apply_dedup_strategies(row_data, existing_data, None)

        # Should return unchanged
        assert result == row_data
        assert result["video_views"] == 150

    def test_apply_strategy_mixed_numeric_values(self, ingestion_service):
        """Test mixed int and float values."""
        dedup_config = {
            "default_strategy": "add",
            "field_strategies": {},
            "is_metric": {
                "clicks": True,  # float compatible metric
                "total_reach": True,  # int metric
            }
        }

        existing_data = {
            "clicks": 100,  # int
            "total_reach": 1000,  # int
        }

        row_data = {
            "clicks": 150,  # int - should become 250 (add)
            "total_reach": 1500,  # int - should become 2500 (add)
        }

        result = ingestion_service._apply_dedup_strategies(row_data, existing_data, dedup_config)

        # Should handle mixed metrics with add strategy
        assert result["clicks"] == 250  # 100 + 150
        assert result["total_reach"] == 2500  # 1000 + 1500

    def test_apply_strategy_complex_scenario(self, ingestion_service):
        """Test complex scenario with multiple strategies."""
        dedup_config = {
            "default_strategy": "subtract",
            "field_strategies": {
                "total_followers": "keep",
                "total_impressions": "add",
                "shares": "skip",
            },
            "is_metric": {
                "video_views": True,
                "total_followers": True,
                "total_impressions": True,
                "shares": True,
                "comments": True,
            }
        }

        existing_data = {
            "video_views": 1000,
            "total_followers": 5000,
            "total_impressions": 50000,
            "shares": 100,
            "comments": 200,
            "title": "Analytics Post",
        }

        row_data = {
            "video_views": 1500,
            "total_followers": 5500,
            "total_impressions": 55000,
            "shares": 150,
            "comments": 250,
            "title": "Analytics Post Updated",
        }

        result = ingestion_service._apply_dedup_strategies(row_data, existing_data, dedup_config)

        # Check each strategy application
        assert result["video_views"] == 500  # subtract: 1500 - 1000
        assert result["total_followers"] == 5500  # keep: 5500
        assert result["total_impressions"] == 105000  # add: 50000 + 55000
        assert "shares" not in result  # skip: removed
        assert result["comments"] == 50  # subtract: 250 - 200
        assert result["title"] == "Analytics Post Updated"  # non-metric unchanged
