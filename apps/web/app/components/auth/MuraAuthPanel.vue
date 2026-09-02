<template lang="pug">
.mura-auth
  .mura-auth__stage
    .mura-auth__brand
      v-icon.mb-2(icon="mdi-storefront-outline" size="40" color="primary")
      h1.text-h5.mb-1 {{ flipped ? t('auth.signUpTitle') : t('auth.signInTitle') }}
      p.text-body-2.text-medium-emphasis.mb-0 {{ flipped ? t('auth.signUpSubtitle') : t('auth.signInSubtitle') }}

    mura-flip-card.mt-6(v-model="flipped")
      //- Front — sign in
      template(#front)
        v-card.mura-auth__card.pa-6(:elevation="2" rounded="lg")
          v-alert.mb-4(
            v-if="signInError"
            type="error"
            variant="tonal"
            density="compact"
          ) {{ signInError }}

          v-alert.mb-4(
            v-if="justRegistered"
            type="success"
            variant="tonal"
            density="compact"
            :text="t('auth.verifyEmailSubtitle', { email: signUp.email })"
          )

          v-form(ref="signInForm" @submit.prevent="submitSignIn")
            v-text-field.mb-3(
              v-model="signIn.email"
              :label="t('auth.email')"
              :rules="[rules.required, rules.email]"
              :error-messages="signInFields.email"
              type="email"
              autocomplete="email"
              variant="outlined"
              density="comfortable"
              prepend-inner-icon="mdi-email-outline"
            )
            v-text-field.mb-2(
              v-model="signIn.password"
              :label="t('auth.password')"
              :rules="[rules.required]"
              :error-messages="signInFields.password"
              :type="showSignInPassword ? 'text' : 'password'"
              :append-inner-icon="showSignInPassword ? 'mdi-eye-off' : 'mdi-eye'"
              autocomplete="current-password"
              variant="outlined"
              density="comfortable"
              prepend-inner-icon="mdi-lock-outline"
              @click:append-inner="showSignInPassword = !showSignInPassword"
            )

            .d-flex.justify-end.mb-4
              v-btn(to="/auth/reset-password" variant="text" size="small") {{ t('auth.forgotPassword') }}

            v-btn(
              type="submit"
              block
              color="primary"
              variant="flat"
              size="large"
              :loading="auth.loading && !flipped"
            ) {{ t('auth.signIn') }}

          v-divider.my-5

          .text-center
            span.text-body-2.text-medium-emphasis {{ t('auth.noAccount') }}
            v-btn.ml-1(
              variant="text"
              color="primary"
              append-icon="mdi-rotate-3d-variant"
              @click="flip(true)"
            ) {{ t('auth.signUp') }}

      //- Back — register
      template(#back)
        v-card.mura-auth__card.pa-6(:elevation="2" rounded="lg")
          v-alert.mb-4(
            v-if="signUpError"
            type="error"
            variant="tonal"
            density="compact"
          ) {{ signUpError }}

          v-form(ref="signUpForm" @submit.prevent="submitSignUp")
            v-row(dense)
              v-col(cols="12" sm="6")
                v-text-field.mb-3(
                  v-model="signUp.first_name"
                  :label="t('auth.firstName')"
                  :rules="[rules.required]"
                  :error-messages="signUpFields.first_name"
                  autocomplete="given-name"
                  variant="outlined"
                  density="comfortable"
                )
              v-col(cols="12" sm="6")
                v-text-field.mb-3(
                  v-model="signUp.last_name"
                  :label="t('auth.lastName')"
                  :error-messages="signUpFields.last_name"
                  autocomplete="family-name"
                  variant="outlined"
                  density="comfortable"
                )

            v-text-field.mb-3(
              v-model="signUp.email"
              :label="t('auth.email')"
              :rules="[rules.required, rules.email]"
              :error-messages="signUpFields.email"
              type="email"
              autocomplete="email"
              variant="outlined"
              density="comfortable"
              prepend-inner-icon="mdi-email-outline"
            )

            v-text-field.mb-3(
              v-model="signUp.phone"
              :label="t('auth.phone')"
              :rules="[rules.phoneOptional]"
              :error-messages="signUpFields.phone"
              autocomplete="tel"
              variant="outlined"
              density="comfortable"
              prepend-inner-icon="mdi-phone-outline"
            )

            v-text-field.mb-3(
              v-model="signUp.password"
              :label="t('auth.password')"
              :rules="[rules.required, rules.min8]"
              :error-messages="signUpFields.password"
              :type="showSignUpPassword ? 'text' : 'password'"
              :append-inner-icon="showSignUpPassword ? 'mdi-eye-off' : 'mdi-eye'"
              autocomplete="new-password"
              variant="outlined"
              density="comfortable"
              prepend-inner-icon="mdi-lock-outline"
              @click:append-inner="showSignUpPassword = !showSignUpPassword"
            )

            v-text-field.mb-1(
              v-model="passwordConfirm"
              :label="t('auth.passwordConfirm')"
              :rules="[rules.required, rules.confirm]"
              :type="showSignUpPassword ? 'text' : 'password'"
              autocomplete="new-password"
              variant="outlined"
              density="comfortable"
              prepend-inner-icon="mdi-lock-check-outline"
            )

            v-checkbox(
              v-model="signUp.accepted_terms"
              :rules="[rules.accepted]"
              :label="t('auth.acceptTerms')"
              density="compact"
              color="primary"
            )
            v-checkbox.mb-3(
              v-model="signUp.marketing_opt_in"
              :label="t('auth.marketingOptIn')"
              density="compact"
              color="primary"
              hide-details
            )

            v-btn(
              type="submit"
              block
              color="primary"
              variant="flat"
              size="large"
              :loading="auth.loading && flipped"
            ) {{ t('auth.signUp') }}

          v-divider.my-5

          .text-center
            span.text-body-2.text-medium-emphasis {{ t('auth.hasAccount') }}
            v-btn.ml-1(
              variant="text"
              color="primary"
              append-icon="mdi-rotate-3d-variant"
              @click="flip(false)"
            ) {{ t('auth.signIn') }}
</template>

<script setup lang="ts">
/**
 * Sign in and register on one page, as two faces of a card that rotates.
 *
 * Flipping is deliberately *not* a route change. Navigating would unmount one
 * page component and mount the other, which kills the animation — the card
 * would vanish and reappear. Instead both forms live here and the URL is
 * corrected afterwards with `history.replaceState`, so the address bar stays
 * honest without the router tearing the card down mid-rotation. It is
 * `replaceState` rather than `pushState` because turning a card over is not a
 * navigation, and stacking history entries would make Back feel broken.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '~/stores/auth'
import { useCartStore } from '~/stores/cart'
import { useFavoritesStore } from '~/stores/favorites'
import { useApiError } from '~/composables/useApiError'
import { StorageKeys, readStorage } from '~/utils/storage'
import * as validation from '~/utils/validation'

const props = withDefaults(defineProps<{
  /** Which face is showing on first paint. */
  initial?: 'signin' | 'signup'
}>(), { initial: 'signin' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const auth = useAuthStore()
const cart = useCartStore()
const favorites = useFavoritesStore()
const { messageFor, fieldErrorsFor } = useApiError()

const flipped = ref(props.initial === 'signup')
const justRegistered = ref(false)

const signIn = ref({ email: '', password: '' })
const signUp = ref({
  first_name: '',
  last_name: '',
  email: '',
  phone: '',
  password: '',
  accepted_terms: false,
  marketing_opt_in: false,
})
const passwordConfirm = ref('')

const showSignInPassword = ref(false)
const showSignUpPassword = ref(false)
const signInError = ref('')
const signUpError = ref('')
const signInFields = ref<Record<string, string[]>>({})
const signUpFields = ref<Record<string, string[]>>({})

const signInForm = ref<{ validate: () => Promise<{ valid: boolean }> } | null>(null)
const signUpForm = ref<{ validate: () => Promise<{ valid: boolean }> } | null>(null)

const rules = computed(() => ({
  required: validation.required(t),
  email: validation.email(t),
  min8: validation.minLength(t, 8),
  accepted: validation.accepted(t),
  confirm: validation.matches(t, () => signUp.value.password),
  // Phone is optional here, so an empty value must pass.
  phoneOptional: (value: unknown) =>
    validation.isBlank(value) ? true : validation.phone(t)(value),
}))

/** Where to land after a successful sign-in. */
const redirectTo = computed(() =>
  typeof route.query.redirect === 'string' ? route.query.redirect : '/',
)

function flip(toSignUp: boolean): void {
  flipped.value = toSignUp
  signInError.value = ''
  signUpError.value = ''

  // Keep the address bar in step without letting the router unmount the card.
  if (import.meta.client) {
    const path = toSignUp ? '/auth/register' : '/auth/login'
    const query = route.query.redirect ? `?redirect=${encodeURIComponent(String(route.query.redirect))}` : ''
    window.history.replaceState(window.history.state, '', `${path}${query}`)
  }
}

/** Sign-in and post-registration both funnel through here. */
async function establishSession(email: string, password: string): Promise<void> {
  // Capture the anonymous cart token before signing in replaces it.
  const anonymousCartToken = readStorage(StorageKeys.cartToken) ?? ''

  await auth.login(email, password)
  await Promise.all([
    cart.mergeAfterLogin(anonymousCartToken),
    favorites.fetch(),
  ])

  await router.push(redirectTo.value)
}

async function submitSignIn(): Promise<void> {
  signInError.value = ''
  signInFields.value = {}

  const result = await signInForm.value?.validate()
  if (result && !result.valid) return

  try {
    await establishSession(signIn.value.email.trim(), signIn.value.password)
  }
  catch (error) {
    signInError.value = messageFor(error)
    signInFields.value = fieldErrorsFor(error)
  }
}

async function submitSignUp(): Promise<void> {
  signUpError.value = ''
  signUpFields.value = {}

  const result = await signUpForm.value?.validate()
  if (result && !result.valid) return

  const email = signUp.value.email.trim()
  const password = signUp.value.password

  try {
    await auth.register({ ...signUp.value, email })
  }
  catch (error) {
    signUpError.value = messageFor(error)
    signUpFields.value = fieldErrorsFor(error)
    return
  }

  // The account exists from here on. A failure signing in is no longer a
  // registration failure, so it must not be reported as one — flip to sign-in
  // and let them try there rather than implying the account was not created.
  try {
    await establishSession(email, password)
  }
  catch {
    justRegistered.value = true
    signIn.value.email = email
    flip(false)
  }
}

onMounted(() => {
  // `?modo=cadastro` (or `?mode=signup`) opens straight on the back face, which
  // is what an emailed "create your account" link should do.
  const mode = String(route.query.modo ?? route.query.mode ?? '')
  if (mode === 'cadastro' || mode === 'signup' || mode === 'register') flipped.value = true
})
</script>

<style scoped>
.mura-auth {
  display: flex;
  align-items: center;
  justify-content: center;
  /*
   * Fill the whole region under the header so the card sits in the middle of
   * what the visitor can actually see.
   *
   * Matched to the content region rather than guessed at: `100vh` minus a
   * number picked to allow for a footer meant the card drifted off centre
   * whenever the footer was a different height. 120px is the header and its
   * search bar, which is the only chrome above this.
   *
   * `svh` because on mobile `vh` is measured with the browser's chrome
   * retracted, which makes the region taller than the screen and pushes the
   * card below the fold on the very devices with least room to spare.
   */
  min-height: calc(100svh - 120px);
  padding: 2rem 1rem;
}

.mura-auth__stage {
  width: 100%;
  max-width: 460px;
}

.mura-auth__brand {
  text-align: center;
}

.mura-auth__card {
  /*
   * Both faces are painted during the rotation, so a transparent card would
   * show the other one through it as it turns.
   */
  background: rgb(var(--v-theme-surface));
}
</style>
