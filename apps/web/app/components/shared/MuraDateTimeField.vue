<template lang="pug">
v-text-field(
  :model-value="display"
  :label="label"
  :hint="hint"
  :persistent-hint="Boolean(hint)"
  :rules="rules"
  :error-messages="errorMessages"
  :disabled="disabled"
  :prepend-inner-icon="icon"
  :placeholder="placeholder"
  readonly
  :clearable="clearable"
  @click:clear="clear"
)
  v-menu(
    v-model="open"
    :close-on-content-click="false"
    activator="parent"
    location="bottom start"
    :disabled="disabled || readonly"
  )
    v-card(rounded="lg" elevation="8")
      //- Date and time side by side when the field is both, so a single
        //- opening of the menu is enough to answer "when". Tabs would hide half
        //- the question behind a click.
      .d-flex.flex-wrap
        v-date-picker(
          v-if="mode !== 'time'"
          :model-value="draftDate"
          show-adjacent-months
          hide-header
          @update:model-value="onDate"
        )

        v-divider(v-if="mode === 'datetime'" vertical class="d-none d-sm-block")

        v-time-picker(
          v-if="mode !== 'date'"
          :model-value="draftTime"
          format="24hr"
          hide-header
          scrollable
          @update:model-value="onTime"
        )

      v-divider

      v-card-actions
        v-btn(variant="text" size="small" @click="clear") {{ t('common.clear') }}
        v-spacer
        v-btn(variant="text" size="small" @click="open = false") {{ t('common.cancel') }}
        v-btn(color="primary" variant="flat" size="small" @click="commit") {{ t('common.done') }}
</template>

<script setup lang="ts">
/**
 * A date, a time, or both.
 *
 * These field types existed in the schema but rendered the browser's own
 * `<input type="date">`, `type="time"` and `type="datetime-local"`. Those look
 * nothing like the rest of the form, differ between browsers, and
 * `datetime-local` in particular is awkward enough that scheduling a banner
 * meant fighting it.
 *
 * The value on the wire is unchanged: `YYYY-MM-DD` for a date, `HH:mm` for a
 * time, and a full ISO instant for a datetime.
 *
 * Timezones are the trap here, and one this project has already been caught by:
 * a date-only string parsed as UTC lands on the previous day everywhere west of
 * Greenwich. So a date is composed from local parts and never round-tripped
 * through `toISOString()`, while a datetime — which *is* an instant — is.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ValidationRule } from '~/types/ui'
import { formatDate, formatDateTime } from '~/utils/format'

const props = withDefaults(defineProps<{
  modelValue: unknown
  mode: 'date' | 'time' | 'datetime'
  label?: string
  hint?: string
  placeholder?: string
  rules?: ValidationRule[]
  errorMessages?: string[]
  disabled?: boolean
  readonly?: boolean
  clearable?: boolean
}>(), {
  label: '',
  hint: '',
  placeholder: '',
  rules: () => [],
  errorMessages: () => [],
  disabled: false,
  readonly: false,
  clearable: true,
})

const emit = defineEmits<{ 'update:modelValue': [value: string | null] }>()

const { t, locale } = useI18n()
const open = ref(false)

const raw = computed(() => (props.modelValue == null ? '' : String(props.modelValue)))

const icon = computed(() => (props.mode === 'time' ? 'mdi-clock-outline' : 'mdi-calendar'))

/** Split the stored value into the two halves the pickers work with. */
function parse(value: string): { date: Date | null, time: string } {
  if (!value) return { date: null, time: '' }

  if (props.mode === 'time') {
    return { date: null, time: value.slice(0, 5) }
  }

  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (dateOnly) {
    // Built from parts, in local time — see the note above.
    return {
      date: new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3])),
      time: '',
    }
  }

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return { date: null, time: '' }

  return {
    date: parsed,
    time: `${String(parsed.getHours()).padStart(2, '0')}:${String(parsed.getMinutes()).padStart(2, '0')}`,
  }
}

const draftDate = ref<Date | null>(null)
const draftTime = ref<string>('')

watch(raw, (value) => {
  const parsed = parse(value)
  draftDate.value = parsed.date
  draftTime.value = parsed.time
}, { immediate: true })

const display = computed(() => {
  if (!raw.value) return ''
  if (props.mode === 'time') return raw.value.slice(0, 5)
  if (props.mode === 'date') return formatDate(raw.value, locale.value)
  return formatDateTime(raw.value, locale.value)
})

function onDate(value: unknown): void {
  draftDate.value = value as Date
}

function onTime(value: unknown): void {
  draftTime.value = String(value ?? '')
}

/** Two digits, because `2026-9-3` is not a date the API accepts. */
function pad(value: number): string {
  return String(value).padStart(2, '0')
}

function commit(): void {
  if (props.mode === 'time') {
    emit('update:modelValue', draftTime.value || null)
    open.value = false
    return
  }

  if (!draftDate.value) {
    emit('update:modelValue', null)
    open.value = false
    return
  }

  const date = draftDate.value
  const ymd = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`

  if (props.mode === 'date') {
    emit('update:modelValue', ymd)
    open.value = false
    return
  }

  // A datetime is a real instant, so the local parts are assembled first and
  // converted once — never by formatting a date that was parsed as UTC.
  const [hours = '00', minutes = '00'] = (draftTime.value || '00:00').split(':')
  const instant = new Date(
    date.getFullYear(), date.getMonth(), date.getDate(), Number(hours), Number(minutes), 0, 0,
  )
  emit('update:modelValue', instant.toISOString())
  open.value = false
}

function clear(): void {
  draftDate.value = null
  draftTime.value = ''
  emit('update:modelValue', null)
  open.value = false
}
</script>
