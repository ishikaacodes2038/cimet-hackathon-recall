from pydantic import BaseModel


class Lead(BaseModel):
    lead_id: str
    first_name: str
    phone: str
    email: str
    last_activity_date: str
    last_completed_step: str
    prefilled_fields: dict[str, str] = {}
