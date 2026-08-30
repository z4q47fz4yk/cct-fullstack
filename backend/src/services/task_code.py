"""任务编码生成服务

负责任务编码的自动生成，使用 PostgreSQL 序列保证并发安全。
"""

from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession


class TaskCodeService:
    """任务编码生成服务"""

    @staticmethod
    async def generate_task_code(session: AsyncSession) -> str:
        """自动生成任务编码 AUTO-{seq_num}

        使用 PostgreSQL 序列保证并发安全和高性能：
        - nextval() 是原子操作，无需额外锁
        - 不占用大量内存，不依赖表大小
        - 支持高并发场景

        参数:
            session: 数据库会话

        返回:
            str: 自动生成的任务编码，格式为 AUTO-{seq_num}
        """
        seq = (await session.exec(select(func.nextval("task_code_seq")))).one()
        return f"AUTO-{seq}"
