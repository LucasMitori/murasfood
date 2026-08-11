// @ts-check
import withNuxt from './.nuxt/eslint.config.mjs'

/**
 * ESLint configuration.
 *
 * Extends the Nuxt preset (Vue + TypeScript rules aware of auto-imports) with
 * the few project rules worth enforcing beyond it.
 */
export default withNuxt({
  files: ['**/*.vue'],
  languageOptions: {
    parserOptions: {
      // Templates are written in Pug. Without this tokenizer the parser sees an
      // empty template and reports every binding as unused code.
      templateTokenizer: { pug: 'vue-eslint-parser-template-tokenizer-pug' },
    },
  },
}, {
  rules: {
    // Every user-visible string goes through i18n, so a stray console message
    // is almost always leftover debugging.
    'no-console': ['warn', { allow: ['warn', 'error'] }],
    'no-debugger': 'error',

    // Explicit `any` hides exactly the mistakes types exist to catch.
    '@typescript-eslint/no-explicit-any': 'warn',

    /*
     * Reading a `const` before its declaration is a runtime `ReferenceError`,
     * not a hoisting quirk. It shipped once already: the checkout page passed a
     * closure to `useAsyncData` that read a `computed` declared below it, and
     * because the handler runs immediately it threw — leaving the delivery
     * options empty and the "Confirm order" button permanently disabled.
     *
     * Functions stay exempt: they hoist, and `<script setup>` reads better with
     * handlers defined after the state they act on.
     */
    'no-use-before-define': 'off',
    '@typescript-eslint/no-use-before-define': ['error', {
      functions: false,
      classes: true,
      variables: true,
      enums: true,
      typedefs: false,
      ignoreTypeReferences: true,
    }],
    '@typescript-eslint/no-unused-vars': ['error', {
      argsIgnorePattern: '^_',
      varsIgnorePattern: '^_',
      caughtErrors: 'none',
    }],

    // Vue conventions.
    'vue/multi-word-component-names': 'off', // pages are single words by design
    'vue/no-v-html': 'error', // untrusted HTML must never be injected
    'vue/component-name-in-template-casing': ['error', 'kebab-case', {
      registeredComponentsOnly: false,
    }],

    // Pug has no closing tags at all, so "require self-closing" has nothing to
    // check and reports every element in the codebase.
    'vue/html-self-closing': 'off',

    // Vuetify's per-cell slots are named `item.<column>`. The rule reads the
    // dot as a directive modifier, which it is not.
    'vue/valid-v-slot': ['error', { allowModifiers: true }],
  },
}).append({
  files: ['tests/**/*.ts'],
  rules: {
    '@typescript-eslint/no-explicit-any': 'off',
  },
})
