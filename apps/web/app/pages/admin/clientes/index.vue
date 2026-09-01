<template lang="pug">
div
  mura-page-header(
    :title="t('admin.customers')"
    :subtitle="t('admin.customersSubtitle')"
    :breadcrumbs="[{ title: 'admin.dashboard', to: '/admin' }, { title: 'admin.customers' }]"
  )

  mura-data-table(
    :table="table"
    :columns="columns"
    :title="t('admin.customers')"
    searchable
  )
    template(#item.full_name="{ item }")
      .d-flex.align-center.ga-3.py-1
        v-avatar(color="primary" size="34")
          span.text-caption {{ initials(String(item.full_name || item.email)) }}
        .min-width-0
          p.text-body-2.mb-0.text-truncate {{ item.full_name || '—' }}
          p.text-caption.text-medium-emphasis.mb-0.text-truncate {{ item.email }}

    template(#item.is_active="{ item }")
      v-chip(:color="item.is_active ? 'success' : 'secondary'" size="x-small" variant="tonal") {{ item.is_active ? t('admin.active') : t('admin.inactive') }}
</template>

<script setup lang="ts">
/**
 * Customer directory.
 *
 * Read-only. Staff can look someone up to answer a question about an order,
 * but editing a customer's own details from the back office is a different
 * decision with its own consequences (and its own audit trail), so this screen
 * does not offer it.
 */
import { useI18n } from 'vue-i18n'
import type { TableColumn } from '~/types/ui'
import { useServerTable } from '~/composables/useServerTable'
import { initials } from '~/utils/format'

definePageMeta({ layout: 'admin', middleware: 'merchant', permission: 'perm.admin.customers' })

interface CustomerRow {
  id: string
  full_name: string
  email: string
  phone: string
  is_active: boolean
  created_at: string
  [key: string]: unknown
}

const { t } = useI18n()

useSeoMeta({ title: () => t('admin.customers') })

const table = useServerTable<CustomerRow>({
  endpoint: '/admin/customers/',
  defaultSort: [{ key: 'created_at', order: 'desc' }],
  sortMap: { full_name: 'first_name' },
  searchParam: 'search',
})

const columns: TableColumn<CustomerRow>[] = [
  { key: 'full_name', title: 'admin.customer', sortable: true },
  { key: 'phone', title: 'auth.phone', sortable: false, hideBelow: 'md', value: row => row.phone || '—' },
  { key: 'created_at', title: 'admin.createdAt', sortable: true, format: 'date', hideBelow: 'lg' },
  { key: 'is_active', title: 'order.status', sortable: true, align: 'center' },
]
</script>
