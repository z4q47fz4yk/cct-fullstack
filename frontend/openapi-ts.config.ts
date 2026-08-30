import { defineConfig } from '@hey-api/openapi-ts'

export default defineConfig({
  // 从入库的契约快照（仓库根 openapi.json，由 scripts/openapi-export.sh 导出）离线生成，
  // 无需运行后端；快照与后端代码的一致性由 scripts/check-contract.sh 保证。
  input: '../openapi.json',
  output: { path: 'src/client', postProcess: ['oxlint', 'oxfmt'] },
  plugins: [
    '@hey-api/typescript',
    {
      name: '@hey-api/sdk',
      operations: {
        strategy: 'byTags',
      },
      validator: 'valibot',
    },
    {
      name: 'valibot',
      definitions: true,
      requests: false,
      responses: false,
      includeInEntry: (s) => {
        return s.name.endsWith('Create') || s.name.endsWith('Update')
      },
    },
    {
      name: '@hey-api/client-ky',
      runtimeConfigPath: '@/hey-api.ts',
    },
    {
      name: '@pinia/colada',
      queryKeys: true,
      mutationOptions: true,
    },
  ],
})
