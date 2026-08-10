/**
 * Client-side permission checks.
 *
 * These must agree with the backend exactly. Where they diverge, a user either
 * sees a link that 403s or is denied a screen they are entitled to — both read
 * as bugs. The hierarchy cases here mirror
 * `apps/api/apps/accounts/tests/test_page_permissions.py`.
 */
import { describe, expect, it } from 'vitest'
import {
  grants,
  isPagePermission,
  permissionAncestors,
} from '../../app/composables/usePermission'

describe('isPagePermission', () => {
  it('recognises the page namespace', () => {
    expect(isPagePermission('perm')).toBe(true)
    expect(isPagePermission('perm.admin')).toBe(true)
    expect(isPagePermission('perm.admin.users')).toBe(true)
  })

  it('rejects capability codes', () => {
    expect(isPagePermission('catalog.view')).toBe(false)
    expect(isPagePermission('orders.refund')).toBe(false)
    // A code that merely starts with the letters is not in the namespace.
    expect(isPagePermission('permissions.view')).toBe(false)
  })
})

describe('permissionAncestors', () => {
  it('runs from specific to general', () => {
    expect(permissionAncestors('perm.admin.users')).toEqual([
      'perm.admin.users',
      'perm.admin',
      'perm',
    ])
  })

  it('gives capability codes no hierarchy', () => {
    expect(permissionAncestors('catalog.view')).toEqual(['catalog.view'])
  })

  it('handles a single-segment page code', () => {
    expect(permissionAncestors('perm')).toEqual(['perm'])
  })
})

describe('grants', () => {
  it('lets a parent grant its children', () => {
    const held = new Set(['perm.admin'])

    expect(grants(held, 'perm.admin')).toBe(true)
    expect(grants(held, 'perm.admin.users')).toBe(true)
    expect(grants(held, 'perm.admin.finance')).toBe(true)
  })

  it('does not let a child grant its parent', () => {
    const held = new Set(['perm.admin.orders'])

    expect(grants(held, 'perm.admin.orders')).toBe(true)
    // Access to one screen is not access to the dashboard at large.
    expect(grants(held, 'perm.admin')).toBe(false)
    expect(grants(held, 'perm.admin.finance')).toBe(false)
  })

  it('keeps the hierarchy out of capability codes', () => {
    const held = new Set(['perm.admin'])

    // A page grant must never imply the ability to act.
    expect(grants(held, 'orders.refund')).toBe(false)
    expect(grants(held, 'catalog.delete')).toBe(false)
  })

  it('matches capability codes exactly', () => {
    const held = new Set(['catalog.view'])

    expect(grants(held, 'catalog.view')).toBe(true)
    expect(grants(held, 'catalog.update')).toBe(false)
  })

  it('denies against an empty set', () => {
    expect(grants(new Set(), 'perm.admin')).toBe(false)
    expect(grants(new Set(), 'catalog.view')).toBe(false)
  })

  it('reflects the staff bundle the backend ships', () => {
    // Staff hold individual pages, never the `perm.admin` parent.
    const staff = new Set([
      'perm.admin.dashboard',
      'perm.admin.orders',
      'perm.admin.products',
      'perm.account',
    ])

    expect(grants(staff, 'perm.admin.orders')).toBe(true)
    expect(grants(staff, 'perm.admin')).toBe(false)
    expect(grants(staff, 'perm.admin.finance')).toBe(false)
    expect(grants(staff, 'perm.admin.users')).toBe(false)
    // The account namespace parent does grant its children.
    expect(grants(staff, 'perm.account.profile')).toBe(true)
  })
})
