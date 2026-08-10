<template lang="pug">
div
  v-progress-linear(v-if="pending" indeterminate color="primary")

  mura-error-state(v-else-if="error" :on-retry="() => refresh()")

  template(v-else-if="home")
    v-carousel.mt-2(
      v-if="home.banners.length"
      height="280"
      hide-delimiter-background
      show-arrows="hover"
      cycle
      interval="6000"
    )
      v-carousel-item(v-for="banner in home.banners" :key="banner.id")
        nuxt-link.d-block.h-100(:to="bannerLink(banner)" :aria-label="banner.title")
          v-img(
            :src="banner.image?.url"
            :alt="banner.image?.alt_text || banner.title"
            height="280"
            cover
            gradient="to top right, rgba(0,0,0,.55), rgba(0,0,0,.05)"
          )
            .d-flex.flex-column.justify-end.fill-height.pa-6
              h2.text-h5.text-white.font-weight-bold {{ banner.title }}
              p.text-body-1.text-white(v-if="banner.subtitle") {{ banner.subtitle }}

    section.mura-container.mura-section(v-if="home.categories.length" aria-labelledby="home-categories")
      .mura-section__title
        h2#home-categories.text-h6 {{ t('nav.categories') }}
      .d-flex.ga-3.overflow-x-auto.pb-2
        v-card.mura-card.flex-shrink-0(
          v-for="category in home.categories"
          :key="category.id"
          :to="`/produtos?category=${category.slug}`"
          width="128"
          flat
        )
          v-img(
            v-if="category.image"
            :src="category.image.url"
            :alt="category.image.alt_text || category.name"
            height="80"
            cover
          )
          .d-flex.align-center.justify-center(v-else style="height:80px")
            v-icon(icon="mdi-tag-outline" color="primary")
          v-card-text.text-center.py-2
            span.text-body-2 {{ category.name }}

    mura-product-rail(
      v-if="home.on_sale.length"
      :title="t('catalog.onSale')"
      :products="home.on_sale"
      to="/produtos?on_sale=true"
    )
    mura-product-rail(
      v-if="home.featured.length"
      :title="t('catalog.featured')"
      :products="home.featured"
      to="/produtos"
    )
    mura-product-rail(
      v-if="home.best_sellers.length"
      :title="t('catalog.bestSellers')"
      :products="home.best_sellers"
      to="/produtos?sort=best_sellers"
    )
    mura-product-rail(
      v-if="home.new_arrivals.length"
      :title="t('catalog.newArrivals')"
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
import type { Banner, StorefrontHome } from '~/types/api'
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

/** Resolve a banner's target to an internal route. */
function bannerLink(banner: Banner): string {
  switch (banner.link_type) {
    case 'CATEGORY':
      return `/produtos?category=${banner.link_target}`
    case 'PRODUCT':
      return `/produtos/${banner.link_target}`
    case 'SEARCH':
      return `/produtos?q=${encodeURIComponent(banner.link_target)}`
    case 'EXTERNAL':
      return banner.link_target
    default:
      return '/produtos'
  }
}
</script>
