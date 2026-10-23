from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    user_name: str | None = None  # who did it: the person's name, or "Admin" for a login without a profile
    action: str
    entity_type: str | None
    entity_id: int | None
    description: str | None
    ip_address: str | None
    created_at: datetime
