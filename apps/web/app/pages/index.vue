<template lang="pug">
div
  v-progress-linear(v-if="pending" indeterminate color="primary")

  mura-error-state(v-else-if="error" :on-retry="() => refresh()")

  template(v-else-if="home")
    mura-hero(v-if="home.banners.length" :banners="home.banners")

    //- Fallback when the merchant has configured no banners yet. Better than a
    //- blank first screen, and it says what to do about it.
    section.mura-hero-empty(v-else)
      .text-center
        h1.text-h3.font-weight-bold.mb-3 {{ tenant.storeName }}
        p.text-h6.text-medium-emphasis.mb-6(v-if="tenant.branding?.tagline") {{ tenant.branding.tagline }}
        v-btn(to="/produtos" color="primary" size="x-large" variant="flat" append-icon="mdi-arrow-right") {{ t('home.browseCatalog') }}

    section.mura-container.mura-section(v-if="home.categories.length" aria-labelledby="home-categories")
      .mura-section__title
        div
          h2#home-categories.text-h5.font-weight-bold {{ t('nav.categories') }}
          p.text-body-2.text-medium-emphasis.mb-0 {{ t('home.categoriesHint') }}

      .mura-category-grid
        nuxt-link.mura-category(
          v-for="category in home.categories"
          :key="category.id"
          :to="`/produtos?category=${category.slug}`"
        )
          .mura-category__art
            v-img(
              v-if="category.image"
              :src="category.image.url"
              :alt="category.image.alt_text || category.name"
              cover
              height="100%"
            )
            .mura-category__fallback(v-else)
              v-icon(icon="mdi-basket-outline" size="28")
          span.mura-category__name {{ category.name }}

    mura-product-rail(
      v-if="home.on_sale.length"
      :title="t('catalog.onSale')"
      :subtitle="t('home.onSaleHint')"
      :products="home.on_sale"
      to="/produtos?on_sale=true"
      highlight
    )

    mura-trust-strip

    mura-product-rail(
      v-if="home.featured.length"
      :title="t('catalog.featured')"
      :subtitle="t('home.featuredHint')"
      :products="home.featured"
      to="/produtos"
    )
    mura-product-rail(
      v-if="home.best_sellers.length"
      :title="t('catalog.bestSellers')"
      :subtitle="t('home.bestSellersHint')"
      :products="home.best_sellers"
      to="/produtos?sort=best_sellers"
    )
    mura-product-rail(
      v-if="home.new_arrivals.length"
      :title="t('catalog.newArrivals')"
      :subtitle="t('home.newArrivalsHint')"
      :products="home.new_arrivals"
      to="/produtos?sort=newest"
    )
</template>

<script setup lang="ts">
/**
 * Storefront home page.
 *
 * One request fills the whole page — banners, categories and every product rail
 * — so a mobile visitor does not pay for a waterfall of round trips.
 */
import { useI18n } from 'vue-i18n'
import type { StorefrontHome } from '~/types/api'
import { useTenantStore } from '~/stores/tenant'

const { t } = useI18n()
const tenant = useTenantStore()

const { data: home, pending, error, refresh } = await useAsyncData<StorefrontHome>(
  'storefront-home',
  () => useNuxtApp().$api.get<StorefrontHome>('/catalog/home/'),
)

useSeoMeta({
  title: () => tenant.storeName,
  description: () => tenant.branding?.tagline || tenant.storeName,
  ogTitle: () => tenant.storeName,
  ogType: 'website',
})
</script>

<style scoped>
.mura-hero-empty {
  display: grid;
  place-items: center;
  min-height: 60svh;
  padding: 4rem 1.5rem;
  background:
    radial-gradient(
      120% 80% at 50% 0%,
      rgba(var(--v-theme-primary), 0.14),
      transparent 70%
    );
}

.mura-category-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(7.5rem, 1fr));
  gap: 1rem;
}

.mura-category {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.625rem;
  padding: 0.75rem 0.5rem;
  border-radius: 14px;
  color: inherit;
  text-decoration: none;
  transition: transform 220ms cubic-bezier(0.16, 1, 0.3, 1), background 220ms ease;
}

.mura-category:hover {
  transform: translateY(-3px);
  background: rgb(var(--v-theme-surface));
}

.mura-category__art {
  width: 4.5rem;
  height: 4.5rem;
  overflow: hidden;
  border: 1px solid rgba(var(--v-border-color), 0.7);
  border-radius: 50%;
  transition: border-color 220ms ease, box-shadow 220ms ease;
}

.mura-category:hover .mura-category__art {
  border-color: rgb(var(--v-theme-primary));
  box-shadow: 0 6px 20px rgba(var(--v-theme-primary), 0.22);
}

.mura-category__fallback {
  display: grid;
  place-items: center;
  height: 100%;
  background: rgb(var(--v-theme-surface-variant));
  color: rgb(var(--v-theme-primary));
}

.mura-category__name {
  font-size: 0.8125rem;
  font-weight: 500;
  text-align: center;
  line-height: 1.25;
}

@media (prefers-reduced-motion: reduce) {
  .mura-category,
  .mura-category__art {
    transition: none;
  }

  .mura-category:hover {
    transform: none;
  }
}
</style>
