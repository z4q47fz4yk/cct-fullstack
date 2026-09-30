<script setup lang="ts">
import type { ResourceCreate, ResourceCategory } from '@/client'
import ResourceCategoryTabs from '@/components/resource/ResourceCategoryTabs.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/valibot'
import { vResourceCategory, vResourceCreate } from '@/client/valibot.gen'
import * as v from 'valibot'
import { computed, onMounted, ref, watch } from 'vue'
import type { ConstraintDraft, ReuseDraft } from '@/types/resource'

const showModal = defineModel<boolean>('show', { required: true })
const data = defineModel<ResourceCreate>('resource', { required: true })

/** 资源限制草稿（仅 resources 页传入 & 编辑） */
const constraint = defineModel<ConstraintDraft>('constraint', {
  default: () => ({ enabled: false, maxUsage: null, description: '' }),
})
/** 周转复用草稿（仅 resources 页传入 & material） */
const reuse = defineModel<ReuseDraft>('reuse', {
  default: () => ({
    enabled: false,
    maxReuses: 1,
    reuseCount: 1,
    affectCost: false,
    description: null,
  }),
})

const emit = defineEmits<{
  submit: []
  cancel: []
}>()

const {
  title,
  isSubmitting,
  error,
  // 资源管理弹窗开启：显示限制/周转复用区块
  configurable = false,
  // 新增资源：分类初始为空并必须显式选择（避免默认 labor 被遗忘）
  requireCategory = false,
} = defineProps<{
  title: string
  isSubmitting?: boolean
  error?: string
  configurable?: boolean
  requireCategory?: boolean
}>()

// 数值边界（与后端 ResourceFields 的 ge/le 保持一致）
const NUM_LIMIT = 1e9

// 基于后端生成的 vResourceCreate，本地补充约束：
// unitPrice（元）允许小数、非负且不超过上限；carbonFactor 允许负值（如光伏抵消，
// 低碳措施「添加类」依赖负碳因子资源）并有上下限；
// 数值输入不使用 min/step 硬拦（step 会拒绝既有合法值如 1.603、min=0 会拦负碳因子，
// 且原生约束拦截提交时零反馈），改为提交前显式校验 + 字段级错误提示；
// category 允许 null（编辑由预填保证非空；新增由 categoryInvalid + submit 守卫强制选择）
const formSchema = toTypedSchema(
  v.object({
    ...vResourceCreate.entries,
    unitPrice: v.optional(
      v.pipe(
        v.number('请输入有效单价'),
        v.minValue(0, '单价不能为负数'),
        v.maxValue(NUM_LIMIT, '单价超出上限（最大 10 亿）'),
      ),
      0,
    ),
    carbonFactor: v.optional(
      v.pipe(
        v.number('请输入有效碳排放因子'),
        v.minValue(-NUM_LIMIT, '碳排放因子超出下限（最小 -10 亿）'),
        v.maxValue(NUM_LIMIT, '碳排放因子超出上限（最大 10 亿）'),
      ),
      0,
    ),
    category: v.nullable(vResourceCategory),
  }),
)

const { handleSubmit, errors, resetForm, defineField } = useForm({
  validationSchema: formSchema,
  initialValues: data.value,
})
const [name, nameAttrs] = defineField('name')
const [category, categoryAttrs] = defineField('category')
const [unit, unitAttrs] = defineField('unit')
const [unitPrice, unitPriceAttrs] = defineField('unitPrice')
const [carbonFactor, carbonFactorAttrs] = defineField('carbonFactor')
const [description, descriptionAttrs] = defineField('description')

// 显式校验失败时的可见反馈（杜绝"点保存没反应"）
const invalidHint = ref('')

function closeModal() {
  showModal.value = false
}

function handleCategoryChange() {
  switch (category.value) {
    case 'labor':
      unit.value = '工日'
      break
    case 'machinery':
      unit.value = '台班'
      break
    case 'material':
      unit.value = 't'
      break
    case 'transport':
      unit.value = '(km·t)⁻¹'
      break
    default:
      unit.value = ''
  }
}

