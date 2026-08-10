<template lang="pug">
mura-auth-panel(initial="signup")
</template>

<script setup lang="ts">
/**
 * Register.
 *
 * The same panel as `/auth/login`, opened on its back face. Flipping between
 * them does not navigate — it rotates in place and rewrites the URL — so this
 * route exists for people arriving at it directly or from a link.
 */
import { useI18n } from 'vue-i18n'

definePageMeta({ layout: 'default' })

const { t } = useI18n()

useSeoMeta({ title: () => t('auth.signUp'), robots: 'noindex' })
</script>
