<template lang="pug">
mura-auth-panel(initial="signin")
</template>

<script setup lang="ts">
/**
 * Sign in.
 *
 * Sign-in and registration are two faces of one card, so both routes render the
 * same panel and differ only in which face is showing. See `MuraAuthPanel`.
 */
import { useI18n } from 'vue-i18n'

definePageMeta({ layout: 'default' })

const { t } = useI18n()

useSeoMeta({ title: () => t('auth.signIn'), robots: 'noindex' })
</script>
