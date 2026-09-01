<script setup lang="ts">
/**
 * ResourceUsageEntryTabs - 历史 / 录入 / 统计 三 tab 切换
 *
 * 历史为默认主视图（展示全部来源批次）；录入为手动/日报统一录入入口。
 */
type TabKey = 'history' | 'entry' | 'statistics'

const activeTab = defineModel<TabKey>('activeTab', { required: true })

const tabs: Array<{ key: TabKey; label: string; icon: string }> = [
  { key: 'history', label: '历史', icon: 'history' },
  { key: 'entry', label: '录入', icon: 'edit_note' },
  { key: 'statistics', label: '统计', icon: 'bar_chart' },
]
</script>

<template>
  <div role="tablist" class="tabs tabs-boxed bg-base-200 self-start">
    <button
      v-for="t in tabs"
      :key="t.key"
      role="tab"
      type="button"
      class="tab gap-1"
      :class="{ 'tab-active': activeTab === t.key }"
      @click="activeTab = t.key"
    >
      <span class="material-symbols-outlined icon-sm">{{ t.icon }}</span>
      {{ t.label }}
    </button>
  </div>
</template>
