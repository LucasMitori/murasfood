<template lang="pug">
div
  v-app-bar.mura-header(
    :class="{ 'mura-header--scrolled': scrolled }"
    :height="64"
    :extension-height="56"
    color="transparent"
    flat
  )
    //- Utility bar: identity on the left, tools on the right, both pinned to
    //- the same gutter the page content uses so nothing sits against the edge.
    .mura-container.d-flex.align-center.ga-1
      v-app-bar-nav-icon.d-md-none(
        :aria-label="t('common.menu')"
        @click="emit('toggle-drawer')"
      )

      nuxt-link.mura-header__brand(to="/" :aria-label="tenant.storeName")
        v-img.mr-2(
          v-if="logoUrl"
          :src="logoUrl"
          :alt="tenant.storeName"
          width="32"
          height="32"
          cover
        )
        v-icon.mr-2(v-else icon="mdi-storefront-outline" color="primary")
        span.text-h6.font-weight-bold.text-truncate {{ tenant.storeName }}

      v-spacer

      v-btn(
        :icon="ui.isDark ? 'mdi-white-balance-sunny' : 'mdi-weather-night'"
        :aria-label="ui.isDark ? t('common.themeLight') : t('common.themeDark')"
        variant="text"
        @click="ui.toggleTheme()"
      )

      v-menu
        template(#activator="{ props: menuProps }")
          v-btn(
            v-bind="menuProps"
            icon="mdi-translate"
            variant="text"
            :aria-label="t('common.language')"
          )
        v-list(density="compact")
          v-list-item(
            v-for="option in locales"
            :key="option.code"
            :active="option.code === locale"
            prepend-icon="mdi-web"
            @click="emit('switch-locale', option.code)"
          )
            v-list-item-title {{ option.name }}

      v-btn(to="/favorites" variant="text" icon :aria-label="t('nav.favorites')")
        v-badge(
          :content="hydrated ? favorites.count : 0"
          :model-value="hydrated && favorites.count > 0"
          color="primary"
        )
          v-icon(icon="mdi-heart-outline")

      v-btn(to="/cart" variant="text" icon :aria-label="t('nav.cart')")
        v-badge(
          :content="hydrated ? cart.itemCount : 0"
          :model-value="hydrated && cart.itemCount > 0"
          color="primary"
        )
          v-icon(icon="mdi-cart-outline")

      v-menu(v-if="hydrated && auth.isAuthenticated")
        template(#activator="{ props: menuProps }")
          v-btn(v-bind="menuProps" icon variant="text" :aria-label="t('nav.account')")
            v-avatar(color="primary" size="32")
              span.text-caption {{ initials(auth.displayName) }}
        v-list(density="compact")
          v-list-item(to="/account" prepend-icon="mdi-account-outline") {{ t('nav.account') }}
          v-list-item(to="/account/orders" prepend-icon="mdi-package-variant-closed") {{ t('nav.orders') }}
          v-list-item(to="/account/lists" prepend-icon="mdi-format-list-checks") {{ t('lists.title') }}
          v-list-item(
            v-if="auth.isMerchantUser"
            to="/admin"
            prepend-icon="mdi-view-dashboard-outline"
          ) {{ t('nav.dashboard') }}
          v-divider
          v-list-item(prepend-icon="mdi-logout" @click="emit('sign-out')") {{ t('nav.signOut') }}

      v-btn.ml-1(
        v-else
        to="/auth/login"
        color="primary"
        variant="flat"
        prepend-icon="mdi-login"
      ) {{ t('nav.signIn') }}

    //- Navigation bar: search on one half, destinations on the other.
    template(#extension)
      .mura-container
        v-row(no-gutters align="center")
          v-col(cols="12" md="6")
            //- An explicit id: Vuetify otherwise generates one from a counter
              //- that can land on a different number on the server than in the
              //- browser, which Vue reports as an attribute mismatch.
            v-text-field.mura-header__search(
              id="mura-header-search"
              v-model="term"
              :placeholder="t('common.searchPlaceholder')"
              :aria-label="t('common.search')"
              :aria-expanded="panelOpen"
              prepend-inner-icon="mdi-magnify"
              variant="solo-filled"
              density="compact"
              rounded="lg"
              flat
              hide-details
              clearable
              autocomplete="off"
              role="combobox"
              aria-controls="mura-search-panel"
              @update:model-value="onType"
              @focus="onType(term)"
              @keydown.enter="submit"
              @keydown.esc="close"
              @click:clear="close"
            )

          //- Labels are hidden below `lg` in CSS rather than by branching on a
            //- JS breakpoint. `useDisplay()` guesses a width on the server and
            //- measures the real one in the browser, so a template that reads it
            //- renders two different things and every button mismatches on
            //- hydration. CSS resolves per viewport with no such split.
          v-col.mura-header__nav.justify-end(cols="12" md="6")
            v-btn.mura-header__link(
              v-for="link in links"
              :key="link.to"
              :to="link.to"
              :prepend-icon="link.icon"
              :active="isActive(link.to)"
              :title="link.label"
              variant="text"
              density="comfortable"
            )
              span.mura-header__label {{ link.label }}

  //- Results panel. A sibling of the app bar rather than a child: the bar uses
  //- `backdrop-filter` when scrolled, which would make it the containing block
  //- for any fixed-position descendant and pin the panel to the bar instead of
  //- the viewport.
  v-fade-transition
    .mura-search-panel(v-if="panelOpen" id="mura-search-panel")
      .mura-container.py-4
        .d-flex.align-center.justify-space-between.mb-3
          span.text-caption.text-medium-emphasis {{ t('search.resultsFor', { term }) }}
          v-btn(
            variant="text"
            size="small"
            append-icon="mdi-arrow-right"
            @click="submit"
          ) {{ t('search.seeAll') }}

        .d-flex.flex-wrap.ga-2.mb-4
          v-chip(
            :variant="onSaleOnly ? 'flat' : 'tonal'"
            :color="onSaleOnly ? 'primary' : undefined"
            size="small"
            prepend-icon="mdi-sale"
            @click="toggleOnSale"
          ) {{ t('nav.offers') }}
          v-chip(
            v-for="category in topCategories"
            :key="category.id"
            :variant="categorySlug === category.slug ? 'flat' : 'tonal'"
            :color="categorySlug === category.slug ? 'primary' : undefined"
            size="small"
            prepend-icon="mdi-tag-outline"
            @click="toggleCategory(category.slug)"
          ) {{ category.name }}

        v-progress-linear(v-if="searching" indeterminate color="primary" rounded)

        p.text-body-2.text-medium-emphasis.py-4.mb-0(v-else-if="!results.length") {{ t('search.noResults') }}

        v-row(v-else dense)
          v-col(v-for="product in results" :key="product.id" cols="12" sm="6" md="3")
            nuxt-link.mura-search-hit(:to="`/products/${product.slug}`" @click="close")
              v-avatar(rounded="lg" size="44")
                v-img(
                  :src="product.image?.variants?.thumbnail || product.image?.url"
                  :alt="product.name"
                  cover
                )
                v-icon(v-if="!product.image" icon="mdi-image-outline" size="20")
              .mura-search-hit__text
                p.mura-search-hit__name {{ product.name }}
                p.mura-search-hit__price {{ money.format(product.price.price ?? '0') }}
</template>

<script setup lang="ts">
/**
 * Storefront header.
 *
 * Two bars: tools on top, navigation below. They are split because they answer
 * different questions — "what can I do here" versus "where do I want to go" —
 * and combining them left the search box squeezed between icon buttons.
 *
 * Both bars lay their contents out inside `.mura-container`, the same wrapper
 * every page section uses, so the logo and the sign-in button line up with the
 * content underneath rather than with the window edge.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Category, Paginated, Product } from '~/types/api'
import { useAuthStore } from '~/stores/auth'
import { useCartStore } from '~/stores/cart'
import { useFavoritesStore } from '~/stores/favorites'
import { useTenantStore } from '~/stores/tenant'
import { useUiStore } from '~/stores/ui'
import { useMoney } from '~/composables/useMoney'
import { useHydrated } from '~/composables/useHydrated'
import { initials } from '~/utils/format'

const props = withDefaults(defineProps<{
  categories?: Category[]
}>(), { categories: () => [] })

const emit = defineEmits<{
  'toggle-drawer': []
  'sign-out': []
  'switch-locale': [code: string]
}>()

const { t, locale, locales: availableLocales } = useI18n()
const route = useRoute()
const router = useRouter()

/** Labelled links only where half the bar is wide enough to hold them. */
const auth = useAuthStore()
const cart = useCartStore()
const favorites = useFavoritesStore()
const tenant = useTenantStore()
const ui = useUiStore()
const money = useMoney()

// Cart and favourite counts come from the account, which the server cannot
// read; the badges stay hidden until the browser knows the real numbers.
const hydrated = useHydrated()

const term = ref('')
const results = ref<Product[]>([])
const searching = ref(false)
const panelOpen = ref(false)
const scrolled = ref(false)
const onSaleOnly = ref(false)
const categorySlug = ref('')

const locales = computed(() =>
  (availableLocales.value as Array<{ code: string, name?: string }>).map(item => ({
    code: item.code,
    name: item.name ?? item.code,
  })),
)

const logoUrl = computed(() => (ui.isDark ? tenant.darkLogoUrl : tenant.logoUrl))

const topCategories = computed(() => props.categories.slice(0, 5))

const links = computed(() => [
  { to: '/', icon: 'mdi-home-outline', label: t('nav.home') },
  { to: '/products', icon: 'mdi-view-grid-outline', label: t('nav.catalog') },
  { to: '/products?on_sale=true', icon: 'mdi-sale', label: t('nav.offers') },
  { to: '/faq', icon: 'mdi-help-circle-outline', label: t('footer.faq') },
  { to: '/contact', icon: 'mdi-email-outline', label: t('footer.contactUs') },
])

function isActive(to: string): boolean {
  const path = to.split('?')[0] ?? '/'
  return path === '/' ? route.path === '/' : route.path.startsWith(path)
}

// --- Search ----------------------------------------------------------------
let debounce: ReturnType<typeof setTimeout> | null = null

function onType(value: string | null): void {
  const next = (value ?? '').trim()
  if (next.length < 2) {
    panelOpen.value = false
    results.value = []
    return
  }

  panelOpen.value = true
  if (debounce) clearTimeout(debounce)
  // One request per pause in typing rather than one per keystroke.
  debounce = setTimeout(() => void search(), 280)
}

async function search(): Promise<void> {
  searching.value = true
  try {
    const page = await useNuxtApp().$api.get<Paginated<Product>>('/catalog/products/', {
      query: {
        q: term.value.trim(),
        page_size: 8,
        ...(onSaleOnly.value ? { on_sale: true } : {}),
        ...(categorySlug.value ? { category: categorySlug.value } : {}),
      },
      anonymous: true,
    })
    results.value = page.results
  }
  catch {
    // A failed lookup shows the empty state; the header must never throw.
    results.value = []
  }
  finally {
    searching.value = false
  }
}

function toggleOnSale(): void {
  onSaleOnly.value = !onSaleOnly.value
  void search()
}

function toggleCategory(slug: string): void {
  categorySlug.value = categorySlug.value === slug ? '' : slug
  void search()
}

/** Carry whatever was narrowed in the panel through to the catalog page. */
function submit(): void {
  const query: Record<string, string> = {}
  if (term.value.trim()) query.q = term.value.trim()
  if (onSaleOnly.value) query.on_sale = 'true'
  if (categorySlug.value) query.category = categorySlug.value

  close()
  router.push({ path: '/products', query })
}

function close(): void {
  panelOpen.value = false
}

// --- Scroll state ----------------------------------------------------------
/**
 * Deliberately synchronous.
 *
 * Deferring to `requestAnimationFrame` looks like the careful choice, but the
 * browser already fires scroll events at roughly one per frame, and rAF does
 * not run at all when frames are not being produced — a background tab, or a
 * window that is not compositing. The header then keeps whatever state it had
 * when it stopped. This is one property read and a boolean compare; Vue only
 * re-renders when the value actually flips.
 */
function onScroll(): void {
  scrolled.value = window.scrollY > 8
}

function onDocumentClick(event: MouseEvent): void {
  const target = event.target as HTMLElement | null
  if (!target?.closest('.mura-search-panel, .mura-header__search')) close()
}

onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  document.addEventListener('click', onDocumentClick)
  onScroll()
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll)
  document.removeEventListener('click', onDocumentClick)
  if (debounce) clearTimeout(debounce)
})
</script>

