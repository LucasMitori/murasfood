<template lang="pug">
v-app
  v-main
    .mura-error
      //- Decorative only, and hidden from assistive tech: the status is
      //- announced by the heading and the code below it.
      .mura-error__glow(aria-hidden="true")

      .mura-error__inner
        .mura-error__code(aria-hidden="true") {{ status }}

        .mura-error__badge
          v-icon(:icon="detail.icon" size="20")
          span {{ detail.badge }}

        h1.mura-error__title {{ detail.title }}
        p.mura-error__text {{ detail.description }}

        .mura-error__actions
          v-btn(
            color="primary"
            variant="flat"
            size="large"
            rounded="lg"
            prepend-icon="mdi-home-outline"
            @click="goHome"
          ) {{ t('nav.home') }}

          v-btn(
            v-if="canRetry"
            variant="tonal"
            size="large"
            rounded="lg"
            prepend-icon="mdi-refresh"
            @click="reload"
          ) {{ t('common.retry') }}

          v-btn(
            v-if="status === 401 || status === 403"
            variant="tonal"
            size="large"
            rounded="lg"
            prepend-icon="mdi-login"
            @click="goSignIn"
          ) {{ t('nav.signIn') }}

        //- Somewhere to go next. A dead end with only "back to home" makes a
        //- mistyped URL feel like the site is broken.
        .mura-error__links
          span.text-caption.text-medium-emphasis {{ t('errors.tryInstead') }}
          .d-flex.flex-wrap.justify-center.ga-2.mt-2
            v-btn(
              v-for="link in suggestions"
              :key="link.to"
              :to="link.to"
              :prepend-icon="link.icon"
              variant="text"
              size="small"
            ) {{ link.label }}
</template>

<script setup lang="ts">
/**
 * Error page for every status Nuxt hands us.
 *
 * Shows a translated explanation, never the underlying exception — a stack
 * trace is neither useful nor safe for a customer (spec §36). Each status gets
 * its own wording, because "not found" and "not allowed" call for different
 * things from the reader: one is a wrong address, the other a wrong account.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { NuxtError } from '#app'

const props = defineProps<{ error: NuxtError }>()
const { t } = useI18n()

const status = computed(() => Number(props.error?.statusCode) || 500)

/** Retrying a 404 or a 403 just repeats it; only a fault is worth another go. */
const canRetry = computed(() => status.value >= 500)

const detail = computed(() => {
  switch (status.value) {
    case 404:
      return {
        icon: 'mdi-map-search-outline',
        badge: t('errors.pages.404.badge'),
        title: t('errors.pages.404.title'),
        description: t('errors.pages.404.description'),
      }
    case 403:
      return {
        icon: 'mdi-lock-outline',
        badge: t('errors.pages.403.badge'),
        title: t('errors.pages.403.title'),
        description: t('errors.pages.403.description'),
      }
    case 401:
      return {
        icon: 'mdi-account-lock-outline',
        badge: t('errors.pages.401.badge'),
        title: t('errors.pages.401.title'),
        description: t('errors.pages.401.description'),
      }
    case 503:
      return {
        icon: 'mdi-tools',
        badge: t('errors.pages.503.badge'),
        title: t('errors.pages.503.title'),
        description: t('errors.pages.503.description'),
      }
    default:
      return {
        icon: 'mdi-alert-circle-outline',
        badge: t('errors.pages.500.badge'),
        title: t('errors.pages.500.title'),
        description: t('errors.pages.500.description'),
      }
  }
})

const suggestions = computed(() => [
  { to: '/produtos', icon: 'mdi-view-grid-outline', label: t('nav.catalog') },
  { to: '/produtos?on_sale=true', icon: 'mdi-sale', label: t('nav.offers') },
  { to: '/faq', icon: 'mdi-help-circle-outline', label: t('footer.faq') },
  { to: '/contato', icon: 'mdi-email-outline', label: t('footer.contactUs') },
])

function goHome(): void {
  clearError({ redirect: '/' })
}

function goSignIn(): void {
  clearError({ redirect: '/auth/login' })
}

function reload(): void {
  clearError({ redirect: useRoute().fullPath })
}
</script>

<style scoped>
.mura-error {
  position: relative;
  display: grid;
  min-height: 100svh;
  overflow: hidden;
  place-items: center;
  padding: 3rem 1.5rem;
  background: rgb(var(--v-theme-background));
}

/* A soft wash of the brand colour behind the number, so the page reads as part
   of the store rather than a browser default. */
.mura-error__glow {
  position: absolute;
  top: -30%;
  left: 50%;
  width: min(52rem, 120vw);
  height: min(52rem, 120vw);
  border-radius: 50%;
  background: radial-gradient(
    circle,
    rgba(var(--v-theme-primary), 0.18),
    transparent 62%
  );
  transform: translateX(-50%);
  pointer-events: none;
}

.mura-error__inner {
  position: relative;
  max-width: 34rem;
  text-align: center;
}

.mura-error__code {
  font-size: clamp(5rem, 18vw, 9rem);
  font-weight: 800;
  line-height: 1;
  letter-spacing: -0.05em;
  /* Outlined rather than filled: at this size a solid block of colour would
     dominate the message it is meant to introduce. */
  color: transparent;
  -webkit-text-stroke: 2px rgba(var(--v-theme-primary), 0.45);
}

.mura-error__badge {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.75rem;
  margin-bottom: 1rem;
  border-radius: 999px;
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.mura-error__title {
  margin-bottom: 0.75rem;
  font-size: clamp(1.5rem, 4vw, 2rem);
  font-weight: 700;
  line-height: 1.15;
  text-wrap: balance;
}

.mura-error__text {
  margin-bottom: 2rem;
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 1rem;
  line-height: 1.6;
  text-wrap: pretty;
}

.mura-error__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.75rem;
}

.mura-error__links {
  padding-top: 1.5rem;
  margin-top: 2.5rem;
  border-top: 1px solid rgba(var(--v-border-color), 0.6);
}
</style>
