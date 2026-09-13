<template lang="pug">
div
  mura-page-header(
    :title="t('admin.homeConfig')"
    :subtitle="t('admin.homeConfigSubtitle')"
    :breadcrumbs="[{ title: 'admin.dashboard', to: '/admin' }, { title: 'admin.homeConfig' }]"
  )
    template(#actions)
      v-btn(
        v-if="tab === 'banners'"
        color="primary"
        variant="flat"
        prepend-icon="mdi-plus"
        @click="openCreate"
      ) {{ t('admin.newBanner') }}

  v-tabs.mb-4(v-model="tab" color="primary")
    v-tab(value="banners" prepend-icon="mdi-image-multiple-outline") {{ t('admin.tabBanners') }}
    v-tab(value="layout" prepend-icon="mdi-view-dashboard-outline") {{ t('admin.tabLayout') }}
    v-tab(value="appearance" prepend-icon="mdi-palette-outline") {{ t('admin.tabAppearance') }}

  mura-loading(v-if="pending" skeleton="card@2")

  mura-error-state(v-else-if="error" :on-retry="() => refresh()")

  v-row(v-else-if="tab === 'banners'")
    //- Preview on the left and wide, because it is the thing being edited; the
      //- controls are the instrument, not the subject.
    v-col(cols="12" lg="9")
      .mura-preview
        .d-flex.align-center.ga-2.mb-2
          v-icon(icon="mdi-monitor-eye" size="18" color="primary")
          span.text-subtitle-2 {{ t('admin.preview') }}
          v-chip(size="x-small" variant="tonal") {{ t('admin.activeCount', { count: activeBanners.length }) }}
          v-spacer
          v-btn(
            to="/"
            target="_blank"
            variant="tonal"
            size="small"
            rounded="lg"
            prepend-icon="mdi-open-in-new"
          ) {{ t('admin.openStorefront') }}

        //- The real hero, not a drawing of one. It takes its banners as a prop,
          //- so the preview cannot drift from what a visitor sees the way a
          //- hand-built mock-up would.
        .mura-preview__frame(v-if="activeBanners.length")
          mura-hero(:banners="activeBanners" :autoplay="false")

        .mura-preview__empty(v-else)
          v-icon(icon="mdi-image-off-outline" size="32" color="on-surface-variant")
          p.text-body-2.text-medium-emphasis.mb-0.mt-2 {{ t('admin.previewEmpty') }}

    //- Controls on the right, narrow and scrolling past the preview.
    v-col(cols="12" lg="3")
      mura-card(:title="t('admin.banners')" icon="mdi-image-multiple-outline" :padded="false")
        template(#actions)
          v-btn(
            color="primary"
            variant="text"
            size="small"
            prepend-icon="mdi-plus"
            @click="openCreate"
          ) {{ t('common.create') }}

        mura-empty-state(
          v-if="!banners.length"
          :title="t('admin.noBanners')"
          :description="t('admin.noBannersHint')"
          icon="mdi-image-multiple-outline"
        )

        v-list(v-else density="comfortable" bg-color="transparent")
          template(v-for="(banner, index) in banners" :key="banner.id")
            v-divider(v-if="index > 0")
            v-list-item.py-2(:active="focused === banner.id" @click="focus(banner)")
              template(#prepend)
                v-avatar(rounded="lg" size="44")
                  v-img(:src="banner.image?.variants?.thumbnail || banner.image?.url" :alt="banner.title" cover)

              v-list-item-title.text-body-2 {{ banner.title }}
              v-list-item-subtitle
                v-chip.mr-1(
                  :color="banner.is_active ? 'success' : 'secondary'"
                  size="x-small"
                  variant="tonal"
                ) {{ banner.is_active ? t('admin.active') : t('admin.inactive') }}
                span.text-caption {{ t('admin.priority') }} {{ banner.priority }}

              template(#append)
                v-btn(
                  icon="mdi-arrow-up"
                  variant="text"
                  size="x-small"
                  :disabled="banner.priority >= 100"
                  :aria-label="t('admin.promote')"
                  @click.stop="bump(banner, 10)"
                )
                v-btn(
                  icon="mdi-pencil-outline"
                  variant="text"
                  size="x-small"
                  :aria-label="t('common.edit')"
                  @click.stop="openEdit(banner)"
                )
                v-btn(
                  icon="mdi-delete-outline"
                  variant="text"
                  size="x-small"
                  color="error"
                  :aria-label="t('common.remove')"
                  @click.stop="askRemove(banner)"
                )

      p.text-caption.text-medium-emphasis.mt-3.mb-0 {{ t('admin.bannersOrderHint') }}

  //- --- Layout ------------------------------------------------------------
  v-row(v-else-if="tab === 'layout'")
    v-col(cols="12" lg="7")
      mura-card(:title="t('admin.homeSections')" :subtitle="t('admin.homeSectionsHint')" icon="mdi-view-dashboard-outline" :padded="false")
        //- Drag to reorder, because the order *is* the page. A list of
          //- checkboxes could say which bands appear but not in what sequence,
          //- and sequence is most of what a front page is.
        draggable.mura-sections(
          v-model="layoutDraft"
          item-key="key"
          handle=".mura-sections__grip"
          :animation="150"
        )
          template(#item="{ element }")
            li.mura-sections__row(:class="{ 'mura-sections__row--off': !element.enabled }")
              v-icon.mura-sections__grip(icon="mdi-drag-horizontal-variant" size="18")

              .flex-grow-1.min-width-0
                .d-flex.align-center.ga-2
                  v-icon(:icon="SECTION_ICONS[element.key]" size="16" color="primary")
                  span.text-body-2.font-weight-medium {{ t(`admin.section.${element.key}`) }}
                p.text-caption.text-medium-emphasis.mb-0.text-truncate
                  | {{ element.title || t('admin.sectionDefaultTitle') }}

              v-text-field.mura-sections__title(
                :model-value="element.title"
                :label="t('admin.sectionTitle')"
                :placeholder="t('admin.sectionDefaultTitle')"
                density="compact"
                variant="outlined"
                hide-details
                maxlength="80"
                @update:model-value="value => element.title = value"
              )

              v-text-field.mura-sections__limit(
                :model-value="element.limit"
                :label="t('admin.sectionLimit')"
                type="number"
                min="1"
                max="24"
                density="compact"
                variant="outlined"
                hide-details
                :disabled="element.key === 'categories'"
                @update:model-value="value => element.limit = clampLimit(value)"
              )

              v-switch(
                :model-value="element.enabled"
                color="primary"
                density="compact"
                hide-details
                :aria-label="t('admin.sectionEnabled')"
                @update:model-value="value => element.enabled = Boolean(value)"
              )

        template(#footer)
          v-spacer
          span.text-caption.text-medium-emphasis.mr-3(v-if="layoutDirty") {{ t('form.unsavedChanges') }}
          v-btn(variant="text" :disabled="savingLayout" @click="resetLayout") {{ t('common.cancel') }}
          v-btn(
            color="primary"
            variant="flat"
            :loading="savingLayout"
            :disabled="!layoutDirty"
            @click="saveLayout"
          ) {{ t('common.save') }}

    v-col(cols="12" lg="5")
      mura-card(:title="t('admin.preview')" icon="mdi-monitor-eye")
        //- The running order as the visitor meets it, so the effect of a drag
          //- is visible without opening the storefront in another tab.
        ol.mura-order
          li.mura-order__item.mura-order__item--fixed
            v-icon(icon="mdi-image-area" size="16")
            span.text-body-2 {{ t('admin.sectionHero') }}
            v-chip(size="x-small" variant="tonal") {{ t('admin.activeCount', { count: activeBanners.length }) }}

          li.mura-order__item(v-for="section in enabledSections" :key="section.key")
            v-icon(:icon="SECTION_ICONS[section.key]" size="16" color="primary")
            span.text-body-2 {{ section.title || t(`admin.section.${section.key}`) }}
            v-chip(v-if="section.key !== 'categories'" size="x-small" variant="tonal") {{ section.limit }}

        p.text-caption.text-medium-emphasis.mt-3.mb-0(v-if="!enabledSections.length") {{ t('admin.sectionsAllOff') }}

  //- --- Appearance --------------------------------------------------------
  v-row(v-else-if="tab === 'appearance'")
    v-col(cols="12" lg="8")
      mura-form-builder(
        v-model:values="brandingValues"
        :schema="brandingSchema"
        :loading="savingBranding"
        require-changes
        @submit="saveBranding"
      )

    v-col(cols="12" lg="4")
      mura-card(:title="t('admin.preview')" icon="mdi-palette-outline")
        //- A palette is only meaningful next to the things it colours, so the
          //- swatches sit above a mock of the pieces that actually use them.
        .d-flex.ga-2.mb-4
          .mura-swatch(v-for="entry in paletteEntries" :key="entry.key" :style="{ background: entry.value }")
            span.mura-swatch__label {{ entry.label }}

        .mura-brandbar(:style="{ background: brandingValues.primary_color }")
          span.text-body-2.font-weight-bold {{ tenant.storeName }}
          v-spacer
          span.mura-brandbar__pill(:style="{ background: brandingValues.accent_color }") {{ t('admin.sampleBadge') }}

        p.text-body-2.text-medium-emphasis.mt-3.mb-0(v-if="brandingValues.tagline") {{ brandingValues.tagline }}

  mura-dialog(v-model="dialogOpen" :title="editing ? t('admin.editBanner') : t('admin.newBanner')" :max-width="880" scrollable)
    mura-form-builder(
      ref="formRef"
      v-model:values="formValues"
      :card="false"
      :schema="schema"
      :loading="saving"
      show-cancel
      @submit="save"
      @cancel="dialogOpen = false"
    )

  mura-confirm-dialog(
    v-model="confirmingRemove"
    :title="t('common.remove')"
    :message="t('admin.removeBannerConfirm')"
    :confirm-label="t('common.remove')"
    :loading="removing"
    danger
    @confirm="remove"
  )
</template>

<script setup lang="ts">
/**
 * The storefront, as the merchant wants it.
 *
 * Three things, because they are the three ways a shop looks like itself: the
 * banners in the hero, the running order of the home page, and the palette.
 * Only the first of those used to be editable — the layout was fixed in the
 * page's own markup, and the branding endpoint had existed all along with no
 * screen behind it, so a merchant could not change their own colours at all.
 *
 * Each tab saves independently. They write to three different endpoints, and
 * one "save everything" button would have to succeed or fail as a unit across
 * three requests — a partial failure would leave the screen lying about what
 * was stored.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import draggable from 'vuedraggable'
import type { Banner, HomeSection, HomeSectionKey } from '~/types/api'
import type { FormSchema, FormValues } from '~/types/ui'
import { useTenantStore } from '~/stores/tenant'
import { useApiError } from '~/composables/useApiError'
import { useUiStore } from '~/stores/ui'

definePageMeta({ layout: 'admin', middleware: 'merchant', permission: 'perm.admin.settings' })

interface AdminBanner extends Banner {
  priority: number
  is_active: boolean
  impression_count: number
  click_count: number
  start_at: string | null
  end_at: string | null
}

const { t } = useI18n()
const ui = useUiStore()
const tenant = useTenantStore()
const { messageFor } = useApiError()

useSeoMeta({ title: () => t('admin.homeConfig'), robots: 'noindex' })

const tab = ref<'banners' | 'layout' | 'appearance'>('banners')

const SECTION_ICONS: Record<HomeSectionKey, string> = {
  categories: 'mdi-shape-outline',
  on_sale: 'mdi-sale',
  featured: 'mdi-star-outline',
  best_sellers: 'mdi-trophy-outline',
  new_arrivals: 'mdi-new-box',
}

const dialogOpen = ref(false)
const confirmingRemove = ref(false)
const saving = ref(false)
const removing = ref(false)
const editing = ref<AdminBanner | null>(null)
const pendingRemoval = ref<AdminBanner | null>(null)
const formValues = ref<FormValues>({})
const formRef = ref<{ applyApiError: (error: unknown) => void } | null>(null)

const { data, pending, error, refresh } = await useAsyncData<{ results: AdminBanner[] }>(
  'admin-banners',
  () => useNuxtApp().$api.get('/media/banners/', { query: { page_size: 50, ordering: '-priority' } }),
  { default: () => ({ results: [] }) },
)

const banners = computed(() =>
  [...(data.value?.results ?? [])].sort((a, b) => b.priority - a.priority),
)

/**
 * What the preview shows: exactly what a visitor would get.
 *
 * Inactive banners stay in the list on the right — they are still yours to edit
 * — but showing them in the preview would make it a picture of the editor's
 * intentions rather than of the site.
 */
const activeBanners = computed(() => banners.value.filter(banner => banner.is_active))

/** The banner the operator last touched, highlighted in the list. */
const focused = ref<string | null>(null)

function focus(banner: Banner): void {
  focused.value = banner.id
}

// --- Layout ------------------------------------------------------------------

const savingLayout = ref(false)

/**
 * The stored layout, or the shipped default.
 *
 * A tenant created before this setting existed has none, and the screen must
 * still offer something to drag rather than an empty list.
 */
const DEFAULT_LAYOUT: HomeSection[] = [
  { key: 'categories', enabled: true, title: '', limit: 12 },
  { key: 'on_sale', enabled: true, title: '', limit: 12 },
  { key: 'featured', enabled: true, title: '', limit: 12 },
  { key: 'best_sellers', enabled: true, title: '', limit: 12 },
  { key: 'new_arrivals', enabled: true, title: '', limit: 12 },
]

const savedLayout = computed<HomeSection[]>(
  () => tenant.tenant?.settings?.home_layout ?? DEFAULT_LAYOUT,
)

// A working copy: editing the store directly would reorder the live storefront
// as the operator experimented, which reads as the change having been published.
const layoutDraft = ref<HomeSection[]>(structuredClone(toRaw(savedLayout.value)))

const layoutDirty = computed(
  () => JSON.stringify(layoutDraft.value) !== JSON.stringify(savedLayout.value),
)

const enabledSections = computed(() => layoutDraft.value.filter(section => section.enabled))

/** The API refuses anything outside 1–24, so the input never offers it. */
function clampLimit(value: unknown): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return 12
  return Math.min(24, Math.max(1, Math.round(parsed)))
}

function resetLayout(): void {
  layoutDraft.value = structuredClone(toRaw(savedLayout.value))
}

async function saveLayout(): Promise<void> {
  savingLayout.value = true
  try {
    await useNuxtApp().$api.patch('/tenants/admin/settings/', { home_layout: layoutDraft.value })
    // Forced: the store returns its cached tenant otherwise, and the draft
    // would then be reset from stale state — the save succeeding while the
    // screen silently reverts.
    await tenant.fetch(true)
    resetLayout()
    ui.success(t('admin.layoutSaved'))
  }
  catch (error_) {
    ui.error(messageFor(error_))
  }
  finally {
    savingLayout.value = false
  }
}

// --- Appearance --------------------------------------------------------------

const savingBranding = ref(false)

const brandingValues = ref<FormValues>({
  primary_color: tenant.branding?.primary_color ?? '#8C1425',
  secondary_color: tenant.branding?.secondary_color ?? '#211E1F',
  accent_color: tenant.branding?.accent_color ?? '#B02233',
  dark_primary_color: tenant.branding?.dark_primary_color ?? '#E2495D',
  tagline: tenant.branding?.tagline ?? '',
  about: tenant.branding?.about ?? '',
  instagram_url: tenant.branding?.instagram_url ?? '',
  facebook_url: tenant.branding?.facebook_url ?? '',
  website_url: tenant.branding?.website_url ?? '',
})

const paletteEntries = computed(() => [
  { key: 'primary_color', label: t('admin.colorPrimary'), value: String(brandingValues.value.primary_color) },
  { key: 'accent_color', label: t('admin.colorAccent'), value: String(brandingValues.value.accent_color) },
  { key: 'secondary_color', label: t('admin.colorSecondary'), value: String(brandingValues.value.secondary_color) },
  { key: 'dark_primary_color', label: t('admin.colorDark'), value: String(brandingValues.value.dark_primary_color) },
])

const brandingSchema = computed<FormSchema>(() => ({
  submitLabel: 'common.save',
  sections: [
    {
      title: 'admin.palette',
      icon: 'mdi-palette-outline',
      description: 'admin.paletteHint',
      fields: [
        { name: 'primary_color', type: 'color', label: 'admin.colorPrimary', hint: 'admin.colorPrimaryHint', md: 6 },
        { name: 'accent_color', type: 'color', label: 'admin.colorAccent', hint: 'admin.colorAccentHint', md: 6 },
        { name: 'secondary_color', type: 'color', label: 'admin.colorSecondary', md: 6 },
        // Named separately because a wine deep enough for white paper is
        // unreadable on near-black, so it cannot be derived from the light one.
        { name: 'dark_primary_color', type: 'color', label: 'admin.colorDark', hint: 'admin.colorDarkHint', md: 6 },
      ],
    },
    {
      title: 'admin.identity',
      icon: 'mdi-storefront-outline',
      fields: [
        { name: 'tagline', type: 'text', label: 'admin.tagline', hint: 'admin.taglineHint', maxLength: 160 },
        { name: 'about', type: 'textarea', label: 'admin.about', rows: 4 },
      ],
    },
    {
      title: 'admin.links',
      icon: 'mdi-link-variant',
      fields: [
        { name: 'website_url', type: 'url', label: 'admin.website', md: 4 },
        { name: 'instagram_url', type: 'url', label: 'Instagram', md: 4 },
        { name: 'facebook_url', type: 'url', label: 'Facebook', md: 4 },
      ],
    },
  ],
}))

async function saveBranding(): Promise<void> {
  savingBranding.value = true
  try {
    await useNuxtApp().$api.patch('/tenants/admin/branding/', brandingValues.value)
    await tenant.fetch(true)
    ui.success(t('admin.brandingSaved'))
  }
  catch (error_) {
    ui.error(messageFor(error_))
  }
  finally {
    savingBranding.value = false
  }
}

const schema = computed<FormSchema>(() => ({
  submitLabel: 'common.save',
  sections: [
    {
      title: 'admin.bannerContent',
      icon: 'mdi-format-text',
      fields: [
        { name: 'title', type: 'text', label: 'admin.bannerTitle', required: true },
        { name: 'subtitle', type: 'text', label: 'admin.bannerSubtitle', hint: 'admin.bannerSubtitleHint' },
        { name: 'cta_label', type: 'text', label: 'admin.bannerCta', hint: 'admin.bannerCtaHint', maxLength: 40, md: 6 },
        {
          name: 'text_align',
          type: 'select',
          label: 'admin.bannerAlign',
          md: 6,
          default: 'CENTER',
          options: [
            { value: 'LEFT', label: 'admin.align.left' },
            { value: 'CENTER', label: 'admin.align.center' },
            { value: 'RIGHT', label: 'admin.align.right' },
          ],
        },
      ],
    },
    {
      title: 'admin.bannerImage',
      icon: 'mdi-image-outline',
      description: 'admin.bannerImageHint',
      fields: [
        { name: 'image_id', type: 'image', label: 'admin.bannerImage', folder: 'banners', required: true },
        {
          name: 'overlay_opacity',
          type: 'number',
          label: 'admin.bannerOverlay',
          hint: 'admin.bannerOverlayHint',
          min: 0,
          max: 90,
          default: 45,
          md: 6,
        },
      ],
    },
    {
      title: 'admin.bannerLink',
      icon: 'mdi-link-variant',
      fields: [
        {
          name: 'link_type',
          type: 'select',
          label: 'admin.bannerLinkType',
          md: 6,
          default: 'NONE',
          options: [
            { value: 'NONE', label: 'admin.linkTypes.NONE' },
            { value: 'CATEGORY', label: 'admin.linkTypes.CATEGORY' },
            { value: 'PRODUCT', label: 'admin.linkTypes.PRODUCT' },
            { value: 'PROMOTION', label: 'admin.linkTypes.PROMOTION' },
            { value: 'SEARCH', label: 'admin.linkTypes.SEARCH' },
            { value: 'EXTERNAL', label: 'admin.linkTypes.EXTERNAL' },
          ],
        },
        {
          name: 'link_target',
          type: 'text',
          label: 'admin.bannerLinkTarget',
          hint: 'admin.bannerLinkTargetHint',
          md: 6,
          visibleWhen: values => values.link_type !== 'NONE',
        },
      ],
    },
    {
      title: 'admin.bannerSchedule',
      icon: 'mdi-calendar-clock',
      description: 'admin.bannerScheduleHint',
      fields: [
        { name: 'start_at', type: 'datetime', label: 'admin.startsAt', md: 6 },
        { name: 'end_at', type: 'datetime', label: 'admin.endsAt', md: 6 },
        { name: 'priority', type: 'number', label: 'admin.priority', hint: 'admin.priorityHint', default: 0, md: 6 },
        { name: 'is_active', type: 'switch', label: 'admin.active', default: true, md: 6 },
      ],
    },
  ],
}))


function openCreate(): void {
  editing.value = null
  formValues.value = { text_align: 'CENTER', overlay_opacity: 45, link_type: 'NONE', is_active: true, priority: 0 }
  dialogOpen.value = true
}

function openEdit(banner: AdminBanner): void {
  editing.value = banner
  formValues.value = {
    title: banner.title,
    subtitle: banner.subtitle,
    cta_label: banner.cta_label,
    text_align: banner.text_align,
    overlay_opacity: banner.overlay_opacity,
    image_id: banner.image?.id ?? null,
    link_type: banner.link_type,
    link_target: banner.link_target,
    start_at: banner.start_at,
    end_at: banner.end_at,
    priority: banner.priority,
    is_active: banner.is_active,
  }
  dialogOpen.value = true
}

async function save(values: FormValues): Promise<void> {
  saving.value = true
  try {
    const api = useNuxtApp().$api
    if (editing.value) await api.patch(`/media/banners/${editing.value.id}/`, values)
    else await api.post('/media/banners/', values)

    dialogOpen.value = false
    await refresh()
    ui.success(t('admin.bannerSaved'))
  }
  catch (error_) {
    formRef.value?.applyApiError(error_)
  }
  finally {
    saving.value = false
  }
}

/** Nudge a banner up the running order without opening the editor. */
async function bump(banner: AdminBanner, by: number): Promise<void> {
  try {
    await useNuxtApp().$api.patch(`/media/banners/${banner.id}/`, {
      priority: Math.min(banner.priority + by, 100),
    })
    await refresh()
  }
  catch {
    ui.error(t('errors.generic'))
  }
}

function askRemove(banner: AdminBanner): void {
  pendingRemoval.value = banner
  confirmingRemove.value = true
}

async function remove(): Promise<void> {
  if (!pendingRemoval.value) return

  removing.value = true
  try {
    await useNuxtApp().$api.delete(`/media/banners/${pendingRemoval.value.id}/`)
    await refresh()
    ui.success(t('admin.bannerRemoved'))
  }
  catch {
    ui.error(t('errors.generic'))
  }
  finally {
    removing.value = false
    confirmingRemove.value = false
    pendingRemoval.value = null
  }
}
</script>

<style scoped>
.mura-sections {
  padding: 0;
  margin: 0;
  list-style: none;
}

.mura-sections__row {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  padding: 0.75rem;
  border-bottom: 1px solid rgba(var(--v-border-color), 0.5);
}

.mura-sections__row:last-child {
  border-bottom: none;
}

/* Still legible, still editable — just clearly not on the page right now. */
.mura-sections__row--off {
  opacity: 0.55;
}

.mura-sections__grip {
  cursor: grab;
  opacity: 0.6;
}

.mura-sections__grip:active {
  cursor: grabbing;
}

.mura-sections__title {
  flex: 0 1 190px;
}

.mura-sections__limit {
  flex: 0 0 92px;
}

.min-width-0 {
  min-width: 0;
}

.mura-order {
  padding: 0;
  margin: 0;
  list-style: none;
  counter-reset: band;
}

.mura-order__item {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  padding: 0.5rem 0.75rem;
  margin-bottom: 0.375rem;
  border: 1px solid rgba(var(--v-border-color), 0.6);
  border-radius: var(--mura-radius-sm);
  background: rgba(var(--v-theme-on-surface), 0.02);
}

/* The hero is not reorderable — it is the top of the page by definition. */
.mura-order__item--fixed {
  border-style: dashed;
}

.mura-swatch {
  position: relative;
  flex: 1;
  height: 56px;
  border: 1px solid rgba(var(--v-border-color), 0.8);
  border-radius: var(--mura-radius-sm);
}

.mura-swatch__label {
  position: absolute;
  right: 0;
  bottom: -1.35rem;
  left: 0;
  overflow: hidden;
  font-size: 0.65rem;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: rgb(var(--v-theme-on-surface));
  opacity: 0.7;
}

.mura-brandbar {
  display: flex;
  align-items: center;
  padding: 0.75rem 1rem;
  margin-top: 1.5rem;
  border-radius: var(--mura-radius-sm);
  color: #fff;
}

.mura-brandbar__pill {
  padding: 0.125rem 0.625rem;
  font-size: 0.7rem;
  border-radius: 999px;
}


.mura-banner-card__preview {
  position: relative;
  overflow: hidden;
  border-radius: 10px 10px 0 0;
}

.mura-banner-card__scrim {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.mura-banner-card__text {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 1rem 1.25rem;
}

.mura-banner-card__text.is-left { align-items: flex-start; text-align: left; }
.mura-banner-card__text.is-center { align-items: center; text-align: center; }
.mura-banner-card__text.is-right { align-items: flex-end; text-align: right; }

.mura-banner-card__state {
  position: absolute;
  top: 8px;
  right: 8px;
}

/*
 * The preview stays put while the controls scroll past it.
 *
 * `top` clears the dashboard's app bar and its search row, so the frame docks
 * just under them rather than sliding beneath.
 */
@media (min-width: 1280px) {
  .mura-preview {
    position: sticky;
    top: 136px;
  }
}

/*
 * A window onto the storefront, not the storefront itself.
 *
 * The hero is `100svh` by design — it is meant to fill a screen. Here it is
 * being looked *at*, so the frame caps the height and the hero fills the frame.
 */
.mura-preview__frame {
  overflow: hidden;
  height: min(60vh, 520px);
  border: 1px solid rgba(var(--v-border-color), 0.8);
  border-radius: 16px;
  box-shadow: 0 18px 40px -24px rgba(var(--v-theme-on-surface), 0.5);
}

.mura-preview__frame :deep(.mura-hero) {
  height: 100%;
  min-height: 0;
}

.mura-preview__empty {
  display: flex;
  height: 240px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 1px dashed rgba(var(--v-border-color), 0.9);
  border-radius: 16px;
  text-align: center;
}
</style>
