from pydantic import BaseModel, Field
from typing import Optional, List, Dict

class TelemetryDevice(BaseModel):
    ip: str
    status: str
    detail: Optional[str] = None
    metrics: Dict[str, str] = Field(default_factory=dict)

class TelemetryPayload(BaseModel):
    site_name: str
    devices: List[TelemetryDevice]
