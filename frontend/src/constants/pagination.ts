/**
 * 分页约定（与后端对齐）
 *
 * 后端统一 page(1基) + per_page，上限 1000（超出返回 422）。
 * 量级约定：任务/资源/图表/措施/优化记录等均 < 1000，
 * 列表页用 FETCH_ALL_PAGE_SIZE 一次拉全量、客户端本地筛选；
 * 用量历史是唯一可能上万的表，走真分页（page/pageSize 由页面控制）。
 */
export const FETCH_ALL_PAGE_SIZE = 1000
