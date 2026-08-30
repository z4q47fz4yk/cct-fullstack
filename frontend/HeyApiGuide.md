# 使用自动生成的客户端

本项目使用 @hey-api/openapi-ts 从后端 `openapi.json` 中生成客户端。

## 项目配置

`openapi-ts` 的配置文件在 [`openapi-ts.config.ts`](./openapi-ts.config.ts)，该文件定义了 `openapi-ts` 工具如何生成客户端。
`openapi-ts` 的运行时配置，由上述配置文件指定，在 [`src/hey-api.ts`](./src/hey-api.ts) 中，确定了运行时发送 API 的 Base
URL。

## 客户端使用

openapi-ts 生成的客户端质量取决于后端提供的 `openapi.json` 文件的好坏。

使用客户端前，如果发现了 API 中有任何定义不清楚（比如返回 Any）、命名不规范（使用 snake 命名方式）等问题，停止代码生成并报告问题。
后端的错误不应该由前端承担。

良好的 openapi 文档能生成易于使用的客户端。
后端类型定义在 [types.gen.ts](./src/client/types.gen.ts)
中，前端可以直接使用，大多数时间无需任何转换。
前端没有必要对字段进行重命名，这没有意义。
只有在遇到领域建模、用户体验、业务规则时才可能需要自定义或派生一些类型。

`@pinia/colada` 是一款基于 pinia 状态管理库的工具，为我们简化了数据访问过程。
`useQeury` 返回的值与 pinia store 一样是一个响应式的 reactive 对象，`asyncStatus`, `refresh` 等简化了状态的管理、实现了防抖操作。
对于一些简单的情况，使用 colada 时，甚至可以不需要手动定义 pinia store!
