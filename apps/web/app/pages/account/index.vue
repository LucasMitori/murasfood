<template lang="pug">
.mura-container.mura-section
  mura-page-header(:title="t('account.title')" :subtitle="auth.user?.email")

  v-row
    v-col(cols="12" md="7")
      mura-card(:title="t('account.profile')" icon="mdi-account-outline")
        mura-form-builder(
          ref="profileForm"
          v-model:values="profileValues"
          :schema="profileSchema"
          :loading="savingProfile"
          @submit="saveProfile"
        )

      mura-card.mt-4(:title="t('auth.changePassword')" icon="mdi-lock-outline")
        mura-form-builder(
          ref="passwordForm"
          v-model:values="passwordValues"
          :schema="passwordSchema"
          :loading="savingPassword"
          @submit="changePassword"
        )

    v-col(cols="12" md="5")
      //- Navigation is a list, not four cards. Each was one line of text and a
      //- full-width button in its own box, which spread three links over the
      //- height of the forms beside them and read as clutter.
      mura-card(:title="t('account.title')" icon="mdi-compass-outline" :padded="false")
        v-list(density="comfortable" bg-color="transparent" nav)
          v-list-item.mx-2(
            v-for="link in shortcuts"
            :key="link.to"
            :to="link.to"
            :prepend-icon="link.icon"
            rounded="lg"
            append-icon="mdi-chevron-right"
          )
            v-list-item-title {{ link.title }}
            v-list-item-subtitle {{ link.subtitle }}

      mura-card.mt-4(:title="t('account.privacy')" icon="mdi-shield-lock-outline")
        p.text-body-2.text-medium-emphasis.mb-3 {{ t('account.exportDescription') }}
        v-btn(
          variant="tonal"
          block
          prepend-icon="mdi-download-outline"
          :loading="exporting"
          @click="exportData"
        ) {{ t('account.exportData') }}

        v-divider.my-4

        p.text-body-2.text-medium-emphasis.mb-3 {{ t('account.deleteDescription') }}
        v-btn(
          variant="tonal"
          color="error"
          block
          prepend-icon="mdi-account-remove-outline"
          @click="confirmingDelete = true"
        ) {{ t('account.deleteAccount') }}

  mura-confirm-dialog(
    v-model="confirmingDelete"
    :title="t('account.deleteAccount')"
    :message="t('account.deleteConfirm')"
    :confirm-label="t('account.deleteAccount')"
    :loading="deleting"
    danger
    @confirm="deleteAccount"
  )
</template>

<script setup lang="ts">
/**
 * The customer's own account.
 *
 * Profile and password save separately because they are separate endpoints and
 * separate risks — changing a phone number should not require re-entering a
 * password, and a failed password change should not roll back a name edit.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { FormSchema, FormValues } from '~/types/ui'
import { useAuthStore } from '~/stores/auth'
import { useUiStore } from '~/stores/ui'
import { minLength } from '~/utils/validation'

definePageMeta({ middleware: 'auth', permission: 'perm.account.profile' })

interface FormHandle {
  applyApiError: (error: unknown) => void
  markPristine: () => void
  reset: () => void
}

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()

useSeoMeta({ title: () => t('account.title'), robots: 'noindex' })

const savingProfile = ref(false)
const savingPassword = ref(false)
const exporting = ref(false)
const deleting = ref(false)
const confirmingDelete = ref(false)

const profileForm = ref<FormHandle | null>(null)
const passwordForm = ref<FormHandle | null>(null)

const shortcuts = computed(() => [
  {
    to: '/account/addresses',
    icon: 'mdi-map-marker-outline',
    title: t('account.addresses'),
    subtitle: t('account.addAddress'),
  },
  {
    to: '/account/lists',
    icon: 'mdi-format-list-checks',
    title: t('lists.title'),
    subtitle: t('lists.subtitle'),
  },
  {
    to: '/account/orders',
    icon: 'mdi-package-variant-closed',
    title: t('nav.orders'),
    subtitle: t('account.ordersHint'),
  },
])

const profileValues = ref<FormValues>({
  first_name: auth.user?.first_name ?? '',
  last_name: auth.user?.last_name ?? '',
  phone: auth.user?.phone ?? '',
  marketing_opt_in: auth.user?.marketing_opt_in ?? false,
})

const passwordValues = ref<FormValues>({ current_password: '', new_password: '' })

const profileSchema = computed<FormSchema>(() => ({
  submitLabel: 'common.save',
  sections: [{
    fields: [
      { name: 'first_name', type: 'text', label: 'auth.firstName', required: true, md: 6 },
      { name: 'last_name', type: 'text', label: 'auth.lastName', md: 6 },
      { name: 'phone', type: 'tel', label: 'auth.phone', md: 6 },
      { name: 'marketing_opt_in', type: 'switch', label: 'auth.marketingOptIn', md: 6 },
    ],
  }],
}))

const passwordSchema = computed<FormSchema>(() => ({
  submitLabel: 'auth.changePassword',
  sections: [{
    fields: [
      {
        name: 'current_password',
        type: 'password',
        label: 'auth.currentPassword',
        required: true,
        autocomplete: 'current-password',
      },
      {
        name: 'new_password',
        type: 'password',
        label: 'auth.newPassword',
        required: true,
        rules: [minLength(t, 8)],
        autocomplete: 'new-password',
      },
    ],
  }],
}))

async function saveProfile(values: FormValues): Promise<void> {
  savingProfile.value = true
  try {
    await useNuxtApp().$api.patch('/customers/me/', values)
    await auth.fetchProfile()
    profileForm.value?.markPristine()
    ui.success(t('account.profileUpdated'))
  }
  catch (error) {
    profileForm.value?.applyApiError(error)
  }
  finally {
    savingProfile.value = false
  }
}

async function changePassword(values: FormValues): Promise<void> {
  savingPassword.value = true
  try {
    await useNuxtApp().$api.post('/customers/me/change-password/', values)
    ui.success(t('auth.passwordChanged'))

    // The server invalidates existing sessions, so staying "signed in" here
    // would just fail on the next request.
    await auth.logout()
    await router.push('/auth/login')
  }
  catch (error) {
    passwordForm.value?.applyApiError(error)
  }
  finally {
    savingPassword.value = false
  }
}

async function exportData(): Promise<void> {
  exporting.value = true
  try {
    const data = await useNuxtApp().$api.get('/customers/me/data-export/')

    // Held entirely in the browser: sending personal data through a third party
    // to produce a download would defeat the point of the feature.
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'murasfood-dados.json'
    link.click()
    URL.revokeObjectURL(url)
  }
  catch {
    ui.error(t('errors.generic'))
  }
  finally {
    exporting.value = false
  }
}

async function deleteAccount(): Promise<void> {
  deleting.value = true
  try {
    await useNuxtApp().$api.delete('/customers/me/')
    await auth.logout()
    await router.push('/')
  }
  catch {
    ui.error(t('errors.generic'))
  }
  finally {
    deleting.value = false
    confirmingDelete.value = false
  }
}
</script>
