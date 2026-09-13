<template lang="pug">
v-text-field(
  :model-value="hex"
  :label="label"
  :hint="hint"
  :persistent-hint="Boolean(hint)"
  :rules="rules"
  :error-messages="errorMessages"
  :disabled="disabled"
  :readonly="readonly"
  placeholder="#8C1425"
  maxlength="7"
  @update:model-value="onType"
)
  //- The swatch *is* the control. A colour written as text is unreadable as a
    //- colour, so the field shows the thing itself and opens the picker from it.
  template(#prepend-inner)
    //- `activator="parent"` makes the swatch open the menu. It must be the
      //- *only* thing that does: a hand-written `@click` here as well toggles
      //- the same menu twice in one click, which opens and immediately closes
      //- it — the field just takes focus and nothing appears.
    .mura-color__swatch(
      :style="{ background: isValid ? hex : 'transparent' }"
      :class="{ 'mura-color__swatch--empty': !isValid }"
      role="button"
      tabindex="0"
      :aria-label="t('form.pickColour')"
    )
      v-menu(
        v-model="open"
        :close-on-content-click="false"
        :disabled="disabled || readonly"
        activator="parent"
        location="bottom start"
      )
        v-card(rounded="lg" elevation="8")
          v-color-picker(
            :model-value="isValid ? hex : '#8C1425'"
            mode="hex"
            :modes="['hex']"
            show-swatches
            :swatches="swatches"
            @update:model-value="onPick"
          )
          v-card-actions
            v-spacer
            v-btn(variant="text" size="small" @click="open = false") {{ t('common.done') }}
</template>

<script setup lang="ts">
/**
 * A colour, chosen as a colour.
 *
 * The form builder has had a `color` field type for as long as it has had a
 * type union, but it rendered a plain text box: the only way to set a brand
 * colour was to know its hex code and type it correctly. This keeps the text
 * box — a hex code is still the quickest input when you have one, and it is
 * what the API stores — and adds the swatch that opens a real picker.
 *
 * Typing and picking write the same value, so neither is second class.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ValidationRule } from '~/types/ui'

const props = withDefaults(defineProps<{
  modelValue: unknown
  label?: string
  hint?: string
  rules?: ValidationRule[]
  errorMessages?: string[]
  disabled?: boolean
  readonly?: boolean
  /** Palette offered above the wheel; the tenant's own colours by default. */
  swatches?: string[][]
}>(), {
  label: '',
  hint: '',
  rules: () => [],
  errorMessages: () => [],
  disabled: false,
  readonly: false,
  swatches: () => [
    ['#8C1425', '#B02233', '#E2495D'],
    ['#211E1F', '#4A4446', '#8A8285'],
    ['#1B5E20', '#2E7D32', '#66BB6A'],
    ['#0D47A1', '#1976D2', '#64B5F6'],
    ['#E65100', '#F57C00', '#FFB74D'],
  ],
})

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const { t } = useI18n()
const open = ref(false)

const hex = computed(() => String(props.modelValue ?? ''))

// The same shape the API validates against, so the swatch never previews a
// value the server would reject.
const isValid = computed(() => /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(hex.value))

function onType(value: string): void {
  // A leading `#` is punctuation, not data the typist should have to remember.
  const next = value?.startsWith('#') || !value ? value : `#${value}`
  emit('update:modelValue', next ?? '')
}

function onPick(value: string): void {
  // The picker can hand back 8 digits (with alpha); the column holds 7.
  emit('update:modelValue', value.slice(0, 7).toUpperCase())
}
</script>

<style scoped>
.mura-color__swatch {
  width: 24px;
  height: 24px;
  margin-right: 8px;
  cursor: pointer;
  border: 1px solid rgba(var(--v-border-color), 0.9);
  border-radius: 6px;
}

.mura-color__swatch--empty {
  /* Reads as "nothing chosen" rather than as the colour white. */
  background-image: linear-gradient(
    45deg,
    rgba(var(--v-theme-on-surface), 0.12) 25%,
    transparent 25%,
    transparent 75%,
    rgba(var(--v-theme-on-surface), 0.12) 75%
  );
  background-size: 8px 8px;
}

.mura-color__swatch:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
</style>
