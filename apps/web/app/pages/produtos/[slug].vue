<template lang="pug">
.mura-container.mura-section
  v-progress-linear(v-if="pending" indeterminate color="primary")

  mura-error-state(v-else-if="error" :on-retry="() => refresh()")

  template(v-else-if="product")
    v-breadcrumbs.px-0(:items="breadcrumbs" density="compact")
      template(#divider)
        v-icon(icon="mdi-chevron-right" size="small")

    v-row
      v-col(cols="12" md="6")
        v-card.mura-card(flat)
          v-img(
            :src="activeImage?.url"
            :alt="activeImage?.alt_text || product.name"
            :aspect-ratio="1"
            cover
          )
        .d-flex.ga-2.mt-3.overflow-x-auto(v-if="product.images.length > 1")
          v-card.mura-card.flex-shrink-0(
            v-for="image in product.images"
            :key="image.id"
            :class="{ 'border-primary': image.asset.id === activeImage?.id }"
            width="72"
            flat
            @click="activeImageId = image.asset.id"
          )
            v-img(
              :src="image.asset.variants?.thumbnail || image.asset.url"
              :alt="image.asset.alt_text || product.name"
              :aspect-ratio="1"
              cover
            )

      v-col(cols="12" md="6")
        p.text-caption.text-medium-emphasis(v-if="product.brand_name") {{ product.brand_name }}
        h1.text-h5.mb-2 {{ product.name }}
        p.text-body-2.text-medium-emphasis.mb-4(v-if="product.short_description") {{ product.short_description }}

        mura-price.mb-4(:price="product.price" :unit="product.unit.code" size="large")

        v-alert.mb-4(
          v-if="product.requires_weighing"
          type="info"
          density="compact"
          variant="tonal"
        ) {{ t('product.weightedNotice') }}

        v-alert.mb-4(
          v-if="!product.stock.in_stock"
          type="warning"
          density="compact"
          variant="tonal"
          icon="mdi-package-variant-remove"
        ) {{ t('product.outOfStock') }}

        .d-flex.flex-wrap.align-center.ga-3.mb-4
          mura-quantity-input(
            v-model="quantity"
            :step-size="Number(product.unit.step)"
            :precision="product.unit.precision"
            :min="Number(product.unit.step)"
            :max="maxQuantity"
            :unit="product.unit.code"
            :disabled="!product.stock.in_stock"
          )
          v-btn(
            color="primary"
            variant="flat"
            size="large"
            prepend-icon="mdi-cart-plus"
            :disabled="!canPurchase"
            :loading="busyProductId === product.id"
            @click="addToCart(product, quantity)"
          ) {{ t('product.addToCart') }}
          v-btn(
            :icon="isFavorite ? 'mdi-heart' : 'mdi-heart-outline'"
            :color="isFavorite ? 'accent' : undefined"
            :aria-label="isFavorite ? t('product.unfavorite') : t('product.favorite')"
            variant="tonal"
            size="large"
            @click="toggleFavorite(product)"
          )

        p.text-caption.text-medium-emphasis(v-if="product.max_quantity_per_order") {{ t('product.maxQuantity', { max: product.max_quantity_per_order }) }}

        v-divider.my-4

        section(v-if="product.description" aria-labelledby="product-description")
          h2#product-description.text-subtitle-1.mb-2 {{ t('product.description') }}
          p.text-body-2 {{ product.description }}

        v-list.mt-4(density="compact" bg-color="transparent")
          v-list-item.px-0
            v-list-item-title.text-body-2 {{ t('product.sku') }}
            template(#append)
              span.text-body-2.text-medium-emphasis {{ product.sku }}
          v-list-item.px-0
            v-list-item-title.text-body-2 {{ t('product.category') }}
            template(#append)
              span.text-body-2.text-medium-emphasis {{ product.category.name }}

    mura-price-chart.mt-6(:slug="slug")

    mura-product-rail.px-0(
      v-if="related?.length"
      :title="t('product.related')"
      :products="related"
    )
</template>

<script setup lang="ts">
/**
 * Product detail page.
 *
 * Server-rendered with structured data so products are indexable (spec §56).
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Product, ProductDetail } from '~/types/api'
import { useFavoritesStore } from '~/stores/favorites'
import { useTenantStore } from '~/stores/tenant'
import { useCartActions } from '~/composables/useCartActions'

const route = useRoute()
const { t } = useI18n()
const tenant = useTenantStore()
const favorites = useFavoritesStore()
const { busyProductId, addToCart, toggleFavorite } = useCartActions()

const slug = computed(() => String(route.params.slug))

const { data: product, pending, error, refresh } = await useAsyncData<ProductDetail>(
  () => `product-${slug.value}`,
  () => useNuxtApp().$api.get<ProductDetail>(`/catalog/products/${slug.value}/`),
  { watch: [slug] },
)

const { data: related } = await useAsyncData<Product[]>(
  () => `product-related-${slug.value}`,
  () => useNuxtApp().$api.get<Product[]>(`/catalog/products/${slug.value}/related/`),
  { default: () => [], watch: [slug] },
)

const activeImageId = ref<string | null>(null)

const activeImage = computed(() => {
  const images = product.value?.images ?? []
  const selected = images.find(image => image.asset.id === activeImageId.value)
  return (selected ?? images[0])?.asset ?? product.value?.image ?? null
})

const quantity = ref(1)
const isFavorite = computed(() => (product.value ? favorites.isFavorite(product.value.id) : false))

const maxQuantity = computed(() =>
  product.value?.max_quantity_per_order ? Number(product.value.max_quantity_per_order) : undefined,
)

const canPurchase = computed(() =>
  Boolean(product.value?.stock.in_stock && product.value.price.price),
)

const breadcrumbs = computed(() => [
  { title: t('nav.home'), to: '/' },
  { title: t('nav.catalog'), to: '/produtos' },
  ...(product.value?.breadcrumb ?? []).map(node => ({
    title: node.name,
    to: `/produtos?category=${node.slug}`,
  })),
])

useSeoMeta({
  title: () => product.value?.name ?? t('catalog.title'),
  description: () => product.value?.short_description || product.value?.description || '',
  ogTitle: () => product.value?.name ?? '',
  ogImage: () => product.value?.image?.url ?? '',
  ogType: 'website',
})

// Structured data lets search engines show price and availability directly.
useHead({
  script: computed(() => (product.value
    ? [{
        type: 'application/ld+json',
        innerHTML: JSON.stringify({
          '@context': 'https://schema.org',
          '@type': 'Product',
          'name': product.value.name,
          'sku': product.value.sku,
          'description': product.value.short_description,
          'image': product.value.image?.url,
          'brand': product.value.brand_name ?? undefined,
          'offers': {
            '@type': 'Offer',
            'price': product.value.price.price,
            'priceCurrency': tenant.currency,
            'availability': product.value.stock.in_stock
              ? 'https://schema.org/InStock'
              : 'https://schema.org/OutOfStock',
          },
        }),
      }]
    : [])),
})
</script>
