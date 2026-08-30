"""任务服务模块（已拆分）

此模块原有的 TaskService 已拆分为以下专用服务：
- TaskCodeService (src/services/task_code.py): 任务编码生成
- TaskDependencyService (src/services/task_dependency.py): 依赖图算法
- TaskSchedulerService (src/services/task_scheduler.py): 关键路径计算
- TaskAssembler (src/services/task_assembler.py): 响应组装

请使用新的专用服务类，而非此模块中已移除的 TaskService。
"""
