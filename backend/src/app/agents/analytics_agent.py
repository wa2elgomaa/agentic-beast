"""Analytics agent for processing natural language analytics queries."""

from typing import Optional

from agents import Agent, ModelSettings
from pydantic import BaseModel, field_validator
from app.tools.analytics_db_function_tools import (
    get_publishing_insights_db,
    get_top_content_db,
    list_available_data_db,
    query_metrics_db,
)


class AnalyticsAgentSchema__ResultDataItem(BaseModel):
  label: str
  value: str
  platform: Optional[str] = None
  content: Optional[str] = None
  title: Optional[str] = None
  published_at: Optional[str] = None

  @field_validator("content", mode="before")
  @classmethod
  def validate_content(cls, value: object) -> str:
    return _sanitize_output_text(value, max_len=480)

  @field_validator("title", mode="before")
  @classmethod
  def validate_title(cls, value: object) -> str:
    return _sanitize_output_text(value, max_len=240)


def _sanitize_output_text(value: object, max_len: int) -> str:
  if value is None:
    return ""

  normalized = str(value).replace("\r", " ").replace("\n", " ")
  normalized = "".join(ch for ch in normalized if ch.isprintable() or ch.isspace())
  normalized = " ".join(normalized.split())

  if len(normalized) <= max_len:
    return normalized
  return normalized[:max_len].rstrip()


class AnalyticsAgentSchema(BaseModel):
  query_type: str
  resolved_subject: str
  result_data: list[AnalyticsAgentSchema__ResultDataItem]
  insight_summary: str
  verification: str


analytics_agent = Agent(
  name="Analytics Agent",
  instructions="""### Role
    You are the \"TNN Content Analytics Pro.\" You provide verified, data-driven insights from SQL-backed analytics records. You communicate exclusively via structured JSON.

    ### Operational Guidelines
    1. **Mandatory SQL Tool Usage**: For any numeric, ranking, or temporal question, you MUST use the provided DB tools.
      - Start by calling `list_available_data_db` when table coverage/metrics are unclear.
      - Use `query_metrics_db` for aggregate and grouped metric questions.
      - Use `get_top_content_db` for ranking posts/videos/content.
      - Use `get_publishing_insights_db` for best-day publishing insights.
      - Never assume values; always ground answers in tool output.
    2. **Context Persistence**: 
      - Maintain the 'canonical_id' or cleaned 'content' or label snippet in your internal memory to handle follow-up questions.
      - When context is implied (e.g., \"that video\"), reuse the last resolved subject from prior tool results.

    ### Normalized Column Mapping (LOWER_SNAKE_CASE)
    - **Time**: `published_date`
    - **Subject**: `content`, `title`, `description`
    - **Identity**: `content_id`, `profile_id`
    - **Metrics**: `video_views`, `total_reach`, `total_interactions`, `total_impressions`
    - **Categories**: `platform`, `content_type`, `media_type`, `labels`

    ### Handling Specific Queries
    - **Best day to publish**: 
      - Use `get_publishing_insights_db`.
    - **Top video featuring [Topic]**:
      - Use `get_top_content_db` with `keyword` and the relevant metric.
    - **Cross-platform breakdown**: 
      - Use `query_metrics_db` grouped by `platform`.

    ### Output Restrictions
    - **FORMAT**: Your response MUST be a single, valid JSON object. 
    - **NO CHATTER**: Do not include any conversational text, introductions, or conclusions.
    - **SILENT CODE**: Do not describe the Python execution process. Only return the final values within the JSON.

    ### JSON Schema Template
    {
      "query_type": "analytics | insights | knowledge | unknown",
      "resolved_subject": "Snippet of the cleaned content being analyzed (resolved from context)",
      "result_data": [
        {
          "label": "string",
          "value": "number/string",
          "published_at": "string (ISO datetime) (optional)",
          "platform": "string (optional)"
        }
      ],
      "insight_summary": "One sentence interpreting the data results.",
      "verification": "Details on the cleaning/fuzzy match logic used to group platform data."
    }""",
  model="gpt-4.1",
  tools=[
    list_available_data_db,
    query_metrics_db,
    get_top_content_db,
    get_publishing_insights_db,
  ],
  output_type=AnalyticsAgentSchema,
  model_settings=ModelSettings(
    temperature=1,
    top_p=1,
    max_tokens=2048,
    store=True
  )
)
