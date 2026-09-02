<template lang="pug">
.mura-fab(
  ref="rootRef"
  :class="{ 'mura-fab--open': open, 'mura-fab--dragging': dragging }"
  :style="rootStyle"
)
  //- Sub-actions, laid out on an arc around the trigger. `inert` while closed
  //- so a collapsed menu is not in the tab order.
  ul.mura-fab__ring(:inert="!open" :aria-hidden="!open")
    li.mura-fab__slot(
      v-for="(action, index) in actions"
      :key="action.key"
      :style="slotStyle(index)"
    )
      v-tooltip(:text="action.label" :location="tooltipSide")
        template(#activator="{ props: tip }")
          v-btn(
            v-bind="tip"
            :icon="action.icon"
            :color="action.color || 'surface-bright'"
            :aria-label="action.label"
            size="small"
            elevation="4"
            @click="run(action)"
          )

  v-btn.mura-fab__trigger(
    :icon="open ? 'mdi-close' : 'mdi-apps'"
    :aria-label="open ? t('tools.close') : t('tools.open')"
    :aria-expanded="open"
    aria-haspopup="true"
    color="primary"
    size="large"
    elevation="8"
    @pointerdown="onPointerDown"
    @click="onTriggerClick"
    @keydown.esc="open = false"
  )

  mura-calculator(v-model="calculatorOpen")
</template>

<script setup lang="ts">
/**
 * Floating tool launcher.
 *
 * A draggable trigger that fans its actions out on an arc. Two details carry
 * most of the behaviour:
 *
 * **Drag versus tap.** The same pointer gesture has to serve both, so a press
 * only becomes a drag once it travels past a threshold. Below that it is a tap
 * and opens the menu — otherwise every attempt to open it would nudge it.
 *
 * **The arc follows the corner.** Fanning up-and-left is only right while the
 * button sits bottom-right. Once it has been dragged the arc is recomputed
 * from the quadrant it now occupies, so the actions always open into the
 * screen rather than off the edge of it.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useCartStore } from '~/stores/cart'
import { useTenantStore } from '~/stores/tenant'
import { useUiStore } from '~/stores/ui'
import { readJson, writeJson } from '~/utils/storage'

interface ToolAction {
  key: string
  icon: string
  label: string
  color?: string
  run: () => void
}

const { t } = useI18n()
const router = useRouter()
const cart = useCartStore()
const tenant = useTenantStore()
const ui = useUiStore()

/** Distance in pixels before a press counts as a drag rather than a tap. */
const DRAG_THRESHOLD = 6
const RADIUS = 92
const EDGE_MARGIN = 16
const POSITION_KEY = 'murasfood.tools_position'

const rootRef = ref<HTMLElement | null>(null)
const open = ref(false)
const dragging = ref(false)
const calculatorOpen = ref(false)
const reducedMotion = ref(false)

/** Distance from the right and bottom edges, so the button survives a resize. */
const position = ref({ right: 24, bottom: 24 })

let pointerId: number | null = null
let start = { x: 0, y: 0, right: 0, bottom: 0 }
let moved = false

const rootStyle = computed(() => ({
  right: `${position.value.right}px`,
  bottom: `${position.value.bottom}px`,
}))

const whatsappUrl = computed(() => {
  const number = tenant.tenant?.whatsapp?.replace(/\D/g, '')
  return number ? `https://wa.me/${number}` : ''
})

const actions = computed<ToolAction[]>(() => {
  const list: ToolAction[] = [
    {
      key: 'calculator',
      icon: 'mdi-calculator-variant-outline',
      label: t('tools.calculator'),
      run: () => { calculatorOpen.value = true },
    },
    {
      key: 'cart',
      icon: 'mdi-cart-outline',
      label: t('nav.cart'),
      run: () => void router.push('/cart'),
    },
    {
      key: 'lists',
      icon: 'mdi-format-list-checks',
      label: t('lists.title'),
      run: () => void router.push('/account/lists'),
    },
    {
      key: 'theme',
      icon: ui.isDark ? 'mdi-white-balance-sunny' : 'mdi-weather-night',
      label: ui.isDark ? t('common.themeLight') : t('common.themeDark'),
      run: () => { ui.toggleTheme() },
    },
    {
      key: 'top',
      icon: 'mdi-arrow-up',
      label: t('tools.backToTop'),
      run: () => window.scrollTo({ top: 0, behavior: reducedMotion.value ? 'auto' : 'smooth' }),
    },
  ]

  // Only offered when the merchant actually published a number.
  if (whatsappUrl.value) {
    list.splice(1, 0, {
      key: 'whatsapp',
      icon: 'mdi-whatsapp',
      label: t('tools.whatsapp'),
      color: 'success',
      run: () => window.open(whatsappUrl.value, '_blank', 'noopener,noreferrer'),
    })
  }

  return list
})

/** Viewport size, tracked so the quadrant can be derived without a DOM read. */
const viewport = ref({ width: 1280, height: 800 })

/**
 * Which quadrant the trigger sits in, which decides where the arc opens.
 *
 * Derived from `position` — the distance already kept from the right and
 * bottom edges — rather than from `getBoundingClientRect()`. Measuring the
 * element looks more direct but is not: the rect is not reactive, and it reads
 * as zero whenever layout has not settled, which silently fanned the actions
 * off the right edge of the screen. The numbers below are the same ones that
 * position the button, so they cannot disagree with it.
 */
const quadrant = computed(() => ({
  left: position.value.right < viewport.value.width / 2,
  up: position.value.bottom < viewport.value.height / 2,
}))

function measureViewport(): void {
  // A zero-sized window is not a real measurement — it happens while a tab is
  // still being laid out, and in embedded contexts. Keeping the last known
  // size beats flipping the arc to the wrong side on a bogus reading.
  const width = window.innerWidth
  const height = window.innerHeight
  if (width > 0 && height > 0) viewport.value = { width, height }
}

const tooltipSide = computed(() => (quadrant.value.left ? 'left' : 'right'))

/**
 * Place one action on the arc.
 *
 * Angles are read in screen terms — 0° points right, 90° up, 180° left, 270°
 * down — which is why `y` is negated below: CSS grows downwards.
 *
 * Each corner gets the quarter turn that sweeps *into* the screen, and the
 * sweep always runs anticlockwise from `start`. Getting this wrong is not
 * subtle: the actions fan out past the edge of the window and cannot be
 * clicked at all.
 */
const ARC_START: Record<string, number> = {
  // Bottom-right: sweep up to left.
  'up-left': 90,
  // Bottom-left: sweep right to up.
  'up-right': 0,
  // Top-right: sweep left to down.
  'down-left': 180,
  // Top-left: sweep down to right.
  'down-right': 270,
}

function slotStyle(index: number): Record<string, string> {
  const { up, left } = quadrant.value
  const count = Math.max(actions.value.length - 1, 1)

  const start = ARC_START[`${up ? 'up' : 'down'}-${left ? 'left' : 'right'}`] ?? 90
  const angle = ((start + (90 / count) * index) * Math.PI) / 180
  const x = Math.cos(angle) * RADIUS
  const y = Math.sin(angle) * RADIUS

  return {
    transform: open.value
      ? `translate(${x.toFixed(1)}px, ${(-y).toFixed(1)}px)`
      : 'translate(0, 0)',
    transitionDelay: open.value && !reducedMotion.value ? `${index * 35}ms` : '0ms',
  }
}

function run(action: ToolAction): void {
  open.value = false
  action.run()
}

function onTriggerClick(): void {
  // A drag ends with a click event too; ignore that one.
  if (moved) {
    moved = false
    return
  }

  open.value = !open.value
}

// --- Dragging --------------------------------------------------------------
function onPointerDown(event: PointerEvent): void {
  pointerId = event.pointerId
  moved = false
  start = {
    x: event.clientX,
    y: event.clientY,
    right: position.value.right,
    bottom: position.value.bottom,
  }

  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  window.addEventListener('pointercancel', onPointerUp)
}

function onPointerMove(event: PointerEvent): void {
  if (event.pointerId !== pointerId) return

  const dx = event.clientX - start.x
  const dy = event.clientY - start.y

  if (!moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return

  if (!moved) {
    moved = true
    dragging.value = true
    // Opening mid-drag would leave the ring chasing the trigger.
    open.value = false
  }

  const size = rootRef.value?.getBoundingClientRect().width ?? 56
  const maxRight = window.innerWidth - size - EDGE_MARGIN
  const maxBottom = window.innerHeight - size - EDGE_MARGIN

  position.value = {
    right: clamp(start.right - dx, EDGE_MARGIN, Math.max(maxRight, EDGE_MARGIN)),
    bottom: clamp(start.bottom - dy, EDGE_MARGIN, Math.max(maxBottom, EDGE_MARGIN)),
  }
}

function onPointerUp(event: PointerEvent): void {
  if (pointerId !== null && event.pointerId !== pointerId) return

  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerUp)

  pointerId = null
  dragging.value = false

  if (moved) writeJson(POSITION_KEY, position.value)
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

function onDocumentPointerDown(event: PointerEvent): void {
  const target = event.target as HTMLElement | null
  if (open.value && !target?.closest('.mura-fab')) open.value = false
}

/** Keep the button on screen when the window shrinks under it. */
function onResize(): void {
  measureViewport()
  const size = rootRef.value?.getBoundingClientRect().width ?? 56
  position.value = {
    right: clamp(position.value.right, EDGE_MARGIN, Math.max(window.innerWidth - size - EDGE_MARGIN, EDGE_MARGIN)),
    bottom: clamp(position.value.bottom, EDGE_MARGIN, Math.max(window.innerHeight - size - EDGE_MARGIN, EDGE_MARGIN)),
  }
}

onMounted(() => {
  reducedMotion.value = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

  const saved = readJson<{ right: number, bottom: number } | null>(POSITION_KEY, null)
  if (saved && Number.isFinite(saved.right) && Number.isFinite(saved.bottom)) {
    position.value = saved
    onResize()
  }

  measureViewport()
  document.addEventListener('pointerdown', onDocumentPointerDown)
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocumentPointerDown)
  window.removeEventListener('resize', onResize)
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerUp)
})

