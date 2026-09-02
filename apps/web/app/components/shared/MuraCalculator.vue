<template lang="pug">
mura-dialog(
  :model-value="modelValue"
  :title="t('tools.calculator')"
  icon="mdi-calculator-variant-outline"
  :max-width="360"
  @update:model-value="value => emit('update:modelValue', value)"
)
  .mura-calc(@keydown="onKey")
    output.mura-calc__screen(aria-live="polite")
      span.mura-calc__history {{ history }}
      //- The value shrinks as it lengthens rather than scrolling: a number you
        //- have to scroll to read is not a readout.
      span.mura-calc__value(:style="{ fontSize: valueSize }") {{ display }}

    .mura-calc__grid
      button.mura-calc__key(
        v-for="key in keys"
        :key="key.label"
        :class="`mura-calc__key--${key.tone}`"
        type="button"
        :aria-label="key.aria || key.label"
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

/**
 * What a key *does*. The keyboard produces these too, and a physical key has
 * no appearance to describe — which is why the visual role lives on `CalcKey`
 * below rather than here.
 */
interface KeyAction {
  label: string
  kind: 'digit' | 'operator' | 'equals' | 'clear' | 'sign' | 'percent' | 'dot' | 'back'
}

/** A key on the pad: what it does, plus how it looks. */
interface CalcKey extends KeyAction {
  /** Visual role; the styling is keyed off this rather than off the label. */
  tone: 'digit' | 'operator' | 'equals' | 'clear' | 'muted'
  /** Spoken name where the glyph is not one, e.g. "⌫". */
  aria?: string
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
  { label: 'C', kind: 'clear', tone: 'clear' },
  { label: '⌫', kind: 'back', tone: 'muted', aria: 'Backspace' },
  { label: '%', kind: 'percent', tone: 'muted' },
  { label: '÷', kind: 'operator', tone: 'operator' },
  { label: '7', kind: 'digit', tone: 'digit' },
  { label: '8', kind: 'digit', tone: 'digit' },
  { label: '9', kind: 'digit', tone: 'digit' },
  { label: '×', kind: 'operator', tone: 'operator' },
  { label: '4', kind: 'digit', tone: 'digit' },
  { label: '5', kind: 'digit', tone: 'digit' },
  { label: '6', kind: 'digit', tone: 'digit' },
  { label: '-', kind: 'operator', tone: 'operator' },
  { label: '1', kind: 'digit', tone: 'digit' },
  { label: '2', kind: 'digit', tone: 'digit' },
  { label: '3', kind: 'digit', tone: 'digit' },
  { label: '+', kind: 'operator', tone: 'operator' },
  { label: '±', kind: 'sign', tone: 'muted' },
  { label: '0', kind: 'digit', tone: 'digit' },
  { label: ',', kind: 'dot', tone: 'digit' },
  { label: '=', kind: 'equals', tone: 'equals' },
]

/**
 * Shrink the readout as the number grows.
 *
 * Five sizes rather than a continuous scale, so a digit landing does not nudge
 * every other character sideways by a fraction.
 */
const valueSize = computed(() => {
  const length = display.value.length
  if (length <= 8) return '2.5rem'
  if (length <= 11) return '2rem'
  if (length <= 14) return '1.625rem'
  return '1.375rem'
})

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

function press(key: KeyAction): void {
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
  const map: Record<string, KeyAction | undefined> = {
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
/*
 * The keys are plain buttons rather than `v-btn`.
 *
 * A calculator wants twenty identical, densely packed targets; `v-btn` brings
 * its own min-width, ripple and elevation, and fighting those produces more CSS
 * than starting from a button does. Every colour below is a theme token, so the
 * pad reads the same way in light and dark.
 */
.mura-calc__screen {
  display: flex;
  min-height: 6.25rem;
  flex-direction: column;
  align-items: flex-end;
  justify-content: flex-end;
  padding: 1rem 1.125rem;
  margin-bottom: 1rem;
  border: 1px solid rgba(var(--v-border-color), 0.65);
  border-radius: 16px;
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.mura-calc__history {
  min-height: 1.125rem;
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.8125rem;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.01em;
}

.mura-calc__value {
  max-width: 100%;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  line-height: 1.15;
  /* Long results wrap rather than overflow the panel. */
  overflow-wrap: anywhere;
  transition: font-size 120ms ease;
}

.mura-calc__grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.5rem;
}

.mura-calc__key {
  height: 3.5rem;
  border: 1px solid transparent;
  border-radius: 14px;
  font-size: 1.125rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  transition:
    transform 90ms ease,
    background-color 140ms ease,
    border-color 140ms ease;
}

.mura-calc__key:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

/* Presses read as a press. Kept small — a calculator is used quickly. */
.mura-calc__key:active {
  transform: scale(0.96);
}

@media (prefers-reduced-motion: reduce) {
  .mura-calc__key {
    transition: background-color 140ms ease;
  }

  .mura-calc__key:active {
    transform: none;
  }
}

.mura-calc__key--digit {
  border-color: rgba(var(--v-border-color), 0.6);
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
}

.mura-calc__key--digit:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
}

.mura-calc__key--muted {
  background: rgba(var(--v-theme-on-surface), 0.07);
  color: rgb(var(--v-theme-on-surface-variant));
}

.mura-calc__key--muted:hover {
  background: rgba(var(--v-theme-on-surface), 0.12);
}

.mura-calc__key--operator {
  background: rgba(var(--v-theme-primary), 0.13);
  color: rgb(var(--v-theme-primary));
  font-size: 1.25rem;
}

.mura-calc__key--operator:hover {
  background: rgba(var(--v-theme-primary), 0.2);
}

.mura-calc__key--clear {
  background: rgba(var(--v-theme-error), 0.13);
  color: rgb(var(--v-theme-error));
}

.mura-calc__key--clear:hover {
  background: rgba(var(--v-theme-error), 0.2);
}

.mura-calc__key--equals {
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
  font-size: 1.25rem;
}

.mura-calc__key--equals:hover {
  filter: brightness(1.08);
}
</style>