<style scoped>
/*
 * At rest the header is opaque. Once the page moves it drops to 60% and blurs
 * whatever passes underneath, so the content stays readable through it instead
 * of being hidden behind a solid band.
 */
.mura-header {
  background: rgb(var(--v-theme-surface));
  border-bottom: 1px solid rgba(var(--v-border-color), 0.6);
  transition: background-color 240ms ease, box-shadow 240ms ease;
}

.mura-header--scrolled {
  background: rgba(var(--v-theme-surface), 0.6);
  backdrop-filter: blur(14px) saturate(140%);
  box-shadow: 0 6px 24px -18px rgba(var(--v-theme-on-surface), 0.6);
}

/*
 * Vuetify pads the toolbar itself, which stacked on top of the container's own
 * gutter and left the header inset further than the page content below it.
 * The container is the single source of the gutter.
 */
.mura-header :deep(.v-toolbar__content),
.mura-header :deep(.v-toolbar__extension) {
  padding-inline: 0;
}

.mura-header__brand {
  display: flex;
  min-width: 0;
  align-items: center;
  color: rgb(var(--v-theme-on-surface));
  text-decoration: none;
}

/*
 * The nav half must never grow past its column: `min-width: 0` lets it shrink
 * inside the flex row instead of pushing its content out of the left edge and
 * over the search field.
 */