onMounted(() => {
  if (!unit.value) handleCategoryChange()
})

function syncFromData() {
  if (data.value) {
    // 新增（requireCategory）时不预填分类，强制用户显式选择；
    // 编辑 / ReviewTable 等由既有数据预填
    const initialCategory = requireCategory
      ? null
      : ((data.value.category || null) as ResourceCategory | null)
    // resetForm 一并清掉上次的校验错误，避免重开弹窗仍显示陈旧报错
    resetForm({
      values: {
        name: data.value.name || '',
        category: initialCategory,
        unit: data.value.unit || '',
        unitPrice: data.value.unitPrice || 0,
        carbonFactor: data.value.carbonFactor || 0,
        description: data.value.description || '',
      },
    })
    invalidHint.value = ''
  }
}

// 提交时回写 data（供父级读取）同样会触发本 watch；
// 跳过这一次回填，避免保存失败（如 409 重名）时把已填内容 / 已选分类清空
let skipNextSync = false

watch(
  data,
  () => {
    if (skipNextSync) {
      skipNextSync = false
      return
    }
    syncFromData()
  },
  { immediate: true },
)

// 仅 material 分类下可配置周转复用
const isMaterial = computed(() => category.value === 'material')
const showReuseSection = computed(() => configurable && isMaterial.value)

// 分类必选：新增且未选时给出必填提示，并在提交时显式拦截
const categoryInvalid = computed(() => requireCategory && !category.value)

function onSubmitClick() {
  invalidHint.value = ''
  handleSubmit(onSubmit, onInvalidSubmit)()
}

function onInvalidSubmit() {
  // 显式校验失败：给出可见原因，不允许"点保存没反应"
  invalidHint.value = '表单存在无效字段，请按标红提示修正后再保存'
}

function onSubmit() {
  if (requireCategory && !category.value) {
    invalidHint.value = '请先选择资源类型'
    return
  }
  skipNextSync = true
  data.value = {
    name: name.value ?? '',
    category: (category.value ?? 'labor') as ResourceCategory,
    unit: unit.value ?? '',
    unitPrice: unitPrice.value ?? 0,
    carbonFactor: carbonFactor.value ?? 0,
    description: description.value ?? '',
  }
  emit('submit')
}
</script>

