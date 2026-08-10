<template lang="pug">
.d-inline-flex.align-center.ga-1(role="group" :aria-label="t('common.quantity')")
  v-btn(
    icon="mdi-minus"
    size="small"
    variant="tonal"
    :disabled="disabled || modelValue <= min"
    :aria-label="decreaseLabel"
    @click="step(-1)"
  )
  v-text-field.mura-quantity__field(
    :model-value="displayValue"
    :disabled="disabled"
    :aria-label="t('common.quantity')"
    type="text"
    inputmode="decimal"
    density="compact"
    variant="outlined"
    hide-details
    @update:model-value="onTyped"
    @blur="commit"
  )
  v-btn(
    icon="mdi-plus"
    size="small"
    variant="tonal"
    :disabled="disabled || (max !== undefined && modelValue >= max)"
    :aria-label="increaseLabel"
    @click="step(1)"
  )
</template>

<script setup lang="ts">
/**
 * Quantity stepper that respects a unit's step and precision.
 *
 * A product sold by the piece steps in whole units; one sold by the kilo steps
 * in 0.1 and keeps three decimals, so `1.350 kg` is expressible (spec §91).
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { normalizeQuantity } from '~/utils/money'

const props = withDefaults(defineProps<{
  modelValue: number
  stepSize?: number
  precision?: number
  min?: number
  max?: number
  disabled?: boolean
  unit?: string
}>(), {
  stepSize: 1,
  precision: 0,
  min: 0,
  max: undefined,
  disabled: false,
  unit: '',
})

const emit = defineEmits<{ 'update:modelValue': [value: number] }>()

const { t } = useI18n()
const draft = ref(format(props.modelValue))

watch(() => props.modelValue, value => (draft.value = format(value)))

const displayValue = computed(() => draft.value)
const increaseLabel = computed(() => `${t('common.add')} ${props.unit}`.trim())
const decreaseLabel = computed(() => `${t('common.remove')} ${props.unit}`.trim())

function format(value: number): string {
  return props.precision > 0 ? value.toFixed(props.precision) : String(Math.round(value))
}

function step(direction: number): void {
  apply(props.modelValue + direction * props.stepSize)
}

function onTyped(value: string): void {
  draft.value = value
}

/** Parse and clamp on blur so typing "1.3" is not fought mid-keystroke. */
function commit(): void {
  const parsed = Number(draft.value.replace(',', '.'))
  apply(Number.isFinite(parsed) ? parsed : props.modelValue)
}

function apply(value: number): void {
  const normalized = normalizeQuantity(value, {
    step: props.stepSize,
    precision: props.precision,
    min: props.min,
    max: props.max,
  })
  draft.value = format(normalized)
  if (normalized !== props.modelValue) emit('update:modelValue', normalized)
}
</script>

<style scoped>
.mura-quantity__field {
  width: 72px;
}

.mura-quantity__field :deep(input) {
  text-align: center;
  font-variant-numeric: tabular-nums;
}
</style>
