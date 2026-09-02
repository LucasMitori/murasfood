<template lang="pug">
.mura-container.mura-section
  mura-page-header(
    :title="t('lists.title')"
    :subtitle="t('lists.subtitle')"
    back-to="/account"
  )
    template(#actions)
      v-btn(color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCreate") {{ t('lists.newList') }}

  mura-loading(v-if="store.loading && !store.hasLists" skeleton="card@2")

  mura-empty-state(
    v-else-if="!store.hasLists"
    :title="t('lists.emptyTitle')"
    :description="t('lists.emptyDescription')"
    icon="mdi-format-list-checks"
  )
    template(#action)
      v-btn(color="primary" variant="flat" @click="openCreate") {{ t('lists.newList') }}

  v-row(v-else)
    v-col(cols="12" md="4")
      //- A card, like the panel beside it. As a bare `v-list` this column had
      //- 8px of list padding against the detail card's 16px, which is what made
      //- the two halves look misaligned.
      mura-card(:title="t('lists.yourLists')" icon="mdi-playlist-check" :padded="false")
        v-list.py-2(density="comfortable" nav bg-color="transparent")
          v-list-item.mx-2(
            v-for="row in store.lists"
            :key="row.id"
            :active="row.id === selectedId"
            rounded="lg"
            color="primary"
            @click="select(row.id)"
          )
            template(#prepend)
              v-icon(icon="mdi-format-list-checks")
            v-list-item-title {{ row.name }}
            v-list-item-subtitle {{ t('lists.itemCount', row.item_count, { count: row.item_count }) }}

    v-col(cols="12" md="8")
      mura-loading(v-if="loadingDetail" skeleton="card")

      mura-card(
        v-else-if="store.current"
        :title="store.current.name"
        :subtitle="t('lists.itemCount', store.current.items.length, { count: store.current.items.length })"
        icon="mdi-format-list-checks"
      )
        template(#actions)
          v-btn.mr-1(
            color="primary"
            variant="flat"
            prepend-icon="mdi-cart-plus"
            :loading="adding"
            :disabled="!store.current.items.length"
            @click="addToCart"
          ) {{ t('lists.addToCart') }}
          v-menu
            template(#activator="{ props: menuProps }")
              v-btn(v-bind="menuProps" icon="mdi-dots-vertical" variant="text" :aria-label="t('common.menu')")
            v-list(density="compact")
              v-list-item(prepend-icon="mdi-pencil-outline" @click="openRename") {{ t('lists.rename') }}
              v-divider
              v-list-item(prepend-icon="mdi-delete-outline" base-color="error" @click="confirmingDelete = true") {{ t('common.remove') }}

        mura-empty-state(
          v-if="!store.current.items.length"
          :title="t('lists.noItems')"
          :description="t('lists.noItemsHint')"
          icon="mdi-cart-outline"
        )
          template(#action)
            v-btn(to="/products" color="primary" variant="tonal") {{ t('cart.continueShopping') }}

        template(v-else)
          ul.mura-list-items
            li.mura-list-item(v-for="item in store.current.items" :key="item.id")
              v-avatar.flex-shrink-0(rounded="lg" size="48")
                v-img(
                  :src="item.product.image?.variants?.thumbnail || item.product.image?.url"
                  :alt="item.product.image?.alt_text || item.product.name"
                  cover
                )

              .mura-list-item__body
                nuxt-link.mura-list-item__name(:to="`/products/${item.product.slug}`") {{ item.product.name }}
                .d-flex.align-center.ga-2.flex-wrap
                  span.text-caption.text-medium-emphasis {{ money.quantity(item.quantity, item.product.unit.code) }} · {{ money.format(item.unit_price) }}
                  v-chip(
                    v-if="!item.is_available"
                    size="x-small"
                    color="warning"
                    variant="tonal"
                  ) {{ t('lists.unavailable') }}

              span.mura-list-item__total {{ money.format(item.line_total) }}

              v-btn.flex-shrink-0(
                icon="mdi-close"
                size="x-small"
                variant="text"
                :aria-label="t('common.remove')"
                @click="removeItem(item.id)"
              )

          .mura-list-total
            div
              p.text-body-2.text-medium-emphasis.mb-0 {{ t('lists.estimatedTotal') }}
              p.text-caption.text-medium-emphasis.mb-0 {{ t('lists.estimatedNote') }}
            span.text-h5.font-weight-bold {{ money.format(store.current.estimated_total) }}

  mura-dialog(v-model="formOpen" :title="renaming ? t('lists.rename') : t('lists.newList')")
    v-form(@submit.prevent="submitForm")
      v-text-field(
        v-model="formName"
        :label="t('lists.name')"
        :placeholder="t('lists.namePlaceholder')"
        :error-messages="formError"
        variant="outlined"
        density="comfortable"
        autofocus
      )
    template(#actions)
      v-btn(variant="text" @click="formOpen = false") {{ t('common.cancel') }}
      v-btn(color="primary" variant="flat" :loading="store.saving" @click="submitForm") {{ t('common.save') }}

  mura-confirm-dialog(
    v-model="confirmingDelete"
    :title="t('common.remove')"
    :message="t('lists.deleteConfirm')"
    :confirm-label="t('common.remove')"
    danger
    @confirm="removeList"
  )
</template>

<script setup lang="ts">
/**
 * Shopping lists.
 *
 * Index and detail side by side rather than as two routes: choosing a list and
 * seeing what is on it is one task, and a customer comparing "monthly" against
 * "weekly" would otherwise be navigating back and forth.
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useShoppingListsStore } from '~/stores/shoppingLists'
import { useCartStore } from '~/stores/cart'
import { useUiStore } from '~/stores/ui'
import { useMoney } from '~/composables/useMoney'
import { useApiError } from '~/composables/useApiError'

definePageMeta({ middleware: 'auth', permission: 'perm.account.lists' })

const { t } = useI18n()
const store = useShoppingListsStore()
const cart = useCartStore()
const ui = useUiStore()
const money = useMoney()
const { messageFor } = useApiError()

useSeoMeta({ title: () => t('lists.title'), robots: 'noindex' })

const selectedId = ref('')
const loadingDetail = ref(false)
const adding = ref(false)
const formOpen = ref(false)
const renaming = ref(false)
const formName = ref('')
const formError = ref('')
const confirmingDelete = ref(false)

async function select(id: string): Promise<void> {
  selectedId.value = id
  loadingDetail.value = true
  try {
    await store.open(id)
  }
  finally {
    loadingDetail.value = false
  }
}

function openCreate(): void {
  renaming.value = false
  formName.value = ''
  formError.value = ''
  formOpen.value = true
}

function openRename(): void {
  renaming.value = true
  formName.value = store.current?.name ?? ''
  formError.value = ''
  formOpen.value = true
}

async function submitForm(): Promise<void> {
  formError.value = ''
  const name = formName.value.trim()
  if (!name) {
    formError.value = t('validation.required')
    return
  }

  try {
    if (renaming.value && store.current) {
      await store.rename(store.current.id, name)
      await select(store.current.id)
    }
    else {
      const created = await store.create(name)
      await select(created.id)
    }
    formOpen.value = false
  }
  catch (error) {
    // A duplicate name is the expected failure, so it belongs on the field.
    formError.value = messageFor(error)
  }
}

async function removeItem(itemId: string): Promise<void> {
  if (!store.current) return
  await store.removeItem(store.current.id, itemId)
}

async function removeList(): Promise<void> {
  if (!store.current) return
  await store.remove(store.current.id)
  confirmingDelete.value = false

  const next = store.lists[0]
  if (next) await select(next.id)
  else selectedId.value = ''
}

async function addToCart(): Promise<void> {
  if (!store.current) return

  adding.value = true
  try {
    const result = await store.addToCart(store.current.id)
    await cart.fetch()

    // Report both halves. A list kept for months will eventually name
    // something that is out of stock, and silently dropping it would leave the
    // customer short without knowing.
    if (result.skipped_count > 0) {
      ui.notify(
        t('lists.addedPartially', {
          added: result.added_count,
          skipped: result.skipped_count,
        }),
        'warning',
        7000,
      )
    }
    else {
      ui.success(t('lists.addedAll', { count: result.added_count }))
    }
  }
  catch (error) {
    ui.error(messageFor(error))
  }
  finally {
    adding.value = false
  }
}

await store.fetch()

// Open the first list so the detail pane is never an empty frame.
const first = store.lists[0]
if (first) await select(first.id)
</script>

<style scoped>
.mura-list-items {
  padding: 0;
  margin: 0;
  list-style: none;
}

.mura-list-item {
  display: flex;
  align-items: center;
  gap: 0.875rem;
  padding: 0.75rem 0;
}

.mura-list-item + .mura-list-item {
  border-top: 1px solid rgba(var(--v-border-color), 0.5);
}

.mura-list-item__body {
  min-width: 0;
  flex: 1 1 auto;
}

.mura-list-item__name {
  display: block;
  overflow: hidden;
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.9375rem;
  font-weight: 500;
  text-decoration: none;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mura-list-item__name:hover {
  color: rgb(var(--v-theme-primary));
}

.mura-list-item__total {
  flex-shrink: 0;
  font-size: 0.9375rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.mura-list-total {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding-top: 1rem;
  margin-top: 0.5rem;
  border-top: 1px solid rgba(var(--v-border-color), 0.8);
}
</style>
