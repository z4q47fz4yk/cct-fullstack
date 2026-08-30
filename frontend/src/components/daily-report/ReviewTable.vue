<script setup lang="ts">
import { useDailyReportStoreV2 } from '@/stores/report'
import { computed, ref } from 'vue'
import type {
  MappingAction,
  ParsedResourceItem,
  ResourceCategory,
  ResourceCreate,
  ResourceMappingCreateItem,
} from '@/client'
import { categoryConfigMap } from '@/types/resource'
import ResourceForm from '@/components/resource/ResourceForm.vue'

function getCategoryIcon(category: string | undefined) {
  if (!category || !categoryConfigMap[category as keyof typeof categoryConfigMap]) {
    return 'help'
  }
  return categoryConfigMap[category as keyof typeof categoryConfigMap].icon
}

const store = useDailyReportStoreV2()

const resourceMap = computed(() => {
  const map: Map<string, ParsedResourceItem> = new Map()
  for (const item of store.parsedResourceItems) {
    map.set(item.resourceName, item)
  }
  return map
})

const isMappingItemChanged = computed<Map<string, boolean>>(() => {
  const map: Map<string, boolean> = new Map()
  for (const item of store.mappingChanges) {
    map.set(
      item.resourceName,
      store.mappingChanges.find((i) => i.resourceName == item.resourceName) != undefined,
    )
  }
  return map
})

const availableActions = computed<Map<string, MappingAction[]>>(() => {
  const map = new Map<string, MappingAction[]>()
  for (const item of store.parsedResourceItems) {
    map.set(
      item.resourceName,
      item.mappingStatus == 'EXACT_MATCH' ? ['SKIP', 'USE_EXISTING'] : ['SKIP', 'CREATE_NEW'],
    )
  }
  return map
})

const defaultResource = () => ({
  name: '',
  category: 'labor' as ResourceCategory,
  unit: '工日',
  unitPrice: 0,
  carbonFactor: 0,
  description: '',
})

const showResourceModal = ref(false)
const newResourceData = ref<ResourceCreate>(defaultResource())
const modelError = ref<string | undefined>(undefined)

function addOrReturnChangingItem(item: ResourceMappingCreateItem): ResourceMappingCreateItem {
  let mappingItem = store.mappingChanges.find((i) => i.resourceName === item.resourceName)
  if (!mappingItem) {
    mappingItem = {
      ...item,
      newResource: {
        ...defaultResource(),
        name: item.resourceName,
        category: resourceMap.value.get(item.resourceName)?.category || 'labor',
      },
    }
    store.mappingChanges.push(mappingItem)
  }
  return mappingItem
}

function addNewResource(item: ResourceMappingCreateItem) {
  const mappingItem = addOrReturnChangingItem(item)

  newResourceData.value = mappingItem.newResource!

  showResourceModal.value = true
}

function saveNewResource() {
  const mappingItem = store.mappingChanges.find((i) => i.resourceName == newResourceData.value.name)
  if (!mappingItem) {
    modelError.value = '请不要修改名称！'
    return
  }
  mappingItem.newResource = newResourceData.value
  mappingItem.action = 'CREATE_NEW'

  showResourceModal.value = false
}

function ignoreResource(item: ResourceMappingCreateItem) {
  const mappingItem = addOrReturnChangingItem(item)
  mappingItem.action = 'SKIP'
}
</script>

