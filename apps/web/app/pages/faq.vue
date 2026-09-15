<template lang="pug">
.mura-container.mura-section
  .text-center.mb-8
    h1.text-h4.font-weight-bold.mb-2 {{ t('faq.title') }}
    p.text-body-1.text-medium-emphasis.mb-0 {{ t('faq.subtitle') }}

  v-row
    v-col(cols="12" md="8")
      section.mb-6(v-for="group in groups" :id="group.id" :key="group.id")
        .d-flex.align-center.ga-2.mb-3
          v-icon(:icon="group.icon" color="primary")
          h2.text-h6.font-weight-bold.mb-0 {{ group.title }}

        v-expansion-panels(variant="accordion" multiple)
          v-expansion-panel(v-for="item in group.items" :key="item.q")
            v-expansion-panel-title {{ item.q }}
            v-expansion-panel-text
              p.text-body-2.mb-0 {{ item.a }}

    v-col(cols="12" md="4")
      v-card.mura-card.mura-faq__aside.pa-5(flat border)
        v-icon.mb-2(icon="mdi-lifebuoy" color="primary" size="28")
        h3.text-subtitle-1.font-weight-bold.mb-1 {{ t('faq.stillStuck') }}
        p.text-body-2.text-medium-emphasis.mb-4 {{ t('faq.stillStuckHint') }}
        v-btn(to="/contact" color="primary" variant="flat" block) {{ t('footer.contactUs') }}
</template>

<script setup lang="ts">
/**
 * Frequently asked questions.
 *
 * The answers describe how *the platform* behaves — delivery windows, PIX
 * expiry, the refund path — so they hold for every merchant on it. Anything
 * merchant-specific (opening hours, delivery radius) is read from the tenant
 * rather than written here.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTenantStore } from '~/stores/tenant'

const { t } = useI18n()
const tenant = useTenantStore()

useSeoMeta({
  title: () => t('faq.title'),
  description: () => t('faq.subtitle'),
})

/**
 * What the merchant has written, if they have written anything.
 *
 * Fetched rather than imported, because these answers used to be locale strings
 * — which meant a shop could not correct its own delivery window without a
 * deploy, and every shop on the platform answered identically.
 */
interface RemoteCategory {
  id: string
  name: string
  slug: string
  icon: string
  entries: { id: string, question: string, answer: string }[]
}

const { data: remote } = await useAsyncData<RemoteCategory[]>(
  'public-faq',
  () => useNuxtApp().$api.get<RemoteCategory[]>('/tenants/faq/'),
  { default: () => [] },
)

/**
 * The shipped copy, used until a shop writes its own.
 *
 * Kept rather than deleted: a new tenant's help page would otherwise be blank
 * on the day they open, and these answers describe how *the platform* behaves —
 * PIX expiry, the refund path — which is true for every shop on it.
 */
const fallbackGroups = computed(() => [
  {
    id: 'pedidos',
    icon: 'mdi-package-variant-closed',
    title: t('faq.orders.title'),
    items: [
      { q: t('faq.orders.q1'), a: t('faq.orders.a1') },
      { q: t('faq.orders.q2'), a: t('faq.orders.a2') },
      { q: t('faq.orders.q3'), a: t('faq.orders.a3') },
    ],
  },
  {
    id: 'entrega',
    icon: 'mdi-truck-outline',
    title: t('faq.delivery.title'),
    items: [
      { q: t('faq.delivery.q1'), a: t('faq.delivery.a1') },
      {
        q: t('faq.delivery.q2'),
        a: t('faq.delivery.a2', { store: tenant.storeName }),
      },
      { q: t('faq.delivery.q3'), a: t('faq.delivery.a3') },
    ],
  },
  {
    id: 'pagamento',
    icon: 'mdi-qrcode',
    title: t('faq.payment.title'),
    items: [
      { q: t('faq.payment.q1'), a: t('faq.payment.a1') },
      { q: t('faq.payment.q2'), a: t('faq.payment.a2') },
    ],
  },
  {
    id: 'trocas',
    icon: 'mdi-swap-horizontal',
    title: t('faq.returns.title'),
    items: [
      { q: t('faq.returns.q1'), a: t('faq.returns.a1') },
      { q: t('faq.returns.q2'), a: t('faq.returns.a2') },
    ],
  },
])

/**
 * Merchant copy wins entirely, or not at all.
 *
 * Deliberately not merged. Interleaving a shop's own answers with the shipped
 * ones produces a page that contradicts itself — their delivery window beside
 * ours — and no way for them to remove the one they disagree with.
 */
const groups = computed(() => {
  const written = remote.value ?? []
  if (!written.length) return fallbackGroups.value

  return written.map(category => ({
    id: category.slug,
    icon: category.icon || 'mdi-help-circle-outline',
    title: category.name,
    items: category.entries.map(entry => ({ q: entry.question, a: entry.answer })),
  }))
})
</script>

<style scoped>
.mura-faq__aside {
  position: sticky;
  top: 5.5rem;
}
</style>