.mura-header__nav {
  display: none;
  min-width: 0;
  gap: 0.125rem;
}

/* The navigation half appears once there is room for it beside the search. */
@media (min-width: 960px) {
  .mura-header__nav {
    display: flex;
  }
}

/*
 * Below `lg` five labels do not fit in half the bar, so the buttons collapse to
 * their icons rather than overflowing the column and spilling across the search
 * field.
 */
@media (max-width: 1279px) {
  .mura-header__label {
    position: absolute;
    overflow: hidden;
    width: 1px;
    height: 1px;
    clip-path: inset(50%);
    white-space: nowrap;
  }

  .mura-header__nav .mura-header__link {
    min-width: 40px;
    padding-inline: 8px;
  }

  .mura-header__nav .mura-header__link :deep(.v-btn__prepend) {
    margin-inline: 0;
  }
}

.mura-header__link {
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
}

.mura-header__link:not(.v-btn--icon) {
  padding-inline: 0.625rem !important;
}

/*
 * The field needs an edge of its own.
 *
 * A 5% tint is invisible against a white header, and Vuetify lightens a
 * `solo-filled` field further while it is focused — so clicking into the
 * search made it disappear exactly when the visitor was looking at it. A
 * border defines it at rest, and focus strengthens rather than removes it.
 */
