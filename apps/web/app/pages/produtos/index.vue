<template lang="pug">
.mura-container.mura-section
  h1.text-h5.mb-1 {{ heading }}
  p.text-body-2.text-medium-emphasis.mb-4(v-if="data") {{ t('common.results', data.count, { count: data.count }) }}

  v-row
    v-col(cols="12" md="3")
      v-card.mura-card.pa-4(flat)
        .d-flex.align-center.justify-space-between.mb-3
          h2.text-subtitle-1 {{ t('common.filters') }}
          v-btn(
            v-if="catalog.hasActiveFilters"
            variant="text"
            size="small"
            @click="clearFilters"
          ) {{ t('common.clearFilters') }}

        v-select.mb-4(
          :model-value="catalog.filters.sort"
          :items="sortOptions"
          :label="t('common.sort')"
          item-title="label"
          item-value="value"
          @update:model-value="value => update({ sort: value })"
        )

        v-select.mb-4(
          :model-value="catalog.filters.category"
          :items="categoryOptions"
          :label="t('product.category')"
          item-title="label"
          item-value="value"
          clearable
          @update:model-value="value => update({ category: value || '' })"
        )

        .d-flex.ga-2.mb-4
          v-text-field(
            :model-value="catalog.filters.minPrice"
            :label="t('common.from')"
            type="number"
            min="0"
            density="compact"
            @update:model-value="value => update({ minPrice: value })"
          )
          v-text-field(
            :model-value="catalog.filters.maxPrice"
            :label="t('common.to')"
            type="number"
            min="0"
            density="compact"
            @update:model-value="value => update({ maxPrice: value })"
          )

        v-switch(
          :model-value="catalog.filters.onSale"
          :label="t('catalog.onlyOnSale')"
          color="primary"
          density="compact"
          hide-details
          @update:model-value="value => update({ onSale: Boolean(value) })"
        )
        v-switch(
          :model-value="catalog.filters.inStock"
          :label="t('catalog.onlyInStock')"
          color="primary"
          density="compact"
          hide-details
          @update:model-value="value => update({ inStock: Boolean(value) })"
        )

    v-col(cols="12" md="9")
      v-progress-linear(v-if="pending" indeterminate color="primary")

      mura-error-state(v-else-if="error" :on-retry="() => refresh()")

      mura-empty-state(
        v-else-if="!data?.results.length"
        :title="t('states.noProducts')"
        :description="t('states.noProductsHint')"
        icon="mdi-magnify"
      )
        template(#action)
          v-btn(color="primary" variant="tonal" @click="clearFilters") {{ t('common.clearFilters') }}

      template(v-else)
        v-row
          v-col(
            v-for="product in data.results"
            :key="product.id"
            cols="6"
            sm="4"
            lg="3"
          )
            mura-product-card(
              :product="product"
              :is-favorite="favorites.isFavorite(product.id)"
              :loading="busyProductId === product.id"
              @add-to-cart="addToCart"
              @toggle-favorite="toggleFavorite"
            )

        v-pagination.mt-6(
          v-if="data.pages > 1"
          :model-value="data.page"
          :length="data.pages"
          :total-visible="5"
          rounded
          @update:model-value="goToPage"
        )
</template>

<script setup lang="ts">
/**
 * Catalog listing.
 *
 * Filters live in the URL so a filtered view can be shared and restored, and in
 * the store so the sidebar and the grid never disagree.
 */
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Category, Paginated, Product } from '~/types/api'
import { useCatalogStore } from '~/stores/catalog'
import { useFavoritesStore } from '~/stores/favorites'
import { useCartActions } from '~/composables/useCartActions'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const catalog = useCatalogStore()
const favorites = useFavoritesStore()
const { busyProductId, addToCart, toggleFavorite } = useCartActions()

// Seed the store from the URL so a deep link renders the right view.
catalog.setFilters({
  search: String(route.query.q ?? ''),
  category: String(route.query.category ?? ''),
  brand: String(route.query.brand ?? ''),
  onSale: route.query.on_sale === 'true',
  inStock: route.query.in_stock === 'true',
  sort: (route.query.sort as never) ?? 'relevance',
  page: Number(route.query.page ?? 1),
})

const { data, pending, error, refresh } = await useAsyncData<Paginated<Product>>(
  'catalog-products',
  () => useNuxtApp().$api.get<Paginated<Product>>('/catalog/products/', {
    query: catalog.queryParams,
  }),
  { watch: [() => catalog.queryParams] },
)

const { data: categories } = await useAsyncData<Category[]>(
  'catalog-categories',
  () => useNuxtApp().$api.get<Category[]>('/catalog/categories/'),
  { default: () => [] },
)

const heading = computed(() =>
  catalog.filters.search
    ? t('catalog.resultsFor', { term: catalog.filters.search })
    : t('catalog.title'),
)

const sortOptions = computed(() => [
  { value: 'relevance', label: t('catalog.sortRelevance') },
  { value: 'price', label: t('catalog.sortPrice') },
  { value: '-price', label: t('catalog.sortPriceDesc') },
  { value: 'name', label: t('catalog.sortName') },
  { value: '-name', label: t('catalog.sortNameDesc') },
  { value: 'newest', label: t('catalog.sortNewest') },
  { value: 'best_sellers', label: t('catalog.sortBestSellers') },
])

const categoryOptions = computed(() =>
  (categories.value ?? []).flatMap(category => [
    { value: category.slug, label: category.name },
    ...category.children.map(child => ({ value: child.slug, label: `— ${child.name}` })),
  ]),
)

useSeoMeta({ title: () => heading.value })

function update(patch: Parameters<typeof catalog.setFilters>[0]): void {
  catalog.setFilters(patch)
}

function clearFilters(): void {
  catalog.clearFilters()
}

function goToPage(page: number): void {
  catalog.setPage(page)
  if (import.meta.client) window.scrollTo({ top: 0, behavior: 'smooth' })
}

// Mirror the filter state back into the URL so the view stays shareable.
watch(
  () => catalog.queryParams,
  (params) => {
    // Router query values must be strings; page 1 is left implicit so the
    // canonical URL of a listing has no `?page=1`.
    const query: Record<string, string> = {}
    for (const [key, value] of Object.entries(params)) {
      if (key === 'page' && value === 1) continue
      query[key] = String(value)
    }
    router.replace({ query })
  },
  { deep: true },
)
</script>
