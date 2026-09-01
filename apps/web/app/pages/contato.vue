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
        v-form(@submit.prevent="openMailClient")
          //- Standard gutters: `dense` squeezed the row to 4px and put the
          //- name and email fields almost against each other.
          v-row
            v-col(cols="12" sm="6")
              v-text-field(
                v-model="form.name"
                :label="t('auth.firstName')"
                :rules="[rules.required]"
                variant="outlined"
                density="comfortable"
              )
            v-col(cols="12" sm="6")
              v-text-field(
                v-model="form.email"
                :label="t('auth.email')"
                :rules="[rules.required, rules.email]"
                type="email"
                variant="outlined"
                density="comfortable"
              )

          v-text-field.mb-4(
            v-model="form.subject"
            :label="t('contact.subject')"
            :rules="[rules.required]"
            variant="outlined"
            density="comfortable"
          )

          v-textarea.mb-4(
            v-model="form.message"
            :label="t('contact.message')"
            :rules="[rules.required]"
            variant="outlined"
            rows="5"
            auto-grow
          )

          //- Right-aligned: the action that ends a form belongs at the end of
          //- the reading order, under the last field it acts on.
          .d-flex.justify-end
            v-btn(
              type="submit"
              color="primary"
              variant="flat"
              size="large"
              rounded="lg"
              append-icon="mdi-send"
              :disabled="!canSend"
            ) {{ t('contact.send') }}
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
import { computed, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTenantStore } from '~/stores/tenant'
import { formatPhone } from '~/utils/format'
import * as validation from '~/utils/validation'

const { t } = useI18n()
const tenant = useTenantStore()

useSeoMeta({
  title: () => t('contact.title'),
  description: () => t('contact.subtitle'),
})

const form = reactive({ name: '', email: '', subject: '', message: '' })

const rules = computed(() => ({
  required: validation.required(t),
  email: validation.email(t),
}))

const canSend = computed(() =>
  Boolean(form.name.trim() && form.email.trim() && form.subject.trim() && form.message.trim()),
)

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

function openMailClient(): void {
  const to = tenant.tenant?.support_email
  if (!to || !canSend.value) return

  const body = `${form.message}\n\n—\n${form.name} <${form.email}>`
  window.location.href =
    `mailto:${to}?subject=${encodeURIComponent(form.subject)}&body=${encodeURIComponent(body)}`
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
