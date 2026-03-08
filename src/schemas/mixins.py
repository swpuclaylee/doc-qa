from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TimestampMixin(BaseModel):
    """时间戳混入"""

    created_at: datetime
    updated_at: datetime


class IDMixin(BaseModel):
    """主键混入"""

    id: int


class ORMConfigMixin(BaseModel):
    """ORM 配置混入"""

    model_config = ConfigDict(from_attributes=True)