<template>
  <BaseModal v-model:open="showModal" :title="title" class="max-w-xl" @close="emit('cancel')">
    <form class="space-y-4" novalidate @submit.prevent="onSubmitClick">
      <div class="grid grid-cols-2 gap-4">
        <!-- 资源名称 -->
        <div class="col-span-2 fieldset">
          <!--使用 fieldset + fieldset-label 营造视觉效果，但是语义上没有 feildset 的含义，不使用 fieldset 标签-->
          <label class="fieldset-label mt-2">
            资源名称 <span class="text-error" aria-hidden="true">*</span>
          </label>
          <input
            v-model="name"
            v-bind="nameAttrs"
            :disabled="isSubmitting"
            class="input"
            :class="{ 'input-error': errors.name }"
            placeholder="输入资源名称"
            type="text"
          />
          <span v-if="errors.name" class="label text-error">
            {{ errors.name }}
          </span>
          <!-- 资源类型 -->
          <label class="fieldset-label mt-2">
            资源类型 <span class="text-error" aria-hidden="true">*</span>
          </label>
          <ResourceCategoryTabs
            v-bind="categoryAttrs"
            :selected-category="category"
            @update:selected-category="
              (v) => {
                category = v!
                handleCategoryChange()
              }
            "
          />
          <p v-if="categoryInvalid || errors.category" class="text-xs text-error mt-1" role="alert">
            {{ errors.category || (requireCategory && !category ? '请选择资源分类（必填）' : '') }}
          </p>
        </div>
        <!-- 单价 -->
        <div class="fieldset">
          <label class="fieldset-label">单价</label>
          <label class="input w-full">
            <span> ¥ </span>
            <input
              v-model.number="unitPrice"
              v-bind="unitPriceAttrs"
              :disabled="isSubmitting"
              class="w-full"
              :class="{ 'input-error': errors.unitPrice }"
              min="0"
              placeholder="0.00"
              step="any"
              type="number"
            />
          </label>
          <span v-if="errors.unitPrice" class="text-xs text-error mt-1">
            {{ errors.unitPrice }}
          </span>
        </div>
        <!-- 计量单位 -->
        <div class="fieldset">
          <label class="fieldset-label">计量单位</label>
          <input
            v-model="unit"
            v-bind="unitAttrs"
            :disabled="isSubmitting"
            class="input w-full"
            :class="{ 'input-error': errors.unit }"
            placeholder="如：工日、台班、吨"
            type="text"
          />
          <span v-if="errors.unit" class="text-xs text-error mt-1">
            {{ errors.unit }}
          </span>
        </div>
        <!-- 碳排放因子 -->
        <div class="fieldset col-span-2">
          <label class="fieldset-label">碳排放因子</label>
          <label class="input w-full">
            <input
              v-model.number="carbonFactor"
              v-bind="carbonFactorAttrs"
              :disabled="isSubmitting"
              class="w-full"
              :class="{ 'input-error': errors.carbonFactor }"
              placeholder="0.00"
              step="any"
              type="number"
            />
            <span> kg/{{ unit || '单位' }} </span>
          </label>
          <p class="mt-1 text-xs text-fg-muted">可为负（如光伏抵消）；绝对值不超过 10 亿</p>
          <p v-if="errors.carbonFactor" class="label text-error">
            {{ errors.carbonFactor }}
          </p>
          <!-- 描述 -->
          <label class="fieldset-label">描述</label>
          <textarea
            v-model="description"
            v-bind="descriptionAttrs"
            :disabled="isSubmitting"
            class="textarea input w-full"
            placeholder="输入资源描述（可选）"
            rows="2"
          ></textarea>
          <span v-if="errors.description" class="text-xs text-error mt-1">
            {{ errors.description }}
          </span>
        </div>
      </div>

      <!-- 资源限制（configurable 时可选配置） -->
      <fieldset
        v-if="configurable"
        class="fieldset rounded-field border border-base-content/10 p-3"
      >
        <label class="fieldset-label flex items-center gap-2 cursor-pointer select-none">
          <input
            v-model="constraint.enabled"
            type="checkbox"
            class="checkbox checkbox-sm"
            :disabled="isSubmitting"
          />
          <span class="material-symbols-outlined icon-sm text-warning">rule</span>
          设置资源限制（日用量上限）
        </label>
        <template v-if="constraint.enabled">
          <div class="grid grid-cols-2 gap-3 mt-2">
            <div class="fieldset">
              <label class="fieldset-label">最大日使用量</label>
              <label class="input flex items-center gap-2">
                <span class="material-symbols-outlined icon-sm text-warning/70">trending_up</span>
                <input
                  v-model.number="constraint.maxUsage"
                  :disabled="isSubmitting"
                  class="w-full bg-transparent outline-none"
                  type="number"
                  min="0"
                  step="any"
                  placeholder="如 100"
                />
              </label>
            </div>
            <div class="fieldset">
              <label class="fieldset-label">备注（可选）</label>
              <input
                v-model="constraint.description"
                :disabled="isSubmitting"
                class="input w-full"
                type="text"
                placeholder="限制用途说明"
              />
            </div>
          </div>
        </template>
      </fieldset>

      <!-- 周转复用（仅材料分类，configurable 时展示） -->
      <fieldset
        v-if="configurable && showReuseSection"
        class="fieldset rounded-field border border-base-content/10 p-3"
      >
        <label class="fieldset-label flex items-center gap-2 cursor-pointer select-none">
          <input
            v-model="reuse.enabled"
            type="checkbox"
            class="checkbox checkbox-sm"
            :disabled="isSubmitting"
          />
          <span class="material-symbols-outlined icon-sm text-cyan">autorenew</span>
          该材料可周转复用
        </label>
        <template v-if="reuse.enabled">
          <div class="grid grid-cols-2 gap-3 mt-2">
            <div class="fieldset">
              <label class="fieldset-label">最大周转次数</label>
              <label class="input flex items-center gap-2">
                <input
                  v-model.number="reuse.maxReuses"
                  :disabled="isSubmitting"
                  class="w-full bg-transparent outline-none"
                  type="number"
                  min="1"
                  step="1"
                  placeholder="理论最大周转次数"
                />
              </label>
            </div>
            <div class="fieldset">
              <label class="fieldset-label">实际周转次数</label>
              <label class="input flex items-center gap-2">
                <input
                  v-model.number="reuse.reuseCount"
                  :disabled="isSubmitting"
                  class="w-full bg-transparent outline-none"
                  type="number"
                  min="1"
                  step="1"
                  placeholder="本项目实际周转次数"
                />
              </label>
              <p v-if="reuse.reuseCount > reuse.maxReuses" class="mt-1 text-xs text-warning">
                实际周转次数已超过最大周转次数，请确认
              </p>
            </div>
            <div class="fieldset col-span-2">
              <span class="fieldset-label">是否影响成本</span>
              <div
                class="flex w-full gap-1 rounded-field border border-base-content/10 bg-base-content/5 p-[0.1rem]"
                role="group"
                aria-label="是否影响成本"
              >
                <button
                  type="button"
                  class="flex-1 rounded-field px-3 py-1 text-sm font-medium transition-colors"
                  :class="
                    reuse.affectCost
                      ? 'bg-primary/15 text-primary shadow-sm'
                      : 'text-fg-muted hover:bg-base-content/5 hover:text-base-content'
                  "
                  :disabled="isSubmitting"
                  :aria-pressed="reuse.affectCost"
                  @click="reuse.affectCost = true"
                >
                  周转摊薄成本
                </button>
                <button
                  type="button"
                  class="flex-1 rounded-field px-3 py-1 text-sm font-medium transition-colors"
                  :class="
                    !reuse.affectCost
                      ? 'bg-primary/15 text-primary shadow-sm'
                      : 'text-fg-muted hover:bg-base-content/5 hover:text-base-content'
                  "
                  :disabled="isSubmitting"
                  :aria-pressed="!reuse.affectCost"
                  @click="reuse.affectCost = false"
                >
                  仅摊薄碳排放
                </button>
              </div>
            </div>
            <div class="fieldset col-span-2">
              <label class="fieldset-label">备注（可选）</label>
              <textarea
                v-model="reuse.description"
                :disabled="isSubmitting"
                rows="2"
                placeholder="周转配置说明"
                class="textarea w-full"
              />
            </div>
          </div>
        </template>
      </fieldset>

      <!-- 错误提示 -->
      <div v-if="error" class="alert alert-error alert-sm">
        <span class="material-symbols-outlined icon-sm"> error </span>
        <span class="text-sm">{{ error }}</span>
      </div>
      <!-- 校验失败提示：提交前显式校验，杜绝"点保存无反应" -->
      <div v-if="invalidHint" class="alert alert-error alert-sm" role="alert">
        <span class="material-symbols-outlined icon-sm"> error </span>
        <span class="text-sm">{{ invalidHint }}</span>
      </div>
      <!-- 操作按钮 -->
      <div class="modal-action">
        <button
          class="btn btn-ghost"
          type="button"
          :disabled="isSubmitting"
          @click="emit('cancel')"
        >
          取消
        </button>
        <button class="btn btn-primary" type="submit" :disabled="isSubmitting">
          <span v-if="isSubmitting" class="loading loading-spinner loading-xs"></span>
          <span>保存</span>
        </button>
      </div>
    </form>
  </BaseModal>
</template>
