<template lang="pug">
div
  mura-page-header(
    :title="t('admin.products')"
    :subtitle="t('admin.productsSubtitle')"
    :breadcrumbs="[{ title: 'admin.dashboard', to: '/admin' }, { title: 'admin.products' }]"
  )
    template(#actions)
      mura-button(
        :label="t('import.action')"
        icon="mdi-database-import-outline"
        variant="tonal"
        permission="catalog.create"
        @click="importOpen = true"
      )
      mura-button(
        :label="t('admin.newProduct')"
        icon="mdi-plus"
        permission="catalog.create"
        @click="openCreate"
      )

  mura-data-table(
    :table="table"
    :columns="columns"
    :actions="rowActions"
    :title="t('admin.products')"
    searchable
    exportable
    clickable
    @action="onAction"
    @row-click="openEdit"
  )
    template(#filters)
      v-select.mura-admin-filter(
        v-model="statusFilter"
        :items="statusOptions"
        :label="t('order.status')"
        item-title="label"
        item-value="value"
        density="compact"
        hide-details
        clearable
        @update:model-value="table.applyFilters()"
      )

    //- A fixed 40px box, whatever the photo is — or whether there is one.
      //-
      //- The thumbnail used to be `width="40" height="40"` as *strings*, which
      //- `MuraImage` dropped as invalid CSS: the frames came out 0px tall and
      //- 117–146px wide, so every product name began at a different x. The units
      //- bug is fixed there; this wrapper is what guarantees the column has one
      //- left edge even when a product has no image at all.
    template(#item.name="{ item }")
      .d-flex.align-center.ga-3.py-1
        .mura-product-thumb
          mura-image(
            :asset="item.images?.[0]?.asset"
            :alt="String(item.name)"
            variant="thumbnail"
            :aspect-ratio="1"
            cover
          )
        .min-width-0
          p.text-body-2.mb-0.text-truncate {{ item.name }}
          p.text-caption.text-medium-emphasis.mb-0 {{ item.sku }}

    template(#item.stock_quantity="{ item }")
      v-chip(
        :color="stockColor(item)"
        size="x-small"
        variant="tonal"
      ) {{ money.quantity(String(item.available_quantity ?? 0)) }}

  mura-dialog(
    v-model="formOpen"
    :title="editing ? t('admin.editProduct') : t('admin.newProduct')"
    :max-width="880"
    persistent
  )
    //- Photos first: a product without a picture is the one thing a shopper
      //- will not click, so it is not the last thing asked for.
    .mb-5
      mura-product-gallery(
        v-model="gallery"
        :label="t('admin.productImages')"
        folder="products"
        :max="8"
      )

    v-divider.mb-5

    mura-form-builder(
      ref="formRef"
      v-model:values="formValues"
      :schema="schema"
      :loading="saving"
      :card="false"
      hide-actions
      @submit="save"
    )

    template(#actions)
      v-btn(variant="text" :disabled="saving" @click="formOpen = false") {{ t('common.cancel') }}
      v-btn(color="primary" variant="flat" :loading="saving" @click="formRef?.submit()") {{ t('common.save') }}

  //- Bringing a catalogue in is the first thing a new shop does, so it lives
    //- on the products screen rather than behind a settings page.
  mura-import-dialog(
    v-model="importOpen"
    endpoint="/admin/products/"
    @imported="table.refresh()"
  )

</template>

<script setup lang="ts">
/**
 * Product administration.
 *
 * A worked example of the two builders: the list is a `useServerTable` plus a
 * column schema, and create/edit is one `FormSchema`. Neither needs bespoke
 * markup, which is the point — the next admin screen is a schema, not a page.
 */
import { computed, ref } from 'vue'
import type { GalleryItem } from '~/components/catalog/MuraProductGallery.vue'
import { useI18n } from 'vue-i18n'
import type { FormSchema, FormValues, TableAction, TableColumn } from '~/types/ui'
import type { Category, MediaAsset, UnitOfMeasure } from '~/types/api'
import { useServerTable } from '~/composables/useServerTable'
import { useMoney } from '~/composables/useMoney'
import { useApiError } from '~/composables/useApiError'
import { useUiStore } from '~/stores/ui'

definePageMeta({ layout: 'admin', middleware: 'merchant', permission: 'perm.admin.products' })

/**
 * Typed rather than `Record<string, unknown>`.
 *
 * An untyped row forces a cast wherever a field is used for anything but
 * display — and a cast written into a template is compiled to plain JavaScript
 * and throws in the browser, which is exactly how /admin/users came to never
 * render. Declaring the shape once removes the reason to reach for one.
 */
interface ProductRow {
  id: string
  name: string
  sku: string
  slug: string
  category: string | null
  short_description: string
  description: string
  sale_unit: string
  base_price: string
  cost_price: string | null
  product_type: string
  status: string
  requires_weighing: boolean
  is_featured: boolean
  images?: { asset?: MediaAsset | null, caption?: string }[]
  [key: string]: unknown
}

const { t } = useI18n()
const money = useMoney()
const ui = useUiStore()
const { notify } = useApiError()

useSeoMeta({ title: () => t('admin.products') })

const statusFilter = ref<string | null>(null)

const table = useServerTable<ProductRow>({
  endpoint: '/admin/products/',
  defaultSort: [{ key: 'name', order: 'asc' }],
  // The list shows a computed price but the API orders on the annotation.
  sortMap: { price: 'effective_price', stock_quantity: 'inventory__quantity' },
  filters: () => ({ status: statusFilter.value ?? undefined }),
  searchParam: 'q',
})

const columns: TableColumn<ProductRow>[] = [
  { key: 'name', title: 'admin.productName', sortable: true },
  { key: 'category', title: 'product.category', sortable: false, hideBelow: 'md', value: row => row.category_name ?? '—' },
  { key: 'base_price', title: 'admin.price', sortable: 'effective_price', format: 'money', align: 'end' },
  { key: 'stock_quantity', title: 'admin.inventory', sortable: true, align: 'end', hideBelow: 'sm' },
  { key: 'status', title: 'order.status', sortable: true, format: 'status', align: 'center' },
  { key: 'updated_at', title: 'admin.updatedAt', sortable: true, format: 'datetime', hideBelow: 'lg' },
]

const rowActions: TableAction<ProductRow>[] = [
  { key: 'edit', label: 'common.edit', icon: 'mdi-pencil-outline', permission: 'catalog.update' },
  {
    key: 'publish',
    label: 'admin.publish',
    icon: 'mdi-publish',
    permission: 'catalog.update',
    visibleWhen: row => row.status === 'DRAFT',
  },
  {
    key: 'archive',
    label: 'admin.archive',
    icon: 'mdi-archive-outline',
    color: 'error',
    permission: 'catalog.delete',
    confirm: 'admin.archiveConfirm',
    visibleWhen: row => row.status !== 'ARCHIVED',
  },
]

const statusOptions = computed(() =>
  ['DRAFT', 'ACTIVE', 'INACTIVE', 'OUT_OF_STOCK', 'ARCHIVED'].map(value => ({
    value,
    label: t(`order.status_labels.${value}`, value),
  })),
)

// --- Reference data for the form's selects ----------------------------------
const { data: categories } = await useAsyncData<Category[]>(
  'admin-categories',
  () => useNuxtApp().$api.get<Category[]>('/admin/categories/'),
  { default: () => [] },
)

const { data: units } = await useAsyncData<UnitOfMeasure[]>(
  'admin-units',
  () => useNuxtApp().$api.get<UnitOfMeasure[]>('/admin/units/'),
  { default: () => [] },
)

// --- Form -------------------------------------------------------------------
const formOpen = ref(false)
const importOpen = ref(false)
const saving = ref(false)
const editing = ref<string | null>(null)
const formValues = ref<FormValues>({})
const formRef = ref<{
  submit: () => void
  applyApiError: (error: unknown) => void
  markPristine: () => void
} | null>(null)

const schema = computed<FormSchema>(() => ({
  sections: [
    // The gallery is rendered above the form rather than as a field in it: it
    // needs ordering and a caption per image, which the schema's `image` type
    // cannot express, and inventing a one-off field type for a single screen
    // would put the complexity somewhere it has to be maintained forever.

    {
      title: 'admin.productDetails',
      icon: 'mdi-package-variant-closed',
      fields: [
        { name: 'name', type: 'text', label: 'admin.productName', required: true, maxLength: 255, md: 8 },
        { name: 'sku', type: 'text', label: 'product.sku', maxLength: 64, md: 4, hint: 'admin.skuHint' },
        { name: 'slug', type: 'slug', label: 'admin.slug', slugSource: 'name', md: 6 },
        {
          name: 'category',
          type: 'autocomplete',
          label: 'product.category',
          required: true,
          md: 6,
          options: () => (categories.value ?? []).map(category => ({
            value: category.id,
            label: category.name,
          })),
        },
        { name: 'short_description', type: 'text', label: 'admin.shortDescription', maxLength: 255 },
        { name: 'description', type: 'textarea', label: 'product.description', rows: 4 },
      ],
    },
    {
      title: 'admin.pricingAndUnit',
      icon: 'mdi-tag-outline',
      fields: [
        {
          name: 'sale_unit',
          type: 'select',
          label: 'admin.saleUnit',
          required: true,
          md: 4,
          options: () => (units.value ?? []).map(unit => ({
            value: unit.id,
            label: `${unit.name} (${unit.code})`,
          })),
        },
        { name: 'base_price', type: 'money', label: 'admin.price', required: true, min: 0, md: 4 },
        { name: 'cost_price', type: 'money', label: 'admin.cost', min: 0, md: 4, hint: 'admin.costHint' },
        {
          name: 'product_type',
          type: 'select',
          label: 'admin.productType',
          md: 6,
          default: 'SIMPLE',
          options: [
            { value: 'SIMPLE', label: 'admin.typeSimple' },
            { value: 'WEIGHTED', label: 'admin.typeWeighted' },
          ],
        },
        {
          name: 'requires_weighing',
          type: 'switch',
          label: 'admin.requiresWeighing',
          md: 6,
          // Only meaningful once the product is sold by weight.
          visibleWhen: values => values.product_type === 'WEIGHTED',
        },
      ],
    },
    {
      title: 'admin.inventory',
      icon: 'mdi-warehouse',
      fields: [
        {
          name: 'initial_stock',
          type: 'quantity',
          label: 'admin.initialStock',
          min: 0,
          md: 6,
          // Stock is set once at creation; afterwards it moves only through
          // audited adjustments, so the field would be a lie on an edit form.
          visibleWhen: () => editing.value === null,
        },
        {
          name: 'track_stock',
          type: 'switch',
          label: 'admin.trackStock',
          hint: 'admin.trackStockHint',
          md: 6,
          default: true,
        },
        // Thresholds are per product on purpose. A shop that sells two sacks of
        // rice a week and forty litres of milk cannot have one number mean "low"
        // for both, and the shared `low_stock_threshold` setting was exactly that
        // — which is why the stock-health screen was either noisy or silent.
        {
          name: 'low_stock_threshold',
          type: 'quantity',
          label: 'admin.lowStockThreshold',
          hint: 'admin.lowStockThresholdHint',
          min: 0,
          md: 6,
          visibleWhen: values => values.track_stock !== false,
        },
        {
          name: 'minimum_stock',
          type: 'quantity',
          label: 'admin.minimumStock',
          hint: 'admin.minimumStockHint',
          min: 0,
          md: 6,
          visibleWhen: values => values.track_stock !== false,
        },
      ],
    },
    {
      title: 'admin.visibility',
      icon: 'mdi-eye-outline',
      fields: [
        { name: 'is_featured', type: 'switch', label: 'admin.featured', md: 6 },
      ],
    },
  ],
}))

/**
 * The gallery's own state.
 *
 * Kept beside the form rather than inside its values because it is a list of
 * objects the schema has no field type for, and because it is sent to the API
 * as `gallery` — a different shape from the `image_ids` the import path and
 * older clients still use.
 */
const gallery = ref<GalleryItem[]>([])

function openCreate(): void {
  editing.value = null
  gallery.value = []
  formValues.value = { product_type: 'SIMPLE', is_featured: false }
  formOpen.value = true
}

function openEdit(row: ProductRow): void {
  editing.value = String(row.id)
  formValues.value = {
    name: row.name,
    sku: row.sku,
    slug: row.slug,
    category: row.category,
    short_description: row.short_description,
    description: row.description,
    sale_unit: row.sale_unit,
    base_price: row.base_price,
    cost_price: row.cost_price,
    product_type: row.product_type,
    requires_weighing: row.requires_weighing,
    is_featured: row.is_featured,
    // Read back so the form shows what is stored rather than a blank box the
    // merchant would fill in again with a different number.
    track_stock: row.track_stock !== false,
    low_stock_threshold: row.low_stock_threshold ?? '',
    minimum_stock: row.minimum_stock ?? '',
  }

  gallery.value = (row.images ?? [])
    .map(image => ({
      id: String(image.asset?.id ?? ''),
      caption: image.caption ?? '',
      asset: image.asset ?? null,
    }))
    .filter(item => item.id)

  formOpen.value = true
}

async function save(values: FormValues): Promise<void> {
  saving.value = true
  try {
    // `gallery` carries order and captions; `image_ids` could carry neither.
    values = {
      ...values,
      gallery: gallery.value.map(item => ({ id: item.id, caption: item.caption })),
    }
    if (editing.value) {
      await useNuxtApp().$api.patch(`/admin/products/${editing.value}/`, values)
    }
    else {
      await useNuxtApp().$api.post('/admin/products/', values)
    }

    formRef.value?.markPristine()
    formOpen.value = false
    ui.success(t('form.saved'))
    await table.refresh()
  }
  catch (error) {
    // Field errors land on their inputs; anything else becomes a banner.
    formRef.value?.applyApiError(error)
  }
  finally {
    saving.value = false
  }
}

async function onAction(payload: { key: string, row: ProductRow }): Promise<void> {
  const { key, row } = payload
  if (key === 'edit') {
    openEdit(row)
    return
  }

  try {
    if (key === 'publish') {
      await useNuxtApp().$api.post(`/admin/products/${row.id}/publish/`)
      ui.success(t('admin.published'))
      await table.refresh()
    }
    else if (key === 'archive') {
      await useNuxtApp().$api.delete(`/admin/products/${row.id}/`)
      ui.success(t('admin.archived'))
      // Stepping back avoids an empty page when the last row on it is gone.
      await table.refreshAfterDelete()
    }
  }
  catch (error) {
    notify(error)
  }
}

function stockColor(row: ProductRow): string {
  const available = Number(row.available_quantity ?? 0)
  if (available <= 0) return 'error'
  return available <= 5 ? 'warning' : 'success'
}
</script>

<style scoped>
.mura-admin-filter {
  max-width: 200px;
}

/*
 * One square per row, so the name column has a single left edge.
 *
 * `flex: 0 0 40px` rather than `width` alone: in a flex row a merely-sized
 * child can still be squeezed by a long product name beside it, which is part
 * of how this column got ragged. The other part was `MuraImage` receiving
 * `width="40"` as a string and dropping it as invalid CSS — fixed there.
 */
.mura-product-thumb {
  width: 40px;
  height: 40px;
  flex: 0 0 40px;
  overflow: hidden;
  border-radius: 8px;
}

.mura-product-thumb :deep(.mura-image) {
  width: 100%;
  height: 100%;
  border-radius: 0;
}

.min-width-0 {
  min-width: 0;
}
</style>
