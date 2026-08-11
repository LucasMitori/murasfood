<template lang="pug">
v-form(ref="formRef" :disabled="loading" @submit.prevent="submit")
  v-alert.mb-4(
    v-if="generalError"
    type="error"
    variant="tonal"
    density="compact"
    role="alert"
  ) {{ generalError }}

  template(v-for="(section, index) in visibleSections" :key="`section-${index}`")
    component.mura-card.mb-4(:is="card ? 'v-card' : 'div'" :flat="card ? true : undefined")
      component(:is="card ? 'v-card-text' : 'div'")
        .mb-4(v-if="section.title")
          .d-flex.align-center.ga-2
            v-icon(v-if="section.icon" :icon="section.icon" color="primary" size="small")
            h3.text-subtitle-1.font-weight-medium {{ translate(section.title) }}
          p.text-caption.text-medium-emphasis.mb-0(v-if="section.description") {{ translate(section.description) }}

        v-row(dense)
          v-col(
            v-for="field in visibleFieldsOf(section)"
            :key="field.name"
            :cols="field.cols ?? 12"
            :sm="field.sm"
            :md="field.md"
            :lg="field.lg"
          )
            mura-form-field(
              :field="field"
              :model-value="values[field.name]"
              :values="values"
              :server-errors="serverErrors[field.name]"
              @update:model-value="value => setValue(field, value)"
            )

  .d-flex.flex-wrap.align-center.ga-3(v-if="!hideActions")
    v-btn(
      type="submit"
      color="primary"
      variant="flat"
      :loading="loading"
      :disabled="loading || (requireChanges && !isDirty)"
    ) {{ translate(schema.submitLabel) || t('common.save') }}

    v-btn(
      v-if="showCancel"
      variant="text"
      :disabled="loading"
      @click="emit('cancel')"
    ) {{ translate(schema.cancelLabel) || t('common.cancel') }}

    v-spacer

    span.text-caption.text-medium-emphasis(v-if="isDirty" role="status") {{ t('form.unsavedChanges') }}

    slot(name="actions")
</template>

<script setup lang="ts">
/**
 * Schema-driven form.
 *
 * A screen declares sections and fields; this component renders them, validates
 * them, maps the API's field errors back onto the right inputs and reports
 * whether anything has changed. Adding a field is a line of schema.
 *
 * ```ts
 * const schema: FormSchema = {
 *   sections: [{
 *     title: 'admin.products',
 *     fields: [
 *       { name: 'name', type: 'text', label: 'product.name', required: true, md: 8 },
 *       { name: 'base_price', type: 'money', label: 'common.total', required: true, md: 4 },
 *     ],
 *   }],
 * }
 * ```
 *
 * The parent owns submission — this component never calls the API itself, which
 * keeps it usable for create, edit and filter forms alike.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { FormField, FormSchema, FormSection, FormValues } from '~/types/ui'
import { ApiRequestError } from '~/utils/api-client'

const props = withDefaults(defineProps<{
  schema: FormSchema
  /** Current values, `v-model:values`. */
  values: FormValues
  loading?: boolean
  /** Wrap each section in a card. Off for forms already inside one. */
  card?: boolean
  showCancel?: boolean
  hideActions?: boolean
  /** Disable submit until something changes. Useful for edit forms. */
  requireChanges?: boolean
}>(), {
  loading: false,
  card: true,
  showCancel: false,
  hideActions: false,
  requireChanges: false,
})

const emit = defineEmits<{
  'update:values': [values: FormValues]
  submit: [values: FormValues]
  cancel: []
}>()

const { t, te } = useI18n()

const formRef = ref<{ validate: () => Promise<{ valid: boolean }>, resetValidation: () => void } | null>(null)
const serverErrors = ref<Record<string, string[]>>({})
const generalError = ref('')

/** Snapshot taken whenever the parent loads data, for dirty tracking. */
const pristine = ref<string>(JSON.stringify(props.values ?? {}))

const isDirty = computed(() => JSON.stringify(props.values ?? {}) !== pristine.value)

function translate(value?: string): string {
  if (!value) return ''
  return te(value) ? t(value) : value
}

/** Sections whose predicate passes. */
const visibleSections = computed(() =>
  props.schema.sections.filter(section =>
    section.visibleWhen ? section.visibleWhen(props.values) : true,
  ),
)

