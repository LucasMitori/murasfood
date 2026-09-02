<template lang="pug">
.mura-container.mura-section
  .mura-verify
    v-card.mura-card.pa-6.text-center(flat border)
      v-progress-circular.mb-4(v-if="state === 'checking'" indeterminate color="primary" size="44")

      v-avatar.mb-4(v-else :color="tone.color" size="64" variant="tonal")
        v-icon(:icon="tone.icon" size="32")

      h1.text-h6.font-weight-bold.mb-2 {{ tone.title }}
      p.text-body-2.text-medium-emphasis.mb-6 {{ tone.description }}

      //- A failed token is usually an expired one, so the way forward is a new
      //- email rather than a retry of the same link.
      v-form.mb-4(v-if="state === 'failed'" @submit.prevent="resend")
        v-text-field.mb-3(
          v-model="email"
          :label="t('auth.email')"
          :error-messages="resendError"
          type="email"
          variant="outlined"
          density="comfortable"
          hide-details="auto"
        )
        v-btn(
          type="submit"
          color="primary"
          variant="flat"
          block
          rounded="lg"
          prepend-icon="mdi-email-sync-outline"
          :loading="resending"
          :disabled="!email.trim()"
        ) {{ t('auth.resendVerification') }}

      .d-flex.flex-wrap.justify-center.ga-2
        v-btn(
          v-if="state === 'verified'"
          to="/auth/login"
          color="primary"
          variant="flat"
          rounded="lg"
          prepend-icon="mdi-login"
        ) {{ t('nav.signIn') }}
        v-btn(to="/" variant="text" rounded="lg" prepend-icon="mdi-home-outline") {{ t('nav.home') }}
</template>

<script setup lang="ts">
/**
 * Confirms an email address from the link in the verification message.
 *
 * The address is confirmed by this page rather than by the API responding to
 * the link directly: the token is single-use, and letting a mail client's
 * link-prefetch spend it would confirm the address without the person ever
 * arriving — and then show them a failure when they did.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useApiError } from '~/composables/useApiError'
import { useUiStore } from '~/stores/ui'

const { t } = useI18n()
const route = useRoute()
const ui = useUiStore()
const { messageFor } = useApiError()

useSeoMeta({ title: () => t('auth.verifyEmail'), robots: 'noindex' })

type State = 'checking' | 'verified' | 'failed' | 'missing'

const state = ref<State>('checking')
const email = ref('')
const resending = ref(false)
const resendError = ref('')

const tone = computed(() => {
  switch (state.value) {
    case 'verified':
      return {
        icon: 'mdi-check-circle-outline',
        color: 'success',
        title: t('auth.verifyEmailDoneTitle'),
        description: t('auth.verifyEmailDoneBody'),
      }
    case 'failed':
      return {
        icon: 'mdi-link-variant-off',
        color: 'error',
        title: t('auth.verifyEmailFailedTitle'),
        description: t('auth.verifyEmailFailedBody'),
      }
    case 'missing':
      return {
        icon: 'mdi-help-circle-outline',
        color: 'warning',
        title: t('auth.verifyEmailMissingTitle'),
        description: t('auth.verifyEmailMissingBody'),
      }
    default:
      return {
        icon: 'mdi-progress-clock',
        color: 'primary',
        title: t('auth.verifyEmailCheckingTitle'),
        description: t('auth.verifyEmailCheckingBody'),
      }
  }
})

onMounted(async () => {
  const token = String(route.query.token ?? '')
  const uid = String(route.query.uid ?? '')

  if (!token) {
    state.value = 'missing'
    return
  }

  try {
    await useNuxtApp().$api.post('/auth/verify-email/', uid ? { token, uid } : { token })
    state.value = 'verified'
  }
  catch {
    // The reason is nearly always an expired or already-spent token, and
    // neither is worth spelling out — the answer to both is a fresh email.
    state.value = 'failed'
  }
})

async function resend(): Promise<void> {
  resendError.value = ''
  resending.value = true

  try {
    await useNuxtApp().$api.post('/auth/resend-verification/', { email: email.value.trim() })
    ui.success(t('auth.resendVerificationSent'))
  }
  catch (error) {
    resendError.value = messageFor(error)
  }
  finally {
    resending.value = false
  }
}
</script>

<style scoped>
.mura-verify {
  max-width: 30rem;
  margin-inline: auto;
}
</style>
