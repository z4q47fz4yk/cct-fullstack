/**
 * 分页约定（与后端对齐）
 *
 * 后端统一 page(1基) + per_page，上限 1000（超出返回 422）。
 * 量级约定：任务/资源/图表/措施/优化记录等均 < 1000，
 * 列表页用 FETCH_ALL_PAGE_SIZE 一次拉全量、客户端本地筛选；
 * 用量历史虽然可能上万，但列表端点不分页——按筛选窗口（默认最近 3 天）
 * 全量返回，前端按 (usage-date, batch-id) 分块展示，故无需 page/per_page。
 */
export const FETCH_ALL_PAGE_SIZE = 1000
