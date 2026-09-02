<template lang="pug">
.mura-container.mura-section
  h1.text-h5.mb-4 {{ t('nav.favorites') }}

  mura-loading(v-if="favorites.loading" skeleton="card@2")

  mura-empty-state(
    v-else-if="!favorites.items.length"
    :title="t('states.noFavorites')"
    :description="t('states.noFavoritesHint')"
    icon="mdi-heart-outline"
  )
    template(#action)
      v-btn(to="/products" color="primary" variant="flat") {{ t('cart.continueShopping') }}

  template(v-else)
    p.text-body-2.text-medium-emphasis.mb-4 {{ t('common.results', favorites.count, { count: favorites.count }) }}

    v-row
      v-col(
        v-for="row in favorites.items"
        :key="row.id"
        cols="6"
        sm="4"
        lg="3"
      )
        mura-product-card(
          :product="row.product"
          is-favorite
          :loading="busyProductId === row.product.id"
          @add-to-cart="addToCart"
          @toggle-favorite="toggleFavorite"
        )
</template>

<script setup lang="ts">
/**
 * Saved products.
 *
 * Favourites live server-side per customer, so this page requires an account —
 * there is nowhere to keep them before one exists.
 */
import { useI18n } from 'vue-i18n'
import { useFavoritesStore } from '~/stores/favorites'
import { useCartActions } from '~/composables/useCartActions'

definePageMeta({ middleware: 'auth', permission: 'perm.account' })

const { t } = useI18n()
const favorites = useFavoritesStore()
const { busyProductId, addToCart, toggleFavorite } = useCartActions()

useSeoMeta({ title: () => t('nav.favorites'), robots: 'noindex' })

await favorites.fetch()
</script>
