<template lang="pug">
div
  //- `order="0"` puts the drawer ahead of the app bar in Vuetify's layout
  //- stack, so the sidebar runs the full height of the window and the header
  //- starts beside it rather than spanning across the top.
  v-navigation-drawer.mura-admin-nav(
    v-model="drawer"
    :class="{ 'mura-admin-nav--rail': rail }"
    :permanent="mdAndUp"
    :rail="rail"
    :order="0"
    width="272"
    rail-width="72"
  )
    //- Who is signed in, at the top where an operator looks to confirm which
    //- account they are acting as before changing anything — and a way in to
    //- change it, because this is where someone looks for their own settings.
    v-tooltip(:text="t('admin.editProfile')" location="end" :disabled="!rail")
      template(#activator="{ props: tip }")
        nuxt-link.mura-admin-nav__identity(
          v-bind="tip"
          :to="profileLink"
          :aria-label="t('admin.editProfile')"
        )
          v-avatar.mura-admin-nav__avatar(color="primary" size="42")
            mura-image(
              v-if="auth.user?.avatar"
              :asset="auth.user.avatar"
              :alt="''"
              variant="thumbnail"
              :aspect-ratio="1"
              :rounded="false"
              cover
            )
            span.text-subtitle-2.font-weight-bold(v-else) {{ initials(auth.displayName) }}

          //- Hidden rather than unmounted, so collapsing the rail does not reflow
            //- the whole list on every toggle.
          .mura-admin-nav__who(v-if="!rail")
            p.mura-admin-nav__name {{ auth.displayName || t('nav.account') }}
            p.mura-admin-nav__email {{ auth.user?.email }}

          v-icon.mura-admin-nav__edit(v-if="!rail" icon="mdi-pencil-outline" size="16")

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
        //- Two renderings rather than one with conditional props.
          //-
          //- `VBtn` draws `icon` only when it has no default slot:
          //- `!slots.default && hasIcon ? <VIcon/> : slots.default()`. Passing
          //- both — an icon *and* a slot holding an empty string — took the
          //- slot branch, so the rail showed a 48px round button with nothing
          //- in it. There is no prop combination that fixes that; the slot has
          //- to actually be absent.
        v-tooltip(v-if="rail" :text="t('admin.viewStorefront')" location="end")
          template(#activator="{ props: tip }")
            v-btn(
              v-bind="tip"
              to="/"
              icon="mdi-storefront-outline"
              variant="tonal"
              color="primary"
              density="comfortable"
              :aria-label="t('admin.viewStorefront')"
            )

        v-btn(
          v-else
          to="/"
          block
          variant="tonal"
          color="primary"
          prepend-icon="mdi-storefront-outline"
        ) {{ t('admin.viewStorefront') }}

  v-app-bar.mura-admin-bar(flat :height="64" :extension-height="52")
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
          v-avatar.mura-admin-bar__avatar(color="primary" size="32")
            mura-image(
              v-if="auth.user?.avatar"
              :asset="auth.user.avatar"
              :alt="''"
              variant="thumbnail"
              :aspect-ratio="1"
              :rounded="false"
              cover
            )
            span.text-caption(v-else) {{ initials(auth.displayName) }}
      v-list(density="compact")
        v-list-item(:to="profileLink" prepend-icon="mdi-account-edit-outline") {{ t('admin.editProfile') }}
        v-list-item(to="/account" prepend-icon="mdi-account-outline") {{ t('nav.account') }}
        v-list-item(to="/" prepend-icon="mdi-storefront-outline") {{ t('admin.viewStorefront') }}
        v-divider
        v-list-item(prepend-icon="mdi-logout" @click="signOut") {{ t('nav.signOut') }}

    //- A second row: one field that reaches everything in the dashboard, and
      //- beside it the handful of actions an operator reaches for from any
      //- screen. Compact, because a toolbar that takes 56px of every page is
      //- paying rent it does not earn.
    template(#extension)
      v-divider.mura-admin-bar__seam(absolute)

      .mura-admin-tools
        .mura-admin-search
          v-text-field(
            id="mura-admin-search"
            ref="searchField"
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
            //- The shortcut is only worth showing where there is a keyboard to
              //- press it on, and only while the field is idle.
            template(#append-inner)
              kbd.mura-admin-kbd.d-none.d-lg-inline-flex(v-if="!query") {{ shortcutHint }}

        v-spacer

        //- Creating things is the most common reason to leave a screen, so the
          //- routes that create are gathered here instead of being scattered
          //- one page deep each.
        v-menu(v-if="quickCreateItems.length" location="bottom end")
          template(#activator="{ props: menuProps }")
            v-btn.mura-admin-tools__btn(
              v-bind="menuProps"
              :aria-label="t('admin.quickCreate')"
              prepend-icon="mdi-plus"
              append-icon="mdi-menu-down"
              variant="tonal"
              color="primary"
              size="small"
              rounded="lg"
            )
              span.d-none.d-sm-inline {{ t('admin.quickCreate') }}
          v-list(density="compact")
            v-list-subheader {{ t('admin.quickCreate') }}
            v-list-item(
              v-for="item in quickCreateItems"
              :key="item.to"
              :to="item.to"
              :prepend-icon="item.icon"
            )
              v-list-item-title {{ t(item.labelKey) }}

        //- What needs attention right now. A number here is the difference
          //- between noticing a shelf is empty today and noticing on Friday.
        v-tooltip(v-if="canSeeStock" :text="t('admin.stockHealth')" location="bottom")
          template(#activator="{ props: tip }")
            v-btn.mura-admin-tools__btn(
              v-bind="tip"
              to="/admin/inventory/alerts"
              :aria-label="alertLabel"
              variant="text"
              size="small"
              density="comfortable"
              icon
            )
              v-badge(
                :model-value="pulse.alertCount.value > 0"
                :content="pulse.alertBadge.value"
                color="warning"
                offset-x="-2"
                offset-y="-2"
              )
                v-icon(icon="mdi-alert-decagram-outline")

        v-tooltip(:text="t('admin.viewStorefront')" location="bottom")
          template(#activator="{ props: tip }")
            v-btn.mura-admin-tools__btn.d-none.d-sm-inline-flex(
              v-bind="tip"
              to="/"
              icon="mdi-storefront-outline"
              :aria-label="t('admin.viewStorefront')"
              variant="text"
              size="small"
              density="comfortable"
            )

        v-tooltip(:text="fullscreen ? t('admin.exitFullscreen') : t('admin.fullscreen')" location="bottom")
          template(#activator="{ props: tip }")
            v-btn.mura-admin-tools__btn.d-none.d-md-inline-flex(
              v-bind="tip"
              :icon="fullscreen ? 'mdi-fullscreen-exit' : 'mdi-fullscreen'"
              :aria-label="fullscreen ? t('admin.exitFullscreen') : t('admin.fullscreen')"
              variant="text"
              size="small"
              density="comfortable"
              @click="toggleFullscreen"
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

  mura-floating-tools
</template>

<script setup lang="ts">
/**
 * Merchant dashboard layout.
 *
 * Navigation entries are filtered by permission code, so a staff member never
 * sees a link to a page the API would refuse. The API re-checks regardless —
 * this only avoids offering a dead end.
 *
 * There is no app footer. The breadcrumb trail that used to live in one is
 * rendered by `MuraPageHeader` at the top of every screen, so the bar was
 * showing the same path twice while pinning 40px of every viewport to a
 * duplicate.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDisplay } from 'vuetify'
import { useAuthStore } from '~/stores/auth'
import { useTenantStore } from '~/stores/tenant'
import { useUiStore } from '~/stores/ui'
import { usePermission } from '~/composables/usePermission'
import { useAdminPulse } from '~/composables/useAdminPulse'
import { initials } from '~/utils/format'
import { StorageKeys, readStorage, writeStorage } from '~/utils/storage'

const { t, locale, locales: availableLocales, setLocale } = useI18n()
const auth = useAuthStore()
const tenant = useTenantStore()
const ui = useUiStore()
const router = useRouter()
const { mdAndUp } = useDisplay()

const drawer = ref(true)

/** Their own record in the staff editor, which is where a profile is edited. */
const profileLink = computed(() =>
  auth.user?.id ? `/admin/users/${auth.user.id}/edit` : '/account',
)

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
  { to: '/admin/reports', icon: 'mdi-chart-box-outline', labelKey: 'reports.title', permission: 'perm.admin.reports' },
  { to: '/admin/users', icon: 'mdi-shield-account-outline', labelKey: 'admin.users', permission: 'perm.admin.users' },
  { to: '/admin/storefront', icon: 'mdi-home-edit-outline', labelKey: 'admin.homeConfig', permission: 'perm.admin.settings' },
  { to: '/admin/tools', icon: 'mdi-gesture-tap-button', labelKey: 'admin.floatingTools', permission: 'perm.admin.settings' },
  { to: '/admin/emails', icon: 'mdi-email-multiple-outline', labelKey: 'admin.emails', permission: 'perm.admin.settings' },
  { to: '/admin/diagnostics', icon: 'mdi-heart-pulse', labelKey: 'admin.diagnostics', permission: 'perm.admin.diagnostics' },
]

const { can } = usePermission()
const visibleEntries = computed(() => entries.filter(entry => can(entry.permission)))

const canSeeStock = computed(() => can('perm.admin.inventory'))

/** Live counts for the badge, shared by every admin screen. */
const pulse = useAdminPulse()

const alertLabel = computed(() =>
  pulse.alertCount.value > 0
    ? t('admin.stockAlertsCount', { count: pulse.alertCount.value })
    : t('admin.stockHealth'),
)

// --- Quick create ------------------------------------------------------------
const quickCreateSources = [
  { to: '/admin/products?new=1', icon: 'mdi-package-variant-closed-plus', labelKey: 'admin.newProduct', permission: 'perm.admin.products' },
  { to: '/admin/users/new', icon: 'mdi-account-plus-outline', labelKey: 'admin.newUser', permission: 'perm.admin.users' },
  { to: '/admin/inventory/expiry', icon: 'mdi-calendar-plus', labelKey: 'admin.batchNew', permission: 'perm.admin.inventory' },
  { to: '/admin/finance?tab=entries&new=expense', icon: 'mdi-cash-minus', labelKey: 'finance.addExpense', permission: 'perm.admin.finance' },
  { to: '/admin/reports', icon: 'mdi-file-chart-outline', labelKey: 'reports.newReport', permission: 'perm.admin.reports' },
]

const quickCreateItems = computed(() =>
  quickCreateSources.filter(item => can(item.permission)),
)

// --- Fullscreen --------------------------------------------------------------
const fullscreen = ref(false)

async function toggleFullscreen(): Promise<void> {
  // Wrapped because a browser may refuse the request (an iframe without the
  // permission, a user gesture that did not count) and an unhandled rejection
  // here would surface as a page error over a cosmetic feature.
  try {
    if (document.fullscreenElement) await document.exitFullscreen()
    else await document.documentElement.requestFullscreen()
  }
  catch {
    /* ignore — the button simply does nothing */
  }
}

function syncFullscreen(): void {
  fullscreen.value = Boolean(document.fullscreenElement)
}

// --- Search ------------------------------------------------------------------
const query = ref('')
const searchField = ref<{ focus: () => void } | null>(null)

/** Mac reads ⌘K; everything else reads Ctrl K. */
const shortcutHint = ref('Ctrl K')

/**
 * Focus the search from anywhere, the way every dashboard of this shape does.
 *
 * Ignored while the caret is already in a field, so the shortcut cannot steal a
 * keystroke from someone typing a product name.
 */
function onKeydown(event: KeyboardEvent): void {
  if (event.key !== 'k' || !(event.metaKey || event.ctrlKey)) return

  const active = document.activeElement as HTMLElement | null
  const tag = active?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || active?.isContentEditable) {
    if (active?.id !== 'mura-admin-search') return
  }

  event.preventDefault()
  searchField.value?.focus()
}

onMounted(() => {
  shortcutHint.value = /mac|iphone|ipad/i.test(navigator.platform || navigator.userAgent)
    ? '⌘ K'
    : 'Ctrl K'
  window.addEventListener('keydown', onKeydown)
  document.addEventListener('fullscreenchange', syncFullscreen)
  syncFullscreen()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  document.removeEventListener('fullscreenchange', syncFullscreen)
})

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
    { to: '/admin/finance', icon: 'mdi-scale-balance', labelKey: 'finance.tabStatement', parent: 'admin.finance', permission: 'perm.admin.finance' },
    { to: '/admin/finance', icon: 'mdi-wallet-outline', labelKey: 'finance.tabBudget', parent: 'admin.finance', permission: 'perm.admin.finance' },
    { to: '/admin/finance', icon: 'mdi-chart-timeline-variant', labelKey: 'finance.tabForecast', parent: 'admin.finance', permission: 'perm.admin.finance' },
    { to: '/admin/finance', icon: 'mdi-tag-arrow-up-outline', labelKey: 'finance.tabPricing', parent: 'admin.finance', permission: 'perm.admin.finance' },
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
  color: inherit;
  text-decoration: none;
  transition: background-color 140ms ease;
}

.mura-admin-nav__identity:hover {
  background: rgba(var(--v-theme-primary), 0.08);
}

.mura-admin-nav__identity:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}

.mura-admin-nav__avatar :deep(.mura-image) {
  width: 100%;
  height: 100%;
  border-radius: inherit;
}

.mura-admin-bar__avatar :deep(.mura-image) {
  width: 100%;
  height: 100%;
  border-radius: inherit;
}

/* Only announced on hover, because the whole block is the control. */
.mura-admin-nav__edit {
  opacity: 0;
  transition: opacity 140ms ease;
}

.mura-admin-nav__identity:hover .mura-admin-nav__edit,
.mura-admin-nav__identity:focus-visible .mura-admin-nav__edit {
  opacity: 0.7;
}

/*
 * Centring the rail.
 *
 * A list item is a grid whose first track is `icon + --v-list-prepend-gap` —
 * 24px + 16px. That gap exists to separate the icon from a title, and in the
 * rail there is no title: it became 16px of dead space on the right of every
 * icon, pushing each one 8px left of the drawer's centre line. Measured before
 * the fix: drawer centre 36px, icon centre 28px.
 *
 * Zeroing the gap leaves a 24px track, and centring the grid puts it on the
 * drawer's axis regardless of how wide the rail is set.
 */
.mura-admin-nav--rail :deep(.v-list-item) {
  --v-list-prepend-gap: 0px;

  /*
   * The three tracks, stated rather than inferred.
   *
   * Vuetify sizes the middle one `auto`, and an `auto` track in a grid with a
   * definite width absorbs the leftover space — so even with the label set to
   * `display: none` the track stayed 15px wide, the tracks exactly filled the
   * box, and `justify-content: center` had no free space to work with. Pinning
   * the two empty tracks to zero is what actually leaves something to centre.
   */
  grid-template-columns: 24px 0 0;
  justify-content: center;
}

.mura-admin-nav--rail :deep(.v-list-item__prepend),
.mura-admin-nav--rail :deep(.v-list-item__append) {
  margin: 0;
}

/*
 * The title track has to go, not just shrink.
 *
 * Vuetify's own rail rule only sets `min-width: 0` on the content, which lets
 * it stay content-sized whenever there is room. With the prepend gap zeroed
 * there suddenly was room: the label claimed the leftover 15px, the grid filled
 * its container exactly, and `justify-content: center` had no free space left
 * to centre anything with — so the icons went straight back to 8px off.
 *
 * Removing it from the grid leaves one 24px track in a 39px box, which is what
 * centring needs. The label is not lost to assistive technology: every item
 * carries an `aria-label`, which is also what the tooltip shows.
 */
.mura-admin-nav--rail :deep(.v-list-item__content) {
  display: none;
}

.mura-admin-nav--rail .mura-admin-nav__identity {
  justify-content: center;
  padding: 0;
}

.mura-admin-nav--rail :deep(.v-navigation-drawer__append) > div {
  display: flex;
  justify-content: center;
  padding-inline: 0 !important;
}

/*
 * A scrollbar must not move the centre line.
 *
 * Fourteen entries overflow a 720px-tall window, and the scrollbar that appears
 * takes its width out of the content box — which shifts every icon by half of
 * it, so the rail would be centred on a tall screen and off-centre on a short
 * one.
 *
 * Reserving the gutter on both edges was the first attempt and cost 20px of a
 * 72px rail — enough that the button at the bottom no longer fitted between the
 * two gutters and sat 5px off the axis. Hiding the bar instead keeps the full
 * width and makes the centring exact.
 *
 * Hiding a scrollbar normally hides the fact that there is more to see; here
 * the fade below restores that, and the rail still scrolls on a wheel or a
 * trackpad. This applies only to the collapsed rail — the expanded drawer keeps
 * its ordinary scrollbar, because there the label tells you what you are
 * looking at and 15px of 272 costs nothing.
 */
.mura-admin-nav--rail :deep(.v-navigation-drawer__content) {
  scrollbar-width: none;
}

.mura-admin-nav--rail :deep(.v-navigation-drawer__content::-webkit-scrollbar) {
  display: none;
}

/* The affordance the hidden scrollbar took away: content running under the
   bottom edge is visibly cut off rather than simply absent. */
.mura-admin-nav--rail :deep(.v-navigation-drawer__content) {
  mask-image: linear-gradient(to bottom, #000 calc(100% - 24px), transparent 100%);
}

/* No fade when there is nothing below the fold — `scroll-state` is progressive:
   where it is unsupported the fade simply stays, which is a soft edge rather
   than a wrong one. */
@supports (container-type: scroll-state) {
  .mura-admin-nav--rail :deep(.v-navigation-drawer__content) {
    container-type: scroll-state;
  }
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

.mura-admin-nav__who {
  min-width: 0;
  flex: 1 1 auto;
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
 * The seam between the two rows.
 *
 * Without it the tools row reads as part of the header block above it and the
 * whole thing looks 116px tall; with it there are two bands, which is what they
 * are — identity and title above, tools for the page below.
 */
.mura-admin-bar__seam {
  top: 0;
  opacity: 0.6;
}

.mura-admin-tools {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 0.25rem;
  padding-inline: 0.5rem;
}

@media (min-width: 960px) {
  .mura-admin-tools {
    gap: 0.5rem;
    padding-inline: 1rem;
  }
}

/*
 * The search bar spans part of the row rather than all of it.
 *
 * Full width it reads as a page element rather than a tool, and on a wide
 * screen the caret ends up a long way from the results that drop under it.
 */
.mura-admin-search {
  min-width: 0;
  max-width: 460px;
  flex: 1 1 460px;
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

.mura-admin-kbd {
  align-items: center;
  padding: 1px 6px;
  border: 1px solid rgba(var(--v-border-color), 0.9);
  border-radius: 4px;
  background: rgba(var(--v-theme-on-surface), 0.05);
  color: rgb(var(--v-theme-on-surface-variant));
  font-family: inherit;
  font-size: 0.68rem;
  letter-spacing: 0.02em;
  line-height: 1.4;
  white-space: nowrap;
}

.mura-admin-tools__btn {
  flex: 0 0 auto;
}

/* The row's own padding is handled above. */
.mura-admin-bar :deep(.v-toolbar__extension) {
  padding-inline: 0;
}

@media (prefers-reduced-motion: reduce) {
  .mura-admin-nav__identity,
  .mura-admin-nav__edit,
  .mura-admin-search :deep(.v-field) {
    transition: none;
  }
}
</style>
