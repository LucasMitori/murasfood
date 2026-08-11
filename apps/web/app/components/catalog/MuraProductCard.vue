<template lang="pug">
v-card.mura-pcard(
  :to="productLink"
  :class="{ 'mura-pcard--sale': isOnSale, 'mura-pcard--out': !product.stock.in_stock }"
  :aria-label="product.name"
  flat
)
  .mura-pcard__media
    v-img.mura-pcard__img(
      :src="imageUrl"
      :srcset="srcSet"
      :alt="imageAlt"
      :aspect-ratio="1"
      cover
      sizes="(max-width: 600px) 45vw, 244px"
    )
      template(#placeholder)
        .d-flex.align-center.justify-center.fill-height.bg-surface-variant
          v-icon(icon="mdi-image-outline" size="32" color="on-surface-variant")

    //- Discount ribbon. The saving in money sits under the percentage because
    //- "R$ 4,50 off" lands harder than "-15%" when you are comparing shelves.
    .mura-pcard__deal(v-if="isOnSale")
      span.mura-pcard__deal-pct −{{ discountPercent }}%
      span.mura-pcard__deal-amount(v-if="savings") {{ savings }}

    v-btn.mura-pcard__fav(
      :icon="isFavorite ? 'mdi-heart' : 'mdi-heart-outline'"
      :color="isFavorite ? 'primary' : undefined"
      :aria-label="isFavorite ? t('product.unfavorite') : t('product.favorite')"
      :aria-pressed="isFavorite"
      size="small"
      variant="flat"
      @click.stop.prevent="$emit('toggle-favorite', product)"
    )

    .mura-pcard__flags
      v-chip(
        v-if="!product.stock.in_stock"
        color="secondary"
        variant="flat"
        size="small"
      ) {{ t('product.outOfStock') }}
      v-chip(
        v-else-if="product.stock.low_stock"
        color="warning"
        variant="flat"
        size="small"
        prepend-icon="mdi-fire"
      ) {{ t('product.lowStock') }}

    //- Desktop affordance only: on touch there is no hover, and the always-on
    //- button below stays the way in.
    .mura-pcard__quick(v-if="canPurchase")
      v-btn(
        color="primary"
        variant="flat"
        size="small"
        block
        rounded="lg"
        prepend-icon="mdi-cart-plus"
        :loading="loading"
        @click.stop.prevent="$emit('add-to-cart', product)"
      ) {{ t('product.addToCart') }}

  .mura-pcard__body
    p.mura-pcard__brand(v-if="product.brand_name") {{ product.brand_name }}
    h3.mura-pcard__name {{ product.name }}

    .mura-pcard__price
      .d-flex.align-baseline.ga-2.flex-wrap
        span.mura-pcard__now {{ money.format(product.price.price ?? '0') }}
        span.mura-pcard__was(v-if="isOnSale") {{ money.format(product.price.base_price ?? '0') }}
      span.mura-pcard__unit(v-if="unitLabel") {{ t('product.perUnit', { unit: unitLabel }) }}

  .mura-pcard__actions
    v-btn(
      color="primary"
      :variant="canPurchase ? 'flat' : 'tonal'"
      block
      rounded="lg"
      :disabled="!canPurchase"
      :loading="loading"
      :prepend-icon="canPurchase ? 'mdi-cart-plus' : 'mdi-bell-outline'"
      @click.stop.prevent="$emit('add-to-cart', product)"
    ) {{ canPurchase ? t('product.addToCart') : t('product.outOfStock') }}
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
import { useMoney } from '~/composables/useMoney'
import { discountPercentage, fromCents, toCents } from '~/utils/money'

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
const money = useMoney()

const productLink = computed(() => `/produtos/${props.product.slug}`)
const imageUrl = computed(() => props.product.image?.variants?.medium ?? props.product.image?.url ?? '')
const srcSet = computed(() => buildSrcSet(props.product.image?.variants))

/** Falls back to the product name so the image is never unlabelled. */
const imageAlt = computed(() => props.product.image?.alt_text || props.product.name)

const unitLabel = computed(() => props.product.unit?.code ?? '')

const canPurchase = computed(() =>
  props.product.stock.in_stock && props.product.price.price !== null,
)

const isOnSale = computed(() =>
  Boolean(props.product.price.is_discounted && props.product.price.base_price),
)

const discountPercent = computed(() =>
  discountPercentage(props.product.price.base_price, props.product.price.price),
)

/** Computed in integer cents so the saving never picks up float drift. */
const savings = computed(() => {
  const was = toCents(props.product.price.base_price)
  const now = toCents(props.product.price.price)
  if (was <= now) return ''
  return money.format(fromCents(was - now))
})
</script>

<style scoped>
.mura-pcard {
  display: flex;
  height: 100%;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(var(--v-border-color), 0.55);
  border-radius: 16px;
  background: rgb(var(--v-theme-surface));
  transition:
    transform 260ms cubic-bezier(0.16, 1, 0.3, 1),
    box-shadow 260ms ease,
    border-color 260ms ease;
}

.mura-pcard:hover {
  transform: translateY(-4px);
  border-color: rgba(var(--v-theme-primary), 0.35);
  box-shadow: 0 14px 32px -12px rgba(var(--v-theme-on-surface), 0.24);
}

.mura-pcard--out {
  /* Not hidden: an out-of-stock product still answers "do they sell this?" */
  opacity: 0.72;
}

.mura-pcard__media {
  position: relative;
  overflow: hidden;
  background: rgb(var(--v-theme-surface-variant));
}

.mura-pcard__img {
  transition: transform 480ms cubic-bezier(0.16, 1, 0.3, 1);
}

.mura-pcard:hover .mura-pcard__img {
  transform: scale(1.06);
}

.mura-pcard__fav {
  position: absolute;
  top: 8px;
  right: 8px;
  background: rgba(var(--v-theme-surface), 0.92) !important;
  backdrop-filter: blur(4px);
}

.mura-pcard__flags {
  position: absolute;
  bottom: 8px;
  left: 8px;
  display: flex;
  gap: 0.375rem;
}

/* --- The sale treatment --------------------------------------------------- */
.mura-pcard__deal {
  position: absolute;
  top: 8px;
  left: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0.3rem 0.55rem;
  border-radius: 10px;
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
  line-height: 1.1;
  box-shadow: 0 4px 14px -4px rgba(var(--v-theme-primary), 0.8);
}

.mura-pcard__deal-pct {
  font-size: 0.875rem;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.mura-pcard__deal-amount {
  font-size: 0.625rem;
  font-weight: 500;
  opacity: 0.88;
}

/*
 * A slow sheen across a discounted card. Long and low-contrast on purpose: it
 * should register at the edge of vision on a grid of thirty products, not
 * blink for attention.
 */
.mura-pcard--sale .mura-pcard__media::after {
  position: absolute;
  top: 0;
  left: -60%;
  width: 45%;
  height: 100%;
  background: linear-gradient(
    100deg,
    transparent,
    rgba(255, 255, 255, 0.28),
    transparent
  );
  content: '';
  animation: mura-sheen 5.5s ease-in-out infinite;
  pointer-events: none;
}

@keyframes mura-sheen {
  0%, 65% { transform: translateX(0); }
  100% { transform: translateX(360%); }
}

/* --- Body ----------------------------------------------------------------- */
.mura-pcard__body {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  padding: 0.875rem 0.875rem 0.5rem;
}

.mura-pcard__brand {
  margin-bottom: 0.125rem;
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.mura-pcard__name {
  display: -webkit-box;
  overflow: hidden;
  margin-bottom: 0.625rem;
  font-size: 0.9375rem;
  font-weight: 500;
  line-height: 1.35;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.mura-pcard__price {
  margin-top: auto;
}

.mura-pcard__now {
  color: rgb(var(--v-theme-on-surface));
  font-size: 1.25rem;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.mura-pcard--sale .mura-pcard__now {
  color: rgb(var(--v-theme-primary));
}

.mura-pcard__was {
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.8125rem;
  text-decoration: line-through;
}

.mura-pcard__unit {
  display: block;
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.75rem;
}

.mura-pcard__actions {
  padding: 0 0.875rem 0.875rem;
}

/* --- Hover quick-add ------------------------------------------------------ */
.mura-pcard__quick {
  position: absolute;
  right: 8px;
  bottom: 8px;
  left: 8px;
  opacity: 0;
  transform: translateY(0.5rem);
  transition: opacity 220ms ease, transform 220ms ease;
}

.mura-pcard:hover .mura-pcard__quick,
.mura-pcard:focus-within .mura-pcard__quick {
  opacity: 1;
  transform: none;
}

/* Hover styling is meaningless on touch, and the overlay would sit on top of
   the flags permanently. */
@media (hover: none) {
  .mura-pcard__quick { display: none; }
}

@media (prefers-reduced-motion: reduce) {
  .mura-pcard,
  .mura-pcard__img,
  .mura-pcard__quick {
    transition: none;
  }

  .mura-pcard:hover {
    transform: none;
  }

  .mura-pcard:hover .mura-pcard__img {
    transform: none;
  }

  .mura-pcard--sale .mura-pcard__media::after {
    animation: none;
    opacity: 0;
  }
}
</style>
