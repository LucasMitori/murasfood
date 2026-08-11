<template lang="pug">
div
  v-app-bar(flat border :elevation="0")
    v-app-bar-nav-icon.d-md-none(:aria-label="t('common.menu')" @click="drawer = !drawer")

    //- `text-high-emphasis` is not decoration: without an explicit colour the
    //- anchor falls back to the user agent's link blue, in both themes.
    nuxt-link.d-flex.align-center.text-decoration-none.text-high-emphasis.mr-4(
      to="/"
      :aria-label="tenant.storeName"
    )
      v-img.mr-2(v-if="logoUrl" :src="logoUrl" :alt="tenant.storeName" width="32" height="32" cover)
      v-icon.mr-2(v-else icon="mdi-storefront-outline" color="primary")
      span.text-h6.font-weight-bold.text-truncate {{ tenant.storeName }}

    v-form.flex-grow-1.mx-4.d-none.d-sm-block(@submit.prevent="submitSearch")
      v-text-field(
        v-model="searchTerm"
        :placeholder="t('common.searchPlaceholder')"
        :aria-label="t('common.search')"
        prepend-inner-icon="mdi-magnify"
        density="compact"
        hide-details
        clearable
      )

    v-spacer

    v-btn(
      :icon="ui.isDark ? 'mdi-weather-sunny' : 'mdi-weather-night'"
      :aria-label="ui.isDark ? t('common.themeLight') : t('common.themeDark')"
      variant="text"
      @click="ui.toggleTheme()"
    )

    v-menu
      template(#activator="{ props: menuProps }")
        v-btn(v-bind="menuProps" icon="mdi-translate" variant="text" :aria-label="t('common.language')")
      v-list(density="compact")
        v-list-item(
          v-for="option in locales"
          :key="option.code"
          :active="option.code === locale"
          @click="switchLocale(option.code)"
        )
          v-list-item-title {{ option.name }}

    v-btn(
      to="/favoritos"
      icon
      variant="text"
      :aria-label="t('nav.favorites')"
    )
      v-badge(:content="favorites.count" :model-value="favorites.count > 0" color="accent")
        v-icon(icon="mdi-heart-outline")

    v-btn(to="/carrinho" icon variant="text" :aria-label="t('nav.cart')")
      v-badge(:content="cart.itemCount" :model-value="cart.itemCount > 0" color="accent")
        v-icon(icon="mdi-cart-outline")

    v-menu(v-if="auth.isAuthenticated")
      template(#activator="{ props: menuProps }")
        v-btn(v-bind="menuProps" icon variant="text" :aria-label="t('nav.account')")
          v-avatar(color="primary" size="32")
            span.text-caption {{ initials(auth.displayName) }}
      v-list(density="compact")
        v-list-item(to="/conta") {{ t('nav.account') }}
        v-list-item(to="/pedidos") {{ t('nav.orders') }}
        v-list-item(to="/conta/listas") {{ t('lists.title') }}
        v-list-item(v-if="auth.isMerchantUser" to="/admin") {{ t('nav.dashboard') }}
        v-divider
        v-list-item(@click="signOut") {{ t('nav.signOut') }}

    v-btn.ml-2(v-else to="/auth/login" color="primary" variant="tonal") {{ t('nav.signIn') }}

  v-navigation-drawer(v-model="drawer" temporary)
    v-list(nav density="comfortable")
      v-list-item(to="/" prepend-icon="mdi-home-outline") {{ t('nav.home') }}
      v-list-item(to="/produtos" prepend-icon="mdi-view-grid-outline") {{ t('nav.catalog') }}
      v-list-item(to="/produtos?on_sale=true" prepend-icon="mdi-sale") {{ t('nav.offers') }}
      v-list-item(to="/favoritos" prepend-icon="mdi-heart-outline") {{ t('nav.favorites') }}
      v-list-item(to="/carrinho" prepend-icon="mdi-cart-outline") {{ t('nav.cart') }}
      v-divider.my-2
      v-list-subheader {{ t('nav.categories') }}
      v-list-item(
        v-for="category in categories"
        :key="category.id"
        :to="`/produtos?category=${category.slug}`"
      ) {{ category.name }}

  v-main
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
</template>

<script setup lang="ts">
/**
 * Storefront layout: header, navigation drawer, footer.
 *
 * Every label is translated and the store's identity comes from the tenant
 * record, never from a constant in this file.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Category } from '~/types/api'
import { useAuthStore } from '~/stores/auth'
import { useCartStore } from '~/stores/cart'
import { useFavoritesStore } from '~/stores/favorites'
import { useTenantStore } from '~/stores/tenant'
import { useUiStore } from '~/stores/ui'
import { initials } from '~/utils/format'

const { t, locale, locales: availableLocales, setLocale } = useI18n()
const router = useRouter()

const auth = useAuthStore()
const cart = useCartStore()
const favorites = useFavoritesStore()
const tenant = useTenantStore()
const ui = useUiStore()

const drawer = ref(false)
const searchTerm = ref('')

const locales = computed(() =>
  (availableLocales.value as Array<{ code: string, name?: string }>).map(item => ({
    code: item.code,
    name: item.name ?? item.code,
  })),
)

const logoUrl = computed(() => (ui.isDark ? tenant.darkLogoUrl : tenant.logoUrl))

// The drawer's category list is small and cached by Nuxt's data layer.
const { data: categories } = await useAsyncData<Category[]>(
  'layout-categories',
  () => useNuxtApp().$api.get<Category[]>('/catalog/categories/', { anonymous: true }),
  { default: () => [], server: false },
)

function submitSearch(): void {
  const term = searchTerm.value?.trim()
  router.push(term ? { path: '/produtos', query: { q: term } } : { path: '/produtos' })
}

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