.mura-header__search :deep(.v-field) {
  border: 1px solid rgba(var(--v-border-color), 0.9);
  background: rgba(var(--v-theme-on-surface), 0.04);
  transition: border-color 160ms ease, background-color 160ms ease;
}

.mura-header__search :deep(.v-field:hover) {
  border-color: rgba(var(--v-theme-on-surface), 0.28);
}

.mura-header__search :deep(.v-field--focused) {
  border-color: rgb(var(--v-theme-primary));
  background: rgb(var(--v-theme-surface));
  box-shadow: 0 0 0 3px rgba(var(--v-theme-primary), 0.16);
}

.mura-search-panel {
  position: fixed;
  top: 120px;
  right: 0;
  left: 0;
  z-index: 1005;
  max-height: min(70vh, 34rem);
  overflow-y: auto;
  border-bottom: 1px solid rgba(var(--v-border-color), 0.7);
  background: rgb(var(--v-theme-surface));
  box-shadow: 0 18px 40px -24px rgba(var(--v-theme-on-surface), 0.55);
}

.mura-search-hit {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem;
  border-radius: 12px;
  color: inherit;
  text-decoration: none;
  transition: background 160ms ease;
}

.mura-search-hit:hover {
  background: rgba(var(--v-theme-primary), 0.08);
}

.mura-search-hit__text {
  min-width: 0;
}

.mura-search-hit__name {
  display: -webkit-box;
  overflow: hidden;
  margin-bottom: 0;
  font-size: 0.8125rem;
  line-height: 1.3;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.mura-search-hit__price {
  margin-bottom: 0;
  color: rgb(var(--v-theme-primary));
  font-size: 0.8125rem;
  font-weight: 700;
}

@media (max-width: 959px) {
  .mura-search-panel { top: 112px; }
}

@media (prefers-reduced-motion: reduce) {
  .mura-header,
  .mura-search-hit {
    transition: none;
  }
}
</style>
