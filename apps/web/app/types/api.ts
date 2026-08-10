/**
 * API contract types.
 *
 * Mirrors the DRF serializers. Monetary values are **strings** on the wire —
 * JSON numbers are IEEE-754 doubles in JavaScript, and `0.1 + 0.2` must never
 * become a price. Parse them with the helpers in `~/utils/money`.
 */

// =============================================================================
// Envelope
// =============================================================================
export interface ApiError {
  code: string
  message: string
  details?: Record<string, unknown>
  request_id?: string
}

export interface ApiErrorResponse {
  error: ApiError
}

export interface Paginated<T> {
  count: number
  page: number
  pages: number
  page_size: number
  next: string | null
  previous: string | null
  results: T[]
}

// =============================================================================
// Tenant
// =============================================================================
export interface MediaAsset {
  id: string
  kind: 'IMAGE' | 'DOCUMENT'
  status: 'PENDING' | 'READY' | 'FAILED'
  url: string
  variants: Record<string, string>
  alt_text: string
  width: number | null
  height: number | null
  size_bytes: number
  content_type: string
  original_filename: string
  created_at: string
}

export interface TenantBranding {
  logo: MediaAsset | null
  logo_dark: MediaAsset | null
  favicon: MediaAsset | null
  primary_color: string
  secondary_color: string
  accent_color: string
  dark_primary_color: string
  tagline: string
  about: string
  instagram_url: string
  facebook_url: string
  website_url: string
}

export interface BusinessHours {
  id: string
  weekday: number
  weekday_label: string
  opens_at: string
  closes_at: string
  is_closed: boolean
}

export interface DeliveryConfig {
  delivery_enabled: boolean
  pickup_enabled: boolean
  minimum_order_amount: string
  base_fee: string
  free_delivery_threshold: string | null
  estimated_delivery_minutes: number
  estimated_pickup_minutes: number
  service_radius_km: string
}

export interface Tenant {
  id: string
  slug: string
  trade_name: string
  support_email: string
  phone: string
  whatsapp: string
  timezone: string
  currency: string
  locale: string
  address: Record<string, string | null>
  branding: TenantBranding | null
  business_hours: BusinessHours[]
  settings: {
    prices_include_tax?: boolean
    allow_orders_when_closed?: boolean
    privacy_policy_url?: string
    terms_url?: string
  }
  delivery: DeliveryConfig
  is_open_now?: boolean
}

// =============================================================================
// Accounts
// =============================================================================
export type UserType = 'CUSTOMER' | 'STAFF' | 'MANAGER' | 'ADMINISTRATOR' | 'PLATFORM_ADMIN'

export interface User {
  id: string
  email: string
  first_name: string
  last_name: string
  full_name: string
  phone: string
  user_type: UserType
  is_verified: boolean
  marketing_opt_in: boolean
  roles: string[]
  permissions: string[]
  created_at: string
}

export interface AuthTokens {
  access: string
  refresh: string
  user: User
}

export interface Address {
  id: string
  label: string
  recipient_name: string
  postal_code: string
  street: string
  number: string
  complement: string
  neighborhood: string
  city: string
  state: string
  country: string
  reference: string
  latitude: string | null
  longitude: string | null
  is_default: boolean
  created_at: string
}

// =============================================================================
// Catalog
// =============================================================================
export interface UnitOfMeasure {
  id: string
  code: string
  name: string
  kind: 'UNIT' | 'WEIGHT' | 'VOLUME' | 'LENGTH'
  precision: number
  step: string
}

export interface ProductPriceInfo {
  price: string | null
  base_price: string | null
  is_discounted: boolean
  discount: string | null
}

export interface ProductStockInfo {
  in_stock: boolean
  low_stock: boolean
}

export interface Product {
  id: string
  name: string
  slug: string
  sku: string
  short_description: string
  image: MediaAsset | null
  price: ProductPriceInfo
  stock: ProductStockInfo
  unit: UnitOfMeasure
  unit_quantity: string
  brand_name: string | null
  category_slug: string
  product_type: 'SIMPLE' | 'WEIGHTED' | 'BUNDLE'
  is_featured: boolean
  is_favorite: boolean
}

export interface ProductDetail extends Product {
  description: string
  images: Array<{ id: string, asset: MediaAsset, position: number, is_primary: boolean }>
  tags: Array<{ id: string, name: string, slug: string, color: string }>
  category: { id: string, name: string, slug: string }
  breadcrumb: Array<{ name: string, slug: string }>
  requires_weighing: boolean
  requires_age_check: boolean
  max_quantity_per_order: string | null
}

export interface Category {
  id: string
  name: string
  slug: string
  description: string
  parent: string | null
  image: MediaAsset | null
  position: number
  is_active: boolean
  is_featured: boolean
  children: Array<{ id: string, name: string, slug: string, position: number }>
  product_count: number
}

export interface Banner {
  id: string
  title: string
  subtitle: string
  image: MediaAsset | null
  mobile_image: MediaAsset | null
  link_type: string
  link_target: string
}

