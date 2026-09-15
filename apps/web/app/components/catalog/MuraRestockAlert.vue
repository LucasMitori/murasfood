<template lang="pug">
.mura-restock
  v-alert(
    type="warning"
    variant="tonal"
    density="compact"
    icon="mdi-package-variant-remove"
  )
    .d-flex.flex-wrap.align-center.ga-3
      div.flex-grow-1
        strong {{ t('product.outOfStock') }}
        //- Social proof, and true: the number comes from how many people have
          //- actually asked. It is what turns "unavailable" into "worth
          //- waiting for".
        p.text-caption.mb-0(v-if="waiting > 0") {{ t('catalog.peopleWaiting', waiting, { count: waiting }) }}

      v-btn(
        v-if="!subscribed"
        color="warning"
        variant="flat"
        size="small"
        prepend-icon="mdi-bell-outline"
        @click="open = true"
      ) {{ t('catalog.notifyMe') }}

      v-btn(
        v-else
        variant="text"
        size="small"
        prepend-icon="mdi-bell-off-outline"
        :loading="busy"
        @click="unsubscribe"
      ) {{ t('catalog.notifyMeCancel') }}

  mura-dialog(v-model="open" :title="t('catalog.notifyMe')" max-width="440")
    p.text-body-2.text-medium-emphasis.mb-4 {{ t('catalog.notifyMeHint') }}

    //- A signed-in shopper never types an address. Their account's is
      //- authoritative, and the API ignores anything sent here anyway — letting
      //- someone name a different address would make this a way to sign
      //- strangers up for mail.
    v-text-field(
      v-if="!auth.isAuthenticated"
      v-model="email"
      :label="t('catalog.notifyMeEmail')"
      :error-messages="emailError ? [emailError] : []"
      type="email"
      variant="outlined"
      density="comfortable"
      autocomplete="email"
      prepend-inner-icon="mdi-email-outline"
      @keydown.enter="subscribe"
    )

    p.text-body-2(v-else) {{ auth.user?.email }}

    template(#actions)
      v-spacer
      v-btn(variant="text" @click="open = false") {{ t('common.cancel') }}
      v-btn(
        color="primary"
        variant="flat"
        :loading="busy"
        prepend-icon="mdi-bell-ring-outline"
        @click="subscribe"
      ) {{ t('catalog.notifyMe') }}
</template>

<script setup lang="ts">
/**
 * "Tell me when it's back."
 *
 * The alternative designs are both worse. Hiding what is out of stock loses the
 * sale *and* the information — the shop never learns anyone wanted it. Showing
 * it greyed out with no action loses the sale and annoys the shopper. This
 * keeps the shopper, and hands the merchant a ranked list of what to reorder
 * (`/admin/inventory/restock-demand/`) built from demand that produced no
 * order and therefore appears in no sales report.
 *
 * Open to visitors without an account on purpose: requiring a signup before
 * someone can say they want a bag of rice is how a shop collects no signal at
 * all.
 *
 * Whether a guest is already subscribed is not knowable from the client — there
 * is no endpoint that will tell you which addresses are on a list, and there
 * must not be, because that would let anyone test whether a given email is a
 * customer. So the subscribed state here is only what happened in this session.
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useApiError } from '~/composables/useApiError'
import { useAuthStore } from '~/stores/auth'
import { useUiStore } from '~/stores/ui'

const props = withDefaults(defineProps<{
  slug: string
  /** How many people are already waiting, from the product payload. */
  waiting?: number
}>(), {
  waiting: 0,
})

const { t } = useI18n()
const auth = useAuthStore()
const ui = useUiStore()
const { messageFor } = useApiError()

const open = ref(false)
const busy = ref(false)
const email = ref('')
const emailError = ref('')
const subscribed = ref(false)

async function subscribe(): Promise<void> {
  emailError.value = ''

  if (!auth.isAuthenticated && !isPlausibleEmail(email.value)) {
    emailError.value = t('validation.email')
    return
  }

  busy.value = true
  try {
    await useNuxtApp().$api.post(`/catalog/products/${props.slug}/restock-alert/`, {
      email: auth.isAuthenticated ? undefined : email.value.trim(),
    })
    subscribed.value = true
    open.value = false
    ui.success(t('catalog.notifyMeDone'))
  }
  catch (error) {
    ui.error(messageFor(error))
  }
  finally {
    busy.value = false
  }
}

async function unsubscribe(): Promise<void> {
  busy.value = true
  try {
    await useNuxtApp().$api.delete(`/catalog/products/${props.slug}/restock-alert/`, {
      body: auth.isAuthenticated ? undefined : { email: email.value.trim() },
    })
    subscribed.value = false
    ui.success(t('catalog.notifyMeCancelled'))
  }
  catch (error) {
    ui.error(messageFor(error))
  }
  finally {
    busy.value = false
  }
}

/**
 * A shape check, not a validation.
 *
 * The address is confirmed by whether the eventual email arrives; anything
 * stricter here rejects real addresses (new TLDs, plus-addressing, unicode
 * domains) for no gain.
 */
function isPlausibleEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim())
}
</script>
