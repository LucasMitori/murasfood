<template lang="pug">
div
  mura-page-header(
    :title="t('admin.homeConfig')"
    :subtitle="t('admin.homeConfigSubtitle')"
    :breadcrumbs="[{ title: 'admin.dashboard', to: '/admin' }, { title: 'admin.homeConfig' }]"
  )
    template(#actions)
      v-btn(color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCreate") {{ t('admin.newBanner') }}

  mura-loading(v-if="pending" skeleton="card@2")

  mura-error-state(v-else-if="error" :on-retry="() => refresh()")

  mura-empty-state(
    v-else-if="!banners.length"
    :title="t('admin.noBanners')"
    :description="t('admin.noBannersHint')"
    icon="mdi-image-multiple-outline"
  )
    template(#action)
      v-btn(color="primary" variant="flat" @click="openCreate") {{ t('admin.newBanner') }}

  template(v-else)
    p.text-body-2.text-medium-emphasis.mb-4 {{ t('admin.bannersOrderHint') }}

    v-row
      v-col(v-for="banner in banners" :key="banner.id" cols="12" md="6")
        v-card.mura-banner-card(flat border)
          .mura-banner-card__preview
            v-img(
              :src="banner.image?.variants?.medium || banner.image?.url"
              :alt="banner.title"
              height="160"
              cover
            )
            .mura-banner-card__scrim(:style="{ background: `rgba(10,8,9,${(banner.overlay_opacity ?? 45) / 100})` }")
            .mura-banner-card__text(:class="`is-${(banner.text_align || 'CENTER').toLowerCase()}`")
              p.text-caption.text-white.mb-1(v-if="banner.subtitle") {{ banner.subtitle }}
              p.text-subtitle-2.text-white.font-weight-bold.mb-0 {{ banner.title }}

            v-chip.mura-banner-card__state(
              :color="banner.is_active ? 'success' : 'secondary'"
              size="x-small"
              variant="flat"
            ) {{ banner.is_active ? t('admin.active') : t('admin.inactive') }}

          v-card-text.pb-2
            .d-flex.flex-wrap.ga-2
              v-chip(size="x-small" variant="tonal" prepend-icon="mdi-sort-numeric-variant") {{ t('admin.priority') }} {{ banner.priority }}
              v-chip(size="x-small" variant="tonal" :prepend-icon="alignIcon(banner.text_align)") {{ t(`admin.align.${(banner.text_align || 'CENTER').toLowerCase()}`) }}
              v-chip(v-if="banner.cta_label" size="x-small" variant="tonal" prepend-icon="mdi-gesture-tap-button") {{ banner.cta_label }}
              v-chip(size="x-small" variant="tonal" prepend-icon="mdi-eye-outline") {{ banner.impression_count }}

          v-card-actions
            v-btn(variant="text" size="small" prepend-icon="mdi-arrow-up" :disabled="banner.priority >= 100" @click="bump(banner, 10)") {{ t('admin.promote') }}
            v-btn(variant="text" size="small" prepend-icon="mdi-pencil-outline" @click="openEdit(banner)") {{ t('common.edit') }}
            v-spacer
            v-btn(variant="text" size="small" color="error" icon="mdi-delete-outline" :aria-label="t('common.remove')" @click="askRemove(banner)")

  mura-dialog(v-model="dialogOpen" :title="editing ? t('admin.editBanner') : t('admin.newBanner')" :max-width="880" scrollable)
    mura-form-builder(
      ref="formRef"
      v-model:values="formValues"
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
 * Home page configuration: the banners behind the storefront hero.
 *
 * Shown as previews rather than a table. The whole point of these records is
 * how they look, and a row of text fields cannot tell a merchant whether their
 * white heading is readable over the photo they chose — which is exactly the
 * mistake the scrim control exists to fix.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Banner } from '~/types/api'
import type { FormSchema, FormValues } from '~/types/ui'
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

useSeoMeta({ title: () => t('admin.homeConfig'), robots: 'noindex' })

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

function alignIcon(align: string | undefined): string {
  return align === 'LEFT'
    ? 'mdi-format-align-left'
    : align === 'RIGHT' ? 'mdi-format-align-right' : 'mdi-format-align-center'
}

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
</style>
