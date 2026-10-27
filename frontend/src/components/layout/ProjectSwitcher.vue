<script setup lang="ts">
/**
 * ProjectSwitcher - 顶栏项目切换下拉（设计稿：当前项目 + 状态点 + 下拉列表）
 *
 * 纯导航交互：列出全部项目，点击切换到对应项目的工序管理页；
 * 「创建新项目」回到项目列表页（创建入口在项目列表页）。
 * 仅项目上下文中展示（项目列表页自身不显示）。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectApi } from '@/composables/useProjectApi'
import { useProjectContext } from '@/composables/useProjectContext'

const router = useRouter()
const { currentProjectId } = useProjectContext()
const { projects, isLoading } = useProjectApi()

const open = ref(false)
const root = ref<HTMLElement | null>(null)

const currentProject = computed(
  () => projects.value.find((p) => p.id === currentProjectId.value) ?? null,
)

function onDocClick(e: MouseEvent) {
  if (root.value && !root.value.contains(e.target as Node)) open.value = false
}

onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))

function switchTo(projectId: number) {
  open.value = false
  if (projectId === currentProjectId.value) return
  void router.push(`/project/${projectId}/schedule`)
}

function goCreate() {
  open.value = false
  void router.push('/')
}
</script>

<template>
  <div ref="root" class="proj-switcher relative">
    <button
      type="button"
      class="proj-trigger flex items-center gap-2 h-9 pl-3 pr-2.5 rounded-lg border border-panel-border bg-base-200 text-sm text-base-content max-w-64"
      :title="currentProject?.name ?? '切换项目'"
      @click="open = !open"
    >
      <span class="w-2 h-2 rounded-full bg-success shrink-0" />
      <span class="truncate font-medium">{{ currentProject?.name ?? `项目 ${currentProjectId}` }}</span>
      <span class="material-symbols-outlined icon-sm text-fg-subtle shrink-0" :class="{ 'rotate-180': open }">
        expand_more
      </span>
    </button>

    <div v-if="open" class="proj-menu">
      <div class="px-3 pt-2.5 pb-1.5 text-xs text-fg-subtle">切换项目</div>
      <div class="px-1.5 pb-1.5 max-h-72 overflow-y-auto scrollbar-thin">
        <div v-if="isLoading" class="px-3 py-2 text-xs text-fg-subtle">加载中…</div>
        <button
          v-for="p in projects"
          :key="p.id"
          type="button"
          class="proj-item"
          :class="{ on: p.id === currentProjectId }"
          @click="switchTo(p.id)"
        >
          <span class="material-symbols-outlined icon-sm shrink-0">folder</span>
          <span class="truncate">{{ p.name }}</span>
          <span
            v-if="p.id === currentProjectId"
            class="ml-auto material-symbols-outlined icon-sm text-primary shrink-0"
          >
            check
          </span>
        </button>
      </div>
      <div class="border-t border-base-300/60 p-1.5">
        <button type="button" class="proj-item" @click="goCreate">
          <span class="material-symbols-outlined icon-sm shrink-0 text-primary">add</span>
          <span class="text-primary">创建新项目</span>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.proj-trigger {
  transition:
    border-color 0.15s,
    box-shadow 0.15s;
}
.proj-trigger:hover {
  border-color: var(--color-primary);
}

/* 下拉菜单：设计稿 dropdown-menu 风格 */
.proj-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  min-width: 260px;
  padding: 0;
  border-radius: 10px;
  border: 1px solid var(--color-panel-border);
  background: var(--color-panel);
  box-shadow: var(--shadow-glass-3);
  z-index: 60;
  animation: proj-pop 0.15s var(--ease-soft, ease);
}
@keyframes proj-pop {
  from {
    opacity: 0;
    transform: translateY(-6px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

.proj-item {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  width: 100%;
  padding: 0.5rem 0.625rem;
  border-radius: 7px;
  font-size: 0.8125rem;
  color: var(--color-base-content);
  text-align: left;
  cursor: pointer;
}
.proj-item:hover {
  background: var(--color-base-200);
}
.proj-item.on {
  background: color-mix(in oklch, var(--color-primary) 10%, transparent);
  color: var(--color-primary);
  font-weight: 500;
}
</style>
