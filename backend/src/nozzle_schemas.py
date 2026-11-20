from datetime import date
from typing import Literal
from pydantic import Field, field_validator
from .revisit_schemas import Inputs

class TrialInput(Inputs):
    serial: str = Field(min_length=1, max_length=50)
    pressure_kpa: float = Field(gt=0, le=2000)
    flow_lpm: float = Field(ge=0, le=100)

class BatchInput(Inputs):
    batch_code: str = Field(min_length=2, max_length=40)
    nozzle_model: str = Field(min_length=2, max_length=80)
    quantity: int = Field(ge=1, le=500)
    arrival_date: date
    trials: list[TrialInput] = Field(min_length=1, max_length=500)

class ReviewInput(Inputs):
    decision: Literal['pass', 'defect']
    note: str = Field(min_length=5, max_length=400)

class VoidInput(Inputs):
    reason: str = Field(min_length=5, max_length=400)

class IssueInput(Inputs):
    permit_id: int
    quantity: int = Field(ge=1, le=100)
    batch_id: int | None = None
    request_id: str = Field(min_length=4, max_length=64)

    @field_validator('request_id')
    @classmethod
    def nonempty(cls, v):
        if not v.strip():
            raise ValueError('请求号不能为空')
        return v.strip()

class ReturnInput(Inputs):
    unit_id: int
    kind: Literal['uninstalled', 'installed']
    note: str = Field(default='', max_length=400)
    request_id: str = Field(min_length=4, max_length=64)

class ResolveInput(Inputs):
    disposition: Literal['restock', 'scrap']
    resolution: str = Field(min_length=5, max_length=400)

class ReplacementInput(Inputs):
    return_id: int
    quantity: int = Field(default=1, ge=1, le=20)
    # 原批次撤销放行时，可从其他已放行批次补发。
    batch_id: int | None = None
    request_id: str = Field(min_length=4, max_length=64)
