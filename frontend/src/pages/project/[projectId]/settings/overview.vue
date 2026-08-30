<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ErrorState from '@/components/common/ErrorState.vue'
import ProjectOverviewCards from '@/components/project-overview/ProjectOverviewCards.vue'
import EmissionByCategoryChart from '@/components/project-overview/EmissionByCategoryChart.vue'
import { useCarbonStats } from '@/composables/useCarbonStats'
import { useDiagnosticsApi } from '@/composables/useDiagnosticsApi'
import { notifyInfo } from '@/composables/useToast'

definePage({
  meta: {
    title: '碳排放总览',
    description: '项目实际碳排放概览',
    icon: 'dashboard',
    showInNav: true,
    parentName: '/project/[projectId]/settings',
    navOrder: 1,
  },
})

const {
  totalEmissionKg,
  totalEmissionTon,
  totalMonths,
  totalResources,
  byCategory,
  isLoading,
  isNotFound,
  error,
  refresh,
} = useCarbonStats()

// ─── 数据体检提示（被动入口：仅存在零碳因子警告时显示，可关闭） ───
const diagBannerDismissed = ref(false)
const { zeroFactorCount: diagZeroFactorCount } = useDiagnosticsApi(() => 'ACTUAL')

// ─── 404 处理 ──────────────────────────────────────────────
const router = useRouter()
const route = useRoute()
const navigating = ref(false)

const projectId = computed(() => (route.params as { projectId?: string }).projectId ?? '')

// 404 时显示提示并跳转到「分析洞察」
watch(isNotFound, async (notFound) => {
  if (notFound && !navigating.value) {
    navigating.value = true
    notifyInfo({
      title: '该项目暂无碳排放数据',
      description: '已为您跳转到分析洞察',
    })
    // 短暂延迟让用户看到 toast
    await new Promise((resolve) => setTimeout(resolve, 1200))
    await router.replace(`/project/${projectId.value}/insights`)
  }
})
</script>

<template>
  <!-- 加载中：骨架屏 -->
  <div v-if="isLoading" class="space-y-4">
    <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
      <div v-for="i in 3" :key="i" class="panel">
        <div class="flex-row items-center justify-between px-5 py-4">
          <div class="space-y-2">
            <div class="skeleton h-3 w-16"></div>
            <div class="skeleton h-7 w-24"></div>
          </div>
          <div class="skeleton h-10 w-10 rounded-xl"></div>
        </div>
      </div>
    </div>
    <div class="panel">
      <div class="p-4">
        <div class="skeleton mb-4 h-4 w-32"></div>
        <div class="skeleton h-80 w-full"></div>
      </div>
    </div>
  </div>

  <!-- 错误（非 404） -->
  <ErrorState
    v-else-if="error && !isNotFound"
    title="加载失败"
    description="无法获取碳排放数据，请检查网络连接"
    @retry="refresh"
  />

  <!-- 正常内容 -->
  <template v-else>
    <!-- 数据体检提示条（可关闭，不阻断） -->
    <div
      v-if="diagZeroFactorCount > 0 && !diagBannerDismissed"
      class="panel px-4 py-3 flex items-center gap-3"
    >
      <span class="material-symbols-outlined text-warning icon-sm shrink-0">
        health_and_safety
      </span>
      <p class="text-xs text-fg-muted flex-1">
        数据体检发现 {{ diagZeroFactorCount }} 种有使用记录的资源碳排放因子为
        0，其用量不计入本页碳排统计。
      </p>
      <RouterLink
        :to="`/project/${projectId}/settings/diagnostics`"
        class="link link-warning text-xs shrink-0"
      >
        查看体检
      </RouterLink>
      <button class="btn btn-ghost btn-xs shrink-0" @click="diagBannerDismissed = true">
        关闭
      </button>
    </div>

    <ProjectOverviewCards
      :total-emission-kg="totalEmissionKg"
      :total-emission-ton="totalEmissionTon"
      :total-months="totalMonths"
      :total-resources="totalResources"
      :loading="isLoading"
    />

    <EmissionByCategoryChart
      :by-category="byCategory"
      :total-emission-kg="totalEmissionKg"
      :loading="isLoading"
    />
  </template>
</template>
