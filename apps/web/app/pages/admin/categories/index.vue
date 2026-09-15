<template lang="pug">
div
  mura-page-header(
    :title="t('admin.categories')"
    :subtitle="t('admin.categoriesSubtitle')"
    :breadcrumbs="[{ title: 'admin.dashboard', to: '/admin' }, { title: 'admin.categories' }]"
  )
    template(#actions)
      v-btn(color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCreate()") {{ createLabel }}

  v-tabs.mb-4(v-model="tab" color="primary")
    v-tab(value="product" prepend-icon="mdi-shape-outline") {{ t('admin.categoriesProduct') }}
    v-tab(value="brand" prepend-icon="mdi-tag-multiple-outline") {{ t('admin.brands') }}
    v-tab(value="tag" prepend-icon="mdi-label-outline") {{ t('admin.tags') }}
    v-tab(value="finance" prepend-icon="mdi-finance") {{ t('admin.categoriesFinance') }}

  v-window(v-model="tab")
    //- --- Product categories: a tree, because they nest ----------------------
    v-window-item(value="product")
      mura-loading(v-if="pendingCategories" skeleton="card")

      mura-empty-state(
        v-else-if="!roots.length"
        :title="t('admin.categoriesEmpty')"
        :description="t('admin.categoriesEmptyHint')"
        icon="mdi-shape-outline"
      )
        template(#action)
          v-btn(color="primary" variant="flat" @click="openCreate()") {{ t('admin.categoryNew') }}

      .mura-cats(v-else)
        article.mura-cat-row(v-for="root in roots" :key="root.id")
          .mura-cat-row__main
            mura-image.mura-cat-row__image(
              v-if="root.image"
              :asset="root.image"
              :alt="''"
              variant="thumbnail"
              :aspect-ratio="1"
              cover
            )
            .mura-cat-row__mark(v-else)
              v-icon(icon="mdi-shape-outline" size="20" color="on-surface-variant")

            .flex-grow-1.min-width-0
              .d-flex.align-center.ga-2.flex-wrap
                h3.mura-cat-row__name {{ root.name }}
                v-chip(v-if="!root.is_active" size="x-small" variant="tonal" color="secondary") {{ t('admin.inactive') }}
                v-chip(v-if="root.is_featured" size="x-small" variant="tonal" color="primary") {{ t('admin.featured') }}
              p.text-caption.text-medium-emphasis.mb-0
                | {{ t('admin.categoryProductCount', root.product_count ?? 0, { count: root.product_count ?? 0 }) }}
                |  · /{{ root.slug }}

            .mura-cat-row__actions
              v-btn(
                icon="mdi-plus"
                variant="text"
                size="small"
                density="comfortable"
                :aria-label="t('admin.categoryAddChild')"
                :title="t('admin.categoryAddChild')"
                @click="openCreate(undefined, root.id)"
              )
              v-btn(
                icon="mdi-pencil-outline"
                variant="text"
                size="small"
                density="comfortable"
                :aria-label="t('common.edit')"
                @click="openCreate(root)"
              )
              v-btn(
                icon="mdi-delete-outline"
                variant="text"
                size="small"
                density="comfortable"
                color="error"
                :aria-label="t('common.delete')"
                @click="confirmDelete(root)"
              )

          //- Children indented under their parent: a listing includes its
            //- subcategories, so the nesting is not decoration — it is what the
            //- storefront filter actually does.
          .mura-cat-row__children(v-if="root.children?.length")
            .mura-cat-child(v-for="child in root.children" :key="child.id")
              v-icon(icon="mdi-subdirectory-arrow-right" size="14" color="on-surface-variant")
              span.flex-grow-1 {{ child.name }}
              v-chip(v-if="!child.is_active" size="x-small" variant="tonal" color="secondary") {{ t('admin.inactive') }}
              v-btn(
                icon="mdi-pencil-outline"
                variant="text"
                size="x-small"
                :aria-label="t('common.edit')"
                @click="openCreate(child)"
              )
              v-btn(
                icon="mdi-delete-outline"
                variant="text"
                size="x-small"
                color="error"
                :aria-label="t('common.delete')"
                @click="confirmDelete(child)"
              )

    //- --- The flat lists ----------------------------------------------------
    v-window-item(value="brand")
      mura-simple-list(
        :items="brands"
        :empty-title="t('admin.brandsEmpty')"
        icon="mdi-tag-multiple-outline"
        @edit="openCreate"
        @delete="confirmDelete"
      )

    v-window-item(value="tag")
      mura-simple-list(
        :items="tags"
        :empty-title="t('admin.tagsEmpty')"
        icon="mdi-label-outline"
        @edit="openCreate"
        @delete="confirmDelete"
      )

    v-window-item(value="finance")
      p.text-body-2.text-medium-emphasis.mb-4 {{ t('admin.categoriesFinanceHint') }}
      mura-simple-list(
        :items="financeCategories"
        :empty-title="t('admin.categoriesEmpty')"
        icon="mdi-finance"
        readonly
      )

  //- --- The editor ----------------------------------------------------------
  mura-dialog(v-model="formOpen" :title="editing ? t('common.edit') : createLabel" max-width="560")
    v-text-field.mb-4(
      v-model="draft.name"
      :label="t('common.name')"
      :error-messages="errors.name"
      variant="outlined"
      density="comfortable"
      autofocus
    )

    template(v-if="tab === 'product'")
      v-select.mb-4(
        v-model="draft.parent"
        :items="parentOptions"
        :label="t('admin.categoryParent')"
        :hint="t('admin.categoryParentHint')"
        item-title="label"
        item-value="value"
        variant="outlined"
        density="comfortable"
        clearable
        persistent-hint
      )

      v-textarea.mb-4(
        v-model="draft.description"
        :label="t('admin.description')"
        variant="outlined"
        rows="2"
        auto-grow
        hide-details
      )

      mura-image-upload.mb-4(
        v-model="draft.image_id"
        :label="t('admin.categoryImage')"
        folder="categories"
      )

      .d-flex.flex-wrap.ga-4
        v-switch(
          v-model="draft.is_active"
          :label="t('admin.active')"
          color="primary"
          density="compact"
          hide-details
        )
        v-switch(
          v-model="draft.is_featured"
          :label="t('admin.featured')"
          color="primary"
          density="compact"
          hide-details
        )

    v-text-field(
      v-if="tab === 'tag'"
      v-model="draft.color"
      :label="t('admin.tagColour')"
      variant="outlined"
      density="comfortable"
      hide-details
      placeholder="#8C1425"
    )

    template(#actions)
      v-spacer
      v-btn(variant="text" @click="formOpen = false") {{ t('common.cancel') }}
      v-btn(color="primary" variant="flat" :loading="saving" @click="save") {{ t('common.save') }}

  mura-confirm-dialog(
    v-model="confirmOpen"
    :message="confirmMessage"
    @confirm="runDelete"
    @cancel="pendingDelete = null"
  )
</template>

<script setup lang="ts">
/**
 * Everything a product gets filed under, in one place.
 *
 * Four tabs because a merchant thinks of these as one job — "how my catalogue
 * is organised" — while the API keeps them as four resources with different
 * shapes. Categories nest and carry an image; brands and tags are flat; finance
 * categories are the chart of accounts and are read-only here, because changing
 * one retroactively rewrites what every past ledger entry means.
 *
 * Product categories render as a tree rather than a list: a listing filtered to
 * "Padaria" includes everything under it, so the nesting is the behaviour, not
 * a presentation choice.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Category } from '~/types/api'
import { useApiError } from '~/composables/useApiError'
import { useUiStore } from '~/stores/ui'

definePageMeta({ layout: 'admin', middleware: 'merchant', permission: 'perm.admin.products' })

interface SimpleRow {
  id: string
  name: string
  slug?: string
  color?: string
  is_active?: boolean
  kind?: string
}

const { t } = useI18n()
const ui = useUiStore()
const { messageFor, notify } = useApiError()

useSeoMeta({ title: () => t('admin.categories') })

const tab = ref<'product' | 'brand' | 'tag' | 'finance'>('product')

/** Which resource each tab writes to. One map rather than four branches. */
const ENDPOINTS: Record<string, string> = {
  product: '/admin/categories/',
  brand: '/admin/brands/',
  tag: '/admin/tags/',
  finance: '/admin/finance/categories/',
}

const { data: categoryData, pending: pendingCategories, refresh: refreshCategories }
  = await useAsyncData<Category[]>(
    'admin-product-categories',
    () => useNuxtApp().$api.get<Category[]>('/admin/categories/'),
    { default: () => [] },
  )

const { data: brandData, refresh: refreshBrands } = await useAsyncData<{ results: SimpleRow[] }>(
  'admin-brands',
  () => useNuxtApp().$api.get<{ results: SimpleRow[] }>('/admin/brands/', {
    query: { page_size: 200 },
  }),
  { default: () => ({ results: [] }) },
)

const { data: tagData, refresh: refreshTags } = await useAsyncData<SimpleRow[]>(
  'admin-tags',
  () => useNuxtApp().$api.get<SimpleRow[]>('/admin/tags/'),
  { default: () => [] },
)

const { data: financeData } = await useAsyncData<SimpleRow[]>(
  'admin-finance-category-list',
  () => useNuxtApp().$api.get<SimpleRow[]>('/admin/finance/categories/'),
  { default: () => [] },
)

/** Only roots at the top level; children are rendered nested under them. */
const roots = computed(() => (categoryData.value ?? []).filter(category => !category.parent))
const brands = computed(() => brandData.value?.results ?? [])
const tags = computed(() => tagData.value ?? [])
const financeCategories = computed(() => financeData.value ?? [])

const createLabel = computed(() => ({
  product: t('admin.categoryNew'),
  brand: t('admin.brandNew'),
  tag: t('admin.tagNew'),
  finance: t('admin.categoryNew'),
}[tab.value]))

// --- The editor --------------------------------------------------------------
const formOpen = ref(false)
const saving = ref(false)
const editing = ref<string | null>(null)
const errors = ref<Record<string, string[]>>({})

/** A category cannot be its own parent, and this tree is two levels deep. */
const parentOptions = computed(() =>
  roots.value
    .filter(root => root.id !== editing.value)
    .map(root => ({ value: root.id, label: root.name })),
)

const draft = ref<Record<string, unknown>>({
  name: '',
  parent: null,
  description: '',
  image_id: null,
  color: '',
  is_active: true,
  is_featured: false,
})

function openCreate(row?: SimpleRow | Category, parent?: string): void {
  errors.value = {}
  editing.value = row?.id ?? null
  draft.value = {
    name: row?.name ?? '',
    parent: (row as Category | undefined)?.parent ?? parent ?? null,
    description: (row as Category | undefined)?.description ?? '',
    image_id: (row as Category | undefined)?.image?.id ?? null,
    color: (row as SimpleRow | undefined)?.color ?? '',
    is_active: row ? (row as Category).is_active !== false : true,
    is_featured: (row as Category | undefined)?.is_featured ?? false,
  }
  formOpen.value = true
}

async function save(): Promise<void> {
  errors.value = {}
  if (!String(draft.value.name).trim()) {
    errors.value = { name: [t('validation.required')] }
    return
  }

  saving.value = true
  try {
    const endpoint = ENDPOINTS[tab.value]!
    // Only the fields the resource on this tab actually has: sending `parent`
    // to the brand endpoint is a 400, and sending it as `null` is still sending
    // it.
    const payload: Record<string, unknown> = { name: draft.value.name }

    if (tab.value === 'product') {
      Object.assign(payload, {
        parent: draft.value.parent || null,
        description: draft.value.description,
        image_id: draft.value.image_id || null,
        is_active: draft.value.is_active,
        is_featured: draft.value.is_featured,
      })
    }
    if (tab.value === 'tag' && draft.value.color) payload.color = draft.value.color

    if (editing.value) await useNuxtApp().$api.patch(`${endpoint}${editing.value}/`, payload)
    else await useNuxtApp().$api.post(endpoint, payload)

    formOpen.value = false
    ui.success(t('form.saved'))
    await reload()
  }
  catch (err) {
    notify(err)
  }
  finally {
    saving.value = false
  }
}

// --- Deleting ----------------------------------------------------------------
const confirmOpen = ref(false)
const pendingDelete = ref<SimpleRow | Category | null>(null)

const confirmMessage = computed(() =>
  pendingDelete.value ? t('admin.categoryDeleteConfirm', { name: pendingDelete.value.name }) : '',
)

function confirmDelete(row: SimpleRow | Category): void {
  pendingDelete.value = row
  confirmOpen.value = true
}

async function runDelete(): Promise<void> {
  const row = pendingDelete.value
  confirmOpen.value = false
  pendingDelete.value = null
  if (!row) return

  try {
    await useNuxtApp().$api.delete(`${ENDPOINTS[tab.value]}${row.id}/`)
    ui.success(t('form.deleted'))
    await reload()
  }
  catch (err) {
    // A category with products in it is protected by the API rather than
    // cascading, so this is the common path and not an exception.
    ui.error(messageFor(err))
  }
}

async function reload(): Promise<void> {
  await Promise.all([refreshCategories(), refreshBrands(), refreshTags()])
}
</script>

<style scoped>
.min-width-0 {
  min-width: 0;
}

.mura-cats {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mura-cat-row {
  padding: 14px 16px;
  border: 1px solid rgba(var(--v-border-color), 0.55);
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
  transition: border-color 140ms ease;
}

.mura-cat-row:hover {
  border-color: rgba(var(--v-theme-primary), 0.45);
}

.mura-cat-row__main {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* A fixed square whatever the image is, so a column of rows has one left edge
   rather than one per aspect ratio. */
.mura-cat-row__image,
.mura-cat-row__mark {
  width: 44px;
  height: 44px;
  flex: 0 0 auto;
  border-radius: 10px;
  overflow: hidden;
}

.mura-cat-row__mark {
  display: grid;
  border: 1px dashed rgba(var(--v-border-color), 0.9);
  place-items: center;
}

.mura-cat-row__name {
  font-size: 0.92rem;
  font-weight: 600;
  line-height: 1.25;
}

.mura-cat-row__actions {
  display: flex;
  flex: 0 0 auto;
  gap: 2px;
}

.mura-cat-row__children {
  display: flex;
  margin-top: 10px;
  margin-inline-start: 56px;
  flex-direction: column;
  gap: 2px;
}

.mura-cat-child {
  display: flex;
  align-items: center;
  padding: 4px 8px;
  border-radius: 8px;
  font-size: 0.83rem;
  gap: 8px;
}

.mura-cat-child:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}

@media (prefers-reduced-motion: reduce) {
  .mura-cat-row {
    transition: none;
  }
}
</style>
