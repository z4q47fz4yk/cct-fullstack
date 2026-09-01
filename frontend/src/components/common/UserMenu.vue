<script setup lang="ts">
import { logout, useAuthUser } from '@/composables/useAuth'

const me = useAuthUser()
</script>

<template>
  <div v-if="me" class="flex items-center gap-2">
    <span class="material-symbols-outlined icon-md text-primary">account_circle</span>
    <div class="flex flex-col leading-tight text-sm">
      <span class="font-medium">{{ me.name }}</span>
      <span class="text-xs text-neutral-content">{{ me.role }}</span>
    </div>
    <button
      class="btn-ghost-outline btn-sm flex items-center gap-1 px-2 py-1 rounded-lg"
      type="button"
      title="退出登录"
      @click="logout"
    >
      <span class="material-symbols-outlined icon-md">logout</span>
    </button>
  </div>
</template>
