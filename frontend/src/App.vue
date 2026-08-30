<script setup lang="ts">
import { RouterView } from 'vue-router'
import { Toaster } from 'vue-sonner'
import 'vue-sonner/style.css'
</script>

<template>
  <div class="min-h-screen bg-transparent">
    <RouterView v-slot="{ Component, route }">
      <KeepAlive :max="10">
        <component :is="Component" v-if="route.meta.keepAlive" />
      </KeepAlive>
      <component :is="Component" v-if="!route.meta.keepAlive" />
    </RouterView>
  </div>
  <!--
    vue-sonner 全局通知挂载点。
    必须挂载，否则现有 `toast()` 调用不会显示。
    PR1 修复：原 App.vue 缺失 Toaster，是真 P0 bug。
  -->
  <Toaster rich-colors position="top-center" />
</template>
