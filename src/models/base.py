from sqlalchemy import Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    所有 ORM 模型的基类

    DeclarativeBase 是 SQLAlchemy 2.0 的声明式基类
    所有模型都需要继承此类才能被 ORM 识别
    """

    # 所有模型默认都有自增主键 id
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="主键 ID"
    )
