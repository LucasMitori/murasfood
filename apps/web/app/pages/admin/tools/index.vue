<template lang="pug">
div
  mura-page-header(
    :title="t('admin.floatingTools')"
    :subtitle="t('admin.floatingToolsSubtitle')"
    :breadcrumbs="[{ title: 'admin.dashboard', to: '/admin' }, { title: 'admin.floatingTools' }]"
  )
    template(#actions)
      v-btn(
        color="primary"
        variant="flat"
        rounded="lg"
        prepend-icon="mdi-content-save"
        :loading="saving"
        :disabled="!isDirty"
        @click="save"
      ) {{ t('common.save') }}

  v-row
    //- Preview left and wide, controls right and narrow: the same arrangement
      //- as the home configurator, because it is the same kind of work.
    v-col(cols="12" lg="9")
      .mura-tools-preview
        .d-flex.align-center.ga-2.mb-2
          v-icon(icon="mdi-monitor-eye" size="18" color="primary")
          span.text-subtitle-2 {{ t('admin.preview') }}
          v-chip(size="x-small" variant="tonal") {{ t('admin.toolsChosen', { count: draft.actions.length }) }}

        //- A stage rather than a real page: the button is `position: fixed` in
          //- the storefront, so mounting it here would pin it to the browser
          //- window instead of to this frame.
        .mura-stage
          .mura-stage__chrome
            span.mura-stage__dot
            span.mura-stage__dot
            span.mura-stage__dot
          .mura-stage__body
            p.text-caption.text-medium-emphasis.mb-0 {{ t('admin.previewHint') }}

            .mura-stage__fab(:class="`is-${draft.position}`")
              ul.mura-stage__ring(v-if="draft.actions.length")
                li.mura-stage__slot(
                  v-for="(key, index) in draft.actions"
                  :key="key"
                  :style="slotStyle(index)"
                )
                  v-btn(
                    :icon="iconFor(key)"
                    :color="key === 'whatsapp' ? 'success' : 'surface-bright'"
                    :aria-label="labelFor(key)"
                    size="small"
                    elevation="4"
                  )

              v-btn(
                :icon="draft.icon"
                :color="draft.color"
                :aria-label="t('tools.open')"
                size="large"
                elevation="8"
              )

    v-col(cols="12" lg="3")
      mura-card(:title="t('admin.toolsSettings')" icon="mdi-tune")
        v-switch(
          v-model="draft.enabled"
          :label="t('admin.toolsEnabled')"
          color="primary"
          density="compact"
          hide-details
        )

        v-divider.my-3

        v-select.mb-3(
          v-model="draft.position"
          :items="positionOptions"
          :label="t('admin.toolsPosition')"
          item-title="label"
          item-value="value"
          variant="outlined"
          density="comfortable"
          hide-details
        )

        v-select.mb-3(
          v-model="draft.icon"
          :items="iconOptions"
          :label="t('admin.toolsIcon')"
          item-title="label"
          item-value="value"
          variant="outlined"
          density="comfortable"
          hide-details
        )
          template(#item="{ props: itemProps, item }")
            v-list-item(v-bind="itemProps" :prepend-icon="item.raw.value")

        v-select(
          v-model="draft.color"
          :items="colorOptions"
          :label="t('admin.toolsColor')"
          item-title="label"
          item-value="value"
          variant="outlined"
          density="comfortable"
          hide-details
        )

      mura-card.mt-4(:title="t('admin.toolsShortcuts')" icon="mdi-gesture-tap-button" :padded="false")
        //- Drag to reorder, and the order is what the arc uses. A checkbox list
          //- could say which tools appear but not in which order they fan out.
        draggable.mura-tools-list(
          v-model="draft.actions"
          item-key="self"
          handle=".mura-tools-list__grip"
          :animation="150"
        )
          template(#item="{ element }")
            li.mura-tools-list__row
              v-icon.mura-tools-list__grip(icon="mdi-drag-horizontal-variant" size="18")
              v-icon(:icon="iconFor(element)" size="18" color="primary")
              span.text-body-2.flex-grow-1 {{ labelFor(element) }}
              v-btn(
                icon="mdi-close"
                variant="text"
                size="x-small"
                :aria-label="t('common.remove')"
                @click="remove(element)"
              )

        .pa-3(v-if="!draft.actions.length")
          p.text-body-2.text-medium-emphasis.mb-0 {{ t('admin.toolsNone') }}

        template(v-if="unusedTools.length" #footer)
          .d-flex.flex-wrap.ga-1
            v-chip(
              v-for="key in unusedTools"
              :key="key"
              size="small"
              variant="tonal"
              prepend-icon="mdi-plus"
              @click="add(key)"
            ) {{ labelFor(key) }}
</template>

<script setup lang="ts">
/**
 * The floating button, as the merchant wants it.
 *
 * Which shortcuts it offers, in what order, which corner it starts in, and
 * whether it appears at all. Order is the substance rather than decoration: it
 * decides the sequence the buttons fan out in, which is why the list is
 * draggable rather than a set of checkboxes.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import draggable from 'vuedraggable'
import type { FloatingToolKey, FloatingToolsConfig } from '~/types/api'
import { useTenantStore } from '~/stores/tenant'
import { useUiStore } from '~/stores/ui'
import { useApiError } from '~/composables/useApiError'

definePageMeta({ layout: 'admin', middleware: 'merchant', permission: 'perm.admin.settings' })

const { t } = useI18n()
const tenant = useTenantStore()
const ui = useUiStore()
const { messageFor } = useApiError()

useSeoMeta({ title: () => t('admin.floatingTools'), robots: 'noindex' })

const ALL_TOOLS: FloatingToolKey[] = ['calculator', 'whatsapp', 'cart', 'lists', 'theme', 'top']

const FALLBACK: FloatingToolsConfig = {
  enabled: true,
  icon: 'mdi-apps',
  color: 'primary',
  position: 'bottom-right',
  actions: [...ALL_TOOLS],
}

/**
 * A working copy, so nothing changes until Save.
 *
 * Editing the store directly would alter the button in the layout around this
 * page as the operator experimented — which reads as the change having already
 * been published.
 */
const saved = computed<FloatingToolsConfig>(() => tenant.tenant?.settings?.floating_tools ?? FALLBACK)
const draft = ref<FloatingToolsConfig>(structuredClone(toRaw(saved.value)))

const saving = ref(false)
const isDirty = computed(() => JSON.stringify(draft.value) !== JSON.stringify(saved.value))

const unusedTools = computed(() => ALL_TOOLS.filter(key => !draft.value.actions.includes(key)))

const positionOptions = computed(() => [
  { value: 'bottom-right', label: t('admin.cornerBottomRight') },
  { value: 'bottom-left', label: t('admin.cornerBottomLeft') },
  { value: 'top-right', label: t('admin.cornerTopRight') },
  { value: 'top-left', label: t('admin.cornerTopLeft') },
])

const iconOptions = [
  { value: 'mdi-apps', label: 'Apps' },
  { value: 'mdi-plus', label: 'Plus' },
  { value: 'mdi-dots-horizontal', label: 'Dots' },
  { value: 'mdi-lightning-bolt', label: 'Bolt' },
  { value: 'mdi-storefront-outline', label: 'Store' },
]

const colorOptions = computed(() => [
  { value: 'primary', label: t('admin.colorPrimary') },
  { value: 'secondary', label: t('admin.colorSecondary') },
  { value: 'success', label: t('admin.colorSuccess') },
  { value: 'warning', label: t('admin.colorWarning') },
])

const ICONS: Record<FloatingToolKey, string> = {
  calculator: 'mdi-calculator-variant-outline',
  whatsapp: 'mdi-whatsapp',
  cart: 'mdi-cart-outline',
  lists: 'mdi-format-list-checks',
  theme: 'mdi-weather-night',
  top: 'mdi-arrow-up',
}

function iconFor(key: FloatingToolKey): string {
  return ICONS[key] ?? 'mdi-help'
}

function labelFor(key: FloatingToolKey): string {
  return t(`admin.tool.${key}`, key)
}

/**
 * Place a shortcut on the arc, the way the real button does.
 *
 * The quarter turn that sweeps *into* the screen depends on the corner, so the
 * preview has to know the corner too — otherwise choosing "top-left" would show
 * an arc fanning off the edge of the stage.
 */
const ARC_START: Record<string, number> = {
  'bottom-right': 90,
  'bottom-left': 0,
  'top-right': 180,
  'top-left': 270,
}

function slotStyle(index: number): Record<string, string> {
  const count = Math.max(draft.value.actions.length - 1, 1)
  const start = ARC_START[draft.value.position] ?? 90
  const angle = ((start + (90 / count) * index) * Math.PI) / 180

  return {
    transform: `translate(${(Math.cos(angle) * 78).toFixed(1)}px, ${(-Math.sin(angle) * 78).toFixed(1)}px)`,
  }
}

function add(key: FloatingToolKey): void {
  draft.value.actions.push(key)
}

function remove(key: FloatingToolKey): void {
  draft.value.actions = draft.value.actions.filter(item => item !== key)
}

async function save(): Promise<void> {
  saving.value = true
  try {
    await useNuxtApp().$api.patch('/tenants/admin/settings/', { floating_tools: draft.value })
    // Forced, because the store returns its cached tenant otherwise. An
    // unforced call here is a silent no-op: the save succeeds, the draft is
    // then reset from stale state, and the shortcut just removed reappears as
    // though nothing had happened.
    await tenant.fetch(true)
    draft.value = structuredClone(toRaw(saved.value))
    ui.success(t('admin.toolsSaved'))
  }
  catch (error) {
    ui.error(messageFor(error))
  }
  finally {
    saving.value = false
  }
}
</script>

<style scoped>
@media (min-width: 1280px) {
  .mura-tools-preview {
    position: sticky;
    top: 136px;
  }
}

/* A browser window standing in for a page, so the button has edges to sit in. */
.mura-stage {
  overflow: hidden;
  border: 1px solid rgba(var(--v-border-color), 0.8);
  border-radius: 16px;
  background: rgb(var(--v-theme-surface));
}

.mura-stage__chrome {
  display: flex;
  gap: 0.375rem;
  padding: 0.625rem 0.875rem;
  border-bottom: 1px solid rgba(var(--v-border-color), 0.6);
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.mura-stage__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: rgba(var(--v-theme-on-surface), 0.18);
}

.mura-stage__body {
  position: relative;
  height: min(52vh, 440px);
  padding: 1rem;
}

/* Absolute within the stage, not fixed to the window: the real button is
   `position: fixed`, which here would pin it to the browser rather than to
   the frame it is meant to be previewed in. */
.mura-stage__fab {
  position: absolute;
}

.mura-stage__fab.is-bottom-right { right: 24px; bottom: 24px; }
.mura-stage__fab.is-bottom-left { left: 24px; bottom: 24px; }
.mura-stage__fab.is-top-right { right: 24px; top: 24px; }
.mura-stage__fab.is-top-left { left: 24px; top: 24px; }

.mura-stage__ring {
  position: absolute;
  inset: 0;
  padding: 0;
  margin: 0;
  list-style: none;
}

.mura-stage__slot {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  transition: transform 240ms cubic-bezier(0.16, 1, 0.3, 1);
}

.mura-tools-list {
  padding: 0;
  margin: 0;
  list-style: none;
}

.mura-tools-list__row {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid rgba(var(--v-border-color), 0.5);
}

.mura-tools-list__row:last-child {
  border-bottom: none;
}

.mura-tools-list__grip {
  cursor: grab;
  opacity: 0.6;
}

.mura-tools-list__grip:active {
  cursor: grabbing;
}
</style>
