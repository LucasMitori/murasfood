<template lang="pug">
div
  mura-page-header(
    :title="t('admin.newUser')"
    :subtitle="t('admin.newUserSubtitle')"
    back-to="/admin/usuarios"
    :breadcrumbs="[{ title: 'admin.dashboard', to: '/admin' }, { title: 'admin.users', to: '/admin/usuarios' }, { title: 'admin.newUser' }]"
  )

  mura-form-builder(
    ref="formRef"
    v-model:values="formValues"
    :schema="schema"
    :loading="saving"
    show-cancel
    @submit="create"
    @cancel="router.push('/admin/usuarios')"
  )
</template>

<script setup lang="ts">
/**
 * Create a staff account.
 *
 * Only the identity fields and a starting role. Permissions and further roles
 * are set in the editor afterwards — they need a user id to attach to, and
 * splitting the steps keeps this form short enough to complete in one sitting.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { FormSchema, FormValues } from '~/types/ui'
import { useUiStore } from '~/stores/ui'

definePageMeta({ layout: 'admin', middleware: 'merchant', permission: 'perm.admin.users' })

interface RoleRow {
  id: string
  slug: string
  name: string
}

const { t } = useI18n()
const router = useRouter()
const ui = useUiStore()

useSeoMeta({ title: () => t('admin.newUser') })

const saving = ref(false)
const formValues = ref<FormValues>({ user_type: 'STAFF', is_active: true, roles: [] })
const formRef = ref<{
  submit: () => void
  applyApiError: (error: unknown) => void
  markPristine: () => void
} | null>(null)

const { data: roles } = await useAsyncData<RoleRow[]>(
  'admin-roles-new-user',
  async () => {
    const page = await useNuxtApp().$api.get<{ results: RoleRow[] }>('/admin/roles/', {
      query: { page_size: 100 },
    })
    return page.results
  },
  { default: () => [] },
)

const schema = computed<FormSchema>(() => ({
  submitLabel: 'admin.createUser',
  sections: [
    {
      title: 'admin.tabDetails',
      icon: 'mdi-account-outline',
      fields: [
        { name: 'first_name', type: 'text', label: 'auth.firstName', required: true, md: 6 },
        { name: 'last_name', type: 'text', label: 'auth.lastName', md: 6 },
        { name: 'email', type: 'email', label: 'auth.email', required: true, md: 6 },
        { name: 'phone', type: 'tel', label: 'auth.phone', md: 6 },
      ],
    },
    {
      title: 'admin.accessSection',
      icon: 'mdi-shield-account-outline',
      description: 'admin.accessSectionHint',
      fields: [
        {
          name: 'user_type',
          type: 'select',
          label: 'admin.userType',
          required: true,
          md: 6,
          default: 'STAFF',
          options: [
            { value: 'STAFF', label: 'admin.userTypes.STAFF' },
            { value: 'MANAGER', label: 'admin.userTypes.MANAGER' },
            { value: 'ADMINISTRATOR', label: 'admin.userTypes.ADMINISTRATOR' },
          ],
        },
        {
          name: 'roles',
          type: 'autocomplete',
          label: 'admin.roles',
          multiple: true,
          md: 6,
          options: () => (roles.value ?? []).map(role => ({
            value: role.slug,
            label: role.name,
          })),
        },
        { name: 'is_active', type: 'switch', label: 'admin.activeAccount', default: true, md: 6 },
      ],
    },
  ],
}))

async function create(values: FormValues): Promise<void> {
  saving.value = true
  try {
    const created = await useNuxtApp().$api.post<{ id: string }>('/admin/users/', values)
    formRef.value?.markPristine()
    ui.success(t('admin.userCreated'))

    // Straight into the editor: permissions and extra roles come next, and the
    // account is not much use until they are set.
    await router.push(`/admin/usuarios/${created.id}/editar`)
  }
  catch (error) {
    formRef.value?.applyApiError(error)
  }
  finally {
    saving.value = false
  }
}
</script>
