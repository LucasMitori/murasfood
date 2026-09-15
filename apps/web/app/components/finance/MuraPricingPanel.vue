<template lang="pug">
mura-card(:title="t('finance.simulationTitle')" :subtitle="t('finance.simulationHint')" icon="mdi-tag-arrow-up-outline")
  v-row.align-end
    v-col(cols="12" sm="4")
      v-text-field(
        v-model="changePercentage"
        :label="t('finance.changePercentage')"
        type="number"
        step="0.5"
        min="-90"
        max="200"
        density="comfortable"
        variant="outlined"
        suffix="%"
        hide-details
      )

    v-col(cols="12" sm="4")
      v-text-field(
        v-model="elasticity"
        :label="t('finance.elasticity')"
        :hint="t('finance.elasticityHint')"
        type="number"
        step="0.1"
        max="0"
        min="-10"
        density="comfortable"
        variant="outlined"
        persistent-hint
      )

    v-col(cols="12" sm="4")
      v-btn(
        color="primary"
        variant="flat"
        size="large"
        block
        :loading="running"
        prepend-icon="mdi-play"
        @click="run"
      ) {{ t('finance.simulate') }}

  //- The slider is the point of the screen: a merchant explores by dragging,
    //- not by typing numbers into a box.
  v-slider.mt-6.mb-2(
    v-model.number="changePercentage"
    :min="-30"
    :max="30"
    :step="0.5"
    :ticks="sliderTicks"
    show-ticks="always"
    tick-size="3"
    color="primary"
    :aria-label="t('finance.changePercentage')"
    @end="run"
  )
    template(#append)
      strong.mura-pricing__value {{ Number(changePercentage) > 0 ? '+' : '' }}{{ changePercentage }}%

  v-divider.my-4

  mura-empty-state(
    v-if="result && !result.has_data"
    :title="t('finance.simulationEmpty')"
    icon="mdi-cart-off"
  )

  template(v-else-if="result")
    v-row
      v-col(cols="12" md="6")
        .mura-pricing__block
          h4.text-subtitle-2.mb-3 {{ t('finance.current') }}
          .mura-pricing__row
            span {{ t('admin.revenue') }}
            strong {{ money.format(result.current.revenue) }}
          .mura-pricing__row
            span {{ t('finance.margin') }}
            strong {{ money.format(result.current.margin) }} ({{ result.current.margin_percentage }}%)
          .mura-pricing__row
            span {{ t('finance.units') }}
            strong {{ result.current.units }}

      v-col(cols="12" md="6")
        .mura-pricing__block.mura-pricing__block--projected
          h4.text-subtitle-2.mb-3 {{ t('finance.projected') }}
          .mura-pricing__row
            span {{ t('admin.revenue') }}
            strong {{ money.format(result.projected.revenue) }}
          .mura-pricing__row
            span {{ t('finance.margin') }}
            strong {{ money.format(result.projected.margin) }} ({{ result.projected.margin_percentage }}%)
          .mura-pricing__row
            span {{ t('finance.units') }}
            strong {{ result.projected.units }}

    //- The single number the whole screen exists to produce.
    v-alert.mt-4(
      :type="Number(result.delta.margin) >= 0 ? 'success' : 'warning'"
      variant="tonal"
      :icon="Number(result.delta.margin) >= 0 ? 'mdi-trending-up' : 'mdi-trending-down'"
    )
      strong {{ Number(result.delta.margin) > 0 ? '+' : '' }}{{ money.format(result.delta.margin) }}
      |  {{ t('finance.margin').toLowerCase() }} ·
      |  {{ Number(result.delta.revenue) > 0 ? '+' : '' }}{{ money.format(result.delta.revenue) }} {{ t('admin.revenue').toLowerCase() }}

    p.text-caption.text-medium-emphasis.mt-3.mb-0 {{ result.assumptions.explanation }}
</template>

<script setup lang="ts">
/**
 * "What happens if I put prices up?"
 *
 * The most consequential question on this screen and the easiest one to answer
 * dishonestly. What it does is narrow and defensible: take the sales that
 * actually happened in the period, recompute them at the new price, and shrink
 * the volume by the elasticity the merchant chose.
 *
 * What it is *not* is a forecast. Nobody knows how a shop's customers will
 * react to a 5% rise; the elasticity is a stated assumption, it is editable,
 * and it is echoed back in the result so the number on screen always carries
 * the guess it rests on. Every label here says "projected", never "expected".
 *
 * The reason it is worth having anyway: the interesting result is usually
 * counter-intuitive. Raising prices 8% while losing 6% of volume barely moves
 * revenue — and lifts margin by a tenth, because the units you no longer sell
 * are units you no longer buy. That is very hard to see without doing the
 * arithmetic, and very easy to see here.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useApiError } from '~/composables/useApiError'
import { useMoney } from '~/composables/useMoney'

interface Simulation {
  has_data: boolean
  assumptions: {
    change_percentage: string
    elasticity: string
    volume_factor: string
    explanation: string
  }
  current: { revenue: string, cost: string, margin: string, margin_percentage: string, units: string }
  projected: { revenue: string, cost: string, margin: string, margin_percentage: string, units: string }
  delta: { revenue: string, margin: string, margin_change_percentage: string | null }
}

const { t } = useI18n()
const money = useMoney()
const { notify } = useApiError()

const changePercentage = ref<number | string>(5)
const elasticity = ref<number | string>(-0.8)
const running = ref(false)
const result = ref<Simulation | null>(null)

const sliderTicks = computed(() => ({ '-30': '-30%', '-15': '', 0: '0', 15: '', 30: '+30%' }))

async function run(): Promise<void> {
  running.value = true
  try {
    result.value = await useNuxtApp().$api.post<Simulation>(
      '/admin/finance/price-simulation/',
      {
        change_percentage: String(changePercentage.value),
        elasticity: String(elasticity.value),
      },
      // A year of sales, because a market's mix varies by season and a single
      // month would let one good fortnight decide a pricing policy.
      { query: { period: 'custom', start: yearAgo(), end: today() } },
    )
  }
  catch (error) {
    notify(error)
  }
  finally {
    running.value = false
  }
}

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

function yearAgo(): string {
  const date = new Date()
  date.setFullYear(date.getFullYear() - 1)
  return date.toISOString().slice(0, 10)
}

// One result on screen when the tab opens, so the panel is never an empty form.
await run()
</script>

<style scoped>
.mura-pricing__value {
  min-width: 64px;
  text-align: end;
}

.mura-pricing__block {
  height: 100%;
  padding: 16px;
  border: 1px solid rgba(var(--v-border-color), 0.6);
  border-radius: var(--mura-radius-md, 10px);
}

/* The side the merchant is reasoning about, lifted out of the comparison. */
.mura-pricing__block--projected {
  border-color: rgba(var(--v-theme-primary), 0.5);
  background: rgba(var(--v-theme-primary), 0.04);
}

.mura-pricing__row {
  display: flex;
  justify-content: space-between;
  padding-block: 6px;
  gap: 1rem;
}

.mura-pricing__row + .mura-pricing__row {
  border-top: 1px solid rgba(var(--v-border-color), 0.4);
}

.mura-pricing__row span {
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.875rem;
}
</style>
