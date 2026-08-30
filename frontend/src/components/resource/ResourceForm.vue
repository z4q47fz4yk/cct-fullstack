<script setup lang="ts">
import type { ResourceCreate, ResourceCategory } from '@/client'
import ResourceCategoryTabs from '@/components/resource/ResourceCategoryTabs.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/valibot'
import { vResourceCreate } from '@/client/valibot.gen'
import * as v from 'valibot'
import { onMounted, watch } from 'vue'

const showModal = defineModel<boolean>('show', { required: true })
const data = defineModel<ResourceCreate>('resource', { required: true })

const emit = defineEmits<{
  submit: []
  cancel: []
}>()

const { title, isSubmitting, error } = defineProps<{
  title: string
  isSubmitting?: boolean
  error?: string
}>()

// 基于后端生成的 vResourceCreate，本地补充约束：
// unitPrice（元）允许小数且须非负（客户端 schema 仅校验 number，min 由本地补）
const validationSchema = toTypedSchema(
  v.object({
    ...vResourceCreate.entries,
    unitPrice: v.optional(v.pipe(v.number(), v.minValue(0)), 0),
  }),
)

const { handleSubmit, resetForm, errors, setValues, meta, defineField } = useForm({
  validationSchema,
  initialValues: data.value,
})
const [name, nameAttrs] = defineField('name')
const [category, categoryAttrs] = defineField('category')
const [unit, unitAttrs] = defineField('unit')
const [unitPrice, unitPriceAttrs] = defineField('unitPrice')
const [carbonFactor, carbonFactorAttrs] = defineField('carbonFactor')
const [description, descriptionAttrs] = defineField('description')

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
    setValues({
      name: data.value.name || '',
      category: (data.value.category || 'labor') as ResourceCategory,
      unit: data.value.unit || '',
      unitPrice: data.value.unitPrice || 0,
      carbonFactor: data.value.carbonFactor || 0,
      description: data.value.description || '',
    })
  }
}

watch(data, syncFromData, { immediate: true })

function onSubmit() {
  data.value = {
    name: name.value ?? '',
    category: category.value ?? 'labor',
    unit: unit.value ?? '',
    unitPrice: unitPrice.value ?? 0,
    carbonFactor: carbonFactor.value ?? 0,
    description: description.value ?? '',
  }
  emit('submit')
}
</script>

<template>
  <BaseModal v-model:open="showModal" :title="title" class="max-w-md" @close="emit('cancel')">
    <form class="space-y-4" @submit.prevent="handleSubmit(onSubmit)()">
      <div class="grid grid-cols-2 gap-4">
        <!-- 资源名称 -->
        <div class="col-span-2 fieldset">
          <!--使用 fieldset + fieldset-label 营造视觉效果，但是语义上没有 feildset 的含义，不使用 fieldset 标签-->
          <label class="fieldset-label mt-2"> 资源名称 </label>
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
          <label class="fieldset-label mt-2">资源类型</label>
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
              step="0.01"
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
              min="0"
              placeholder="0.00"
              step="0.01"
              type="number"
            />
            <span> kg/{{ unit || '单位' }} </span>
          </label>
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
      <!-- 错误提示 -->
      <div v-if="error" class="alert alert-error alert-sm">
        <span class="material-symbols-outlined icon-sm"> error </span>
        <span class="text-sm">{{ error }}</span>
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
        <button class="btn btn-primary" type="submit" :disabled="isSubmitting || !meta.valid">
          <span v-if="isSubmitting" class="loading loading-spinner loading-xs"></span>
          <span>保存</span>
        </button>
      </div>
    </form>
  </BaseModal>
</template>
