<template lang="pug">
div
  mura-page-header(
    :title="user?.full_name || user?.email || t('admin.viewUser')"
    :subtitle="user?.email"
    back-to="/admin/usuarios"
    :breadcrumbs="[{ title: 'admin.dashboard', to: '/admin' }, { title: 'admin.users', to: '/admin/usuarios' }, { title: 'admin.viewUser' }]"
  )
    template(#actions)
      mura-button(
        :label="t('common.edit')"
        icon="mdi-pencil-outline"
        permission="users.manage"
        @click="router.push(`/admin/usuarios/${userId}/editar`)"
      )

  mura-loading(v-if="pending" skeleton="card")

  mura-error-state(v-else-if="error" :on-retry="() => refresh()")

  v-row(v-else-if="user")
    v-col(cols="12" md="5")
      mura-card(:title="t('admin.tabDetails')" icon="mdi-account-outline")
        v-list(density="compact" bg-color="transparent")
          v-list-item.px-0
            v-list-item-title.text-body-2 {{ t('auth.email') }}
            template(#append)
              span.text-body-2.text-medium-emphasis {{ user.email }}
          v-list-item.px-0
            v-list-item-title.text-body-2 {{ t('auth.phone') }}
            template(#append)
              span.text-body-2.text-medium-emphasis {{ formatPhone(user.phone) || '—' }}
          v-list-item.px-0
            v-list-item-title.text-body-2 {{ t('admin.userType') }}
            template(#append)
              span.text-body-2.text-medium-emphasis {{ t(`admin.userTypes.${user.user_type}`, user.user_type) }}
          v-list-item.px-0
            v-list-item-title.text-body-2 {{ t('order.status') }}
            template(#append)
              v-chip(:color="user.is_active ? 'success' : 'error'" size="x-small" variant="tonal") {{ user.is_active ? t('admin.active') : t('admin.inactive') }}

      mura-card.mt-4(:title="t('admin.roles')" icon="mdi-shield-account-outline")
        .d-flex.flex-wrap.ga-2
          v-chip(v-for="role in user.roles" :key="role" size="small" variant="tonal") {{ role }}
          span.text-body-2.text-medium-emphasis(v-if="!user.roles.length") {{ t('admin.noRoles') }}

    v-col(cols="12" md="7")
      mura-card(
        :title="t('admin.effectivePermissions')"
        :subtitle="t('admin.effectivePermissionsHint')"
        icon="mdi-key-outline"
      )
        .d-flex.flex-wrap.ga-1
          v-chip(
            v-for="code in permissions?.effective ?? []"
            :key="code"
            :color="permissions?.direct.includes(code) ? 'primary' : undefined"
            size="x-small"
            variant="tonal"
            :title="permissions?.direct.includes(code) ? t('admin.grantedDirectly') : t('admin.grantedByRole')"
          ) {{ code }}
          span.text-body-2.text-medium-emphasis(v-if="!permissions?.effective.length") {{ t('admin.noPermissions') }}

        template(#footer)
          span.text-caption.text-medium-emphasis
            v-chip.mr-1(size="x-small" color="primary" variant="tonal") &nbsp;
            | {{ t('admin.grantedDirectly') }}
</template>

<script setup lang="ts">
/**
 * Read-only view of one account.
 *
 * Exists so someone holding `users.view` but not `users.manage` can inspect an
 * account without the editor offering controls the API would refuse.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatPhone } from '~/utils/format'

definePageMeta({ layout: 'admin', middleware: 'merchant', permission: 'perm.admin.users' })

interface StaffUser {
  id: string
  email: string
  full_name: string
  phone: string
  user_type: string
  is_active: boolean
  roles: string[]
}

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const userId = computed(() => String(route.params.id))

const { data: user, pending, error, refresh } = await useAsyncData<StaffUser>(
  () => `admin-user-view-${userId.value}`,
  () => useNuxtApp().$api.get<StaffUser>(`/admin/users/${userId.value}/`),
)

const { data: permissions } = await useAsyncData<{
  direct: string[]
  from_roles: string[]
  effective: string[]
}>(
  () => `admin-user-permissions-view-${userId.value}`,
  () => useNuxtApp().$api.get(`/admin/users/${userId.value}/permissions/`),
  { default: () => ({ direct: [], from_roles: [], effective: [] }) },
)

useSeoMeta({ title: () => user.value?.full_name || t('admin.viewUser') })
</script>
