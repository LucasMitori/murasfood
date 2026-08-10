<template lang="pug">
.mura-price-block(:class="blockClass")
  span.mura-price(:class="priceClass") {{ formattedPrice }}
  template(v-if="showDiscount")
    span.mura-price--struck.text-medium-emphasis.ml-2 {{ formattedBase }}
    v-chip.ml-2(
      v-if="discountPercent > 0"
      size="x-small"
      color="accent"
      variant="flat"
      density="comfortable"
    ) -{{ discountPercent }}%
  span.text-caption.text-medium-emphasis.ml-1(v-if="unitLabel") {{ unitLabel }}
</template>

<script setup lang="ts">
/**
 * Renders a price, its struck-through list price and the discount badge.
 *
 * Amounts arrive as strings and are formatted with the tenant's currency; this
 * component never does arithmetic on them beyond computing the badge
 * percentage.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ProductPriceInfo } from '~/types/api'
import { useMoney } from '~/composables/useMoney'

const props = withDefaults(defineProps<{
  price: ProductPriceInfo | null
  unit?: string
  size?: 'small' | 'medium' | 'large'
  /** Lay the list price under the current price instead of beside it. */
  stacked?: boolean
}>(), {
  unit: '',
  size: 'medium',
  stacked: false,
})

const money = useMoney()
const { t } = useI18n()

const formattedPrice = computed(() => money.format(props.price?.price ?? null))
const formattedBase = computed(() => money.format(props.price?.base_price ?? null))

const showDiscount = computed(() =>
  Boolean(props.price?.is_discounted && props.price.base_price && props.price.base_price !== props.price.price),
)

const discountPercent = computed(() =>
  money.discountPercent(props.price?.base_price, props.price?.price),
)

const unitLabel = computed(() => (props.unit ? t('product.perUnit', { unit: props.unit }) : ''))

const priceClass = computed(() => ({
  'text-body-2': props.size === 'small',
  'text-h6': props.size === 'medium',
  'text-h5': props.size === 'large',
}))

const blockClass = computed(() => ({ 'd-flex flex-column align-start': props.stacked }))
</script>
