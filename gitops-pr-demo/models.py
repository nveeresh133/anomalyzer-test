from pydantic import BaseModel


class RecommendationRequest(BaseModel):

    resource_name: str

    resource_type: str

    file_path: str

    field: str

    current_value: str

    recommended_value: str

    estimated_savings: str