<template lang="pug">
mura-dialog(
  :model-value="modelValue"
  :title="t('reports.export')"
  :max-width="620"
  @update:model-value="close"
)
  v-select.mb-4(
    v-model="reportType"
    :items="typeOptions"
    :label="t('reports.whichReport')"
    item-title="label"
    item-value="value"
    variant="outlined"
    density="comfortable"
    hide-details
  )

  v-btn-toggle.mb-2(v-model="format" mandatory divided variant="outlined" density="comfortable")
    v-btn(value="PDF" prepend-icon="mdi-file-pdf-box") PDF
    v-btn(value="CSV" prepend-icon="mdi-file-delimited-outline") CSV

  p.text-caption.text-medium-emphasis.mb-0 {{ t('reports.formatHint') }}

  //- Queued rather than downloaded: a year of sales takes long enough that
    //- holding the request open would time out, so the API answers with a job
    //- and this waits on it.
  template(v-if="job")
    v-divider.my-4

    .d-flex.align-center.ga-3(v-if="!job.is_ready && !failed")
      v-progress-circular(indeterminate size="20" width="2" color="primary")
      span.text-body-2 {{ t('reports.preparing') }}

    v-alert(v-else-if="failed" type="error" variant="tonal" density="comfortable")
      | {{ job.error_message || t('reports.failed') }}

    v-alert(v-else type="success" variant="tonal" density="comfortable")
      .d-flex.flex-wrap.align-center.ga-3
        span.text-body-2.flex-grow-1 {{ t('reports.ready') }}
        v-btn(
          color="success"
          variant="flat"
          size="small"
          rounded="lg"
          prepend-icon="mdi-download"
          :loading="downloading"
          @click="download"
        ) {{ t('reports.download') }}

  template(#actions)
    v-btn(variant="text" @click="close(false)") {{ t('common.close') }}
    v-spacer
    v-btn(
      color="primary"
      variant="flat"
      rounded="lg"
      prepend-icon="mdi-cog-play-outline"
      :loading="queueing"
      @click="queue"
    ) {{ t('reports.generate') }}
</template>

<script setup lang="ts">
/**
 * Ask for a report, then wait for it.
 *
 * The API answers a request with a job rather than a file, because a year of
 * sales can take longer than a request may stay open. That makes this a small
 * state machine: queue, poll, download — and it has to survive the merchant
 * closing the dialog, which is why the poll is cancelled on unmount rather than
 * left running against a component that no longer exists.
 */
import { computed, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUiStore } from '~/stores/ui'
import { useApiError } from '~/composables/useApiError'
import { saveFile } from '~/utils/format'

const props = defineProps<{
  modelValue: boolean
  /** The period chosen on the page, so the file matches what is on screen. */
  period: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

interface ReportJob {
  id: string
  status: string
  is_ready: boolean
  download_url: string | null
  filename: string | null
  error_message: string
}

const { t } = useI18n()
const ui = useUiStore()
const { messageFor } = useApiError()

const reportType = ref('SALES')
const format = ref<'PDF' | 'CSV'>('PDF')
const job = ref<ReportJob | null>(null)
const queueing = ref(false)
const downloading = ref(false)

let timer: ReturnType<typeof setTimeout> | null = null

const failed = computed(() => job.value?.status === 'FAILED')

const typeOptions = computed(() => [
  { value: 'SALES', label: t('reports.sales') },
  { value: 'FINANCIAL', label: t('admin.finance') },
])

function stopPolling(): void {
  if (timer) clearTimeout(timer)
  timer = null
}

// A dialog closed mid-render would otherwise keep asking the API about a job
// nobody is waiting for.
onUnmounted(stopPolling)

async function queue(): Promise<void> {
  stopPolling()
  queueing.value = true
  job.value = null

  try {
    job.value = await useNuxtApp().$api.post<ReportJob>('/admin/reports/export/', {
      report_type: reportType.value,
      period: props.period,
      output_format: format.value,
    })
    poll()
  }
  catch (error) {
    ui.error(messageFor(error))
  }
  finally {
    queueing.value = false
  }
}

/**
 * Ask again in a moment, until the worker is done.
 *
 * Two seconds rather than a tight loop: the job is rendering a document, and a
 * merchant watching a spinner is not helped by four requests a second. Polling
 * stops on any terminal state, so a failed job does not spin forever.
 */
function poll(): void {
  stopPolling()

  timer = setTimeout(async () => {
    if (!job.value) return

    try {
      const latest = await useNuxtApp().$api.get<ReportJob>(
        `/admin/report-jobs/${job.value.id}/`,
      )
      job.value = latest

      if (!latest.is_ready && latest.status !== 'FAILED') poll()
    }
    catch {
      // A transient failure is not worth an error banner while a document is
      // being written; the next tick will say either way.
      poll()
    }
  }, 2000)
}

/**
 * Fetch the finished document.
 *
 * `download_url` is a signed, expiring URL straight to the storage backend, not
 * an API path — so it must not go through the API client, which would prefix
 * the API base and attach an access token the storage does not want. The
 * signature is the authorisation.
 */
async function download(): Promise<void> {
  const url = job.value?.download_url
  if (!url) return

  downloading.value = true
  try {
    const response = await fetch(url)
    if (!response.ok) throw new Error(String(response.status))

    saveFile(await response.blob(), job.value?.filename || 'relatorio')
  }
  catch (error) {
    ui.error(messageFor(error))
  }
  finally {
    downloading.value = false
  }
}

function close(value: boolean): void {
  if (!value) {
    stopPolling()
    job.value = null
  }
  emit('update:modelValue', value)
}
</script>
