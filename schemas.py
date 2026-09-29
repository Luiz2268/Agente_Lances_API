from pydantic import BaseModel, Field
from typing import List, Optional, Literal

AgentStatus = Literal["desligado", "pronto", "executando", "pausado", "concluido", "erro"]

class Competitor(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    min_value: float = Field(gt=0)

class AgentConfig(BaseModel):
    initial_value: float = Field(gt=0)
    floor_value: float = Field(gt=0)
    decrement: float = Field(gt=0)
    interval_seconds: float = Field(default=2.0, ge=0.5, le=60)
    competitors: List[Competitor] = Field(default_factory=list)

class StatusResponse(BaseModel):
    status: AgentStatus
    authorized: bool
    mode: Literal["simulacao", "real"]
    current_value: Optional[float] = None
    last_bid: Optional[float] = None
    last_bidder: Optional[str] = None
    round: int = 0
    winner: Optional[str] = None
    final_price: Optional[float] = None
    message: Optional[str] = None

class ActionResponse(BaseModel):
    ok: bool
    status: StatusResponse
    message: str

class LogEntry(BaseModel):
    id: int
    created_at: str
    level: str
    event: str
    message: str
    data: dict = Field(default_factory=dict)
