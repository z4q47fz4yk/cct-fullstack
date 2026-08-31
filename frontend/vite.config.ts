import { fileURLToPath, URL } from 'node:url'

import { loadEnv } from 'vite'
import { defineConfig } from 'vite-plus'
import vue from '@vitejs/plugin-vue'
import VueRouter from 'vue-router/vite'
// import vize from '@vizejs/vite-plugin'
import vueDevTools from 'vite-plugin-vue-devtools'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // 仓库根 .env 由 scripts/worktree-env.sh 按 worktree 生成：
  // FRONTEND_PORT / DOCS_PORT / VITE_API_BASE —— 前端与后端共用同一份，
  // 保证端口一一对应、前端永远访问自己 worktree 的后端。
  const env = loadEnv(mode, '..', '')
  const frontendPort = Number(env.FRONTEND_PORT ?? 5173)
  const docsPort = Number(env.DOCS_PORT ?? 5174)
  const backendPort = Number(env.BACKEND_PORT ?? 8000)

  return {
    staged: {
      '*': 'vp check --fix',
    },
    fmt: {
      printWidth: 100,
      singleQuote: true,
      semi: false,
      tabWidth: 2,
      useTabs: false,
    },
    lint: {
      plugins: ['eslint', 'typescript', 'unicorn', 'oxc', 'vue'],
      categories: {
        correctness: 'error',
      },
      env: {
        browser: true,
        builtin: true,
      },
      ignorePatterns: ['**/dist/**', '**/dist-ssr/**', '**/coverage/**', '**/src/client/**'],
      rules: {
        '@typescript-eslint/ban-ts-comment': 'error',
        'no-array-constructor': 'error',
        '@typescript-eslint/no-empty-object-type': 'error',
        '@typescript-eslint/no-explicit-any': 'error',
        '@typescript-eslint/no-namespace': 'error',
        '@typescript-eslint/no-require-imports': 'error',
        '@typescript-eslint/no-unnecessary-type-constraint': 'error',
        '@typescript-eslint/no-unsafe-function-type': 'error',
      },
      overrides: [
        {
          files: ['**/*.ts', '**/*.tsx', '**/*.mts', '**/*.cts', '**/*.vue'],
          rules: {
            'constructor-super': 'off',
            'getter-return': 'off',
            'no-class-assign': 'off',
            'no-const-assign': 'off',
            'no-dupe-class-members': 'off',
            'no-dupe-keys': 'off',
            'no-func-assign': 'off',
            'no-import-assign': 'off',
            'no-new-native-nonconstructor': 'off',
            'no-obj-calls': 'off',
            'no-redeclare': 'off',
            'no-setter-return': 'off',
            'no-this-before-super': 'off',
            'no-undef': 'off',
            'no-unreachable': 'off',
            'no-unsafe-negation': 'off',
            'no-var': 'error',
            'no-with': 'off',
            'prefer-const': 'error',
            'prefer-rest-params': 'error',
            'prefer-spread': 'error',
          },
        },
      ],
      // TODO: 解决 lint 问题
      options: {
        typeAware: true,
        typeCheck: true,
      },
    },
    plugins: [
      VueRouter({
        routesFolder: 'src/pages',
        dts: './typed-router.d.ts',
      }),
      vue(),
      vueDevTools(),
      tailwindcss(),
    ],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
        '@site': fileURLToPath(new URL('./site.config.ts', import.meta.url)),
      },
    },
    // 读取仓库根 .env（含 VITE_API_BASE），使其进入 import.meta.env 供客户端使用
    envDir: '..',
    server: {
      // 端口由 worktree 的根 .env 决定；strictPort 冲突即报错，避免配对静默漂移
      port: frontendPort,
      strictPort: true,
      proxy: {
        // 同源 /api：浏览器只访问前端端口，不需要 CORS；反代到本 worktree 后端（BACKEND_PORT）。
        // 后端路由本身不带 /api 前缀（OpenAPI 契约不变），此处剥离后转发——
        // 与部署环境 nginx `location /api { proxy_pass http://backend:8000/; }` 同构。
        '/api': {
          target: `http://localhost:${backendPort}`,
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api/, ''),
        },
        // L1 同源双构建：/docs/ 代理到 VitePress dev server（见 scripts/dev-docs.sh）
        '/docs': `http://localhost:${docsPort}`,
      },
    },
    test: {
      alias: {
        '@/': new URL('./src', import.meta.url).pathname,
      },
    },
  }
})
