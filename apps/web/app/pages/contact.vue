<template lang="pug">
.mura-container.mura-section
  .text-center.mb-8
    h1.text-h4.font-weight-bold.mb-2 {{ t('contact.title') }}
    p.text-body-1.text-medium-emphasis.mb-0 {{ t('contact.subtitle') }}

  v-row
    v-col(cols="12" md="5")
      v-card.mura-card.pa-5.mb-4(flat border)
        h2.text-subtitle-1.font-weight-bold.mb-4 {{ t('store.contact') }}

        .mura-contact__row(v-if="address")
          v-icon(icon="mdi-map-marker-outline" color="primary")
          div
            p.text-body-2.font-weight-medium.mb-0 {{ t('account.addresses') }}
            p.text-body-2.text-medium-emphasis.mb-0 {{ address }}

        .mura-contact__row(v-if="tenant.tenant?.phone")
          v-icon(icon="mdi-phone-outline" color="primary")
          div
            p.text-body-2.font-weight-medium.mb-0 {{ t('auth.phone') }}
            a.text-body-2.text-medium-emphasis(:href="`tel:${tenant.tenant.phone}`") {{ formatPhone(tenant.tenant.phone) }}

        .mura-contact__row(v-if="tenant.tenant?.support_email")
          v-icon(icon="mdi-email-outline" color="primary")
          div
            p.text-body-2.font-weight-medium.mb-0 {{ t('auth.email') }}
            a.text-body-2.text-medium-emphasis(:href="`mailto:${tenant.tenant.support_email}`") {{ tenant.tenant.support_email }}

        .mura-contact__row(v-if="whatsapp")
          v-icon(icon="mdi-whatsapp" color="success")
          div
            p.text-body-2.font-weight-medium.mb-0 WhatsApp
            a.text-body-2.text-medium-emphasis(:href="whatsapp" target="_blank" rel="noopener noreferrer") {{ t('contact.openWhatsapp') }}

      v-card.mura-card.pa-5(flat border)
        .d-flex.align-center.ga-2.mb-2
          v-icon(icon="mdi-clock-outline" color="primary")
          h2.text-subtitle-1.font-weight-bold.mb-0 {{ t('contact.hours') }}
        p.text-body-2.text-medium-emphasis.mb-0 {{ t('contact.hoursHint') }}

    v-col(cols="12" md="7")
      v-card.mura-card.pa-5(flat border)
        h2.text-subtitle-1.font-weight-bold.mb-1 {{ t('contact.sendMessage') }}
        p.text-body-2.text-medium-emphasis.mb-4 {{ t('contact.sendMessageHint') }}

        //- Opens the visitor's own mail client rather than posting anywhere.
        //- There is no inbox behind this page, and a form that silently
        //- discarded messages would be worse than no form.
        //-
        //- Declared as a schema rather than hand-written inputs: every field
        //- then owns a grid cell and the row's gutter spaces them all
        //- identically. Written by hand, each field carried its own margin and
        //- they disagreed — which is what left the name and e-mail row sitting
        //- against the subject below it.
        mura-form-builder(
          v-model:values="form"
          :schema="schema"
          :card="false"
          @submit="openMailClient"
        )

</template>

<script setup lang="ts">
/**
 * Contact page.
 *
 * The merchant's real details come from the tenant record. The form composes a
 * `mailto:` rather than posting to an endpoint: no support inbox exists in the
 * platform yet, and a form that accepted a message and dropped it would be a
 * worse answer than handing it to the visitor's mail client.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { FormSchema, FormValues } from '~/types/ui'
import { useTenantStore } from '~/stores/tenant'
import { formatPhone } from '~/utils/format'

const { t } = useI18n()
const tenant = useTenantStore()

useSeoMeta({
  title: () => t('contact.title'),
  description: () => t('contact.subtitle'),
})

const form = ref<FormValues>({ name: '', email: '', subject: '', message: '' })

const schema = computed<FormSchema>(() => ({
  submitLabel: 'contact.send',
  submitIcon: 'mdi-send',
  sections: [{
    fields: [
      { name: 'name', type: 'text', label: 'auth.firstName', required: true, md: 6 },
      { name: 'email', type: 'email', label: 'auth.email', required: true, md: 6 },
      { name: 'subject', type: 'text', label: 'contact.subject', required: true },
      { name: 'message', type: 'textarea', label: 'contact.message', required: true, rows: 5 },
    ],
  }],
}))

const address = computed(() => {
  const parts = tenant.tenant?.address
  if (!parts) return ''
  return [parts.street, parts.number, parts.neighborhood, parts.city, parts.state]
    .filter(Boolean)
    .join(', ')
})

const whatsapp = computed(() => {
  const number = tenant.tenant?.whatsapp?.replace(/\D/g, '')
  return number ? `https://wa.me/${number}` : ''
})

/**
 * Hands the message to the visitor's own mail client.
 *
 * The builder only emits `submit` once its own validation has passed, so the
 * values are known good by the time they arrive here.
 */
function openMailClient(values: FormValues): void {
  const to = tenant.tenant?.support_email
  if (!to) return

  const body = `${values.message}

—
${values.name} <${values.email}>`
  window.location.href
    = `mailto:${to}?subject=${encodeURIComponent(String(values.subject))}`
      + `&body=${encodeURIComponent(body)}`
}
</script>

<style scoped>
.mura-contact__row {
  display: flex;
  align-items: flex-start;
  gap: 0.875rem;
}

.mura-contact__row + .mura-contact__row {
  margin-top: 1.25rem;
}

.mura-contact__row a {
  color: inherit;
  text-decoration: none;
}

.mura-contact__row a:hover {
  color: rgb(var(--v-theme-primary));
}
</style>
