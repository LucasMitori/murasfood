<template lang="pug">
v-app
  a.mura-skip-link(href="#main-content") {{ t('common.skipToContent') }}
  nuxt-layout
    nuxt-page
  mura-notifications
</template>

<script setup lang="ts">
/**
 * Application shell.
 *
 * Sets the document language from the active locale and provides the skip link
 * that keyboard users need to bypass the header (spec §57).
 */
import { useI18n } from 'vue-i18n'
import { useTenantStore } from '~/stores/tenant'

const { t, locale } = useI18n()
const tenant = useTenantStore()

// A reactive getter keeps `lang` in step with the locale switcher without
// wrapping the whole options object in a ref.
useHead(() => ({
  htmlAttrs: { lang: locale.value },
  titleTemplate: (title?: string) => (title ? `${title} · ${tenant.storeName}` : tenant.storeName),
}))
</script>
