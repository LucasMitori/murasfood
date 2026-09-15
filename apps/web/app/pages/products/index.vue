<template lang="pug">
.mura-container.mura-section
  h1.text-h5.mb-1 {{ heading }}
  p.text-body-2.text-medium-emphasis.mb-4(v-if="data") {{ t('common.results', data.count, { count: data.count }) }}

  //- Search first, and inside the listing rather than only in the header.
    //- A shop with ten thousand items is browsed by typing, and someone who has
    //- already narrowed to a category wants to search *within* it rather than
    //- start again from the global field in the header.
  v-text-field.mb-4(
    :model-value="searchDraft"
    :placeholder="t('catalog.searchInCatalog')"
    :aria-label="t('common.search')"
    prepend-inner-icon="mdi-magnify"
    variant="solo-filled"
    density="comfortable"
    rounded="lg"
    flat
    hide-details
    clearable
    @update:model-value="onSearch"
  )

  //- Categories as cards, under the title, filtering the grid in place.
    //- A dropdown hides the shape of the catalogue; a row of cards *is* that
    //- shape, and one tap re-renders below without leaving the page.
  .mura-cat-rail.mb-5(v-if="categoryCards.length")
    button.mura-cat(
      :class="{ 'mura-cat--active': !catalog.filters.category }"
      type="button"
      :aria-pressed="!catalog.filters.category"
      @click="update({ category: '' })"
    )
      v-icon.mura-cat__icon(icon="mdi-view-grid-outline" size="22")
      span.mura-cat__name {{ t('catalog.allCategories') }}

    button.mura-cat(
      v-for="category in categoryCards"
      :key="category.slug"
      :class="{ 'mura-cat--active': catalog.filters.category === category.slug }"
      type="button"
      :aria-pressed="catalog.filters.category === category.slug"
      @click="update({ category: category.slug })"
    )
      mura-image.mura-cat__image(
        v-if="category.image"
        :asset="category.image"
        :alt="''"
        variant="thumbnail"
        :aspect-ratio="1"
        :rounded="false"
        cover
      )
      v-icon.mura-cat__icon(v-else icon="mdi-tag-outline" size="22")
      span.mura-cat__name {{ category.name }}
      span.mura-cat__count(v-if="category.product_count") {{ category.product_count }}

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

        //- What is actually narrowing the list, as removable chips.
          //- With eight controls it stops being obvious why a search returned
          //- four items, and the fix is to show the answer rather than expect
          //- the shopper to audit the sidebar.
        .mura-filter-chips.mb-4(v-if="activeChips.length")
          v-chip(
            v-for="chip in activeChips"
            :key="chip.key"
            size="small"
            closable
            variant="tonal"
            color="primary"
            @click:close="chip.clear()"
          ) {{ chip.label }}

        v-select.mb-4(
          :model-value="catalog.filters.sort"
          :items="sortOptions"
          :label="t('common.sort')"
          item-title="label"
          item-value="value"
          density="comfortable"
          hide-details
          @update:model-value="value => update({ sort: value })"
        )

        v-select.mb-4(
          :model-value="catalog.filters.category"
          :items="categoryOptions"
          :label="t('product.category')"
          item-title="label"
          item-value="value"
          density="comfortable"
          hide-details
          clearable
          @update:model-value="value => update({ category: value || '' })"
        )

        v-select.mb-4(
          v-if="brandOptions.length"
          :model-value="catalog.filters.brand"
          :items="brandOptions"
          :label="t('product.brand')"
          item-title="label"
          item-value="value"
          density="comfortable"
          hide-details
          clearable
          @update:model-value="value => update({ brand: value || '' })"
        )

        p.text-caption.text-medium-emphasis.mb-1 {{ t('catalog.filterAvailability') }}
        v-btn-toggle.mb-4.mura-filter-toggle(
          :model-value="catalog.filters.availability"
          color="primary"
          density="compact"
          variant="outlined"
          divided
          mandatory
          @update:model-value="value => update({ availability: value ?? '' })"
        )
          v-btn(value="" size="small") {{ t('catalog.availabilityAll') }}
          v-btn(value="in" size="small") {{ t('catalog.availabilityIn') }}
          v-btn(value="out" size="small") {{ t('catalog.availabilityOut') }}

        p.text-caption.text-medium-emphasis.mb-1 {{ t('catalog.priceRange') }}
        .d-flex.ga-2.mb-4
          v-text-field(
            :model-value="catalog.filters.minPrice"
            :label="t('common.from')"
            type="number"
            min="0"
            density="compact"
            hide-details
            @update:model-value="value => update({ minPrice: value })"
          )
          v-text-field(
            :model-value="catalog.filters.maxPrice"
            :label="t('common.to')"
            type="number"
            min="0"
            density="compact"
            hide-details
            @update:model-value="value => update({ maxPrice: value })"
          )

        p.text-caption.text-medium-emphasis.mb-1 {{ t('catalog.filterDiscount') }}
        v-slider.mb-2(
          :model-value="Number(catalog.filters.minDiscount) || 0"
          :min="0"
          :max="70"
          :step="5"
          color="primary"
          density="compact"
          hide-details
          :aria-label="t('catalog.filterDiscount')"
          @end="value => update({ minDiscount: value ? String(value) : '' })"
        )
          template(#append)
            span.text-caption.mura-filter-pct {{ Number(catalog.filters.minDiscount) || 0 }}%

        v-switch(
          :model-value="catalog.filters.onSale"
          :label="t('catalog.onlyOnSale')"
          color="primary"
          density="compact"
          hide-details
          @update:model-value="value => update({ onSale: Boolean(value) })"
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
 *
 * Sized for a real market rather than a demo. Ten thousand products is not
 * browsed by scrolling, so this screen offers three ways in and lets them
 * compose: type into the field, tap a category card, or narrow in the sidebar.
 * The chips above the filters exist because with this many controls a shopper
 * otherwise cannot tell why the grid has four things in it.
 */
import { computed, ref, watch } from 'vue'
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
  availability: (['in', 'out'].includes(String(route.query.availability))
    ? String(route.query.availability)
    : '') as '' | 'in' | 'out',
  minDiscount: String(route.query.min_discount ?? ''),
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

// --- Search ------------------------------------------------------------------
const searchDraft = ref(catalog.filters.search)

/**
 * Debounced, because each keystroke is a request against the whole catalogue.
 *
 * 350 ms matches the admin tables. Shorter and a four-letter word costs four
 * round trips; longer and the grid feels like it is lagging behind the typing.
 */
let searchTimer: ReturnType<typeof setTimeout> | null = null

function onSearch(value: string | null): void {
  searchDraft.value = value ?? ''
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    catalog.setFilters({ search: searchDraft.value })
  }, 350)
}