export interface StorefrontHome {
  banners: Banner[]
  categories: Category[]
  featured: Product[]
  on_sale: Product[]
  best_sellers: Product[]
  new_arrivals: Product[]
}

// =============================================================================
// Cart
// =============================================================================
export interface CartItem {
  id: string
  product: Product
  quantity: string
  unit_price: string
  base_unit_price: string
  line_total: string
  is_available: boolean
  note: string
}

export interface CartDiscountLine {
  promotion: string
  amount: string
  type: string
  coupon: string | null
}

export interface CartTotals {
  subtotal: string
  discount: string
  delivery_fee: string
  total: string
  item_count: number
  free_delivery: boolean
  discounts: CartDiscountLine[]
  delivery: { method: string, fee?: string, estimated_minutes?: number, error?: string, message?: string } | null
}

export interface CartIssue {
  item_id: string
  product: string
  reason: 'UNAVAILABLE' | 'NO_PRICE' | 'OUT_OF_STOCK'
}

export interface Cart {
  id: string
  token: string
  status: string
  coupon_code: string
  items: CartItem[]
  totals: CartTotals
  issues: CartIssue[]
  updated_at: string
}

// =============================================================================
// Orders and payments
// =============================================================================
export type OrderStatus =
  | 'DRAFT'
  | 'PENDING_PAYMENT'
  | 'PAYMENT_PROCESSING'
  | 'PAID'
  | 'CONFIRMED'
  | 'PREPARING'
  | 'READY_FOR_PICKUP'
  | 'OUT_FOR_DELIVERY'
  | 'DELIVERED'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'PAYMENT_FAILED'
  | 'REFUNDED'
  | 'PARTIALLY_REFUNDED'

export interface OrderItem {
  id: string
  product: string | null
  product_slug: string | null
  product_name: string
  product_sku: string
  unit_code: string
  quantity: string
  unit_price: string
  base_unit_price: string
  discount_amount: string
  line_total: string
  note: string
  image: MediaAsset | null
}

export interface OrderTimelineStep {
  status: OrderStatus
  label_key: string
  completed: boolean
  timestamp: string | null
  reason: string
}

export interface Payment {
  id: string
  method: string
  status: 'PENDING' | 'PROCESSING' | 'PAID' | 'FAILED' | 'EXPIRED' | 'CANCELLED' | 'REFUNDED' | 'PARTIALLY_REFUNDED'
  status_label: string
  amount: string
  currency: string
  pix_payload: string
  pix_qr_code: string
  expires_at: string | null
  paid_at: string | null
  is_expired: boolean
  created_at: string
}

export interface OrderSummary {
  id: string
  number: string
  status: OrderStatus
  status_label: string
  delivery_method: 'PICKUP' | 'DELIVERY'
  total: string
  currency: string
  item_count: number
  placed_at: string | null
  created_at: string
}

export interface Order extends OrderSummary {
  subtotal: string
  discount_total: string
  delivery_fee: string
  tax_total: string
  refunded_total: string
  coupon_code: string
  customer_note: string
  items: OrderItem[]
  address: Record<string, string> | null
  timeline: OrderTimelineStep[]
  payment: Payment | null
  can_cancel: boolean
  scheduled_for: string | null
  estimated_ready_at: string | null
  paid_at: string | null
  completed_at: string | null
}

export interface CheckoutPayload {
  delivery_method: 'PICKUP' | 'DELIVERY'
  address?: string | null
  customer_note?: string
  scheduled_for?: string | null
  payment_method?: string
  contact_name?: string
  contact_email?: string
  contact_phone?: string
}

export interface DeliveryOption {
  method: 'PICKUP' | 'DELIVERY'
  available: boolean
  fee?: string
  is_free?: boolean
  estimated_minutes?: number
  minimum_order_amount?: string
  zone?: string | null
  reason?: string
  message?: string
}

// =============================================================================
// Dashboard
// =============================================================================
export interface DashboardChartPoint {
  date: string | null
  revenue: string
  orders: number
  average_ticket: string
}

export interface DashboardSummary {
  period: { key: string, start: string, end: string, days: number }
  revenue: {
    period: string
    net: string
    today: string
    month: string
    change_percentage: string | null
  }
  orders: {
    count: number
    cancelled: number
    average_ticket: string
    units_sold: string
    change_percentage: string | null
  }
  counters: {
    pending_orders: number
    awaiting_payment: number
    ready_orders: number
    pending_payments: number
  }
  charts: {
    revenue_by_day: DashboardChartPoint[]
    top_products: Array<{ product_id: string | null, name: string, sku: string, units: string, revenue: string, estimated_margin: string }>
    categories: Array<{ category: string, revenue: string, units: string }>
    payment_methods: Array<{ method: string, total: string, count: number }>
  }
  customers: {
    new_customers: number
    active_customers: number
    repeat_customers: number
    repeat_rate: string
  }
  recent_orders: OrderSummary[]
  alerts: {
    low_stock_count: number
    low_stock: Array<{ product: string, sku: string, available: string, threshold: string }>
  }
}
