"""SubTask — one tool call step within a ConversationTask's chain.

Each ConversationTask can have 0..N subtasks, each mapping to one
ToolchainLink. The readiness state machine lives here:

    pending → ready (params populated from previous step) → running → done | error

The chain planner creates subtasks when it plans a chain. The
ChainedAssistant reads/writes subtask state during execution.
"""

from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from auth.models import Base, _uuid, _now


class SubTask(Base):
    __tablename__ = "subtasks"

    id = Column(String(36), primary_key=True, default=_uuid)
    task_id = Column(
        String(36),
        ForeignKey("conversation_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_number = Column(Integer, nullable=False)  # 1-indexed
    tool_name = Column(String(128), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    params_json = Column(JSON, nullable=True)   # resolved params (None = not ready yet)
    result_json = Column(JSON, nullable=True)   # tool result after execution
    param_map = Column(JSON, nullable=True)     # original $step_N.field specs from planner
    created_at = Column(DateTime(timezone=True), default=_now)

    task = relationship("ConversationTask", backref="subtasks")

    @property
    def ready(self) -> bool:
        return self.params_json is not None and self.status == "ready"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "step_number": self.step_number,
            "tool_name": self.tool_name,
            "status": self.status,
            "params": self.params_json,
            "result": self.result_json,
            "param_map": self.param_map,
        }
