<template lang="pug">
v-footer.mt-8(color="surface" border)
  .mura-container.py-8
    v-row
      v-col(cols="12" md="4")
        h3.text-subtitle-1.font-weight-bold.mb-2 {{ tenant.storeName }}
        p.text-body-2.text-medium-emphasis.mb-3(v-if="branding?.tagline") {{ branding.tagline }}
        .d-flex.ga-2
          v-btn(
            v-if="branding?.instagram_url"
            :href="branding.instagram_url"
            icon="mdi-instagram"
            variant="text"
            size="small"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Instagram"
          )
          v-btn(
            v-if="branding?.facebook_url"
            :href="branding.facebook_url"
            icon="mdi-facebook"
            variant="text"
            size="small"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Facebook"
          )

      v-col(cols="12" sm="6" md="4")
        h4.text-subtitle-2.font-weight-bold.mb-2 {{ t('store.contact') }}
        p.text-body-2.text-medium-emphasis.mb-1(v-if="address") {{ address }}
        p.text-body-2.text-medium-emphasis.mb-1(v-if="tenant.tenant?.phone") {{ formatPhone(tenant.tenant.phone) }}
        p.text-body-2.text-medium-emphasis(v-if="tenant.tenant?.support_email") {{ tenant.tenant.support_email }}

      v-col(cols="12" sm="6" md="4")
        h4.text-subtitle-2.font-weight-bold.mb-2 {{ t('footer.legal') }}
        v-list(density="compact" bg-color="transparent")
          v-list-item.px-0(
            v-if="settings?.privacy_policy_url"
            :href="settings.privacy_policy_url"
            target="_blank"
            rel="noopener noreferrer"
          )
            v-list-item-title.text-body-2 {{ t('footer.privacyPolicy') }}
          v-list-item.px-0(
            v-if="settings?.terms_url"
            :href="settings.terms_url"
            target="_blank"
            rel="noopener noreferrer"
          )
            v-list-item-title.text-body-2 {{ t('footer.terms') }}

    v-divider.my-4

    .d-flex.flex-wrap.justify-space-between.ga-2
      span.text-caption.text-medium-emphasis © {{ year }} {{ tenant.storeName }}. {{ t('footer.rights') }}
      span.text-caption.text-medium-emphasis {{ t('footer.poweredBy') }}
</template>

<script setup lang="ts">
/**
 * Storefront footer.
 *
 * Contact details, legal links and social profiles all come from the tenant
 * record; nothing here is hard-coded to a particular merchant.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTenantStore } from '~/stores/tenant'
import { formatPhone } from '~/utils/format'

const { t } = useI18n()
const tenant = useTenantStore()

const branding = computed(() => tenant.branding)
const settings = computed(() => tenant.tenant?.settings)
const year = new Date().getFullYear()

const address = computed(() => {
  const parts = tenant.tenant?.address
  if (!parts) return ''
  return [parts.street, parts.number, parts.neighborhood, parts.city, parts.state]
    .filter(Boolean)
    .join(', ')
})
</script>
