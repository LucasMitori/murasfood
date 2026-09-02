<template lang="pug">
div
  mura-header(
    :categories="categories ?? []"
    @toggle-drawer="drawer = !drawer"
    @switch-locale="switchLocale"
    @sign-out="signOut"
  )

  v-navigation-drawer(v-model="drawer" temporary)
    v-list(nav density="comfortable")
      v-list-item(to="/" prepend-icon="mdi-home-outline") {{ t('nav.home') }}
      v-list-item(to="/products" prepend-icon="mdi-view-grid-outline") {{ t('nav.catalog') }}
      v-list-item(to="/products?on_sale=true" prepend-icon="mdi-sale") {{ t('nav.offers') }}
      v-list-item(to="/favorites" prepend-icon="mdi-heart-outline") {{ t('nav.favorites') }}
      v-list-item(to="/cart" prepend-icon="mdi-cart-outline") {{ t('nav.cart') }}
      v-list-item(to="/faq" prepend-icon="mdi-help-circle-outline") {{ t('footer.faq') }}
      v-list-item(to="/contact" prepend-icon="mdi-email-outline") {{ t('footer.contactUs') }}
      v-divider.my-2
      v-list-subheader {{ t('nav.categories') }}
      v-list-item(
        v-for="category in categories"
        :key="category.id"
        :to="`/products?category=${category.slug}`"
        prepend-icon="mdi-tag-outline"
      ) {{ category.name }}

  v-main.mura-main
    v-alert.rounded-0(
      v-if="!tenant.isOpenNow"
      type="info"
      variant="tonal"
      density="compact"
      icon="mdi-clock-outline"
    ) {{ t('store.closedNow') }}

    #main-content(tabindex="-1")
      slot

  mura-footer

  //- Floating tools sit above every page, so they live in the layout rather
  //- than being repeated per page.
  mura-floating-tools
</template>

<script setup lang="ts">
/**
 * Storefront layout: header, navigation drawer, footer.
 *
 * Every label is translated and the store's identity comes from the tenant
 * record, never from a constant in this file. The header itself lives in
 * `MuraHeader` — it owns enough behaviour (search, scroll state, menus) to be
 * worth keeping out of the layout.
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Category } from '~/types/api'
import { useAuthStore } from '~/stores/auth'
import { useCartStore } from '~/stores/cart'
import { useFavoritesStore } from '~/stores/favorites'
import { useTenantStore } from '~/stores/tenant'
import { useUiStore } from '~/stores/ui'

const { t, setLocale } = useI18n()
const router = useRouter()

const auth = useAuthStore()
const cart = useCartStore()
const favorites = useFavoritesStore()
const tenant = useTenantStore()
const ui = useUiStore()

const drawer = ref(false)

// Small, and cached by Nuxt's data layer; feeds both the drawer and the
// header's search filters.
const { data: categories } = await useAsyncData<Category[]>(
  'layout-categories',
  () => useNuxtApp().$api.get<Category[]>('/catalog/categories/', { anonymous: true }),
  { default: () => [], server: false },
)

async function switchLocale(code: string): Promise<void> {
  await setLocale(code as never)
}

async function signOut(): Promise<void> {
  await auth.logout()
  favorites.reset()
  await cart.fetch()
  ui.success(t('auth.signedOut'))
  await router.push('/')
}
</script>

<style scoped>
/*
 * Hold the content region to the height of the window.
 *
 * The footer is an ordinary block after `v-main`, so on a short page — an
 * order list with one order, an empty cart — `v-main` collapsed to the height
 * of its content and the footer rode up into the middle of the screen.
 *
 * `svh` rather than `vh`: on mobile `vh` is the height with the browser chrome
 * *retracted*, so a `100vh` region is taller than what is actually visible and
 * leaves a strip of footer showing under the fold. Only the height is
 * constrained — a viewport width unit here would ignore the scrollbar and push
 * the page sideways.
 *
 * 120px is the header and its search bar.
 */
.mura-main {
  min-height: calc(100svh - 120px);
}
</style>
