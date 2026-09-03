<template lang="pug">
div
  //- `order="0"` puts the drawer ahead of the app bar in Vuetify's layout
  //- stack, so the sidebar runs the full height of the window and the header
  //- starts beside it rather than spanning across the top.
  v-navigation-drawer.mura-admin-nav(
    v-model="drawer"
    :permanent="mdAndUp"
    :rail="rail"
    :order="0"
    width="272"
    rail-width="72"
  )
    //- Who is signed in, at the top where an operator looks to confirm which
    //- account they are acting as before changing anything.
    .mura-admin-nav__identity
      v-avatar(color="primary" size="42")
        span.text-subtitle-2.font-weight-bold {{ initials(auth.displayName) }}
      //- Hidden rather than unmounted, so collapsing the rail does not reflow
        //- the whole list on every toggle.
      .mura-admin-nav__who(v-if="!rail")
        p.mura-admin-nav__name {{ auth.displayName || t('nav.account') }}
        p.mura-admin-nav__email {{ auth.user?.email }}

    v-divider

    v-list.flex-grow-1.py-2(nav density="comfortable")
      //- The tooltip is the label when the rail has taken the label away, and
        //- is suppressed otherwise so it never duplicates text already on screen.
      v-tooltip(
        v-for="entry in visibleEntries"
        :key="entry.to"
        :text="t(entry.labelKey)"
        location="end"
        :disabled="!rail"
      )
        template(#activator="{ props: tip }")
          v-list-item(
            v-bind="tip"
            :to="entry.to"
            :prepend-icon="entry.icon"
            :aria-label="t(entry.labelKey)"
            color="primary"
            rounded="lg"
          )
            v-list-item-title {{ t(entry.labelKey) }}

    //- Pinned to the bottom: leaving the dashboard is a different kind of
    //- action from navigating inside it, so it does not belong in the list.
    template(#append)
      v-divider
      .pa-3
        v-tooltip(:text="t('admin.viewStorefront')" location="end" :disabled="!rail")
          template(#activator="{ props: tip }")
            v-btn(
              v-bind="tip"
              to="/"
              block
              variant="tonal"
              color="primary"
              :icon="rail ? 'mdi-storefront-outline' : undefined"
              :prepend-icon="rail ? undefined : 'mdi-storefront-outline'"
              :aria-label="t('admin.viewStorefront')"
            ) {{ rail ? '' : t('admin.viewStorefront') }}

  v-app-bar.mura-admin-bar(flat :height="64" :extension-height="56")
    v-app-bar-nav-icon.d-md-none(:aria-label="t('common.menu')" @click="drawer = !drawer")

    //- Before the title, because it acts on the column to its left.
    v-tooltip(:text="rail ? t('admin.expandMenu') : t('admin.collapseMenu')" location="bottom")
      template(#activator="{ props: tip }")
        v-btn.d-none.d-md-inline-flex(
          v-bind="tip"
          :icon="rail ? 'mdi-menu-open' : 'mdi-backburger'"
          :aria-label="rail ? t('admin.expandMenu') : t('admin.collapseMenu')"
          :aria-expanded="!rail"
          variant="text"
          @click="toggleRail"
        )

    .mura-admin-bar__title
      h1.text-subtitle-1.font-weight-bold.mb-0 {{ t('nav.admin') }}
      p.text-caption.text-medium-emphasis.mb-0 {{ tenant.storeName }}

    v-spacer

    v-menu
      template(#activator="{ props: menuProps }")
        v-btn(v-bind="menuProps" icon="mdi-translate" variant="text" :aria-label="t('common.language')")
      v-list(density="compact")
        v-list-item(
          v-for="option in availableLocales"
          :key="option.code"
          :active="option.code === locale"
          prepend-icon="mdi-web"
          @click="switchLocale(option.code)"
        )
          v-list-item-title {{ option.name }}

    v-btn(
      :icon="ui.isDark ? 'mdi-white-balance-sunny' : 'mdi-weather-night'"
      :aria-label="ui.isDark ? t('common.themeLight') : t('common.themeDark')"
      variant="text"
      @click="ui.toggleTheme()"
    )

    v-menu
      template(#activator="{ props: menuProps }")
        v-btn(v-bind="menuProps" icon variant="text" :aria-label="t('nav.account')")
          v-avatar(color="primary" size="32")
            span.text-caption {{ initials(auth.displayName) }}
      v-list(density="compact")
        v-list-item(to="/account" prepend-icon="mdi-account-outline") {{ t('nav.account') }}
        v-list-item(to="/" prepend-icon="mdi-storefront-outline") {{ t('admin.viewStorefront') }}
        v-divider
        v-list-item(prepend-icon="mdi-logout" @click="signOut") {{ t('nav.signOut') }}

    //- One field that reaches everything in the dashboard, so a screen is never
      //- more than a keystroke away regardless of how deep the menu grows.
    template(#extension)
      .mura-admin-search
        v-text-field(
          id="mura-admin-search"
          v-model="query"
          :placeholder="t('admin.searchPlaceholder')"
          :aria-label="t('common.search')"
          :aria-expanded="resultsOpen"
          prepend-inner-icon="mdi-magnify"
          variant="solo-filled"
          density="compact"
          rounded="lg"
          flat
          hide-details
          clearable
          autocomplete="off"
          role="combobox"
          aria-controls="mura-admin-results"
          @keydown.esc="query = ''"
          @keydown.enter="openFirst"
        )

  //- A sibling of the app bar rather than a child: an app bar clips its own
    //- overflow, so a panel hanging below it would be cut off at the bar's edge.
  v-menu(
    v-model="resultsOpen"
    :close-on-content-click="false"
    activator="#mura-admin-search"
    location="bottom"
    :max-height="420"
    :min-width="320"
  )
    v-list#mura-admin-results(density="compact" role="listbox")
      v-list-subheader(v-if="results.length") {{ t('admin.searchResults', { count: results.length }) }}

      v-list-item(
        v-for="hit in results"
        :key="hit.to"
        :to="hit.to"
        :prepend-icon="hit.icon"
        role="option"
        @click="query = ''"
      )
        v-list-item-title {{ hit.label }}
        v-list-item-subtitle(v-if="hit.section") {{ hit.section }}

      v-list-item(v-if="!results.length")
        v-list-item-title.text-medium-emphasis {{ t('admin.searchEmpty') }}

  v-main
    #main-content.mura-container.py-6(tabindex="-1")
      slot

  //- Where am I, and how do I get back?
  //-
  //- Derived from the route rather than declared per page, so a new screen gets
  //- its trail without remembering to add one, and a page that moves cannot
  //- leave a stale path behind.
  //-
  //- A sibling of `v-main`, not a child of it: Vuetify's layout system only
  //- reserves space for `app` components it owns directly, and nesting this one
  //- inside the main region took the whole dashboard down.
  v-footer.mura-admin-foot(app)
    .mura-container.d-flex.align-center.flex-wrap.ga-1
      v-icon.mr-1(icon="mdi-map-marker-path" size="16" color="primary")
      template(v-for="(crumb, index) in trail" :key="crumb.to")
        v-icon(v-if="index > 0" icon="mdi-chevron-right" size="14" class="text-medium-emphasis")
        nuxt-link.mura-admin-foot__crumb(v-if="index < trail.length - 1" :to="crumb.to") {{ crumb.label }}
        span.mura-admin-foot__crumb.mura-admin-foot__crumb--current(v-else) {{ crumb.label }}

      v-spacer

      span.text-caption.text-medium-emphasis.d-none.d-sm-inline {{ tenant.storeName }}

  mura-floating-tools
</template>

<script setup lang="ts">
/**
 * Merchant dashboard layout.
 *
 * Navigation entries are filtered by permission code, so a staff member never
 * sees a link to a page the API would refuse. The API re-checks regardless —
 * this only avoids offering a dead end.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDisplay } from 'vuetify'
import { useAuthStore } from '~/stores/auth'
import { useTenantStore } from '~/stores/tenant'
import { useUiStore } from '~/stores/ui'
import { usePermission } from '~/composables/usePermission'
import { initials } from '~/utils/format'
import { StorageKeys, readStorage, writeStorage } from '~/utils/storage'

const { t, locale, locales: availableLocales, setLocale } = useI18n()
const auth = useAuthStore()
const tenant = useTenantStore()
const ui = useUiStore()
const router = useRouter()
const { mdAndUp } = useDisplay()

const drawer = ref(true)

/**
 * Collapsed navigation, remembered between visits.
 *
 * An operator who works from the rail wants it every time, and one who does not
 * should never be surprised by it — so the choice is stored rather than reset
 * on each load. Read after mount, because the server cannot see storage and
 * rendering one width then swapping to the other is a hydration mismatch.
 */
const rail = ref(false)

onMounted(() => {
  rail.value = readStorage(StorageKeys.adminRail) === '1'
})

function toggleRail(): void {
  rail.value = !rail.value
  writeStorage(StorageKeys.adminRail, rail.value ? '1' : '0')
}

async function switchLocale(code: string): Promise<void> {
  await setLocale(code as never)
}

// Navigation is driven by *page* permissions, the same codes the route guard
// enforces — so a visible link never leads to a 403. Every entry here has a
// page behind it; the link test fails the build if one stops being true.
const entries = [
  { to: '/admin', icon: 'mdi-view-dashboard-outline', labelKey: 'admin.dashboard', permission: 'perm.admin.dashboard' },
  { to: '/admin/orders', icon: 'mdi-receipt-text-outline', labelKey: 'admin.orders', permission: 'perm.admin.orders' },
  { to: '/admin/products', icon: 'mdi-package-variant-closed', labelKey: 'admin.products', permission: 'perm.admin.products' },
  { to: '/admin/inventory', icon: 'mdi-warehouse', labelKey: 'admin.inventory', permission: 'perm.admin.inventory' },
  { to: '/admin/inventory/alerts', icon: 'mdi-alert-decagram-outline', labelKey: 'admin.stockHealth', permission: 'perm.admin.inventory' },
  { to: '/admin/inventory/expiry', icon: 'mdi-calendar-clock', labelKey: 'admin.expiry', permission: 'perm.admin.inventory' },
  { to: '/admin/customers', icon: 'mdi-account-group-outline', labelKey: 'admin.customers', permission: 'perm.admin.customers' },
  { to: '/admin/finance', icon: 'mdi-finance', labelKey: 'admin.finance', permission: 'perm.admin.finance' },
  { to: '/admin/users', icon: 'mdi-shield-account-outline', labelKey: 'admin.users', permission: 'perm.admin.users' },
  { to: '/admin/storefront', icon: 'mdi-home-edit-outline', labelKey: 'admin.homeConfig', permission: 'perm.admin.settings' },
  { to: '/admin/tools', icon: 'mdi-gesture-tap-button', labelKey: 'admin.floatingTools', permission: 'perm.admin.settings' },
]

const { can } = usePermission()
const visibleEntries = computed(() => entries.filter(entry => can(entry.permission)))

// --- Search ------------------------------------------------------------------
const query = ref('')

/**
 * Everything reachable in the dashboard, flattened.
 *
 * Built from the same `entries` the menu is built from, plus the actions that
 * live inside a screen rather than on it — creating a product, adjusting stock —
 * because those are what someone actually searches for and no menu lists them.
 */
const searchable = computed(() => {
  const fromMenu = visibleEntries.value.map(entry => ({
    to: entry.to,
    icon: entry.icon,
    label: t(entry.labelKey),
    section: '',
  }))

  const actions = [
    { to: '/admin/products', icon: 'mdi-plus-box-outline', labelKey: 'admin.newProduct', parent: 'admin.products', permission: 'perm.admin.products' },
    { to: '/admin/users/new', icon: 'mdi-account-plus-outline', labelKey: 'admin.newUser', parent: 'admin.users', permission: 'perm.admin.users' },
    { to: '/admin/inventory/expiry', icon: 'mdi-calendar-clock', labelKey: 'admin.batchNew', parent: 'admin.expiry', permission: 'perm.admin.inventory' },
    { to: '/admin/inventory/alerts', icon: 'mdi-package-variant-remove', labelKey: 'admin.outOfStock', parent: 'admin.stockHealth', permission: 'perm.admin.inventory' },
    { to: '/admin/storefront', icon: 'mdi-image-edit-outline', labelKey: 'admin.homeConfig', parent: 'admin.settings', permission: 'perm.admin.settings' },
  ]
    .filter(action => can(action.permission))
    .map(action => ({
      to: action.to,
      icon: action.icon,
      label: t(action.labelKey),
      section: t(action.parent),
    }))

  return [...fromMenu, ...actions]
})

/**
 * Accent-insensitive matching.
 *
 * "Usuarios" must find "Usuários": nobody reaches for the accent key while
 * searching, and a menu that hides behind one is worse than no search.
 */
function normalise(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .trim()
}

const results = computed(() => {
  const term = normalise(query.value)
  if (!term) return []

  return searchable.value.filter(entry =>
    normalise(`${entry.label} ${entry.section}`).includes(term),
  )
})

const resultsOpen = computed({
  get: () => query.value.trim().length > 0,
  set: (open: boolean) => {
    if (!open) query.value = ''
  },
})

/** Enter goes to the best match, which is what a search bar promises. */
async function openFirst(): Promise<void> {
  const first = results.value[0]
  if (!first) return

  query.value = ''
  await router.push(first.to)
}


const route = useRoute()

/**
 * The path back out of wherever we are.
 *
 * Built from the URL and matched against the navigation entries, so a page
 * inherits its trail from where it sits rather than declaring one. A segment
 * with no matching entry (an id, say) falls back to a readable form of itself.
 */
const trail = computed(() => {
  const segments = route.path.split('/').filter(Boolean)
  const crumbs: { to: string, label: string }[] = []
  let path = ''

  for (const segment of segments) {
    path += `/${segment}`
    const entry = entries.find(candidate => candidate.to === path)

    if (entry) {
      crumbs.push({ to: path, label: t(entry.labelKey) })
      continue
    }

    // An id or an unlisted leaf. A raw uuid tells the reader nothing, so it is
    // shown as the action it represents where we know one, and otherwise as
    // the segment with its separators softened.
    // Kept in step with the route segments themselves; these were still the
    // Portuguese ones after the rename, so the trail read "… › edit".
    const known: Record<string, string> = {
      new: t('common.create'),
      edit: t('common.edit'),
      alerts: t('admin.stockHealth'),
      expiry: t('admin.expiry'),
    }
    const label = known[segment]
      ?? (segment.length > 20 ? t('admin.details') : segment.replace(/[-_]/g, ' '))

    crumbs.push({ to: path, label })
  }

  return crumbs
})

async function signOut(): Promise<void> {
  await auth.logout()
  await router.push('/')
}
</script>

<style scoped>
/*
 * Matched to the app bar's 64px so the divider under this block lines up with
 * the bottom of the header beside it. Left as free padding the two edges
 * disagreed by a few pixels, which reads as a misaligned seam across the top.
 */
.mura-admin-nav__identity {
  display: flex;
  min-height: 64px;
  box-sizing: border-box;
  align-items: center;
  gap: 0.75rem;
  padding: 0 1rem;
}

/* The title was hard against the sidebar's edge; this gives it the same
   breathing room the drawer's own content has. */
.mura-admin-bar__title {
  padding-inline-start: 0.5rem;
}

@media (min-width: 960px) {
  .mura-admin-bar__title {
    padding-inline-start: 1rem;
  }
}

.mura-admin-foot {
  min-height: 40px;
  padding-block: 0;
  border-top: 1px solid rgba(var(--v-border-color), 0.6);
  background: rgb(var(--v-theme-surface));
  font-size: 0.75rem;
}

.mura-admin-foot__crumb {
  padding-inline: 0.25rem;
  color: rgb(var(--v-theme-on-surface-variant));
  text-decoration: none;
  white-space: nowrap;
}

.mura-admin-foot__crumb:hover {
  color: rgb(var(--v-theme-primary));
  text-decoration: underline;
}

.mura-admin-foot__crumb--current {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 600;
}

.mura-admin-nav__who {
  min-width: 0;
}

.mura-admin-nav__name {
  overflow: hidden;
  margin-bottom: 0;
  font-size: 0.875rem;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mura-admin-nav__email {
  overflow: hidden;
  margin-bottom: 0;
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.75rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mura-admin-bar {
  border-bottom: 1px solid rgba(var(--v-border-color), 0.6);
  background: rgb(var(--v-theme-surface));
}

/*
 * The search bar spans the content region rather than the whole extension.
 *
 * Full width it reads as a page element rather than a tool, and on a wide
 * screen the caret ends up a long way from the results that drop under it.
 */
.mura-admin-search {
  width: 100%;
  max-width: 520px;
  padding-inline: 0.5rem;
}

@media (min-width: 960px) {
  .mura-admin-search {
    padding-inline: 1rem;
  }
}

/* Same treatment as the storefront's field: a 5% tint disappears against a
   light bar, so the field carries its own edge and gains a ring on focus. */
.mura-admin-search :deep(.v-field) {
  border: 1px solid rgba(var(--v-border-color), 0.9);
  background: rgba(var(--v-theme-on-surface), 0.04);
  transition: border-color 160ms ease, background-color 160ms ease;
}

.mura-admin-search :deep(.v-field--focused) {
  border-color: rgb(var(--v-theme-primary));
  background: rgb(var(--v-theme-surface));
  box-shadow: 0 0 0 3px rgba(var(--v-theme-primary), 0.16);
}

/* The bar's own padding is handled above. */
.mura-admin-bar :deep(.v-toolbar__extension) {
  padding-inline: 0;
}
</style>
