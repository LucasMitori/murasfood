<template lang="pug">
v-footer.mura-footer(color="surface")
  .mura-footer__top
    .mura-container
      v-row
        //- Identity and social
        v-col(cols="12" md="4")
          .d-flex.align-center.ga-2.mb-3
            v-avatar(color="primary" size="34" rounded="lg")
              v-icon(icon="mdi-storefront-outline" size="20")
            span.text-h6.font-weight-bold {{ tenant.storeName }}

          p.text-body-2.text-medium-emphasis.mb-4(v-if="branding?.tagline") {{ branding.tagline }}

          .d-flex.ga-1
            v-btn(
              v-for="social in socials"
              :key="social.icon"
              :href="social.url"
              :icon="social.icon"
              :aria-label="social.label"
              variant="tonal"
              size="small"
              target="_blank"
              rel="noopener noreferrer"
            )

        //- Link columns
        v-col(v-for="column in columns" :key="column.title" cols="6" sm="4" md="2")
          h4.mura-footer__heading {{ column.title }}
          ul.mura-footer__list
            li(v-for="link in column.links" :key="link.label")
              nuxt-link.mura-footer__link(v-if="link.to" :to="link.to") {{ link.label }}
              a.mura-footer__link(
                v-else-if="link.href"
                :href="link.href"
                target="_blank"
                rel="noopener noreferrer"
              ) {{ link.label }}

        //- Contact
        v-col(cols="12" sm="4" md="2")
          h4.mura-footer__heading {{ t('store.contact') }}
          ul.mura-footer__list
            li(v-if="address")
              span.mura-footer__contact
                v-icon.mr-2(icon="mdi-map-marker-outline" size="16")
                span {{ address }}
            li(v-if="tenant.tenant?.phone")
              a.mura-footer__link(:href="`tel:${tenant.tenant.phone}`")
                v-icon.mr-2(icon="mdi-phone-outline" size="16")
                span {{ formatPhone(tenant.tenant.phone) }}
            li(v-if="tenant.tenant?.support_email")
              a.mura-footer__link(:href="`mailto:${tenant.tenant.support_email}`")
                v-icon.mr-2(icon="mdi-email-outline" size="16")
                span {{ tenant.tenant.support_email }}

  //- Payment and delivery reassurance, immediately above the legal line where
  //- a hesitant shopper looks last.
  .mura-footer__strip
    .mura-container.d-flex.flex-wrap.align-center.justify-space-between.ga-3
      .d-flex.align-center.ga-2
        v-icon(icon="mdi-shield-lock-outline" size="18" color="primary")
        span.text-caption.text-medium-emphasis {{ t('footer.securePayments') }}
      .d-flex.align-center.ga-4
        .d-flex.align-center.ga-1
          v-icon(icon="mdi-qrcode" size="18")
          span.text-caption PIX
        .d-flex.align-center.ga-1
          v-icon(icon="mdi-cash" size="18")
          span.text-caption {{ t('footer.cashOnDelivery') }}

  v-divider

  .mura-container.py-4
    .d-flex.flex-wrap.justify-space-between.ga-2
      span.text-caption.text-medium-emphasis © {{ year }} {{ tenant.storeName }}. {{ t('footer.rights') }}
      span.text-caption.text-medium-emphasis {{ t('footer.poweredBy') }}
</template>

<script setup lang="ts">
/**
 * Storefront footer.
 *
 * Contact details, legal links and social profiles all come from the tenant
 * record; nothing here is hard-coded to a particular merchant. Legal links
 * only appear once the merchant has supplied a URL — an empty "Privacy policy"
 * link is worse than none.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTenantStore } from '~/stores/tenant'
import { formatPhone } from '~/utils/format'

const { t } = useI18n()
const tenant = useTenantStore()

const branding = computed(() => tenant.branding)
const settings = computed(() => tenant.tenant?.settings)
const year = new Date().getFullYear()

const whatsappUrl = computed(() => {
  const number = tenant.tenant?.whatsapp?.replace(/\D/g, '')
  return number ? `https://wa.me/${number}` : ''
})

const socials = computed(() =>
  [
    { icon: 'mdi-instagram', url: branding.value?.instagram_url, label: 'Instagram' },
    { icon: 'mdi-facebook', url: branding.value?.facebook_url, label: 'Facebook' },
    { icon: 'mdi-whatsapp', url: whatsappUrl.value, label: 'WhatsApp' },
  ].filter((social): social is { icon: string, url: string, label: string } => Boolean(social.url)),
)

const columns = computed(() => [
  {
    title: t('footer.shop'),
    links: [
      { label: t('nav.catalog'), to: '/products' },
      { label: t('nav.offers'), to: '/products?on_sale=true' },
      { label: t('nav.favorites'), to: '/favorites' },
      { label: t('lists.title'), to: '/account/lists' },
    ],
  },
  {
    title: t('footer.help'),
    links: [
      { label: t('footer.faq'), to: '/faq' },
      { label: t('footer.contactUs'), to: '/contact' },
      { label: t('nav.orders'), to: '/account/orders' },
      { label: t('footer.deliveryInfo'), to: '/faq#entrega' },
    ],
  },
  {
    title: t('footer.legal'),
    links: [
      ...(settings.value?.privacy_policy_url
        ? [{ label: t('footer.privacyPolicy'), href: settings.value.privacy_policy_url }]
        : []),
      ...(settings.value?.terms_url
        ? [{ label: t('footer.terms'), href: settings.value.terms_url }]
        : []),
      { label: t('footer.exchanges'), to: '/faq#trocas' },
    ],
  },
])

const address = computed(() => {
  const parts = tenant.tenant?.address
  if (!parts) return ''
  return [parts.street, parts.number, parts.neighborhood, parts.city, parts.state]
    .filter(Boolean)
    .join(', ')
})
</script>

<style scoped>
.mura-footer {
  display: block;
  padding: 0;
  border-top: 1px solid rgba(var(--v-border-color), 0.7);
}

.mura-footer__top {
  padding: 3rem 0 2rem;
}

.mura-footer__heading {
  margin-bottom: 0.75rem;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.mura-footer__list {
  padding: 0;
  margin: 0;
  list-style: none;
}

.mura-footer__list li + li {
  margin-top: 0.5rem;
}

.mura-footer__link,
.mura-footer__contact {
  display: inline-flex;
  align-items: center;
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.8125rem;
  line-height: 1.4;
  text-decoration: none;
  transition: color 180ms ease;
}

.mura-footer__link:hover {
  color: rgb(var(--v-theme-primary));
}

.mura-footer__strip {
  padding: 0.875rem 0;
  border-top: 1px solid rgba(var(--v-border-color), 0.7);
  background: rgba(var(--v-theme-primary), 0.04);
}

@media (prefers-reduced-motion: reduce) {
  .mura-footer__link { transition: none; }
}
</style>
