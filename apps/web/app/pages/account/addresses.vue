<template lang="pug">
.mura-container.mura-section
  mura-page-header(:title="t('account.addresses')" back-to="/account")
    template(#actions)
      v-btn(color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCreate") {{ t('account.addAddress') }}

  mura-loading(v-if="pending" skeleton="card@2")

  mura-error-state(v-else-if="error" :on-retry="() => refresh()")

  mura-empty-state(
    v-else-if="!addresses.length"
    :title="t('checkout.selectAddress')"
    :description="t('account.addAddress')"
    icon="mdi-map-marker-outline"
  )
    template(#action)
      v-btn(color="primary" variant="flat" @click="openCreate") {{ t('account.addAddress') }}

  v-row(v-else)
    v-col(v-for="address in addresses" :key="address.id" cols="12" md="6")
      mura-card
        .d-flex.align-start.justify-space-between.mb-2
          div
            .d-flex.align-center.ga-2.mb-1
              span.text-subtitle-1.font-weight-medium {{ address.label || address.recipient_name }}
              v-chip(
                v-if="address.is_default"
                size="x-small"
                color="primary"
                variant="tonal"
              ) {{ t('account.defaultAddress') }}
            p.text-body-2.text-medium-emphasis.mb-0 {{ address.recipient_name }}

          v-menu
            template(#activator="{ props: menuProps }")
              v-btn(v-bind="menuProps" icon="mdi-dots-vertical" variant="text" size="small" :aria-label="t('common.menu')")
            v-list(density="compact")
              v-list-item(prepend-icon="mdi-pencil-outline" @click="openEdit(address)") {{ t('common.edit') }}
              v-list-item(
                v-if="!address.is_default"
                prepend-icon="mdi-star-outline"
                @click="setDefault(address)"
              ) {{ t('account.setDefault') }}
              v-divider
              v-list-item(
                prepend-icon="mdi-delete-outline"
                base-color="error"
                @click="askRemove(address)"
              ) {{ t('common.remove') }}

        p.text-body-2.mb-0 {{ formatAddress(address) }}
        p.text-caption.text-medium-emphasis.mb-0(v-if="address.reference") {{ address.reference }}

  mura-dialog(
    v-model="dialogOpen"
    :title="editing ? t('account.editAddress') : t('account.addAddress')"
    :max-width="720"
    scrollable
  )
    mura-form-builder(
      ref="formRef"
      v-model:values="formValues"
      :schema="schema"
      :loading="saving"
      show-cancel
      @submit="save"
      @cancel="dialogOpen = false"
    )

  mura-confirm-dialog(
    v-model="confirmingRemove"
    :title="t('common.remove')"
    :message="t('account.removeAddressConfirm')"
    :confirm-label="t('common.remove')"
    :loading="removing"
    danger
    @confirm="remove"
  )
</template>

<script setup lang="ts">
/**
 * Delivery addresses.
 *
 * Reached from checkout as well as the account menu, so it has to work as a
 * detour mid-purchase: after saving, the checkout page refetches and the new
 * address is selectable.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { FormSchema, FormValues } from '~/types/ui'
import { useUiStore } from '~/stores/ui'
import { postalCode } from '~/utils/validation'

definePageMeta({ middleware: 'auth', permission: 'perm.account.addresses' })

/** UF codes. Not translated — they are the same in every locale. */
const STATES = [
  'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS', 'MG',
  'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO',
] as const

interface Address {
  id: string
  label: string
  recipient_name: string
  postal_code: string
  street: string
  number: string
  complement: string
  neighborhood: string
  city: string
  state: string
  reference: string
  is_default: boolean
}

const { t } = useI18n()
const ui = useUiStore()

useSeoMeta({ title: () => t('account.addresses'), robots: 'noindex' })

const dialogOpen = ref(false)
const confirmingRemove = ref(false)
const saving = ref(false)
const removing = ref(false)
const editing = ref<Address | null>(null)
const pendingRemoval = ref<Address | null>(null)
const formValues = ref<FormValues>({})
const formRef = ref<{ applyApiError: (error: unknown) => void } | null>(null)

const { data, pending, error, refresh } = await useAsyncData<{ results: Address[] }>(
  'account-addresses',
  () => useNuxtApp().$api.get('/customers/me/addresses/', { query: { page_size: 50 } }),
  { default: () => ({ results: [] }) },
)

const addresses = computed(() => data.value?.results ?? [])

const schema = computed<FormSchema>(() => ({
  submitLabel: 'common.save',
  sections: [{
    fields: [
      { name: 'label', type: 'text', label: 'account.addressLabel', placeholder: 'account.addressLabelPlaceholder', md: 6 },
      { name: 'recipient_name', type: 'text', label: 'account.recipient', required: true, md: 6 },
      {
        name: 'postal_code',
        type: 'text',
        label: 'account.postalCode',
        required: true,
        maxLength: 9,
        rules: [postalCode(t)],
        md: 4,
      },
      { name: 'street', type: 'text', label: 'account.street', required: true, md: 8 },
      { name: 'number', type: 'text', label: 'account.number', required: true, md: 3 },
      { name: 'complement', type: 'text', label: 'account.complement', md: 4 },
      { name: 'neighborhood', type: 'text', label: 'account.neighborhood', required: true, md: 5 },
      { name: 'city', type: 'text', label: 'account.city', required: true, md: 8 },
      {
        name: 'state',
        type: 'select',
        label: 'account.state',
        required: true,
        md: 4,
        options: STATES.map(code => ({ value: code, label: code })),
      },
      { name: 'reference', type: 'text', label: 'account.reference' },
      { name: 'is_default', type: 'switch', label: 'account.setDefault' },
    ],
  }],
}))

function formatAddress(address: Address): string {
  const parts = [
    [address.street, address.number].filter(Boolean).join(', '),
    address.complement,
    address.neighborhood,
    [address.city, address.state].filter(Boolean).join(' - '),
    address.postal_code,
  ]
  return parts.filter(Boolean).join(' · ')
}

function openCreate(): void {
  editing.value = null
  // First address is the default one: there is nothing to choose between.
  formValues.value = { is_default: addresses.value.length === 0, state: '' }
  dialogOpen.value = true
}

function openEdit(address: Address): void {
  editing.value = address
  formValues.value = { ...address }
  dialogOpen.value = true
}

async function save(values: FormValues): Promise<void> {
  saving.value = true
  try {
    const api = useNuxtApp().$api
    if (editing.value) await api.patch(`/customers/me/addresses/${editing.value.id}/`, values)
    else await api.post('/customers/me/addresses/', values)

    dialogOpen.value = false
    await refresh()
    ui.success(t('account.addressSaved'))
  }
  catch (error_) {
    formRef.value?.applyApiError(error_)
  }
  finally {
    saving.value = false
  }
}

async function setDefault(address: Address): Promise<void> {
  try {
    await useNuxtApp().$api.patch(`/customers/me/addresses/${address.id}/`, { is_default: true })
    await refresh()
    ui.success(t('account.addressSaved'))
  }
  catch {
    ui.error(t('errors.generic'))
  }
}

function askRemove(address: Address): void {
  pendingRemoval.value = address
  confirmingRemove.value = true
}

async function remove(): Promise<void> {
  if (!pendingRemoval.value) return

  removing.value = true
  try {
    await useNuxtApp().$api.delete(`/customers/me/addresses/${pendingRemoval.value.id}/`)
    await refresh()
    ui.success(t('account.addressRemoved'))
  }
  catch {
    ui.error(t('errors.generic'))
  }
  finally {
    removing.value = false
    confirmingRemove.value = false
    pendingRemoval.value = null
  }
}
</script>
