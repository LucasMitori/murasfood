<template lang="pug">
section.mura-container.mura-section(:aria-labelledby="headingId")
  .mura-section__title
    h2.text-h6(:id="headingId") {{ title }}
    v-btn(v-if="to" :to="to" variant="text" density="comfortable" append-icon="mdi-chevron-right") {{ t('common.seeAll') }}

  v-slide-group(show-arrows)
    v-slide-group-item(v-for="product in products" :key="product.id")
      .pr-3(style="width: 220px")
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
  to?: string
}>(), { to: '' })

const { t } = useI18n()
const favorites = useFavoritesStore()
const { busyProductId, addToCart, toggleFavorite } = useCartActions()

const headingId = computed(() => `rail-${props.title.toLowerCase().replace(/\W+/g, '-')}`)
</script>
