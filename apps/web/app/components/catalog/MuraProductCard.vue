<template lang="pug">
v-card.mura-card.mura-card--interactive.h-100.d-flex.flex-column(
  :to="productLink"
  :aria-label="product.name"
  flat
)
  .position-relative
    v-img.rounded-t-lg(
      :src="imageUrl"
      :srcset="srcSet"
      :alt="imageAlt"
      :aspect-ratio="1"
      cover
      sizes="(max-width: 600px) 45vw, 240px"
    )
      template(#placeholder)
        .d-flex.align-center.justify-center.fill-height.bg-surface-variant
          v-icon(icon="mdi-image-outline" size="32" color="on-surface-variant")

    v-btn.mura-product-card__favorite(
      :icon="isFavorite ? 'mdi-heart' : 'mdi-heart-outline'"
      :color="isFavorite ? 'accent' : undefined"
      :aria-label="isFavorite ? t('product.unfavorite') : t('product.favorite')"
      :aria-pressed="isFavorite"
      size="small"
      variant="flat"
      @click.stop.prevent="$emit('toggle-favorite', product)"
    )

    v-chip.mura-product-card__flag(
      v-if="!product.stock.in_stock"
      color="secondary"
      variant="flat"
      size="small"
    ) {{ t('product.outOfStock') }}
    v-chip.mura-product-card__flag(
      v-else-if="product.stock.low_stock"
      color="warning"
      variant="flat"
      size="small"
    ) {{ t('product.lowStock') }}

  v-card-text.pb-2.flex-grow-1
    p.text-caption.text-medium-emphasis.mb-1(v-if="product.brand_name") {{ product.brand_name }}
    h3.text-body-1.font-weight-medium.mura-clamp-2.mb-2 {{ product.name }}
    mura-price(:price="product.price" :unit="unitLabel" size="medium")

  v-card-actions.pt-0
    v-btn.flex-grow-1(
      color="primary"
      variant="flat"
      :disabled="!canPurchase"
      :loading="loading"
      prepend-icon="mdi-cart-plus"
      @click.stop.prevent="$emit('add-to-cart', product)"
    ) {{ t('product.addToCart') }}
</template>

<script setup lang="ts">
/**
 * Product card used across the storefront rails and the catalog grid.
 *
 * Emits rather than mutating: the page owns cart and favourite behaviour, which
 * keeps the card usable in contexts (an order, a wishlist) with different
 * semantics.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Product } from '~/types/api'
import { buildSrcSet } from '~/utils/format'

const props = withDefaults(defineProps<{
  product: Product
  isFavorite?: boolean
  loading?: boolean
}>(), { isFavorite: false, loading: false })

defineEmits<{
  'add-to-cart': [product: Product]
  'toggle-favorite': [product: Product]
}>()

const { t } = useI18n()

const productLink = computed(() => `/produtos/${props.product.slug}`)
const imageUrl = computed(() => props.product.image?.variants?.medium ?? props.product.image?.url ?? '')
const srcSet = computed(() => buildSrcSet(props.product.image?.variants))

/** Falls back to the product name so the image is never unlabelled. */
const imageAlt = computed(() => props.product.image?.alt_text || props.product.name)

const unitLabel = computed(() => props.product.unit?.code ?? '')

const canPurchase = computed(() =>
  props.product.stock.in_stock && props.product.price.price !== null,
)
</script>

<style scoped>
.mura-product-card__favorite {
  position: absolute;
  top: 8px;
  right: 8px;
  background: rgb(var(--v-theme-surface));
}

.mura-product-card__flag {
  position: absolute;
  bottom: 8px;
  left: 8px;
}
</style>
