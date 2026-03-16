"""Analytics agent for processing natural language analytics queries."""

from typing import Dict, Optional
import json
from agents import CodeInterpreterTool, Agent, ModelSettings, TResponseInputItem, Runner, RunConfig, trace
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, field_validator
from app.agents.base import BaseAgent
from app.config import settings
from app.logging import get_logger
from app.tools.analytics_tools import AnalyticsTools

logger = get_logger(__name__)

code_interpreter = CodeInterpreterTool(tool_config={
  "type": "code_interpreter",
  "container": {
    "type": "auto",
    "file_ids": [
      "file-U27nohfaSQspmwAGpdbhKH",
      "file-GHT4TfF8fjNjizcHuJBz9W"
    ]
  }
})
class AnalyticsAgentSchema__ResultDataItem(BaseModel):
  platform: str
  content: str
  title: str
  published_at: Optional[str] = None
  views: str

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
  resolved_context: str
  result_data: list[AnalyticsAgentSchema__ResultDataItem]
  insight_summary: str
  verification: str


analytics_agent = Agent(
  name="Analytics Agent",
  instructions="""### Role
    You are the \"TNN Content Analytics Pro.\" You provide verified, data-driven insights from normalized social media performance exports. You communicate exclusively via structured JSON.

    ### Operational Guidelines
    1. **Mandatory Code Execution**: For any numeric, ranking, or temporal question, you MUST use the Python Code Interpreter. 
    2. **Context Persistence**: 
      - Maintain the 'canonical_id' or cleaned 'content' or label snippet in your internal memory to handle follow-up questions.
      - When context is implied (e.g., \"that video\"), filter the dataframe using the previously identified identifier from the conversation history.
    3. **Fuzzy & Canonical Matching (Link/Hashtag Mitigation)**:
      - Social platforms often append different links or CTAs to the same content.
      - When grouping or matching, you MUST implement a Python function to clean the 'content' column:
        - Remove URLs (http/https).
        - Remove common signatures like \"Follow us on...\", \"Like us on...\", or \"All the latest news...\".
        - Strip whitespace and newlines.
      - Match content based on the first 100 characters of this cleaned text or use a similarity ratio > 0.85 to ensure cross-platform videos are linked correctly.

    ### Normalized Column Mapping (LOWER_SNAKE_CASE)
    - **Time**: `published_at`
    - **Subject**: `content`, `title`, `description`
    - **Identity**: `content_id`, `canonical_id`
    - **Metrics**: `video_view_count`, `media_views`, `total_reach`, `total_interactions`, `total_impressions`
    - **Categories**: `platform`, `content_type`, `media_type`, `labels`

    ### Handling Specific Queries
    - **Best day to publish**: 
      - Python: Convert `published_at` to datetime, extract `day_name()`, and group by it to find the mean of `video_view_count`.
    - **Top video featuring [Topic]**:
      - Python: Use the cleaning function above. Filter by keyword, group by the cleaned content string, sum `video_view_count`, and sort descending.
    - **Cross-platform breakdown**: 
      - Python: Identify the target video via its cleaned content snippet, then group the original matches by `platform` to show the distribution of views.

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
    code_interpreter
  ],
  output_type=AnalyticsAgentSchema,
  model_settings=ModelSettings(
    temperature=1,
    top_p=1,
    max_tokens=2048,
    store=True
  )
)
