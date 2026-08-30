import { defineConfig } from '@hey-api/openapi-ts'

export default defineConfig({
  input: 'http://localhost:8000/openapi.json',
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
