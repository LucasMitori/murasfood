<template lang="pug">
v-card.mura-card(:class="{ 'mura-card--interactive': Boolean(to || clickable) }" :to="to" flat)
  .d-flex.align-center.ga-3.pa-4.pb-2(v-if="title || $slots.header || $slots.actions")
    v-avatar(v-if="icon" :color="iconColor" variant="tonal" size="36")
      v-icon(:icon="icon" size="20")
    div.flex-grow-1.min-width-0
      slot(name="header")
        h3.text-subtitle-1.font-weight-medium.text-truncate {{ title }}
        p.text-caption.text-medium-emphasis.mb-0(v-if="subtitle") {{ subtitle }}
    slot(name="actions")

  v-divider(v-if="divided && (title || $slots.header)")

  mura-loading(v-if="loading" :skeleton="loadingSkeleton")

  mura-error-state(v-else-if="error" :description="error" :on-retry="onRetry")

  component(:is="padded ? 'v-card-text' : 'div'" v-else)
    slot

  v-card-actions(v-if="$slots.footer")
    slot(name="footer")
</template>

<script setup lang="ts">
/**
 * Section card with the header, loading, error and empty states that every
 * panel in the app needs.
 *
 * Using it rather than a bare `v-card` is what keeps those states consistent —
 * and present at all, which is the more common failure.
 */
withDefaults(defineProps<{
  title?: string
  subtitle?: string
  icon?: string
  iconColor?: string
  to?: string
  clickable?: boolean
  loading?: boolean
  loadingSkeleton?: string
  /** Already-translated error message; shows the error state when set. */
  error?: string
  onRetry?: () => void
  padded?: boolean
  divided?: boolean
}>(), {
  title: '',
  subtitle: '',
  icon: '',
  iconColor: 'primary',
  to: undefined,
  clickable: false,
  loading: false,
  loadingSkeleton: 'card',
  error: '',
  onRetry: undefined,
  padded: true,
  divided: false,
})
</script>

<style scoped>
.min-width-0 {
  min-width: 0;
}
</style>
