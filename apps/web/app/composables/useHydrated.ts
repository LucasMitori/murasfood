import { onMounted, readonly, ref } from 'vue'

/**
 * Whether the client has taken over from the server-rendered markup.
 *
 * Some state is knowable only in the browser — which products the visitor has
 * favourited, what is in their cart — because it is fetched with a token the
 * server never sees. Rendering it during hydration guarantees a mismatch: the
 * server draws an empty heart, the client draws a full one, and Vue reports
 * every element that disagrees.
 *
 * Gating that markup on this flag makes both sides render the neutral state,
 * and the personalised one appears a tick later, once it is actually known.
 */
export function useHydrated() {
  const hydrated = ref(false)

  onMounted(() => {
    hydrated.value = true
  })

  return readonly(hydrated)
}
