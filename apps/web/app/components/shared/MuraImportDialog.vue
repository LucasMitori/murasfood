<template lang="pug">
mura-dialog(
  :model-value="modelValue"
  :title="t('import.title')"
  :max-width="760"
  scrollable
  @update:model-value="close"
)
  //- Step one is always the template. A merchant who has not seen this format
    //- needs to know what goes in each column before filling four hundred
    //- lines, not after the import refuses them.
  v-alert.mb-4(type="info" variant="tonal" density="comfortable" icon="mdi-information-outline")
    .d-flex.flex-wrap.align-center.ga-3
      span.text-body-2.flex-grow-1 {{ t('import.templateHint') }}
      v-btn(
        variant="tonal"
        size="small"
        rounded="lg"
        prepend-icon="mdi-file-download-outline"
        :loading="downloading"
        @click="downloadTemplate"
      ) {{ t('import.downloadTemplate') }}

  v-file-input(
    v-model="file"
    :label="t('import.chooseFile')"
    :hint="t('import.chooseFileHint')"
    persistent-hint
    accept=".csv,.xlsx"
    prepend-icon=""
    prepend-inner-icon="mdi-paperclip"
    variant="outlined"
    density="comfortable"
    show-size
    clearable
    @update:model-value="reset"
  )

  v-switch.mt-2(
    v-model="createMissing"
    :label="t('import.createMissing')"
    :messages="t('import.createMissingHint')"
    color="primary"
    density="compact"
  )

  //- The preview is the whole point: a merchant should never discover what an
    //- import did by looking at their catalogue afterwards.
  template(v-if="report")
    v-divider.my-4

    .d-flex.flex-wrap.ga-2.mb-3
      v-chip(:color="report.ok ? 'success' : 'error'" variant="tonal" size="small")
        | {{ report.ok ? t('import.readyToApply') : t('import.hasErrors') }}
      v-chip(variant="tonal" size="small") {{ t('import.willCreate', { count: report.created }) }}
      v-chip(variant="tonal" size="small") {{ t('import.willUpdate', { count: report.updated }) }}
      v-chip(variant="tonal" size="small") {{ t('import.rowsRead', { count: report.total }) }}

    //- Errors name the line in the merchant's own file, so they can fix it
    //- there rather than guessing which of four hundred rows was meant.
    v-table.mura-import__errors(v-if="report.errors.length" density="compact")
      thead
        tr
          th {{ t('import.line') }}
          th SKU
          th {{ t('import.problem') }}
      tbody
        tr(v-for="error in report.errors.slice(0, 50)" :key="error.line")
          td.text-no-wrap {{ error.line }}
          td.text-no-wrap {{ error.sku }}
          td {{ error.messages.join(' · ') }}

    p.text-caption.text-medium-emphasis.mt-2.mb-0(v-if="report.errors.length > 50")
      | {{ t('import.moreErrors', { count: report.errors.length - 50 }) }}

    p.text-body-2.text-medium-emphasis.mt-3.mb-0(v-if="!report.ok")
      | {{ t('import.nothingApplied') }}

  template(#actions)
    v-btn(variant="text" :disabled="busy" @click="close(false)") {{ t('common.cancel') }}
    v-spacer
    v-btn(
      variant="tonal"
      rounded="lg"
      prepend-icon="mdi-eye-outline"
      :disabled="!file || busy"
      :loading="checking"
      @click="preview"
    ) {{ t('import.preview') }}
    v-btn(
      color="primary"
      variant="flat"
      rounded="lg"
      prepend-icon="mdi-database-import-outline"
      :disabled="!report || !report.ok || busy"
      :loading="applying"
      @click="apply"
    ) {{ t('import.apply') }}
</template>

<script setup lang="ts">
/**
 * Bringing a catalogue in from a spreadsheet.
 *
 * The flow is deliberately three steps — take the template, preview, apply —
 * because this writes a shop's entire product list from a file they made by
 * hand. The preview runs the real import with `dry_run`, so what it reports is
 * what will happen rather than a second implementation's guess at it.
 *
 * Applying is only offered when the preview came back clean. The API refuses a
 * sheet with any bad row anyway, so a disabled button here is the same rule
 * said earlier, where it is still cheap to fix.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUiStore } from '~/stores/ui'
import { useApiError } from '~/composables/useApiError'
import { saveFile } from '~/utils/format'

const props = defineProps<{
  modelValue: boolean
  /** Collection endpoint, e.g. `/admin/products/`. */
  endpoint: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  /** Raised after a successful apply, so the caller can refresh its table. */
  'imported': [report: ImportReport]
}>()

interface ImportError {
  line: number
  sku: string
  messages: string[]
}

interface ImportReport {
  dry_run: boolean
  ok: boolean
  total: number
  created: number
  updated: number
  errors: ImportError[]
}

const { t } = useI18n()
const ui = useUiStore()
const { messageFor } = useApiError()

const file = ref<File | File[] | null>(null)
const createMissing = ref(false)
const report = ref<ImportReport | null>(null)
const checking = ref(false)
const applying = ref(false)
const downloading = ref(false)

const busy = computed(() => checking.value || applying.value)

const base = computed(() => props.endpoint.replace(/\/$/, ''))

/** `v-file-input` hands back a File or an array depending on `multiple`. */
function selected(): File | null {
  const value = file.value
  if (Array.isArray(value)) return value[0] ?? null
  return value
}

function reset(): void {
  report.value = null
}

async function downloadTemplate(): Promise<void> {
  downloading.value = true
  try {
    const result = await useNuxtApp().$api.download(`${base.value}/import-template/`, {
      query: { fmt: 'xlsx' },
    })
    saveFile(result.blob, result.filename)
  }
  catch (error) {
    ui.error(messageFor(error))
  }
  finally {
    downloading.value = false
  }
}

async function send(dryRun: boolean): Promise<ImportReport | null> {
  const chosen = selected()
  if (!chosen) return null

  const body = new FormData()
  body.append('file', chosen)
  body.append('dry_run', String(dryRun))
  body.append('create_missing', String(createMissing.value))

  return useNuxtApp().$api.post<ImportReport>(`${base.value}/import/`, body)
}

async function preview(): Promise<void> {
  checking.value = true
  try {
    report.value = await send(true)
  }
  catch (error) {
    ui.error(messageFor(error))
  }
  finally {
    checking.value = false
  }
}

async function apply(): Promise<void> {
  applying.value = true
  try {
    const result = await send(false)
    if (!result) return

    report.value = result
    if (result.ok) {
      ui.success(t('import.done', { created: result.created, updated: result.updated }))
      emit('imported', result)
      close(false)
    }
  }
  catch (error) {
    ui.error(messageFor(error))
  }
  finally {
    applying.value = false
  }
}

function close(value: boolean): void {
  if (!value) {
    file.value = null
    report.value = null
  }
  emit('update:modelValue', value)
}
</script>

<style scoped>
.mura-import__errors {
  max-height: 260px;
  overflow-y: auto;
}
</style>
