<template lang="pug">
.mura-container.d-flex.justify-center.py-12
  v-card.mura-card.pa-6(flat width="440")
    h1.text-h5.mb-1 {{ t('auth.signInTitle') }}
    p.text-body-2.text-medium-emphasis.mb-6 {{ t('auth.signInSubtitle') }}

    v-alert.mb-4(v-if="errorMessage" type="error" variant="tonal" density="compact") {{ errorMessage }}

    v-form(@submit.prevent="submit")
      v-text-field.mb-3(
        v-model="email"
        :label="t('auth.email')"
        :error-messages="fieldErrors.email"
        type="email"
        autocomplete="email"
        required
      )
      v-text-field.mb-2(
        v-model="password"
        :label="t('auth.password')"
        :error-messages="fieldErrors.password"
        :type="showPassword ? 'text' : 'password'"
        :append-inner-icon="showPassword ? 'mdi-eye-off' : 'mdi-eye'"
        autocomplete="current-password"
        required
        @click:append-inner="showPassword = !showPassword"
      )

      .d-flex.justify-end.mb-4
        v-btn(to="/auth/recuperar-senha" variant="text" size="small") {{ t('auth.forgotPassword') }}

      v-btn(
        type="submit"
        block
        color="primary"
        variant="flat"
        size="large"
        :loading="auth.loading"
      ) {{ t('auth.signIn') }}

    v-divider.my-6

    .text-center
      span.text-body-2.text-medium-emphasis {{ t('auth.noAccount') }}
      v-btn.ml-1(to="/auth/cadastro" variant="text" color="primary") {{ t('auth.signUp') }}
</template>

<script setup lang="ts">
/**
 * Sign-in page.
 *
 * On success the anonymous cart is merged into the account cart, so items added
 * before signing in are not lost.
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '~/stores/auth'
import { useCartStore } from '~/stores/cart'
import { useFavoritesStore } from '~/stores/favorites'
import { useApiError } from '~/composables/useApiError'
import { StorageKeys, readStorage } from '~/utils/storage'

definePageMeta({ layout: 'default' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const auth = useAuthStore()
const cart = useCartStore()
const favorites = useFavoritesStore()
const { messageFor, fieldErrorsFor } = useApiError()

useSeoMeta({ title: () => t('auth.signIn'), robots: 'noindex' })

const email = ref('')
const password = ref('')
const showPassword = ref(false)
const errorMessage = ref('')
const fieldErrors = ref<Record<string, string[]>>({})

async function submit(): Promise<void> {
  errorMessage.value = ''
  fieldErrors.value = {}

  // Capture the anonymous cart token before signing in replaces it.
  const anonymousCartToken = readStorage(StorageKeys.cartToken) ?? ''

  try {
    await auth.login(email.value.trim(), password.value)
    await Promise.all([
      cart.mergeAfterLogin(anonymousCartToken),
      favorites.fetch(),
    ])

    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.push(redirect)
  }
  catch (error) {
    errorMessage.value = messageFor(error)
    fieldErrors.value = fieldErrorsFor(error)
  }
}
</script>
