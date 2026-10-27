<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import BasicLayout from '@/components/layout/BasicLayout.vue'

const route = useRoute()

/**
 * 全屏路由（如碳排数据看板大屏）：不套侧边栏/顶栏，页面占满视口。
 * 由路由 meta.fullscreen 标记。
 */
const isFullscreen = computed(() => Boolean(route.meta.fullscreen))
</script>

<template>
  <!-- 全屏页（大屏）：独立布局，无侧边栏 -->
  <RouterView v-if="isFullscreen" />
  <BasicLayout v-else>
    <RouterView />
  </BasicLayout>
</template>
