<script setup lang="ts">
/**
 * InfoTooltip - 悬停/聚焦显示说明文字的轻量气泡
 *
 * 基于 Vuetify0 无样式 Tooltip（原生 popover + CSS anchor positioning）：
 * - 内容渲染在浏览器 top layer，不受父级 `overflow` 裁剪，也无需调 z-index；
 * - 触发器可聚焦（`tabindex="0"`），正文经 `aria-describedby` 关联，键盘与读屏可达；
 *   焦点进入时立即显示（不等待延迟），`Esc` / 失焦关闭；
 * - 打开延迟由全局插件统一下发（500ms，见 `src/plugins/vuetify0.ts`），
 *   相邻气泡在预热窗口内即时打开，故本组件不逐个配置延迟。
 *
 * 皮肤类 `tooltip-trigger` / `tooltip-surface` 定义在 `src/assets/components.css`。
 */
import { Tooltip } from '@vuetify/v0'

interface Props {
  /** 气泡正文（纯文本，Vue 自动转义）；空值应由调用方降级，不渲染本组件 */
  content: string
}

const { content } = defineProps<Props>()

// 根是 Tooltip.Root（renderless，内部插槽含 Activator + Content 两个节点），
// 不禁用自动继承会触发 Vue「fragment root 无法继承属性」告警，故显式转发给触发器。
defineOptions({ inheritAttrs: false })
</script>

<template>
  <Tooltip.Root>
    <Tooltip.Activator as="span" tabindex="0" class="tooltip-trigger" v-bind="$attrs">
      <slot />
    </Tooltip.Activator>
    <Tooltip.Content class="tooltip-surface">{{ content }}</Tooltip.Content>
  </Tooltip.Root>
</template>