// --- Categories --------------------------------------------------------------
/** Root categories only: the rail is a way in, not the whole tree. */
const categoryCards = computed(() => categories.value ?? [])

const categoryOptions = computed(() =>
  (categories.value ?? []).flatMap(category => [
    { value: category.slug, label: category.name },
    ...category.children.map(child => ({ value: child.slug, label: `— ${child.name}` })),
  ]),
)

/**
 * Brands present in the current result set.
 *
 * Derived from what came back rather than fetched separately: a market carries
 * hundreds of brands and a dropdown listing all of them is unusable, while the
 * ones on screen are exactly the ones worth narrowing by.
 */
const brandOptions = computed(() => {
  const names = new Set<string>()
  for (const product of data.value?.results ?? []) {
    if (product.brand_name) names.add(product.brand_name)
  }
  return [...names].sort().map(name => ({ value: name, label: name }))
})

const sortOptions = computed(() => [
  { value: 'relevance', label: t('catalog.sortRelevance') },
  { value: 'price', label: t('catalog.sortPrice') },
  { value: '-price', label: t('catalog.sortPriceDesc') },
  { value: 'name', label: t('catalog.sortName') },
  { value: '-name', label: t('catalog.sortNameDesc') },
  { value: 'newest', label: t('catalog.sortNewest') },
  { value: 'best_sellers', label: t('catalog.sortBestSellers') },
])

