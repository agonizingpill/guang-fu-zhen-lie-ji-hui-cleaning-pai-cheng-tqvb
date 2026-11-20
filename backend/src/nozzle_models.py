from datetime import date, datetime
from sqlalchemy import String, Float, ForeignKey, JSON, CheckConstraint, Date, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

class NozzleBatch(Base):
    __tablename__ = 'nozzle_batches'
    __table_args__ = (CheckConstraint('quantity>0'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_code: Mapped[str] = mapped_column(String(40), unique=True)
    nozzle_model: Mapped[str] = mapped_column(String(80))
    quantity: Mapped[int] = mapped_column()
    arrival_date: Mapped[date] = mapped_column(Date)
    # pending / released / void
    state: Mapped[str] = mapped_column(String(24), default='pending')
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    released_by: Mapped[str] = mapped_column(String(120), default='')
    released_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    voided_by: Mapped[str] = mapped_column(String(120), default='')
    voided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    void_reason: Mapped[str] = mapped_column(String(400), default='')

class NozzleUnit(Base):
    __tablename__ = 'nozzle_units'
    __table_args__ = (CheckConstraint('pressure_kpa>0 AND flow_lpm>=0'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('nozzle_batches.id'))
    serial: Mapped[str] = mapped_column(String(50), unique=True)
    pressure_kpa: Mapped[float] = mapped_column(Float)
    flow_lpm: Mapped[float] = mapped_column(Float)
    defect_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    # pass / defect / uncertain
    model_verdict: Mapped[str] = mapped_column(String(16), default='')
    review_decision: Mapped[str] = mapped_column(String(16), default='')
    review_note: Mapped[str] = mapped_column(String(400), default='')
    reviewed_by: Mapped[str] = mapped_column(String(120), default='')
    # pending / rejected / in_stock / issued / recall_required / quarantined / scrapped / voided
    status: Mapped[str] = mapped_column(String(24), default='pending')
    # 清点时据此区分未装退回与已经装用。
    installed: Mapped[bool] = mapped_column(default=False)
    issue_id: Mapped[int | None] = mapped_column(ForeignKey('nozzle_issues.id'), nullable=True)
    mission_id: Mapped[int | None] = mapped_column(ForeignKey('wash_missions.id'), nullable=True)
    permit_id: Mapped[int | None] = mapped_column(ForeignKey('work_permits.id'), nullable=True)

class NozzleIssue(Base):
    __tablename__ = 'nozzle_issues'
    __table_args__ = (CheckConstraint('quantity>0'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    permit_id: Mapped[int] = mapped_column(ForeignKey('work_permits.id'))
    mission_id: Mapped[int] = mapped_column(ForeignKey('wash_missions.id'))
    batch_id: Mapped[int] = mapped_column(ForeignKey('nozzle_batches.id'))
    quantity: Mapped[int] = mapped_column()
    request_id: Mapped[str] = mapped_column(String(64), unique=True)
    state: Mapped[str] = mapped_column(String(24), default='issued')
    issued_by: Mapped[str] = mapped_column(String(120), default='')
    issued_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class NozzleReturn(Base):
    """清点退回 / 召回。uninstalled 与 installed 必须分开登记。"""
    __tablename__ = 'nozzle_returns'
    __table_args__ = (CheckConstraint("kind IN ('uninstalled','installed')"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey('nozzle_units.id'), unique=True)
    issue_id: Mapped[int | None] = mapped_column(ForeignKey('nozzle_issues.id'), nullable=True)
    kind: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(String(400), default='')
    # pending_resolution / restocked / scrapped
    state: Mapped[str] = mapped_column(String(24), default='pending_resolution')
    resolution: Mapped[str] = mapped_column(String(400), default='')
    request_id: Mapped[str] = mapped_column(String(64), unique=True)
    recorded_by: Mapped[str] = mapped_column(String(120), default='')
    recorded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_by: Mapped[str] = mapped_column(String(120), default='')
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class NozzleReplacement(Base):
    __tablename__ = 'nozzle_replacements'
    __table_args__ = (CheckConstraint('quantity>0'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    return_id: Mapped[int] = mapped_column(ForeignKey('nozzle_returns.id'), unique=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey('nozzle_units.id'))
    batch_id: Mapped[int] = mapped_column(ForeignKey('nozzle_batches.id'))
    mission_id: Mapped[int] = mapped_column(ForeignKey('wash_missions.id'))
    permit_id: Mapped[int] = mapped_column(ForeignKey('work_permits.id'))
    quantity: Mapped[int] = mapped_column(default=1)
    request_id: Mapped[str] = mapped_column(String(64), unique=True)
    issued_by: Mapped[str] = mapped_column(String(120), default='')
    issued_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
