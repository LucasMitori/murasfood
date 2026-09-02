<template lang="pug">
.mura-auth-simple
  .mura-auth-simple__stage
    .text-center.mb-6
      v-icon.mb-2(icon="mdi-lock-reset" size="40" color="primary")
      h1.text-h5.mb-1 {{ t('auth.resetPassword') }}
      p.text-body-2.text-medium-emphasis.mb-0 {{ hasToken ? t('auth.newPassword') : t('auth.resetPasswordSubtitle') }}

    v-card.pa-6(:elevation="2" rounded="lg")
      v-alert.mb-4(v-if="errorMessage" type="error" variant="tonal" density="compact") {{ errorMessage }}

      //- Request stage: always reports success, whether or not the address exists.
      template(v-if="!hasToken")
        v-alert(
          v-if="sent"
          type="success"
          variant="tonal"
          density="compact"
          :text="t('auth.resetSent')"
        )

        v-form(v-else ref="requestForm" @submit.prevent="submitRequest")
          v-text-field.mb-4(
            v-model="email"
            :label="t('auth.email')"
            :rules="[rules.required, rules.email]"
            :error-messages="fieldErrors.email"
            type="email"
            autocomplete="email"
            variant="outlined"
            density="comfortable"
            prepend-inner-icon="mdi-email-outline"
          )
          v-btn(
            type="submit"
            block
            color="primary"
            variant="flat"
            size="large"
            :loading="loading"
          ) {{ t('auth.sendLink') }}

      //- Confirm stage: arrived from the emailed link.
      template(v-else)
        v-form(ref="confirmForm" @submit.prevent="submitConfirm")
          v-text-field.mb-3(
            v-model="password"
            :label="t('auth.newPassword')"
            :rules="[rules.required, rules.min8]"
            :error-messages="fieldErrors.password"
            :type="showPassword ? 'text' : 'password'"
            :append-inner-icon="showPassword ? 'mdi-eye-off' : 'mdi-eye'"
            autocomplete="new-password"
            variant="outlined"
            density="comfortable"
            prepend-inner-icon="mdi-lock-outline"
            @click:append-inner="showPassword = !showPassword"
          )
          v-text-field.mb-4(
            v-model="passwordConfirm"
            :label="t('auth.passwordConfirm')"
            :rules="[rules.required, rules.confirm]"
            :type="showPassword ? 'text' : 'password'"
            autocomplete="new-password"
            variant="outlined"
            density="comfortable"
            prepend-inner-icon="mdi-lock-check-outline"
          )
          v-btn(
            type="submit"
            block
            color="primary"
            variant="flat"
            size="large"
            :loading="loading"
          ) {{ t('auth.resetPassword') }}

      v-divider.my-5

      .text-center
        v-btn(to="/auth/login" variant="text" color="primary" prepend-icon="mdi-arrow-left") {{ t('auth.signIn') }}
</template>

<script setup lang="ts">
/**
 * Password recovery — both halves of the flow.
 *
 * Without a token in the URL this asks for an address; with one it sets the new
 * password. They are one page because the emailed link lands here, and a
 * separate route would only exist to be redirected from.
 *
 * The request stage always reports success. Saying "no such account" would turn
 * this form into a way to test whether an address is registered.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '~/stores/auth'
import { useApiError } from '~/composables/useApiError'
import * as validation from '~/utils/validation'

definePageMeta({ layout: 'default' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const { messageFor, fieldErrorsFor } = useApiError()

useSeoMeta({ title: () => t('auth.resetPassword'), robots: 'noindex' })

const token = computed(() => String(route.query.token ?? ''))
const uid = computed(() => String(route.query.uid ?? ''))
const hasToken = computed(() => token.value.length > 0)

const email = ref('')
const password = ref('')
const passwordConfirm = ref('')
const showPassword = ref(false)
const sent = ref(false)
const loading = ref(false)
const errorMessage = ref('')
const fieldErrors = ref<Record<string, string[]>>({})

const requestForm = ref<{ validate: () => Promise<{ valid: boolean }> } | null>(null)
const confirmForm = ref<{ validate: () => Promise<{ valid: boolean }> } | null>(null)

const rules = computed(() => ({
  required: validation.required(t),
  email: validation.email(t),
  min8: validation.minLength(t, 8),
  confirm: validation.matches(t, () => password.value),
}))

async function submitRequest(): Promise<void> {
  errorMessage.value = ''
  fieldErrors.value = {}

  const result = await requestForm.value?.validate()
  if (result && !result.valid) return

  loading.value = true
  try {
    await useNuxtApp().$api.post('/auth/password-reset/', { email: email.value.trim() }, { anonymous: true })
    sent.value = true
  }
  catch (error) {
    errorMessage.value = messageFor(error)
    fieldErrors.value = fieldErrorsFor(error)
  }
  finally {
    loading.value = false
  }
}

async function submitConfirm(): Promise<void> {
  errorMessage.value = ''
  fieldErrors.value = {}

  const result = await confirmForm.value?.validate()
  if (result && !result.valid) return

  loading.value = true
  try {
    await useNuxtApp().$api.post(
      '/auth/password-reset/confirm/',
      { token: token.value, ...(uid.value ? { uid: uid.value } : {}), password: password.value },
      { anonymous: true },
    )

    // Any session opened with the old password is no longer trustworthy.
    auth.clearTokens()
    await router.push('/auth/login')
  }
  catch (error) {
    errorMessage.value = messageFor(error)
    fieldErrors.value = fieldErrorsFor(error)
  }
  finally {
    loading.value = false
  }
}
</script>

<style scoped>
.mura-auth-simple {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 220px);
  padding: 2rem 1rem 3rem;
}

.mura-auth-simple__stage {
  width: 100%;
  max-width: 440px;
}
</style>