// Referenced so the badge stays reactive if a slot ever shows the cart count.
void cart
</script>

<style scoped>
.mura-fab {
  position: fixed;
  z-index: 1200;
  touch-action: none;
}

.mura-fab--dragging {
  cursor: grabbing;
}

.mura-fab__trigger {
  cursor: grab;
  transition: transform 240ms cubic-bezier(0.16, 1, 0.3, 1);
}

.mura-fab--open .mura-fab__trigger {
  transform: rotate(135deg);
}

.mura-fab--dragging .mura-fab__trigger {
  cursor: grabbing;
  transform: scale(1.08);
}

.mura-fab__ring {
  position: absolute;
  /* Anchored on the trigger's centre so the arc is drawn around it. */
  top: 50%;
  left: 50%;
  padding: 0;
  margin: 0;
  list-style: none;
}

.mura-fab__slot {
  position: absolute;
  top: -20px;
  left: -20px;
  opacity: 0;
  transition:
    transform 320ms cubic-bezier(0.16, 1, 0.3, 1),
    opacity 200ms ease;
  pointer-events: none;
}

.mura-fab--open .mura-fab__slot {
  opacity: 1;
  pointer-events: auto;
}

@media (prefers-reduced-motion: reduce) {
  .mura-fab__trigger,
  .mura-fab__slot {
    transition: none;
  }

  .mura-fab--open .mura-fab__trigger {
    transform: none;
  }
}
</style>
