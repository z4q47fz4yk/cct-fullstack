<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useQuery } from '@pinia/colada'
import { useRoute, useRouter } from 'vue-router'

import { listAuthProvidersQuery } from '@/client/@pinia/colada.gen'
import type { ProviderInfo } from '@/client/types.gen'
import { ensureAuth } from '@/composables/useAuth'

definePage({ meta: { title: '登录' } })

const route = useRoute()
const router = useRouter()

const { data: providers, asyncStatus } = useQuery(() => ({
  ...listAuthProvidersQuery(),
  staleTime: 60_000,
}))

const errorCode = typeof route.query.error === 'string' ? route.query.error : ''
const errorDetail = typeof route.query.detail === 'string' ? route.query.detail : ''
const isDone = route.query.done === '1'

/** 后端错误 code → 兜底文案（正常情况 detail 已携带中文描述） */
const ERROR_FALLBACK: Record<string, string> = {
  INVALID_STATE: '本次登录请求无效，请重试',
  LOGIN_CANCELLED: '您已取消登录授权',
  TOKEN_EXCHANGE_FAILED: '第三方认证服务暂时不可用，请稍后重试',
  USERINFO_FAILED: '第三方认证服务暂时不可用，请稍后重试',
  REGISTRATION_DISABLED: '系统暂未开放自助注册，请联系管理员邀请加入',
  AUTH_FAILED: '登录失败，请稍后重试',
}

/**
 * 错误提示文案：仅当后端回调携带 error/detail（?error=&detail=）时展示。
 * 未登录被跳到本页（无 error 参数）时不展示错误，避免"登录失败"误导。
 * 语义区分：未登录 = 中性提示（见模板副标题）；登录失败 = 下方错误横幅。
 */
const errorText = computed(() => {
  if (errorDetail) return errorDetail
  if (errorCode) return ERROR_FALLBACK[errorCode] ?? '登录失败，请稍后重试'
  return ''
})

/** 登录成功后的回跳目标：优先 startLogin 时存入的 sessionStorage，其次 query.redirect */
function redirectTarget(): string {
  const saved = sessionStorage.getItem('auth_redirect')
  if (saved) {
    sessionStorage.removeItem('auth_redirect')
    return saved
  }
  const q = route.query.redirect
  return typeof q === 'string' && q ? q : '/'
}

function startLogin(provider: ProviderInfo): void {
  sessionStorage.setItem('auth_redirect', redirectTarget())
  // 整页跳转：由后端生成 state 并 302 至 Provider 授权页（回调自然回跳本页）
  window.location.assign(`/api/auth/${provider.name}/login`)
}

onMounted(async () => {
  // 回调成功回跳 done=1：确认会话已建立后进入目标页
  if (isDone && (await ensureAuth())) {
    await router.replace(redirectTarget())
  }
})
</script>

<template>
  <main class="min-h-screen flex items-center justify-center p-4">
    <section class="panel w-full max-w-sm p-6 flex flex-col gap-5">
      <div class="flex flex-col gap-1">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined icon-lg text-primary">construction</span>
          <h1 class="text-lg font-semibold">施工多目标优化平台</h1>
        </div>
        <p class="text-xs text-neutral-content">
          {{ errorCode ? '登录未完成，请重试或更换方式' : '未登录，请选择下方登录方式进入工作台' }}
        </p>
      </div>

      <div
        v-if="errorText"
        class="flex items-start gap-2 rounded-lg border border-error/30 bg-error/8 px-3 py-2 text-sm text-error"
        role="alert"
      >
        <span class="material-symbols-outlined icon-md shrink-0">error</span>
        <span>{{ errorText }}</span>
      </div>

      <div v-if="asyncStatus === 'loading'" class="flex flex-col gap-2">
        <div v-for="i in 2" :key="i" class="skeleton h-10 rounded-lg" />
      </div>

      <template v-else-if="providers && providers.length > 0">
        <div class="flex flex-col gap-2">
          <button
            v-for="p in providers"
            :key="p.name"
            type="button"
            class="btn btn-primary btn-block"
            @click="startLogin(p)"
          >
            <span class="material-symbols-outlined icon-md">login</span>
            {{ p.displayName }} 登录
          </button>
        </div>
        <p class="text-xs text-neutral-content">
          登录后即可进入工作台；未配置登录方式时可直接浏览公开内容
        </p>
      </template>

      <div v-else class="flex flex-col items-center gap-3 py-2 text-sm">
        <span class="material-symbols-outlined icon-lg text-neutral-content">lock</span>
        <p class="text-neutral-content">系统未配置第三方登录方式</p>
        <RouterLink class="btn btn-ghost btn-sm" to="/">返回首页</RouterLink>
      </div>
    </section>
  </main>
</template>