<template>
  <div class="panel p-0 h-full overflow-hidden">
    <div class="h-full overflow-x-auto">
      <table class="table h-full table-pin-rows">
        <thead>
          <tr>
            <th></th>
            <th>类别</th>
            <th>资源名称</th>
            <th>货物类别</th>
            <th class="table-num">资源用量</th>
            <th>单位</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody class="overflow-y-auto">
          <tr
            v-for="item in store.mappingDecision"
            :key="item.resourceName"
            :class="{ 'text-fg-subtle': item.action == 'SKIP' }"
            class="[&_span,&_button]:text-nowrap"
          >
            <!-- checkBox -->
            <td>
              <label class="">
                <input
                  type="checkbox"
                  class="checkbox checkbox-sm"
                  :class="{ 'checkbox-secondary': isMappingItemChanged.get(item.resourceName) }"
                  :checked="item.action != 'SKIP'"
                  @click.prevent
              /></label>
            </td>

            <!-- resourceName -->
            <td>
              <span class="material-symbols-outlined text-fg-muted">
                {{ getCategoryIcon(resourceMap.get(item.resourceName)?.category) }}
              </span>
            </td>
            <td>{{ item.resourceName }}</td>

            <!-- 货物类别（运输块） -->
            <td>
              <span v-if="item.cargo" class="badge badge-sm badge-info whitespace-nowrap">
                {{ item.cargo }}
              </span>
              <span v-else class="text-fg-subtle">—</span>
            </td>

            <!--数量编辑-->
            <td class="table-num">
              <div v-if="isMappingItemChanged.get(item.resourceName)" class="col-span-3">
                <input
                  type="number"
                  class="input input-sm py-0 w-16 text-right font-num"
                  v-model.number.lazy="
                    store.mappingChanges.find((i) => i.resourceName == item.resourceName)!.quantity
                  "
                />
              </div>
              <div v-else class="flex items-center justify-end gap-2">
                <span class="font-num">{{ item.quantity }}</span>
                <button
                  class="btn btn-ghost btn-circle btn-sm"
                  @click="addOrReturnChangingItem(item)"
                >
                  <span class="material-symbols-outlined icon-sm text-fg-muted"> edit</span>
                </button>
              </div>
            </td>

            <!--单位-->
            <td>
              <span>
                {{
                  resourceMap.get(item.resourceName)!.resourceUnit ||
                  store.mappingChanges.find((i) => i.resourceName == item.resourceName)?.newResource
                    ?.unit ||
                  '--'
                }}
              </span>
            </td>

            <!--状态-->
            <td class="[&>span]:flex [&_span]:items-center [&_span]:gap-2 text-xs!">
              <span v-if="item.action == 'SKIP'" class="text-neutral">
                <span class="material-symbols-outlined"> block </span>
                已忽略
              </span>
              <span v-else-if="item.action == 'USE_EXISTING'" class="text-primary">
                <span class="material-symbols-outlined"> check_circle </span>
                已匹配
              </span>
              <span v-else class="text-secondary">
                <span class="material-symbols-outlined"> add_circle </span>
                已新建
              </span>
            </td>

            <!--actions-->
            <td class="">
              <div class="grid grid-cols-3 gap-2">
                <button
                  v-if="availableActions.get(item.resourceName)!.includes('CREATE_NEW')"
                  class="btn btn-xs btn-outline btn-secondary"
                  @click="addNewResource(item)"
                >
                  {{ item.action == 'CREATE_NEW' ? '修改' : '新建' }}
                </button>
                <button
                  v-if="availableActions.get(item.resourceName)!.includes('SKIP')"
                  :disabled="item.action == 'SKIP'"
                  class="btn btn-xs btn-outline col-start-2"
                  @click="ignoreResource(item)"
                >
                  忽略
                </button>
                <button
                  :disabled="!store.mappingChanges.find((i) => i.resourceName == item.resourceName)"
                  class="btn btn-xs btn-ghost col-start-3"
                  @click="
                    () =>
                      (store.mappingChanges = store.mappingChanges.filter(
                        (i) => i.resourceName != item.resourceName,
                      ))
                  "
                >
                  <span class="material-symbols-outlined icon-sm">replay</span>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
  <ResourceForm
    v-model:show="showResourceModal"
    title="新建资源，对名称的修改被忽略"
    v-model:resource="newResourceData"
    :error="modelError"
    @cancel="showResourceModal = false"
    @submit="saveNewResource"
  ></ResourceForm>
</template>
