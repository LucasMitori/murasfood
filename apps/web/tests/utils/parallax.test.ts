import { describe, expect, it } from 'vitest'
import { parallaxShift } from '~/utils/format'

/**
 * The invariant this whole function exists for.
 *
 * A parallax layer is a picture larger than its frame, slid within it. The only
 * way it can look broken is if it slides further than it is large — which is
 * exactly what happened: travel was a fraction of the *scroll distance* while
 * the overscan was a fraction of the *element height*, two unrelated numbers
 * that disagreed by about 4x, leaving a blank strip at one edge for most of the
 * scroll.
 *
 * So the test is not "does it produce a nice number". It is: across every
 * position the element can occupy, at every plausible viewport and element
 * size, is the travel still inside the picture?
 */
describe('parallaxShift', () => {
  const VIEWPORTS = [568, 720, 860, 1080, 1440]
  const HEIGHTS = [200, 504, 602, 720, 1080, 2000]
  const SLACKS = [0, 12, 74, 108.4, 300]

  it('never travels further than there is picture to travel over', () => {
    const breaches: string[] = []

    for (const viewport of VIEWPORTS) {
      for (const height of HEIGHTS) {
        for (const slack of SLACKS) {
          // Every position from fully below the fold to fully above it.
          for (let top = -height - 200; top <= viewport + 200; top += 17) {
            const shift = parallaxShift(top, height, viewport, slack)

            if (Math.abs(shift) > slack + 1e-9) {
              breaches.push(
                `viewport=${viewport} height=${height} slack=${slack} top=${top} → ${shift}`,
              )
            }
          }
        }
      }
    }

    expect(breaches.slice(0, 5), `${breaches.length} position(s) exposed an edge`).toEqual([])
  })

  it('is still at rest when the element is centred', () => {
    // 602-tall band centred in an 860 viewport: top = (860 - 602) / 2 = 129.
    expect(parallaxShift(129, 602, 860, 108)).toBeCloseTo(0, 6)
  })

  it('reaches the full slack only at the extremes', () => {
    const viewport = 860
    const height = 602
    const slack = 108

    // Entering: the band's top edge is at the bottom of the viewport.
    expect(parallaxShift(viewport, height, viewport, slack)).toBeCloseTo(slack, 6)
    // Leaving: the band's bottom edge is at the top of the viewport.
    expect(parallaxShift(-height, height, viewport, slack)).toBeCloseTo(-slack, 6)
  })

  it('clamps rather than running away past the extremes', () => {
    const slack = 108
    // Far below the fold, and far above it.
    expect(parallaxShift(5000, 602, 860, slack)).toBeCloseTo(slack, 6)
    expect(parallaxShift(-5000, 602, 860, slack)).toBeCloseTo(-slack, 6)
  })

  it('moves in the direction that reads as depth', () => {
    // A band still below the viewport's centre should have its image pushed
    // down — lagging behind the page, which is what makes it look further away.
    expect(parallaxShift(700, 602, 860, 108)).toBeGreaterThan(0)
    expect(parallaxShift(-300, 602, 860, 108)).toBeLessThan(0)
  })

  it('does nothing when there is no overscan', () => {
    // A frame with no spare picture must not move at all, rather than moving
    // and showing the background through it.
    expect(parallaxShift(300, 602, 860, 0)).toBe(0)
  })

  it('survives a zero-height viewport without producing NaN', () => {
    // Happens in a hidden tab and during SSR hydration.
    expect(parallaxShift(0, 0, 0, 100)).toBe(0)
    expect(Number.isNaN(parallaxShift(0, 602, 0, 108))).toBe(false)
  })

  it('reproduces the bug it was written to prevent', () => {
    // The old rule, for the record: travel was 0.4 of the distance the band's
    // centre had moved from the viewport's centre, against a 12% overscan.
    const viewport = 860
    const height = 602
    const oldSlack = 0.12 * height // 72.2px of picture to spare
    const oldShift = 0.4 * (viewport + height / 2 - viewport / 2) // ≈ 316px

    expect(oldShift).toBeGreaterThan(oldSlack * 4)

    // The same position under the current rule stays within the picture.
    const now = parallaxShift(viewport, height, viewport, oldSlack)
    expect(Math.abs(now)).toBeLessThanOrEqual(oldSlack)
  })
})
