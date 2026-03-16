from pydantic import BaseModel

class IntentSchema(BaseModel):
    intent: str # query_metrics, analytics, ingestion, tagging, document_qa, general