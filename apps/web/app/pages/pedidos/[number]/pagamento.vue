<template lang="pug">
.mura-container.mura-section(style="max-width: 640px")
  v-progress-linear(v-if="pending" indeterminate color="primary")

  mura-error-state(v-else-if="error" :on-retry="() => refresh()")

  template(v-else-if="order")
    .text-center.mb-6
      v-icon.mb-2(:icon="statusIcon" size="48" :color="statusColor")
      h1.text-h5 {{ statusTitle }}
      p.text-body-2.text-medium-emphasis {{ t('order.orderNumber') }} {{ order.number }}

    v-card.mura-card.pa-6.text-center(v-if="showPixCode" flat)
      p.text-body-2.text-medium-emphasis.mb-4 {{ t('payment.instructions') }}

      v-img.mx-auto.mb-4(
        v-if="qrImage"
        :src="qrImage"
        :alt="t('payment.title')"
        width="240"
        height="240"
      )

      .text-h6.mb-1 {{ t('payment.amount') }}
      .text-h4.mura-price.mb-4 {{ money.format(order.payment?.amount) }}

      v-textarea.mb-3(
        :model-value="order.payment?.pix_payload"
        :label="t('payment.title')"
        readonly
        rows="3"
        variant="outlined"
      )

      v-btn.mb-4(
        color="primary"
        variant="flat"
        block
        prepend-icon="mdi-content-copy"
        @click="copyCode"
      ) {{ t('payment.copyCode') }}

      v-alert(type="info" variant="tonal" density="compact" icon="mdi-timer-outline")
        span(v-if="countdown") {{ t('payment.expiresIn', { time: countdown }) }}
        span.d-block.mt-1 {{ t('payment.waiting') }}
      v-progress-linear.mt-3(indeterminate color="primary")

    v-card.mura-card.pa-6.text-center(v-else-if="isExpired" flat)
      p.text-body-1.mb-4 {{ t('payment.expired') }}
      v-btn(color="primary" variant="flat" :loading="regenerating" @click="regeneratePayment") {{ t('payment.generateNew') }}

    v-card.mura-card.pa-6.text-center(v-else flat)
      v-icon.mb-3(icon="mdi-check-circle-outline" size="48" color="success")
      p.text-body-1.mb-4 {{ t('payment.confirmed') }}
      v-btn(:to="`/pedidos/${order.number}`" color="primary" variant="flat") {{ t('order.trackOrder') }}

    .text-center.mt-6
      v-btn(:to="`/pedidos/${order.number}`" variant="text") {{ t('order.trackOrder') }}
</template>

<script setup lang="ts">
/**
 * PIX payment screen.
 *
 * Polls the order until the backend reports the payment as confirmed. The page
 * never decides that a payment succeeded — only a verified provider webhook
 * can do that (invariant #4), so this waits for the server to say so.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Order } from '~/types/api'
import { useMoney } from '~/composables/useMoney'
import { useApiError } from '~/composables/useApiError'
import { useUiStore } from '~/stores/ui'

definePageMeta({ middleware: 'auth', permission: 'perm.account.orders' })

const route = useRoute()
const { t } = useI18n()
const money = useMoney()
const ui = useUiStore()
const { notify } = useApiError()

const orderNumber = computed(() => String(route.params.number))

const { data: order, pending, error, refresh } = await useAsyncData<Order>(
  () => `order-payment-${orderNumber.value}`,
  () => useNuxtApp().$api.get<Order>(`/orders/${orderNumber.value}/`),
)

useSeoMeta({ title: () => t('payment.title'), robots: 'noindex' })

const regenerating = ref(false)
const countdown = ref('')

let pollTimer: ReturnType<typeof setInterval> | null = null
let countdownTimer: ReturnType<typeof setInterval> | null = null

const payment = computed(() => order.value?.payment ?? null)
const isPaid = computed(() => order.value?.status !== 'PENDING_PAYMENT' && Boolean(order.value?.paid_at))
const isExpired = computed(() => Boolean(payment.value?.is_expired) && !isPaid.value)
const showPixCode = computed(() => Boolean(payment.value?.pix_payload) && !isPaid.value && !isExpired.value)

const qrImage = computed(() =>
  payment.value?.pix_qr_code ? `data:image/png;base64,${payment.value.pix_qr_code}` : '',
)

const statusIcon = computed(() => (isPaid.value ? 'mdi-check-circle-outline' : 'mdi-qrcode-scan'))
const statusColor = computed(() => (isPaid.value ? 'success' : 'primary'))
const statusTitle = computed(() => t(isPaid.value ? 'payment.confirmed' : 'payment.title'))

async function copyCode(): Promise<void> {
  const code = payment.value?.pix_payload
  if (!code) return

  try {
    await navigator.clipboard.writeText(code)
    ui.success(t('payment.codeCopied'))
  }
  catch {
    // Clipboard access can be denied; the code is on screen and selectable.
    ui.notify(t('payment.copyCode'))
  }
}

async function regeneratePayment(): Promise<void> {
  regenerating.value = true
  try {
    await useNuxtApp().$api.post('/payments/', { order: order.value?.id, method: 'PIX' })
    await refresh()
  }
  catch (err) {
    notify(err)
  }
  finally {
    regenerating.value = false
  }
}

function updateCountdown(): void {
  const expiresAt = payment.value?.expires_at
  if (!expiresAt) {
    countdown.value = ''
    return
  }

  const remaining = new Date(expiresAt).getTime() - Date.now()
  if (remaining <= 0) {
    countdown.value = ''
    return
  }

  const minutes = Math.floor(remaining / 60000)
  const seconds = Math.floor((remaining % 60000) / 1000)
  countdown.value = `${minutes}:${String(seconds).padStart(2, '0')}`
}

onMounted(() => {
  // Five seconds is responsive enough for a PIX transfer without hammering the
  // API while a customer switches to their banking app.
  pollTimer = setInterval(async () => {
    if (isPaid.value) return
    await refresh()
    if (isPaid.value) ui.success(t('payment.confirmed'))
  }, 5000)

  countdownTimer = setInterval(updateCountdown, 1000)
  updateCountdown()
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (countdownTimer) clearInterval(countdownTimer)
})
</script>
