<template lang="pug">
//- Layout-only field types render without an input.
.py-2(v-if="field.type === 'heading'")
  h3.text-subtitle-1.font-weight-medium {{ label }}
  p.text-caption.text-medium-emphasis.mb-0(v-if="description") {{ description }}

v-divider.my-2(v-else-if="field.type === 'divider'")

component(
  :is="field.component"
  v-else-if="field.type === 'custom' && field.component"
  :model-value="modelValue"
  :field="field"
  :error-messages="errorMessages"
  :disabled="isDisabled"
  v-bind="field.props"
  @update:model-value="update"
)

v-textarea(
  v-else-if="field.type === 'textarea'"
  :model-value="modelValue"
  :label="label"
  :placeholder="field.placeholder"
  :hint="hint"
  :persistent-hint="Boolean(hint)"
  :rules="rules"
  :error-messages="errorMessages"
  :disabled="isDisabled"
  :readonly="field.readonly"
  :clearable="field.clearable"
  :counter="field.maxLength"
  :maxlength="field.maxLength"
  :rows="field.rows ?? 3"
  :autofocus="field.autofocus"
  v-bind="field.props"
  @update:model-value="update"
)

v-select(
  v-else-if="field.type === 'select'"
  :model-value="modelValue"
  :items="options"
  :label="label"
  :hint="hint"
  :persistent-hint="Boolean(hint)"
  :rules="rules"
  :error-messages="errorMessages"
  :disabled="isDisabled"
  :readonly="field.readonly"
  :clearable="field.clearable"
  :multiple="field.multiple"
  :chips="field.multiple"
  item-title="label"
  item-value="value"
  v-bind="field.props"
  @update:model-value="update"
)

v-autocomplete(
  v-else-if="field.type === 'autocomplete' || field.type === 'combobox'"
  :model-value="modelValue"
  :items="options"
  :label="label"
  :hint="hint"
  :persistent-hint="Boolean(hint)"
  :rules="rules"
  :error-messages="errorMessages"
  :disabled="isDisabled"
  :readonly="field.readonly"
  :clearable="field.clearable !== false"
  :multiple="field.multiple"
  :chips="field.multiple"
  item-title="label"
  item-value="value"
  v-bind="field.props"
  @update:model-value="update"
)

v-checkbox(
  v-else-if="field.type === 'checkbox'"
  :model-value="modelValue"
  :label="label"
  :hint="hint"
  :persistent-hint="Boolean(hint)"
  :rules="rules"
  :error-messages="errorMessages"
  :disabled="isDisabled"
  color="primary"
  density="comfortable"
  v-bind="field.props"
  @update:model-value="update"
)

v-switch(
  v-else-if="field.type === 'switch'"
  :model-value="modelValue"
  :label="label"
  :hint="hint"
  :persistent-hint="Boolean(hint)"
  :error-messages="errorMessages"
  :disabled="isDisabled"
  color="primary"
  density="comfortable"
  inset
  v-bind="field.props"
  @update:model-value="update"
)

v-radio-group(
  v-else-if="field.type === 'radio'"
  :model-value="modelValue"
  :label="label"
  :rules="rules"
  :error-messages="errorMessages"
  :disabled="isDisabled"
  v-bind="field.props"
  @update:model-value="update"
)
  v-radio(
    v-for="option in options"
    :key="String(option.value)"
    :label="option.label"
    :value="option.value"
    :disabled="option.disabled"
  )

mura-image-upload(
  v-else-if="field.type === 'image'"
  :model-value="modelValue"
  :label="label"
  :folder="field.folder"
  :error-messages="errorMessages"
  :disabled="isDisabled"
  @update:model-value="update"
)

mura-file-upload(
  v-else-if="field.type === 'file'"
  :model-value="modelValue"
  :label="label"
  :accept="field.accept"
  :error-messages="errorMessages"
  :disabled="isDisabled"
  @update:model-value="update"
)