/**
 * Fields of a section that should render right now.
 *
 * Hidden fields are also excluded from validation and from the submitted
 * payload: a rule on an invisible field produces a form that cannot be
 * submitted for a reason nobody can see.
 */
function visibleFieldsOf(section: FormSection): FormField[] {
  return section.fields.filter(field =>
    field.visibleWhen ? field.visibleWhen(props.values) : true,
  )
}

/** Every field currently rendered, across all visible sections. */
const activeFields = computed(() =>
  visibleSections.value.flatMap(section => visibleFieldsOf(section)),
)

function setValue(field: FormField, value: unknown): void {
  const next = { ...props.values, [field.name]: value }

  // Editing a field clears the server error that was pinned to it; leaving it
  // would tell the user their correction is still wrong.
  if (serverErrors.value[field.name]) {
    const { [field.name]: _removed, ...rest } = serverErrors.value
    serverErrors.value = rest
  }

  if (field.name !== 'slug') maybeDeriveSlug(next, field)
  emit('update:values', next)
}

/** Slugs the user has edited by hand, which stop tracking their source. */
const touchedSlugs = ref(new Set<string>())

/**
 * Keep a slug in step with its source field until someone edits it by hand.
 *
 * Once a slug has been typed, it stops following the name — silently rewriting
 * a deliberate URL would break links.
 */
function maybeDeriveSlug(next: FormValues, changed: FormField): void {
  const slugField = activeFields.value.find(
    field => field.type === 'slug' && field.slugSource === changed.name,
  )
  if (!slugField || touchedSlugs.value.has(slugField.name)) return

  next[slugField.name] = slugify(String(next[changed.name] ?? ''))
}

watch(
  () => props.values,
  (next) => {
    for (const field of activeFields.value) {
      if (field.type !== 'slug') continue
      const value = String(next[field.name] ?? '')
      const source = field.slugSource ? String(next[field.slugSource] ?? '') : ''
      if (value && value !== slugify(source)) touchedSlugs.value.add(field.name)
    }
  },
  { deep: true },
)

/** Apply the schema's defaults to any value the parent left undefined. */
function applyDefaults(): void {
  const next = { ...props.values }
  let changed = false

  for (const field of props.schema.sections.flatMap(section => section.fields)) {
    if (next[field.name] === undefined && field.default !== undefined) {
      next[field.name] = field.default
      changed = true
    }
  }

  if (changed) emit('update:values', next)
}

applyDefaults()

async function submit(): Promise<void> {
  generalError.value = ''
  serverErrors.value = {}

  const result = await formRef.value?.validate()
  if (result && !result.valid) return

  // Only visible fields are submitted; a hidden branch of a conditional form
  // should not send stale values the user cannot see or correct.
  const visibleNames = new Set(activeFields.value.map(field => field.name))
  const payload: FormValues = {}
  for (const [key, value] of Object.entries(props.values)) {
    if (visibleNames.has(key)) payload[key] = value
  }

  emit('submit', payload)
}

/**
 * Display an API failure against the fields it refers to.
 *
 * Called by the parent after a failed request; anything the API blamed on a
 * field the form does not have falls back to the banner, so no message is lost.
 */
function applyApiError(error: unknown): void {
  if (!(error instanceof ApiRequestError)) {
    generalError.value = t('errors.generic')
    return
  }

  const fields = error.fieldErrors
  const known: Record<string, string[]> = {}
  const orphaned: string[] = []
  const names = new Set(props.schema.sections.flatMap(s => s.fields.map(f => f.name)))

  for (const [name, messages] of Object.entries(fields)) {
    if (names.has(name)) known[name] = messages
    else orphaned.push(...messages)
  }

  serverErrors.value = known

  const key = `errors.${error.code}`
  generalError.value = orphaned.length
    ? orphaned.join(' ')
    : (te(key) ? t(key) : t('form.submitError'))
}

/** Mark the current values as saved, clearing the dirty flag. */
function markPristine(): void {
  pristine.value = JSON.stringify(props.values ?? {})
  serverErrors.value = {}
  generalError.value = ''
  formRef.value?.resetValidation()
}

function slugify(value: string): string {
  return value
    .normalize('NFD')
    // Strip combining diacritics so "Pão" becomes "pao" rather than "p-o".
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60)
}

defineExpose({ applyApiError, markPristine, isDirty, submit })
</script>
