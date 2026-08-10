<template lang="pug">
header.mb-6
  v-breadcrumbs.px-0.pb-1(v-if="breadcrumbs.length" :items="breadcrumbItems" density="compact")
    template(#divider)
      v-icon(icon="mdi-chevron-right" size="small")

  .d-flex.flex-wrap.align-center.ga-3
    v-btn(
      v-if="backTo"
      :to="backTo"
      :aria-label="t('common.back')"
      icon="mdi-arrow-left"
      variant="text"
      density="comfortable"
    )

    div.flex-grow-1.min-width-0
      h1.text-h5.mb-0.text-truncate {{ title }}
      p.text-body-2.text-medium-emphasis.mb-0(v-if="subtitle") {{ subtitle }}

    slot(name="actions")
</template>

<script setup lang="ts">
/**
 * Page heading with breadcrumbs, an optional back button and an actions slot.
 *
 * There is exactly one `h1` per page, which is what a screen reader's document
 * outline depends on (spec §57).
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = withDefaults(defineProps<{
  title: string
  subtitle?: string
  backTo?: string
  /** `{ title, to }` pairs; `title` may be an i18n key. */
  breadcrumbs?: Array<{ title: string, to?: string }>
}>(), {
  subtitle: '',
  backTo: undefined,
  breadcrumbs: () => [],
})

const { t, te } = useI18n()

const breadcrumbItems = computed(() =>
  props.breadcrumbs.map(item => ({
    title: te(item.title) ? t(item.title) : item.title,
    to: item.to,
    disabled: !item.to,
  })),
)
</script>

<style scoped>
.min-width-0 {
  min-width: 0;
}
</style>