v-text-field(
  v-else
  :model-value="modelValue"
  :label="label"
  :placeholder="field.placeholder"
  :hint="hint"
  :persistent-hint="Boolean(hint)"
  :rules="rules"
  :error-messages="errorMessages"
  :disabled="isDisabled"
  :readonly="field.readonly"
  :clearable="field.clearable"
  :type="inputType"
  :inputmode="inputMode"
  :prefix="prefix"
  :suffix="suffix"
  :counter="field.maxLength"
  :maxlength="field.maxLength"
  :autofocus="field.autofocus"
  :autocomplete="field.autocomplete"
  :step="field.step"
  :min="field.min"
  :max="field.max"
  v-bind="field.props"
  @update:model-value="update"
)
</template>

<script setup lang="ts">
/**
 * Renders one field of a `MuraFormBuilder` schema.
 *
 * Everything a field needs — label, hint, rules, options, disabled state — is
 * derived from its definition, so adding a field to a form is a line of schema
 * rather than a block of markup.
 *
 * Labels and hints go through i18n when the schema gives a translation key, and
 * fall back to the literal string when it does not: some labels are data (a
 * merchant's own attribute names) rather than product copy.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { FormField, FormFieldOption, FormValues, ValidationRule } from '~/types/ui'
import { rulesForField } from '~/utils/validation'
import { useTenantStore } from '~/stores/tenant'

const props = withDefaults(defineProps<{
  field: FormField
  modelValue: unknown
  /** All form values, for `visibleWhen`, dynamic options and dynamic disabling. */
  values: FormValues
  /** Field errors returned by the API, already extracted from the envelope. */
  serverErrors?: string[]
}>(), { serverErrors: () => [] })

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const { t, te } = useI18n()
const tenant = useTenantStore()

/** Translate when the schema gave a key; otherwise show the literal. */
function translate(value?: string): string {
  if (!value) return ''
  return te(value) ? t(value) : value
}

const label = computed(() => {
  const base = translate(props.field.label)
  // Marking optional fields is less noisy than marking the many required ones.
  return props.field.required || !base ? base : `${base} (${t('common.optional')})`
})

const hint = computed(() => translate(props.field.hint))
const description = computed(() => translate(props.field.description))

const isDisabled = computed(() =>
  typeof props.field.disabled === 'function'
    ? props.field.disabled(props.values)
    : Boolean(props.field.disabled),
)

const options = computed<FormFieldOption[]>(() => {
  const source = props.field.options
  if (!source) return []
  const resolved = typeof source === 'function' ? source(props.values) : source
  return resolved.map(option => ({ ...option, label: translate(option.label) || option.label }))
})

/** Client-side rules; server errors are surfaced separately. */
const rules = computed<ValidationRule[]>(() => rulesForField(props.field, t))

const errorMessages = computed(() => props.serverErrors)

const inputType = computed(() => {
  switch (props.field.type) {
    case 'password':
      return 'password'
    case 'email':
      return 'email'
    case 'tel':
      return 'tel'
    case 'url':
      return 'url'
    case 'date':
      return 'date'
    case 'time':
      return 'time'
    case 'datetime':
      return 'datetime-local'
    case 'color':
      return 'text'
    default:
      // Money and quantity stay `text` so a comma decimal separator is typable
      // and the browser does not impose its own numeric formatting.
      return 'text'
  }
})

const inputMode = computed(() => {
  if (['number', 'money', 'quantity', 'percent'].includes(props.field.type)) return 'decimal'
  if (props.field.type === 'tel') return 'tel'
  if (props.field.type === 'email') return 'email'
  return undefined
})

/** Currency symbol for money fields, taken from the tenant. */
const prefix = computed(() => {
  if (props.field.type !== 'money') return undefined
  return tenant.currency === 'BRL' ? 'R$' : tenant.currency
})

const suffix = computed(() => (props.field.type === 'percent' ? '%' : undefined))

function update(value: unknown): void {
  emit('update:modelValue', value)
}
</script>