/** Every filter currently narrowing the list, each with its own undo. */
const activeChips = computed(() => {
  const chips: { key: string, label: string, clear: () => void }[] = []
  const filters = catalog.filters

  if (filters.category) {
    const match = categoryOptions.value.find(option => option.value === filters.category)
    chips.push({
      key: 'category',
      label: match?.label ?? filters.category,
      clear: () => update({ category: '' }),
    })
  }
  if (filters.brand) {
    chips.push({ key: 'brand', label: filters.brand, clear: () => update({ brand: '' }) })
  }
  if (filters.availability) {
    chips.push({
      key: 'availability',
      label: t(filters.availability === 'in' ? 'catalog.availabilityIn' : 'catalog.availabilityOut'),
      clear: () => update({ availability: '' }),
    })
  }
  if (filters.minPrice || filters.maxPrice) {
    chips.push({
      key: 'price',
      label: `${filters.minPrice || '0'} – ${filters.maxPrice || '∞'}`,
      clear: () => update({ minPrice: '', maxPrice: '' }),
    })
  }
  if (filters.minDiscount) {
    chips.push({
      key: 'discount',
      label: `${filters.minDiscount}%+`,
      clear: () => update({ minDiscount: '' }),
    })
  }
  if (filters.onSale) {
    chips.push({
      key: 'onSale',
      label: t('catalog.onlyOnSale'),
      clear: () => update({ onSale: false }),
    })
  }

  return chips
})

useSeoMeta({ title: () => heading.value })

function update(patch: Parameters<typeof catalog.setFilters>[0]): void {
  catalog.setFilters(patch)
}

function clearFilters(): void {
  searchDraft.value = ''
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

<style scoped>
/*
 * The category rail.
 *
 * A horizontal strip rather than a wrapping grid: it keeps its height fixed
 * however many categories a shop has, and on a phone it is the gesture people
 * already expect from every other shop they use.
 */
.mura-cat-rail {
  display: flex;
  padding-bottom: 6px;
  gap: 0.75rem;
  overflow-x: auto;
  scroll-snap-type: x proximity;
  scrollbar-width: thin;
}

.mura-cat {
  display: flex;
  min-width: 96px;
  max-width: 132px;
  flex: 0 0 auto;
  flex-direction: column;
  align-items: center;
  padding: 12px 10px;
  border: 1px solid rgba(var(--v-border-color), 0.7);
  border-radius: var(--mura-radius-md, 10px);
  background: rgb(var(--v-theme-surface));
  cursor: pointer;
  gap: 6px;
  scroll-snap-align: start;
  text-align: center;
  transition: border-color 160ms ease, transform 160ms ease, box-shadow 160ms ease;
}

.mura-cat:hover {
  border-color: rgba(var(--v-theme-primary), 0.6);
  box-shadow: 0 6px 18px -12px rgba(var(--v-theme-on-surface), 0.5);
  transform: translateY(-2px);
}

.mura-cat:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

/* The selected card is the one piece of state the rail has to communicate, so
   it gets both a border and a tint rather than relying on either alone. */
.mura-cat--active {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.08);
}

.mura-cat__image {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  overflow: hidden;
}

.mura-cat__icon {
  height: 44px;
  color: rgb(var(--v-theme-on-surface-variant));
}

.mura-cat__name {
  display: -webkit-box;
  overflow: hidden;
  font-size: 0.78rem;
  font-weight: 600;
  line-height: 1.25;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.mura-cat__count {
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.68rem;
}

.mura-filter-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.mura-filter-toggle {
  width: 100%;
}

.mura-filter-toggle :deep(.v-btn) {
  flex: 1 1 0;
  font-size: 0.72rem;
}

.mura-filter-pct {
  min-width: 36px;
  text-align: end;
}

@media (prefers-reduced-motion: reduce) {
  .mura-cat {
    transition: none;
  }

  .mura-cat:hover {
    transform: none;
  }
}
</style>
