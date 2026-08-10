/**
 * Schema types for the dynamic builders.
 *
 * `MuraFormBuilder` and `MuraDataTable` are driven by plain objects rather than
 * bespoke markup, so a new admin screen is a schema plus an endpoint. These
 * types are what make that schema checkable at compile time instead of failing
 * at render.
 */
import type { Component } from 'vue'

// =============================================================================
// Forms
// =============================================================================

/** Every input kind the form builder knows how to render. */
export type FormFieldType =
  | 'text'
  | 'email'
  | 'password'
  | 'tel'
  | 'url'
  | 'number'
  | 'money'
  | 'quantity'
  | 'percent'
  | 'textarea'
  | 'select'
  | 'autocomplete'
  | 'combobox'
  | 'checkbox'
  | 'switch'
  | 'radio'
  | 'date'
  | 'time'
  | 'datetime'
  | 'file'
  | 'image'
  | 'color'
  | 'slug'
  | 'divider'
  | 'heading'
  | 'custom'

/** A single validation rule. Returns `true` when valid, or a message. */
export type ValidationRule = (value: unknown) => true | string

/** Option for a select-style field. */
export interface FormFieldOption {
  value: string | number | boolean | null
  label: string
  disabled?: boolean
  /** Free-form payload a custom item slot can use. */
  meta?: Record<string, unknown>
}

/** Values of the whole form, keyed by field name. */
export type FormValues = Record<string, unknown>

export interface FormField {
  /** Key in the form's value object. Also the API field name for error mapping. */
  name: string
  type: FormFieldType

  /**
   * i18n key for the label. Resolved with `t()`, so no copy lives in a schema.
   * A literal string is accepted for fields whose label is data (a tenant's own
   * custom attribute, say).
   */
  label?: string
  placeholder?: string
  hint?: string
  /** Longer explanation rendered under the field. */
  description?: string

  /** Grid width out of 12 at each breakpoint. Defaults to full width. */
  cols?: number
  sm?: number
  md?: number
  lg?: number

  required?: boolean
  disabled?: boolean | ((values: FormValues) => boolean)
  readonly?: boolean
  clearable?: boolean
  autofocus?: boolean
  autocomplete?: string

  /** Initial value when the form has no data for this field. */
  default?: unknown

  /** Options for select/autocomplete/radio, static or derived from values. */
  options?: FormFieldOption[] | ((values: FormValues) => FormFieldOption[])
  multiple?: boolean

  /** Numeric bounds; also used to derive validation rules. */
  min?: number
  max?: number
  step?: number
  /** Decimal places for money/quantity/percent fields. */
  precision?: number
  maxLength?: number
  rows?: number

  /** Extra rules on top of the ones derived from the field definition. */
  rules?: ValidationRule[]

  /**
   * Render only when this predicate passes.
   *
   * Hidden fields are also excluded from validation and from the submitted
   * payload — a rule on an invisible field is a form that cannot be submitted
   * for reasons the user cannot see.
   */
  visibleWhen?: (values: FormValues) => boolean

  /** Component to render for `type: 'custom'`. Receives modelValue + field. */
  component?: Component

  /** Passed straight through to the underlying Vuetify component. */
  props?: Record<string, unknown>

  /** Accepted MIME types for file/image fields. */
  accept?: string
  /** Upload folder for image fields, matching the API's `AssetFolder`. */
  folder?: string

  /** For `slug`: the field to derive the slug from while it is untouched. */
  slugSource?: string
}

/** A titled group of fields, rendered as one card. */
export interface FormSection {
  /** i18n key for the section heading. */
  title?: string
  description?: string
  icon?: string
  fields: FormField[]
  visibleWhen?: (values: FormValues) => boolean
}

/** A complete form definition. */
export interface FormSchema {
  sections: FormSection[]
  /** i18n key for the submit button. */
  submitLabel?: string
  cancelLabel?: string
}

// =============================================================================
// Tables
// =============================================================================

/** Sort direction as Vuetify reports it. */
export type SortOrder = 'asc' | 'desc'

export interface SortItem {
  key: string
  order?: SortOrder | boolean
}

/** Options object emitted by `v-data-table-server`. */
export interface DataTableOptions {
  page: number
  itemsPerPage: number
  sortBy: SortItem[]
  groupBy?: SortItem[]
  search?: string
}

export interface TableColumn<T = Record<string, unknown>> {
  /** Property path on the row, and the slot name for custom cells. */
  key: string
  /** i18n key for the header. */
  title: string

  /**
   * Whether the column can be sorted, and by which API field.
   *
   * `true` sorts by `key`; a string sorts by that API field instead — needed
   * whenever the display key differs from what the backend orders on.
   */
  sortable?: boolean | string

  align?: 'start' | 'center' | 'end'
  width?: number | string
  nowrap?: boolean

  /** Render as currency, quantity, date… instead of a raw value. */
  format?: 'text' | 'money' | 'quantity' | 'number' | 'percent' | 'date' | 'datetime' | 'boolean' | 'status'

  /** Derive the displayed value. Takes precedence over `format`. */
  value?: (row: T) => unknown

  /** Hide below this breakpoint so a phone shows only what matters. */
  hideBelow?: 'sm' | 'md' | 'lg'
}

export interface TableAction<T = Record<string, unknown>> {
  /** Stable identifier, emitted with the action event. */
  key: string
  /** i18n key for the label / tooltip. */
  label: string
  icon: string
  color?: string
  /** Permission code required; the action is hidden without it. */
  permission?: string
  /** Hide for rows where this returns false. */
  visibleWhen?: (row: T) => boolean
  /** Ask for confirmation first; the value is an i18n key for the question. */
  confirm?: string
}
