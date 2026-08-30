"""任务响应组装工具

纯静态工具类，负责将 Task 模型转换为响应字典。
"""

from typing import Any

from src.models.task import Task
from src.schemas.task import TaskDependencyInfo


class TaskAssembler:
    """任务响应组装工具类"""

    @staticmethod
    def build_task_response(
        task: Task,
        is_critical: bool | None = None,
        predecessors: list[TaskDependencyInfo] | None = None,
    ) -> dict[str, Any]:
        """将 Task 模型转换为包含 is_critical 和 predecessors 的响应字典

        由于 is_critical 是动态计算的，不在数据库中存储，
        所以使用此方法构造响应数据。

        参数:
            task: 任务模型
            is_critical: 是否是关键任务；列表接口传入计算结果，
                单条接口不计算时传 None（响应中为 null）
            predecessors: 前置任务依赖列表，默认为空列表

        返回:
            dict: 任务响应字典
        """
        return {
            "id": task.id,
            "code": task.code,
            "name": task.name,
            "description": task.description or "",
            "duration": task.duration,
            "completed": task.completed,
            "createdAt": task.created_at,
            "updatedAt": task.updated_at,
            "isCritical": is_critical,
            "predecessors": predecessors or [],
        }
