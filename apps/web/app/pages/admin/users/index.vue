<template lang="pug">
div
  mura-page-header(
    :title="t('admin.users')"
    :subtitle="t('admin.usersSubtitle')"
    :breadcrumbs="[{ title: 'admin.dashboard', to: '/admin' }, { title: 'admin.users' }]"
  )
    template(#actions)
      mura-button(
        :label="t('admin.newUser')"
        icon="mdi-account-plus-outline"
        permission="users.manage"
        @click="router.push('/admin/users/new')"
      )

  mura-data-table(
    :table="table"
    :columns="columns"
    :actions="rowActions"
    :title="t('admin.users')"
    searchable
    clickable
    @action="onAction"
    @row-click="row => router.push(`/admin/users/${row.id}`)"
  )
    template(#filters)
      v-select.mura-admin-filter(
        v-model="typeFilter"
        :items="typeOptions"
        :label="t('admin.userType')"
        item-title="label"
        item-value="value"
        density="compact"
        hide-details
        clearable
        @update:model-value="table.applyFilters()"
      )

    template(#item.full_name="{ item }")
      .d-flex.align-center.ga-3.py-1
        v-avatar(color="primary" size="36")
          span.text-caption {{ initials(String(item.full_name || item.email)) }}
        .min-width-0
          p.text-body-2.mb-0.text-truncate {{ item.full_name || '—' }}
          p.text-caption.text-medium-emphasis.mb-0.text-truncate {{ item.email }}

    template(#item.roles="{ item }")
      .d-flex.flex-wrap.ga-1
        v-chip(
          v-for="role in (item.roles as string[]) ?? []"
          :key="role"
          size="x-small"
          variant="tonal"
        ) {{ role }}
        span.text-caption.text-medium-emphasis(v-if="!(item.roles as string[])?.length") —

    template(#item.is_active="{ item }")
      v-chip(
        :color="item.is_active ? 'success' : 'error'"
        :prepend-icon="item.is_active ? 'mdi-check-circle' : 'mdi-close-circle'"
        size="x-small"
        variant="tonal"
      ) {{ item.is_active ? t('admin.active') : t('admin.inactive') }}
</template>

<script setup lang="ts">
/**
 * User and role administration.
 *
 * The list only lists. Creating and editing are real pages
 * (`/novo`, `/:id/editar`) rather than a dialog, because the editor carries
 * tabs and two transfer lists — far too much for a modal, and a URL worth
 * linking to.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { TableAction, TableColumn } from '~/types/ui'
import { useServerTable } from '~/composables/useServerTable'
import { useApiError } from '~/composables/useApiError'
import { useAuthStore } from '~/stores/auth'
import { useUiStore } from '~/stores/ui'
import { initials } from '~/utils/format'

definePageMeta({ layout: 'admin', middleware: 'merchant', permission: 'perm.admin.users' })

type UserRow = Record<string, unknown>

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()
const { notify } = useApiError()

useSeoMeta({ title: () => t('admin.users') })

const typeFilter = ref<string | null>(null)

const table = useServerTable<UserRow>({
  endpoint: '/admin/users/',
  defaultSort: [{ key: 'email', order: 'asc' }],
  filters: () => ({ user_type: typeFilter.value ?? undefined }),
})

const columns: TableColumn<UserRow>[] = [
  { key: 'full_name', title: 'admin.userName', sortable: 'email' },
  { key: 'user_type', title: 'admin.userType', sortable: true, hideBelow: 'sm' },
  { key: 'roles', title: 'admin.roles', sortable: false, hideBelow: 'md' },
  { key: 'is_active', title: 'order.status', sortable: true, align: 'center' },
  { key: 'created_at', title: 'admin.createdAt', sortable: true, format: 'date', hideBelow: 'lg' },
]

const rowActions: TableAction<UserRow>[] = [
  { key: 'view', label: 'admin.view', icon: 'mdi-eye-outline', permission: 'users.view' },
  { key: 'edit', label: 'common.edit', icon: 'mdi-pencil-outline', permission: 'users.manage' },
  {
    key: 'delete',
    label: 'admin.deactivate',
    icon: 'mdi-account-off-outline',
    color: 'error',
    permission: 'users.manage',
    confirm: 'admin.deactivateConfirm',
    // Deactivating yourself would lock you out of the screen you are on.
    visibleWhen: row => row.id !== auth.user?.id && row.is_active === true,
  },
]

const typeOptions = computed(() =>
  ['STAFF', 'MANAGER', 'ADMINISTRATOR'].map(value => ({
    value,
    label: t(`admin.userTypes.${value}`, value),
  })),
)

async function onAction(payload: { key: string, row: UserRow }): Promise<void> {
  const { key, row } = payload
  if (key === 'view') {
    await router.push(`/admin/users/${row.id}`)
    return
  }
  if (key === 'edit') {
    await router.push(`/admin/users/${row.id}/editar`)
    return
  }

  if (key === 'delete') {
    try {
      // The API deactivates rather than deletes: audit rows must keep their actor.
      await useNuxtApp().$api.delete(`/admin/users/${row.id}/`)
      ui.success(t('admin.deactivated'))
      await table.refreshAfterDelete()
    }
    catch (error) {
      notify(error)
    }
  }
}
</script>

<style scoped>
.mura-admin-filter {
  max-width: 200px;
}

.min-width-0 {
  min-width: 0;
}
</style>
