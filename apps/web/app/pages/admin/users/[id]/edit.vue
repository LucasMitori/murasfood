<template lang="pug">
div
  mura-page-header(
    :title="user?.full_name || user?.email || t('admin.editUser')"
    :subtitle="user?.email"
    back-to="/admin/users"
    :breadcrumbs="[{ title: 'admin.dashboard', to: '/admin' }, { title: 'admin.users', to: '/admin/users' }, { title: 'admin.editUser' }]"
  )

  mura-loading(v-if="pending" skeleton="card")

  mura-error-state(v-else-if="error" :on-retry="() => refresh()")

  template(v-else-if="user")
    v-tabs.mb-4(v-model="tab" color="primary")
      v-tab(value="details" prepend-icon="mdi-account-outline") {{ t('admin.tabDetails') }}
      v-tab(value="permissions" prepend-icon="mdi-key-outline") {{ t('admin.tabPermissions') }}
      v-tab(value="roles" prepend-icon="mdi-shield-account-outline") {{ t('admin.tabRoles') }}

    v-window(v-model="tab")
      //- --- Details -------------------------------------------------------
      v-window-item(value="details")
        mura-form-builder(
          ref="formRef"
          v-model:values="formValues"
          :schema="schema"
          :loading="savingDetails"
          show-cancel
          require-changes
          @submit="saveDetails"
          @cancel="router.push('/admin/users')"
        )

      //- --- Permissions ---------------------------------------------------
      v-window-item(value="permissions")
        mura-card(
          :title="t('admin.directPermissions')"
          :subtitle="t('admin.directPermissionsHint')"
          icon="mdi-key-outline"
        )
          v-alert.mb-4(
            v-if="inheritedCodes.length"
            type="info"
            variant="tonal"
            density="compact"
            icon="mdi-information-outline"
          ) {{ t('admin.inheritedNotice', { count: inheritedCodes.length }) }}

          mura-transfer-list(
            v-model="directCodes"
            :options="permissionOptions"
            :locked-values="inheritedCodes"
            :available-label="t('admin.availablePermissions')"
            :assigned-label="t('admin.assignedPermissions')"
            :disabled="savingPermissions"
            group="permissions"
          )

          template(#footer)
            v-spacer
            span.text-caption.text-medium-emphasis.mr-3(v-if="permissionsDirty") {{ t('form.unsavedChanges') }}
            v-btn(variant="text" :disabled="savingPermissions" @click="resetPermissions") {{ t('common.cancel') }}
            v-btn(
              color="primary"
              variant="flat"
              :loading="savingPermissions"
              :disabled="!permissionsDirty"
              @click="savePermissions"
            ) {{ t('common.save') }}

      //- --- Roles ----------------------------------------------------------
      v-window-item(value="roles")
        mura-card(
          :title="t('admin.roles')"
          :subtitle="t('admin.rolesHint')"
          icon="mdi-shield-account-outline"
        )
          mura-transfer-list(
            v-model="roleSlugs"
            :options="roleOptions"
            :available-label="t('admin.availableRoles')"
            :assigned-label="t('admin.assignedRoles')"
            :disabled="savingRoles"
            group="roles"
          )

          template(#footer)
            v-spacer
            span.text-caption.text-medium-emphasis.mr-3(v-if="rolesDirty") {{ t('form.unsavedChanges') }}
            v-btn(variant="text" :disabled="savingRoles" @click="resetRoles") {{ t('common.cancel') }}
            v-btn(
              color="primary"
              variant="flat"
              :loading="savingRoles"
              :disabled="!rolesDirty"
              @click="saveRoles"
            ) {{ t('common.save') }}
</template>

<script setup lang="ts">
/**
 * User editor.
 *
 * Three tabs, each saving independently: details, direct permissions, and
 * roles. Independent saves matter because the three write to different
 * endpoints — one "save everything" button would have to succeed or fail as a
 * unit across three requests, and a partial failure would leave the screen
 * lying about what was stored.
 *
 * Permissions inherited from a role appear in the assigned column but locked:
 * they are real, and they are not this screen's to revoke.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { FormSchema, FormValues } from '~/types/ui'
import type { TransferItem } from '~/components/shared/MuraTransferList.vue'
import { useApiError } from '~/composables/useApiError'
import { useAuthStore } from '~/stores/auth'
import { useUiStore } from '~/stores/ui'

definePageMeta({ layout: 'admin', middleware: 'merchant', permission: 'perm.admin.users' })

interface PermissionRow {
  id: string
  code: string
  description: string
  is_page: boolean
  group: string
}

interface RoleRow {
  id: string
  slug: string
  name: string
  description: string
  is_system: boolean
}

interface StaffUser {
  id: string
  email: string
  first_name: string
  last_name: string
  full_name: string
  phone: string
  user_type: string
  is_active: boolean
  roles: string[]
}

const { t, te } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()
const { messageFor, notify } = useApiError()

const userId = computed(() => String(route.params.id))
const tab = ref('details')

const { data: user, pending, error, refresh } = await useAsyncData<StaffUser>(
  () => `admin-user-${userId.value}`,
  () => useNuxtApp().$api.get<StaffUser>(`/admin/users/${userId.value}/`),
)

useSeoMeta({ title: () => user.value?.full_name || t('admin.editUser') })

const { data: permissions } = await useAsyncData<PermissionRow[]>(
  'admin-permissions',
  () => useNuxtApp().$api.get<PermissionRow[]>('/admin/permissions/'),
  { default: () => [] },
)

const { data: roles } = await useAsyncData<RoleRow[]>(
  'admin-roles-list',
  async () => {
    const page = await useNuxtApp().$api.get<{ results: RoleRow[] }>('/admin/roles/', {
      query: { page_size: 100 },
    })
    return page.results
  },
  { default: () => [] },
)

const { data: userPermissions, refresh: refreshPermissions } = await useAsyncData<{
  direct: string[]
  from_roles: string[]
  effective: string[]
}>(
  () => `admin-user-permissions-${userId.value}`,
  () => useNuxtApp().$api.get(`/admin/users/${userId.value}/permissions/`),
  { default: () => ({ direct: [], from_roles: [], effective: [] }) },
)

// --- Details tab ------------------------------------------------------------
const savingDetails = ref(false)
const formValues = ref<FormValues>({})
const formRef = ref<{
  submit: () => void
  applyApiError: (error: unknown) => void
  markPristine: () => void
} | null>(null)

watch(user, (value) => {
  if (!value) return
  formValues.value = {
    first_name: value.first_name,
    last_name: value.last_name,
    email: value.email,
    phone: value.phone,
    user_type: value.user_type,
    is_active: value.is_active,
  }
}, { immediate: true })

const schema = computed<FormSchema>(() => ({
  sections: [
    {
      title: 'admin.tabDetails',
      icon: 'mdi-account-outline',
      fields: [
        { name: 'first_name', type: 'text', label: 'auth.firstName', required: true, md: 6 },
        { name: 'last_name', type: 'text', label: 'auth.lastName', md: 6 },
        // Changing an email changes the login identity; the API treats it as a
        // separate, verified operation.
        { name: 'email', type: 'email', label: 'auth.email', md: 6, disabled: true },
        { name: 'phone', type: 'tel', label: 'auth.phone', md: 6 },
        {
          name: 'user_type',
          type: 'select',
          label: 'admin.userType',
          required: true,
          md: 6,
          options: [
            { value: 'STAFF', label: 'admin.userTypes.STAFF' },
            { value: 'MANAGER', label: 'admin.userTypes.MANAGER' },
            { value: 'ADMINISTRATOR', label: 'admin.userTypes.ADMINISTRATOR' },
          ],
        },
        {
          name: 'is_active',
          type: 'switch',
          label: 'admin.activeAccount',
          md: 6,
          // Deactivating yourself would lock you out of this very screen.
          disabled: () => user.value?.id === auth.user?.id,
        },
      ],
    },
  ],
}))

async function saveDetails(values: FormValues): Promise<void> {
  savingDetails.value = true
  try {
    await useNuxtApp().$api.patch(`/admin/users/${userId.value}/`, values)
    formRef.value?.markPristine()
    ui.success(t('form.saved'))
    await refresh()
  }
  catch (err) {
    formRef.value?.applyApiError(err)
  }
  finally {
    savingDetails.value = false
  }
}

// --- Permissions tab --------------------------------------------------------
const savingPermissions = ref(false)
const directCodes = ref<string[]>([])

const inheritedCodes = computed(() => userPermissions.value?.from_roles ?? [])

watch(userPermissions, (value) => {
  directCodes.value = [...(value?.direct ?? [])]
}, { immediate: true })

const permissionsDirty = computed(() => {
  const saved = [...(userPermissions.value?.direct ?? [])].sort().join(',')
  return [...directCodes.value].sort().join(',') !== saved
})

/** Human label for a code, falling back to the API's own description. */
function permissionLabel(row: PermissionRow): string {
  const key = `permissions.${row.code}`
  return te(key) ? t(key) : row.code
}

const permissionOptions = computed<TransferItem[]>(() =>
  (permissions.value ?? []).map(row => ({
    value: row.code,
    label: permissionLabel(row),
    description: row.description,
  })),
)

function resetPermissions(): void {
  directCodes.value = [...(userPermissions.value?.direct ?? [])]
}

async function savePermissions(): Promise<void> {
  savingPermissions.value = true
  try {
    await useNuxtApp().$api.put(`/admin/users/${userId.value}/permissions/`, {
      codes: directCodes.value,
    })
    ui.success(t('form.saved'))
    await refreshPermissions()

    // The editor may be changing their own access; refresh the session so the
    // navigation reflects reality rather than a stale permission set.
    if (user.value?.id === auth.user?.id) await auth.fetchProfile()
  }
  catch (err) {
    ui.error(messageFor(err))
  }
  finally {
    savingPermissions.value = false
  }
}

// --- Roles tab --------------------------------------------------------------
const savingRoles = ref(false)
const roleSlugs = ref<string[]>([])

watch(user, (value) => {
  roleSlugs.value = [...(value?.roles ?? [])]
}, { immediate: true })

const rolesDirty = computed(() => {
  const saved = [...(user.value?.roles ?? [])].sort().join(',')
  return [...roleSlugs.value].sort().join(',') !== saved
})

const roleOptions = computed<TransferItem[]>(() =>
  (roles.value ?? []).map(role => ({
    value: role.slug,
    label: role.name,
    description: role.description || (role.is_system ? t('admin.systemRole') : ''),
  })),
)

function resetRoles(): void {
  roleSlugs.value = [...(user.value?.roles ?? [])]
}

async function saveRoles(): Promise<void> {
  savingRoles.value = true
  try {
    await useNuxtApp().$api.put(`/admin/users/${userId.value}/roles/`, {
      roles: roleSlugs.value,
    })
    ui.success(t('form.saved'))
    await Promise.all([refresh(), refreshPermissions()])

    if (user.value?.id === auth.user?.id) await auth.fetchProfile()
  }
  catch (err) {
    notify(err)
  }
  finally {
    savingRoles.value = false
  }
}
</script>
