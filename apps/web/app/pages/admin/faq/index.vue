<template lang="pug">
div
  mura-page-header(
    :title="t('admin.faq')"
    :subtitle="t('admin.faqSubtitle')"
    :breadcrumbs="[{ title: 'admin.dashboard', to: '/admin' }, { title: 'admin.faq' }]"
  )
    template(#actions)
      v-btn(
        variant="text"
        prepend-icon="mdi-open-in-new"
        to="/faq"
        target="_blank"
      ) {{ t('admin.faqPreview') }}
      v-btn(
        color="primary"
        variant="flat"
        prepend-icon="mdi-plus"
        :disabled="!categories.length"
        @click="openCreate()"
      ) {{ t('admin.faqNew') }}

  mura-loading(v-if="pending" skeleton="card@2")

  mura-error-state(v-else-if="error" :on-retry="() => refresh()")

  template(v-else)
    //- Nothing can be asked before there is somewhere to file it, so an empty
      //- shop is pointed at the heading first rather than at a disabled button.
    mura-empty-state(
      v-if="!categories.length"
      :title="t('admin.faqNoCategories')"
      :description="t('admin.faqNoCategoriesHint')"
      icon="mdi-help-circle-outline"
    )
      template(#action)
        v-btn(color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCategory()") {{ t('admin.faqNewCategory') }}

    template(v-else)
      .d-flex.flex-wrap.align-center.ga-3.mb-4
        v-btn-toggle(
          v-model="statusFilter"
          color="primary"
          density="compact"
          variant="outlined"
          divided
          mandatory
        )
          v-btn(value="all" size="small") {{ t('admin.faqAll') }} ({{ entries.length }})
          v-btn(value="PUBLISHED" size="small") {{ t('admin.faqPublished') }} ({{ publishedCount }})
          v-btn(value="DRAFT" size="small") {{ t('admin.faqDrafts') }} ({{ draftCount }})

        v-spacer

        v-btn(variant="tonal" size="small" prepend-icon="mdi-tag-outline" @click="openCategory()") {{ t('admin.faqNewCategory') }}

      //- Grouped by heading, because that is how the help page reads and a flat
        //- list gives no sense of whether a section is thin.
      section.mb-6(v-for="group in grouped" :key="group.category.id")
        .d-flex.align-center.ga-2.mb-2
          v-icon(:icon="group.category.icon || 'mdi-help-circle-outline'" color="primary" size="20")
          h2.text-subtitle-1.font-weight-bold.mb-0 {{ group.category.name }}
          span.mura-faq__count {{ group.entries.length }}
          v-spacer
          v-btn(
            variant="text"
            size="x-small"
            icon="mdi-pencil-outline"
            :aria-label="t('common.edit')"
            @click="openCategory(group.category)"
          )
          v-btn(
            variant="text"
            size="x-small"
            icon="mdi-delete-outline"
            color="error"
            :aria-label="t('common.delete')"
            @click="confirmCategoryDelete(group.category)"
          )

        p.text-caption.text-medium-emphasis(v-if="!group.entries.length") {{ t('admin.faqEmptyGroup') }}

        //- Drag to reorder: the order here is the order on the help page, and
          //- typing position numbers into a field is a worse way to express
          //- "this one should be first".
        draggable.mura-faq__list(
          v-else
          :list="group.entries"
          item-key="id"
          handle=".mura-faq__grip"
          @end="persistOrder(group)"
        )
          template(#item="{ element }")
            article.mura-faq__item(:class="{ 'mura-faq__item--draft': element.status === 'DRAFT' }")
              v-icon.mura-faq__grip(icon="mdi-drag-vertical" size="18" color="on-surface-variant")

              .flex-grow-1.min-width-0
                .d-flex.align-center.ga-2.flex-wrap
                  h3.mura-faq__question {{ element.question }}
                  v-chip(
                    :color="element.status === 'PUBLISHED' ? 'success' : 'secondary'"
                    size="x-small"
                    variant="tonal"
                  ) {{ element.status === 'PUBLISHED' ? t('admin.faqPublished') : t('admin.faqDraft') }}
                p.mura-faq__answer.mb-0 {{ element.answer }}

              .mura-faq__actions
                v-tooltip(:text="element.status === 'PUBLISHED' ? t('admin.faqUnpublish') : t('admin.faqPublish')" location="top")
                  template(#activator="{ props: tip }")
                    v-btn(
                      v-bind="tip"
                      :icon="element.status === 'PUBLISHED' ? 'mdi-eye-off-outline' : 'mdi-publish'"
                      :color="element.status === 'PUBLISHED' ? undefined : 'success'"
                      variant="text"
                      size="small"
                      density="comfortable"
                      :loading="busyId === element.id"
                      @click="togglePublish(element)"
                    )
                v-btn(
                  icon="mdi-pencil-outline"
                  variant="text"
                  size="small"
                  density="comfortable"
                  :aria-label="t('common.edit')"
                  @click="openCreate(element)"
                )
                v-btn(
                  icon="mdi-delete-outline"
                  variant="text"
                  size="small"
                  density="comfortable"
                  color="error"
                  :aria-label="t('common.delete')"
                  @click="confirmDelete(element)"
                )

  //- --- The question editor --------------------------------------------------
  mura-dialog(v-model="formOpen" :title="editing ? t('common.edit') : t('admin.faqNew')" max-width="680")
    v-select.mb-4(
      v-model="draft.category"
      :items="categoryOptions"
      :label="t('admin.faqCategory')"
      item-title="label"
      item-value="value"
      variant="outlined"
      density="comfortable"
      hide-details
    )

    v-text-field.mb-4(
      v-model="draft.question"
      :label="t('admin.faqQuestion')"
      :error-messages="errors.question"
      variant="outlined"
      density="comfortable"
      counter="255"
      maxlength="255"
    )

    v-textarea(
      v-model="draft.answer"
      :label="t('admin.faqAnswer')"
      :hint="t('admin.faqAnswerHint')"
      :error-messages="errors.answer"
      variant="outlined"
      rows="6"
      auto-grow
      persistent-hint
    )

    template(#actions)
      v-spacer
      v-btn(variant="text" @click="formOpen = false") {{ t('common.cancel') }}
      v-btn(
        v-if="!editing"
        variant="tonal"
        :loading="saving"
        @click="save(false)"
      ) {{ t('admin.faqSaveDraft') }}
      v-btn(
        color="primary"
        variant="flat"
        :loading="saving"
        @click="save(true)"
      ) {{ editing ? t('common.save') : t('admin.faqSaveAndPublish') }}

  //- --- The heading editor ---------------------------------------------------
  mura-dialog(v-model="categoryOpen" :title="t('admin.faqNewCategory')" max-width="480")
    v-text-field.mb-4(
      v-model="categoryDraft.name"
      :label="t('common.name')"
      variant="outlined"
      density="comfortable"
      hide-details
    )
    v-text-field(
      v-model="categoryDraft.icon"
      :label="t('admin.faqIcon')"
      :hint="t('admin.faqIconHint')"
      variant="outlined"
      density="comfortable"
      persistent-hint
      :prepend-inner-icon="categoryDraft.icon || 'mdi-help-circle-outline'"
    )

    template(#actions)
      v-spacer
      v-btn(variant="text" @click="categoryOpen = false") {{ t('common.cancel') }}
      v-btn(color="primary" variant="flat" :loading="savingCategory" @click="saveCategory") {{ t('common.save') }}

  mura-confirm-dialog(
    v-model="confirmOpen"
    :message="confirmMessage"
    @confirm="runDelete"
    @cancel="pendingDelete = null"
  )
</template>

<script setup lang="ts">
/**
 * The help page, editable.
 *
 * Every answer used to live in the locale files — which meant a merchant could
 * not correct their own delivery window without a deploy, and every shop on the
 * platform answered identically regardless of what they actually sell.
 *
 * Draft and published are real states rather than a visibility toggle. The
 * useful thing is writing an answer over several sittings without it being live
 * in between; a shop hiding a published answer is a different action and keeps
 * its copy.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import draggable from 'vuedraggable'
import { useApiError } from '~/composables/useApiError'
import { useUiStore } from '~/stores/ui'

definePageMeta({ layout: 'admin', middleware: 'merchant', permission: 'perm.admin.settings' })

interface FaqCategory {
  id: string
  name: string
  slug: string
  icon: string
  position: number
  is_active: boolean
  entry_count: number
}

interface FaqEntry {
  id: string
  category: string
  category_name: string
  question: string
  answer: string
  status: 'DRAFT' | 'PUBLISHED'
  position: number
}

const { t } = useI18n()
const ui = useUiStore()
const { messageFor, notify } = useApiError()

useSeoMeta({ title: () => t('admin.faq') })

const statusFilter = ref<'all' | 'DRAFT' | 'PUBLISHED'>('all')
const busyId = ref<string | null>(null)

const { data: categoryData, pending, error, refresh: refreshCategories } = await useAsyncData<FaqCategory[]>(
  'admin-faq-categories',
  () => useNuxtApp().$api.get<FaqCategory[]>('/tenants/admin/faq-categories/'),
  { default: () => [] },
)

const { data: entryData, refresh: refreshEntries } = await useAsyncData<{ results: FaqEntry[] }>(
  'admin-faq-entries',
  () => useNuxtApp().$api.get<{ results: FaqEntry[] }>('/tenants/admin/faq/', {
    query: { page_size: 200 },
  }),
  { default: () => ({ results: [] }) },
)

const categories = computed(() => categoryData.value ?? [])
const entries = computed(() => entryData.value?.results ?? [])

const publishedCount = computed(() => entries.value.filter(e => e.status === 'PUBLISHED').length)
const draftCount = computed(() => entries.value.filter(e => e.status === 'DRAFT').length)

const categoryOptions = computed(() =>
  categories.value.map(category => ({ value: category.id, label: category.name })),
)

/**
 * Entries under their heading, filtered.
 *
 * The array handed to `draggable` has to be a real, mutable array — it reorders
 * in place — so this deliberately produces new arrays rather than a computed
 * view the library would fight with.
 */
const grouped = computed(() =>
  categories.value.map(category => ({
    category,
    entries: entries.value.filter(entry =>
      entry.category === category.id
      && (statusFilter.value === 'all' || entry.status === statusFilter.value),
    ),
  })),
)

// --- The question editor -----------------------------------------------------
const formOpen = ref(false)
const saving = ref(false)
const editing = ref<string | null>(null)
const errors = ref<Record<string, string[]>>({})
const draft = ref({ category: '', question: '', answer: '' })

function openCreate(entry?: FaqEntry): void {
  errors.value = {}
  editing.value = entry?.id ?? null
  draft.value = entry
    ? { category: entry.category, question: entry.question, answer: entry.answer }
    : { category: categories.value[0]?.id ?? '', question: '', answer: '' }
  formOpen.value = true
}

async function save(publish: boolean): Promise<void> {
  errors.value = {}

  if (!draft.value.question.trim()) {
    errors.value = { question: [t('validation.required')] }
    return
  }
  if (!draft.value.answer.trim()) {
    errors.value = { answer: [t('validation.required')] }
    return
  }

  saving.value = true
  try {
    const saved = editing.value
      ? await useNuxtApp().$api.patch<FaqEntry>(`/tenants/admin/faq/${editing.value}/`, draft.value)
      : await useNuxtApp().$api.post<FaqEntry>('/tenants/admin/faq/', draft.value)

    // Publishing is its own endpoint, so a new-and-published question is two
    // calls. Worth it: it keeps `published_at` in step with the state, which a
    // PATCH of `status` alone cannot guarantee.
    if (publish && saved.status !== 'PUBLISHED') {
      await useNuxtApp().$api.post(`/tenants/admin/faq/${saved.id}/publish/`)
    }

    formOpen.value = false
    ui.success(t('form.saved'))
    await reload()
  }
  catch (err) {
    notify(err)
  }
  finally {
    saving.value = false
  }
}

async function togglePublish(entry: FaqEntry): Promise<void> {
  busyId.value = entry.id
  try {
    const action = entry.status === 'PUBLISHED' ? 'unpublish' : 'publish'
    await useNuxtApp().$api.post(`/tenants/admin/faq/${entry.id}/${action}/`)
    await reload()
  }
  catch (err) {
    ui.error(messageFor(err))
  }
  finally {
    busyId.value = null
  }
}

/** Persist a drag, sending the whole group's order in one write. */
async function persistOrder(group: { entries: FaqEntry[] }): Promise<void> {
  try {
    await useNuxtApp().$api.post('/tenants/admin/faq/reorder/', {
      order: group.entries.map(entry => entry.id),
    })
  }
  catch (err) {
    ui.error(messageFor(err))
    await reload()
  }
}

// --- Headings ----------------------------------------------------------------
const categoryOpen = ref(false)
const savingCategory = ref(false)
const editingCategory = ref<string | null>(null)
const categoryDraft = ref({ name: '', icon: 'mdi-help-circle-outline' })

function openCategory(category?: FaqCategory): void {
  editingCategory.value = category?.id ?? null
  categoryDraft.value = category
    ? { name: category.name, icon: category.icon }
    : { name: '', icon: 'mdi-help-circle-outline' }
  categoryOpen.value = true
}

async function saveCategory(): Promise<void> {
  if (!categoryDraft.value.name.trim()) return

  savingCategory.value = true
  try {
    if (editingCategory.value) {
      await useNuxtApp().$api.patch(
        `/tenants/admin/faq-categories/${editingCategory.value}/`,
        categoryDraft.value,
      )
    }
    else {
      await useNuxtApp().$api.post('/tenants/admin/faq-categories/', categoryDraft.value)
    }
    categoryOpen.value = false
    ui.success(t('form.saved'))
    await reload()
  }
  catch (err) {
    notify(err)
  }
  finally {
    savingCategory.value = false
  }
}

// --- Deleting ----------------------------------------------------------------
const confirmOpen = ref(false)
const pendingDelete = ref<{ kind: 'entry' | 'category', id: string, label: string } | null>(null)

const confirmMessage = computed(() => {
  const pending = pendingDelete.value
  if (!pending) return ''
  return pending.kind === 'category'
    ? t('admin.faqDeleteCategoryConfirm', { name: pending.label })
    : t('admin.faqDeleteConfirm', { name: pending.label })
})

function confirmDelete(entry: FaqEntry): void {
  pendingDelete.value = { kind: 'entry', id: entry.id, label: entry.question }
  confirmOpen.value = true
}

function confirmCategoryDelete(category: FaqCategory): void {
  pendingDelete.value = { kind: 'category', id: category.id, label: category.name }
  confirmOpen.value = true
}

async function runDelete(): Promise<void> {
  const pending = pendingDelete.value
  confirmOpen.value = false
  pendingDelete.value = null
  if (!pending) return

  try {
    const path = pending.kind === 'category' ? 'faq-categories' : 'faq'
    await useNuxtApp().$api.delete(`/tenants/admin/${path}/${pending.id}/`)
    ui.success(t('form.deleted'))
    await reload()
  }
  catch (err) {
    ui.error(messageFor(err))
  }
}

async function reload(): Promise<void> {
  await Promise.all([refreshCategories(), refreshEntries()])
}
</script>

<style scoped>
.min-width-0 {
  min-width: 0;
}

.mura-faq__count {
  padding: 1px 8px;
  border-radius: 999px;
  background: rgba(var(--v-theme-on-surface), 0.08);
  font-size: 0.7rem;
  font-weight: 600;
}

.mura-faq__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mura-faq__item {
  display: flex;
  align-items: flex-start;
  padding: 12px 14px;
  border: 1px solid rgba(var(--v-border-color), 0.55);
  border-radius: 10px;
  background: rgb(var(--v-theme-surface));
  gap: 10px;
  transition: border-color 140ms ease;
}

.mura-faq__item:hover {
  border-color: rgba(var(--v-theme-primary), 0.45);
}

/* A draft is visibly not live — a dashed edge reads as "unfinished" without
   needing the chip to be read. */
.mura-faq__item--draft {
  border-style: dashed;
  background: rgba(var(--v-theme-on-surface), 0.02);
}

.mura-faq__grip {
  margin-top: 2px;
  cursor: grab;
}

.mura-faq__grip:active {
  cursor: grabbing;
}

.mura-faq__question {
  margin-bottom: 2px;
  font-size: 0.9rem;
  font-weight: 600;
  line-height: 1.3;
}

/* Two lines of the answer: enough to tell which one this is, not so much that
   the list stops being scannable. */
.mura-faq__answer {
  display: -webkit-box;
  overflow: hidden;
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.8rem;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.mura-faq__actions {
  display: flex;
  flex: 0 0 auto;
  gap: 2px;
}

@media (prefers-reduced-motion: reduce) {
  .mura-faq__item {
    transition: none;
  }
}
</style>
