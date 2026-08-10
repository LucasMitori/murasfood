/**
 * Currency and quantity formatting bound to the active tenant and locale.
 *
 * Components should never call `Intl` directly: currency and locale are
 * per-tenant settings, and hard-coding "R$" is exactly the kind of assumption a
 * white-label product cannot make.
 */
import { useI18n } from 'vue-i18n'
import { useTenantStore } from '~/stores/tenant'
import { amountToFreeDelivery, discountPercentage, formatCurrency, formatQuantity } from '~/utils/money'

export function useMoney() {
  const tenant = useTenantStore()
  const { locale } = useI18n()

  const currency = computed(() => tenant.currency)
  const activeLocale = computed(() => locale.value || tenant.locale)

  return {
    currency,

    /** Format an API amount for display. */
    format: (value: string | number | null | undefined): string =>
      formatCurrency(value, currency.value, activeLocale.value),

    /** Format a quantity with its unit code. */
    quantity: (value: string | number, unitCode = ''): string =>
      formatQuantity(value, unitCode, activeLocale.value),

    /** Whole-number discount percentage, for the "-20%" badge. */
    discountPercent: discountPercentage,

    /** How much more is needed for free delivery, already formatted. */
    remainingForFreeDelivery: (subtotal: string | number): string | null => {
      const missing = amountToFreeDelivery(subtotal, tenant.delivery?.free_delivery_threshold)
      return missing ? formatCurrency(missing, currency.value, activeLocale.value) : null
    },
  }
}
