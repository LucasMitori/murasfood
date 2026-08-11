<template lang="pug">
section.mura-trust(:aria-label="t('home.whyUs')")
  .mura-container
    .mura-trust__grid
      .mura-trust__item(v-for="point in points" :key="point.icon")
        .mura-trust__icon
          v-icon(:icon="point.icon" size="22")
        div
          p.mura-trust__title {{ point.title }}
          p.mura-trust__text {{ point.text }}
</template>

<script setup lang="ts">
/**
 * The four things a first-time visitor wants to know before ordering food.
 *
 * Deliberately static copy rather than merchant-editable: these are claims
 * about how the platform works — delivery windows, payment, freshness policy —
 * and every deployment honours them.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const points = computed(() => [
  { icon: 'mdi-truck-fast-outline', title: t('home.trust.deliveryTitle'), text: t('home.trust.deliveryText') },
  { icon: 'mdi-leaf', title: t('home.trust.freshTitle'), text: t('home.trust.freshText') },
  { icon: 'mdi-shield-check-outline', title: t('home.trust.secureTitle'), text: t('home.trust.secureText') },
  { icon: 'mdi-headset', title: t('home.trust.supportTitle'), text: t('home.trust.supportText') },
])
</script>

<style scoped>
.mura-trust {
  padding: 2.5rem 0;
  border-block: 1px solid rgba(var(--v-border-color), 0.6);
  background: rgb(var(--v-theme-surface));
}

.mura-trust__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
  gap: 1.75rem;
}

.mura-trust__item {
  display: flex;
  align-items: flex-start;
  gap: 0.875rem;
}

.mura-trust__icon {
  display: grid;
  flex-shrink: 0;
  place-items: center;
  width: 2.75rem;
  height: 2.75rem;
  border-radius: 12px;
  background: rgba(var(--v-theme-primary), 0.1);
  color: rgb(var(--v-theme-primary));
}

.mura-trust__title {
  margin-bottom: 0.125rem;
  font-size: 0.9375rem;
  font-weight: 600;
}

.mura-trust__text {
  margin-bottom: 0;
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.8125rem;
  line-height: 1.45;
}
</style>
