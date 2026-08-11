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
        v-btn(to="/contato" color="primary" variant="flat" block) {{ t('footer.contactUs') }}
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

const groups = computed(() => [
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
</script>

<style scoped>
.mura-faq__aside {
  position: sticky;
  top: 5.5rem;
}
</style>
