<template lang="pug">
mura-dialog(
  :model-value="modelValue"
  :title="t('tools.calculator')"
  icon="mdi-calculator-variant-outline"
  :max-width="360"
  @update:model-value="value => emit('update:modelValue', value)"
)
  .mura-calc(@keydown="onKey")
    output.mura-calc__screen(:aria-live="'polite'")
      span.mura-calc__history {{ history }}
      span.mura-calc__value {{ display }}

    .mura-calc__grid
      v-btn(
        v-for="key in keys"
        :key="key.label"
        :class="key.wide ? 'mura-calc__key--wide' : ''"
        :color="key.color"
        :variant="key.variant || 'tonal'"
        size="large"
        @click="press(key)"
      ) {{ key.label }}

  template(#actions)
    v-btn(variant="text" prepend-icon="mdi-content-copy" @click="copy") {{ t('tools.copyResult') }}
    v-btn(color="primary" variant="flat" @click="emit('update:modelValue', false)") {{ t('common.close') }}
</template>

<script setup lang="ts">
/**
 * Pocket calculator.
 *
 * Arithmetic runs on integers scaled by 10⁴ rather than on floats, because the
 * thing people reach for a calculator for in a grocery back-office is money,
 * and `0.1 + 0.2` visibly failing in a shop's own tool destroys confidence in
 * every other number on the screen.
 *
 * It deliberately evaluates one operation at a time — no precedence, no
 * parentheses — which is what a physical calculator does and what the layout
 * promises.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUiStore } from '~/stores/ui'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const { t } = useI18n()
const ui = useUiStore()

type Operator = '+' | '-' | '×' | '÷'

interface CalcKey {
  label: string
  kind: 'digit' | 'operator' | 'equals' | 'clear' | 'sign' | 'percent' | 'dot' | 'back'
  color?: string
  variant?: 'flat' | 'tonal' | 'text'
  wide?: boolean
}

/** Four decimal places: enough for unit prices and percentage work. */
const SCALE = 10_000

const current = ref('0')
const stored = ref<number | null>(null)
const operator = ref<Operator | null>(null)
const replace = ref(true)

const display = computed(() => current.value)
const history = computed(() =>
  stored.value === null ? ' ' : `${format(stored.value)} ${operator.value ?? ''}`,
)

const keys: CalcKey[] = [
  { label: 'C', kind: 'clear', color: 'error', variant: 'tonal' },
  { label: '±', kind: 'sign' },
  { label: '%', kind: 'percent' },
  { label: '÷', kind: 'operator', color: 'primary' },
  { label: '7', kind: 'digit' },
  { label: '8', kind: 'digit' },
  { label: '9', kind: 'digit' },
  { label: '×', kind: 'operator', color: 'primary' },
  { label: '4', kind: 'digit' },
  { label: '5', kind: 'digit' },
  { label: '6', kind: 'digit' },
  { label: '-', kind: 'operator', color: 'primary' },
  { label: '1', kind: 'digit' },
  { label: '2', kind: 'digit' },
  { label: '3', kind: 'digit' },
  { label: '+', kind: 'operator', color: 'primary' },
  { label: '0', kind: 'digit', wide: true },
  { label: ',', kind: 'dot' },
  { label: '=', kind: 'equals', color: 'primary', variant: 'flat' },
]

/** Parse the display into scaled integer units. */
function toUnits(text: string): number {
  const normalised = text.replace(',', '.')
  const value = Number(normalised)
  return Number.isFinite(value) ? Math.round(value * SCALE) : 0
}

function format(units: number): string {
  const text = (units / SCALE).toFixed(4).replace(/\.?0+$/, '')
  return (text || '0').replace('.', ',')
}

function apply(a: number, b: number, op: Operator): number | null {
  switch (op) {
    case '+': return a + b
    case '-': return a - b
    // Both operands are scaled, so a product carries the scale twice.
    case '×': return Math.round((a * b) / SCALE)
    case '÷': return b === 0 ? null : Math.round((a * SCALE) / b)
  }
}

function press(key: CalcKey): void {
  switch (key.kind) {
    case 'digit':
      current.value = replace.value ? key.label : (current.value + key.label).slice(0, 14)
      replace.value = false
      break

    case 'dot':
      if (replace.value) {
        current.value = '0,'
        replace.value = false
      }
      else if (!current.value.includes(',')) {
        current.value += ','
      }
      break

    case 'operator':
      resolve()
      operator.value = key.label as Operator
      stored.value = toUnits(current.value)
      replace.value = true
      break

    case 'equals':
      resolve()
      operator.value = null
      stored.value = null
      replace.value = true
      break

    case 'clear':
      current.value = '0'
      stored.value = null
      operator.value = null
      replace.value = true
      break

    case 'sign':
      current.value = current.value.startsWith('-')
        ? current.value.slice(1)
        : `-${current.value}`
      break

    case 'percent':
      current.value = format(Math.round(toUnits(current.value) / 100))
      break

    case 'back':
      current.value = current.value.length > 1 ? current.value.slice(0, -1) : '0'
      if (current.value === '0') replace.value = true
      break
  }
}

function resolve(): void {
  if (stored.value === null || operator.value === null) return

  const result = apply(stored.value, toUnits(current.value), operator.value)
  if (result === null) {
    current.value = t('tools.cannotDivide')
    replace.value = true
    return
  }

  current.value = format(result)
  replace.value = true
}

/** Physical keyboards are how anyone actually uses a calculator. */
function onKey(event: KeyboardEvent): void {
  const map: Record<string, CalcKey | undefined> = {
    '/': { label: '÷', kind: 'operator' },
    '*': { label: '×', kind: 'operator' },
    '+': { label: '+', kind: 'operator' },
    '-': { label: '-', kind: 'operator' },
    '=': { label: '=', kind: 'equals' },
    'Enter': { label: '=', kind: 'equals' },
    'Escape': { label: 'C', kind: 'clear' },
    'Backspace': { label: '⌫', kind: 'back' },
    ',': { label: ',', kind: 'dot' },
    '.': { label: ',', kind: 'dot' },
    '%': { label: '%', kind: 'percent' },
  }

  if (/^\d$/.test(event.key)) {
    event.preventDefault()
    press({ label: event.key, kind: 'digit' })
    return
  }

  const key = map[event.key]
  if (key) {
    event.preventDefault()
    press(key)
  }
}

async function copy(): Promise<void> {
  try {
    await navigator.clipboard.writeText(current.value)
    ui.success(t('tools.copied'))
  }
  catch {
    // Clipboard access can be refused; the number is on screen either way.
    ui.error(t('errors.generic'))
  }
}

// Referenced so the dialog re-reads `modelValue` reactively in the template.
void props
</script>

<style scoped>
.mura-calc__screen {
  display: flex;
  min-height: 5rem;
  flex-direction: column;
  align-items: flex-end;
  justify-content: center;
  padding: 0.75rem 1rem;
  margin-bottom: 0.75rem;
  border-radius: 12px;
  background: rgb(var(--v-theme-surface-variant));
}

.mura-calc__history {
  min-height: 1rem;
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.8125rem;
}

.mura-calc__value {
  overflow-x: auto;
  max-width: 100%;
  font-size: 2rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

.mura-calc__grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.5rem;
}

.mura-calc__key--wide {
  grid-column: span 2;
}
</style>
