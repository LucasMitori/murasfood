<template lang="pug">
section.mura-section(:class="{ 'mura-rail--highlight': highlight }" :aria-labelledby="headingId")
  .mura-container
    .mura-rail__head
      div
        .d-flex.align-center.ga-2
          span.mura-rail__dot(v-if="highlight" aria-hidden="true")
          h2.text-h5.font-weight-bold.mb-0(:id="headingId") {{ title }}
        p.text-body-2.text-medium-emphasis.mb-0.mt-1(v-if="subtitle") {{ subtitle }}

      v-btn(
        v-if="to"
        :to="to"
        variant="text"
        density="comfortable"
        append-icon="mdi-arrow-right"
        color="primary"
      ) {{ t('common.seeAll') }}

    v-slide-group.mura-rail__group(show-arrows)
      v-slide-group-item(v-for="product in products" :key="product.id")
        .mura-rail__item
          mura-product-card(
            :product="product"
            :is-favorite="favorites.isFavorite(product.id)"
            :loading="busyProductId === product.id"
            @add-to-cart="addToCart"
            @toggle-favorite="toggleFavorite"
          )
</template>

<script setup lang="ts">
/**
 * Horizontal product rail used on the home page.
 *
 * Owns the cart/favourite behaviour so each card stays presentational.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Product } from '~/types/api'
import { useFavoritesStore } from '~/stores/favorites'
import { useCartActions } from '~/composables/useCartActions'

const props = withDefaults(defineProps<{
  title: string
  products: Product[]
  subtitle?: string
  to?: string
  /** Tints the section, marking it out from the rails around it. */
  highlight?: boolean
}>(), { subtitle: '', to: '', highlight: false })

const { t } = useI18n()
const favorites = useFavoritesStore()
const { busyProductId, addToCart, toggleFavorite } = useCartActions()

const headingId = computed(() => `rail-${props.title.toLowerCase().replace(/\W+/g, '-')}`)
</script>

<style scoped>
.mura-rail__head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.25rem;
}

.mura-rail__item {
  width: 244px;
  padding-right: 1rem;
  /* Cards lift on hover; without this the shadow is clipped by the slide group. */
  padding-block: 4px;
}

.mura-rail__dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background: rgb(var(--v-theme-primary));
  box-shadow: 0 0 0 4px rgba(var(--v-theme-primary), 0.18);
  animation: mura-rail-pulse 2.6s ease-in-out infinite;
}

/* A tint rather than a border: the offers rail should read as a different
   surface without cutting the page into boxes. */
.mura-rail--highlight {
  background:
    linear-gradient(
      180deg,
      rgba(var(--v-theme-primary), 0.06),
      rgba(var(--v-theme-primary), 0.02)
    );
}

@keyframes mura-rail-pulse {
  0%, 100% { box-shadow: 0 0 0 4px rgba(var(--v-theme-primary), 0.18); }
  50% { box-shadow: 0 0 0 7px rgba(var(--v-theme-primary), 0.06); }
}

@media (prefers-reduced-motion: reduce) {
  .mura-rail__dot { animation: none; }
}
</style>
