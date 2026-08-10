<template lang="pug">
template(v-if="allowed")
  v-btn(
    v-bind="$attrs"
    :color="color"
    :variant="variant"
    :size="size"
    :loading="loading"
    :disabled="disabled"
    :prepend-icon="icon"
    :aria-label="ariaLabel || label"
    @click="onClick"
  )
    slot {{ label }}

  mura-confirm-dialog(
    v-if="confirm"
    v-model="confirmOpen"
    :message="confirmMessage"
    :danger="danger"
    :loading="loading"
    @confirm="emitClick"
  )
</template>

<script setup lang="ts">
/**
 * Button with permission gating and optional confirmation.
 *
 * Two things a bare `v-btn` cannot do on its own:
 *
 * - **Permission.** With `permission`, the button is not rendered at all when
 *   the user lacks the code. Affordance only — the API enforces the same rule.
 * - **Confirmation.** With `confirm`, the click is routed through a dialog, so
 *   destructive actions cannot be a single misplaced tap.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '~/stores/auth'

defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<{
  label?: string
  icon?: string
  color?: string
  variant?: 'flat' | 'tonal' | 'text' | 'outlined' | 'elevated' | 'plain'
  size?: 'x-small' | 'small' | 'default' | 'large' | 'x-large'
  loading?: boolean
  disabled?: boolean
  /** Permission code required to see this button. */
  permission?: string
  /** i18n key for a confirmation question; enables the dialog. */
  confirm?: string
  danger?: boolean
  ariaLabel?: string
}>(), {
  label: '',
  icon: undefined,
  color: 'primary',
  variant: 'flat',
  size: 'default',
  loading: false,
  disabled: false,
  permission: undefined,
  confirm: undefined,
  danger: false,
  ariaLabel: '',
})

const emit = defineEmits<{ click: [] }>()

const { t, te } = useI18n()
const auth = useAuthStore()

const confirmOpen = ref(false)

const allowed = computed(() => !props.permission || auth.can(props.permission))

const confirmMessage = computed(() => {
  if (!props.confirm) return ''
  return te(props.confirm) ? t(props.confirm) : props.confirm
})

function onClick(): void {
  if (props.confirm) {
    confirmOpen.value = true
    return
  }
  emit('click')
}

function emitClick(): void {
  confirmOpen.value = false
  emit('click')
}
</script>
