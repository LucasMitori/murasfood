<template lang="pug">
div
  mura-page-header(
    :title="t('admin.emails')"
    :subtitle="t('admin.emailsSubtitle')"
    :breadcrumbs="[{ title: 'admin.dashboard', to: '/admin' }, { title: 'admin.emails' }]"
  )

  v-row
    v-col(cols="12" lg="8")
      mura-card(:title="t('admin.emailTemplates')" icon="mdi-email-multiple-outline" :padded="false")
        v-data-table(
          :items="templates ?? []"
          :headers="headers"
          :loading="pending"
          :items-per-page="15"
          item-value="id"
          density="comfortable"
          hover
          @click:row="(_, { item }) => open(item)"
        )
          template(#item.key="{ item }")
            div
              p.text-body-2.mb-0 {{ labelFor(item.key) }}
              p.text-caption.text-medium-emphasis.mb-0 {{ item.key }}

          template(#item.is_active="{ item }")
            v-chip(:color="item.is_active ? 'success' : 'secondary'" size="x-small" variant="tonal")
              | {{ item.is_active ? t('admin.active') : t('admin.inactive') }}

          template(#item.updated_at="{ item }")
            span.text-caption.text-medium-emphasis {{ formatDateTime(item.updated_at, locale) }}

          template(#item.actions="{ item }")
            v-btn(
              icon="mdi-eye-outline"
              variant="text"
              size="small"
              :aria-label="t('admin.preview')"
              @click.stop="open(item, 'preview')"
            )
            v-btn(
              icon="mdi-pencil-outline"
              variant="text"
              size="small"
              :aria-label="t('common.edit')"
              @click.stop="open(item, 'content')"
            )

    v-col(cols="12" lg="4")
      mura-card(:title="t('admin.smtp')" icon="mdi-server-network")
        p.text-body-2.text-medium-emphasis.mb-4 {{ t('admin.smtpHint') }}

        v-text-field.mb-3(
          v-model="smtp.smtp_host"
          :label="t('admin.smtpHost')"
          :placeholder="t('admin.smtpPlatform')"
          variant="outlined"
          density="comfortable"
          hide-details
        )

        v-row(dense)
          v-col(cols="7")
            v-text-field(
              v-model="smtp.smtp_port"
              :label="t('admin.smtpPort')"
              type="number"
              variant="outlined"
              density="comfortable"
              hide-details
            )
          v-col(cols="5")
            v-switch.mt-1(
              v-model="smtp.smtp_use_tls"
              label="TLS"
              color="primary"
              density="compact"
              hide-details
            )

        v-text-field.mb-3.mt-3(
          v-model="smtp.smtp_username"
          :label="t('admin.smtpUser')"
          variant="outlined"
          density="comfortable"
          autocomplete="off"
          hide-details
        )

        //- Never pre-filled: the API does not return the stored secret, so an
          //- empty box means "unchanged" rather than "blank".
        v-text-field.mb-3(
          v-model="smtp.smtp_password"
          :label="passwordLabel"
          type="password"
          variant="outlined"
          density="comfortable"
          autocomplete="new-password"
          :hint="t('admin.smtpPasswordHint')"
          persistent-hint
        )

        v-text-field(
          v-model="smtp.smtp_from_email"
          :label="t('admin.smtpFrom')"
          type="email"
          variant="outlined"
          density="comfortable"
          hide-details
        )

        template(#footer)
          v-spacer
          v-btn(
            color="primary"
            variant="flat"
            rounded="lg"
            prepend-icon="mdi-content-save"
            :loading="savingSmtp"
            @click="saveSmtp"
          ) {{ t('common.save') }}

  mura-dialog(
    v-model="dialogOpen"
    :title="selected ? labelFor(selected.key) : ''"
    icon="mdi-email-edit-outline"
    :max-width="960"
    scrollable
  )
    v-tabs.mb-4(v-model="tab" density="comfortable")
      v-tab(value="content" prepend-icon="mdi-code-tags") {{ t('admin.emailContent') }}
      v-tab(value="preview" prepend-icon="mdi-eye-outline") {{ t('admin.preview') }}
      v-tab(value="variables" prepend-icon="mdi-variable") {{ t('admin.emailVariables') }}
      v-tab(value="test" prepend-icon="mdi-send-check-outline") {{ t('admin.emailTest') }}

    v-window(v-model="tab")
      v-window-item(value="content")
        v-text-field.mb-3(
          v-model="draft.subject"
          :label="t('admin.emailSubject')"
          variant="outlined"
          density="comfortable"
          hide-details
        )
        v-textarea.mb-3(
          v-model="draft.html_body"
          :label="t('admin.emailHtml')"
          variant="outlined"
          rows="12"
          hide-details
          spellcheck="false"
        )
        v-textarea(
          v-model="draft.text_body"
          :label="t('admin.emailText')"
          :hint="t('admin.emailTextHint')"
          variant="outlined"
          rows="5"
          persistent-hint
        )

      v-window-item(value="preview")
        .d-flex.align-center.ga-2.mb-2
          v-btn(
            variant="tonal"
            size="small"
            rounded="lg"
            prepend-icon="mdi-refresh"
            :loading="previewing"
            @click="refreshPreview"
          ) {{ t('admin.emailRender') }}
          span.text-caption.text-medium-emphasis(v-if="preview") {{ preview.subject }}

        //- Sandboxed, and deliberately so. The body is HTML the merchant wrote;
          //- putting it straight into this document would let a template script
          //- run with the operator's session. An iframe with no permissions
          //- renders it and can do nothing else.
        iframe.mura-email-preview(
          v-if="preview"
          :srcdoc="preview.html"
          sandbox=""
          :title="t('admin.preview')"
        )
        mura-empty-state(
          v-else
          :title="t('admin.emailNoPreview')"
          :description="t('admin.emailNoPreviewHint')"
          icon="mdi-eye-outline"
        )

      v-window-item(value="variables")
        p.text-body-2.text-medium-emphasis.mb-3 {{ t('admin.emailVariablesHint') }}
        .d-flex.flex-wrap.ga-2
          v-chip(
            v-for="name in selected?.available_variables ?? []"
            :key="name"
            size="small"
            variant="tonal"
            prepend-icon="mdi-code-braces"
          ) {{ placeholder(name) }}
        p.text-body-2.text-medium-emphasis.mb-0(v-if="!selected?.available_variables?.length")
          | {{ t('admin.emailNoVariables') }}

      v-window-item(value="test")
        p.text-body-2.text-medium-emphasis.mb-3 {{ t('admin.emailTestHint') }}
        v-text-field.mb-3(
          v-model="testRecipient"
          :label="t('auth.email')"
          type="email"
          variant="outlined"
          density="comfortable"
          hide-details
        )
        v-btn(
          color="primary"
          variant="flat"
          rounded="lg"
          prepend-icon="mdi-send"
          :loading="testing"
          :disabled="!testRecipient.trim()"
          @click="sendTest"
        ) {{ t('admin.emailSendTest') }}

        //- The server's own words. A failed test is a result, and the reason is
          //- the only thing that tells an operator what to change.
        v-alert.mt-4(
          v-if="testResult"
          :type="testResult.sent ? 'success' : 'error'"
          variant="tonal"
          density="compact"
        ) {{ testResult.sent ? t('admin.emailTestSent') : testResult.detail }}

    template(#actions)
      v-btn(variant="text" @click="dialogOpen = false") {{ t('common.cancel') }}
      v-btn(
        color="primary"
        variant="flat"
        :loading="saving"
        :disabled="!isDirty"
        @click="saveTemplate"
      ) {{ t('common.save') }}
</template>

<script setup lang="ts">
/**
 * Transactional email, from the dashboard.
 *
 * Twelve templates are seeded per tenant and every one of them is editable, but
 * they are raw HTML with `{{ placeholders }}` — which nobody can read a result
 * from. So each template can be rendered with sample values, and sent to a real
 * address, because a template that renders perfectly still fails if the mail
 * server is wrong and sending is the only way to find out.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTenantStore } from '~/stores/tenant'
import { useUiStore } from '~/stores/ui'
import { useApiError } from '~/composables/useApiError'
import { formatDateTime } from '~/utils/format'

definePageMeta({ layout: 'admin', middleware: 'merchant', permission: 'perm.admin.settings' })

interface Template {
  id: string
  key: string
  locale: string
  subject: string
  html_body: string
  text_body: string
  available_variables: string[]
  is_active: boolean
  updated_at: string
}

interface Preview {
  subject: string
  html: string
  text: string
}

const { t, locale } = useI18n()
const tenant = useTenantStore()
const ui = useUiStore()
const { messageFor } = useApiError()

useSeoMeta({ title: () => t('admin.emails'), robots: 'noindex' })

const { data: templates, pending, refresh } = await useAsyncData<Template[]>(
  'admin-email-templates',
  () => useNuxtApp().$api.get('/admin/email-templates/'),
)

const headers = computed(() => [
  { title: t('admin.emailTemplate'), key: 'key' },
  { title: t('common.language'), key: 'locale', width: 90 },
  { title: t('admin.status'), key: 'is_active', width: 110 },
  { title: t('admin.updatedAt'), key: 'updated_at', width: 170 },
  { title: t('table.actions'), key: 'actions', sortable: false, align: 'end' as const, width: 110 },
])

/**
 * How a variable is written inside a template.
 *
 * Built here rather than in the template: the braces are the whole point, and
 * a mustache holding another mustache is not something the compiler can read.
 */
function placeholder(name: string): string {
  return `{{ ${name} }}`
}

/** A readable name per template key, falling back to the key itself. */
function labelFor(key: string): string {
  return t(`admin.emailKeys.${key}`, key)
}

const dialogOpen = ref(false)
const tab = ref('content')
const selected = ref<Template | null>(null)
const draft = ref({ subject: '', html_body: '', text_body: '' })
const saving = ref(false)

const isDirty = computed(() =>
  Boolean(selected.value)
  && (draft.value.subject !== selected.value!.subject
    || draft.value.html_body !== selected.value!.html_body
    || draft.value.text_body !== selected.value!.text_body),
)

const preview = ref<Preview | null>(null)
const previewing = ref(false)

const testRecipient = ref('')
const testing = ref(false)
const testResult = ref<{ sent: boolean, detail: string } | null>(null)

function open(template: Template, startOn: string = 'content'): void {
  selected.value = template
  draft.value = {
    subject: template.subject,
    html_body: template.html_body,
    text_body: template.text_body,
  }
  // Cleared rather than kept: a preview of the previous template sitting under
  // a new one's name is worse than an empty panel.
  preview.value = null
  testResult.value = null
  tab.value = startOn
  dialogOpen.value = true

  if (startOn === 'preview') void refreshPreview()
}

/**
 * Render what is on screen, not what is stored.
 *
 * The unsaved draft is sent with the request so an operator can look at an
 * edit before committing it — which is the only reason to have a preview
 * beside an editor at all.
 */
async function refreshPreview(): Promise<void> {
  if (!selected.value) return

  previewing.value = true
  try {
    preview.value = await useNuxtApp().$api.post(
      `/admin/email-templates/${selected.value.id}/preview/`,
      {},
    )
  }
  catch (error) {
    ui.error(messageFor(error))
  }
  finally {
    previewing.value = false
  }
}

async function saveTemplate(): Promise<void> {
  if (!selected.value) return

  saving.value = true
  try {
    await useNuxtApp().$api.patch(`/admin/email-templates/${selected.value.id}/`, draft.value)
    await refresh()
    // Re-point at the refreshed row so the dirty check compares against what
    // was actually stored.
    selected.value = (templates.value ?? []).find(item => item.id === selected.value!.id) ?? null
    preview.value = null
    ui.success(t('admin.emailSaved'))
  }
  catch (error) {
    ui.error(messageFor(error))
  }
  finally {
    saving.value = false
  }
}

async function sendTest(): Promise<void> {
  if (!selected.value) return

  testing.value = true
  testResult.value = null
  try {
    testResult.value = await useNuxtApp().$api.post(
      `/admin/email-templates/${selected.value.id}/test/`,
      { recipient: testRecipient.value.trim() },
    )
  }
  catch (error) {
    testResult.value = { sent: false, detail: messageFor(error) }
  }
  finally {
    testing.value = false
  }
}

// --- SMTP --------------------------------------------------------------------
const savingSmtp = ref(false)

const smtp = ref({
  smtp_host: '',
  smtp_port: '' as string | number,
  smtp_username: '',
  smtp_password: '',
  smtp_use_tls: true,
  smtp_from_email: '',
})

const passwordLabel = computed(() =>
  tenant.tenant?.settings?.smtp_password_set
    ? t('admin.smtpPasswordStored')
    : t('admin.smtpPassword'),
)

async function saveSmtp(): Promise<void> {
  savingSmtp.value = true
  try {
    const payload: Record<string, unknown> = { ...smtp.value }

    // An untouched box means "leave the stored secret alone". Sending the empty
    // string would clear it, which is not what an operator editing the host
    // asked for.
    if (!smtp.value.smtp_password) delete payload.smtp_password
    if (payload.smtp_port === '') payload.smtp_port = null

    await useNuxtApp().$api.patch('/tenants/admin/settings/', payload)
    await tenant.fetch(true)
    smtp.value.smtp_password = ''
    ui.success(t('admin.smtpSaved'))
  }
  catch (error) {
    ui.error(messageFor(error))
  }
  finally {
    savingSmtp.value = false
  }
}
</script>

<style scoped>
.mura-email-preview {
  width: 100%;
  height: 60vh;
  border: 1px solid rgba(var(--v-border-color), 0.8);
  border-radius: 12px;
  /* The rendered mail is designed on a light ground; showing it on the
     dashboard's dark surface would misrepresent it. */
  background: #ffffff;
}
</style>
