这是一个前后端分离项目。


## Git 合并规则

1. 通过 git rebase 消除重复
2. 使用 ff-only 合并到 main 分支

## 多 worktree 开发

1. 通过环境变量控制后端 CORS 策略（允许`*`），以适应前端的 Port 变化
2. 后端 OpenAPI 契约如有更改，前端需要重新生成对应客户端
