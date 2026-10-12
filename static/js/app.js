/* ── Dulceras Team — Alpine.js global stores & components ─────────────────── */

document.addEventListener('alpine:init', () => {

  /* ── Cart ──────────────────────────────────────────────────────────────── */
  Alpine.store('cart', {
    items: JSON.parse(localStorage.getItem('dt_cart') || '[]'),

    get count() { return this.items.reduce((n, i) => n + i.quantity, 0) },
    get total() { return this.items.reduce((n, i) => n + i.price * i.quantity, 0) },
    get maxAdvanceHours() { return this.items.reduce((mx, i) => Math.max(mx, i.requiresAdvanceHours || 0), 0) },

    _save() { localStorage.setItem('dt_cart', JSON.stringify(this.items)) },

    add(item) {
      const existing = this.items.find(i => i.variantId === item.variantId)
      if (existing) {
        existing.quantity++
      } else {
        this.items.push({ ...item, quantity: 1 })
      }
      this._save()
    },

    remove(variantId) {
      this.items = this.items.filter(i => i.variantId !== variantId)
      this._save()
    },

    setQty(variantId, qty) {
      if (qty <= 0) { this.remove(variantId); return }
      const item = this.items.find(i => i.variantId === variantId)
      if (item) { item.quantity = qty; this._save() }
    },

    clear() { this.items = []; this._save() },

    fmt(n) { return n.toLocaleString('es-AR') },
  })

  /* ── Dark mode ─────────────────────────────────────────────────────────── */
  Alpine.store('darkMode', {
    enabled: localStorage.getItem('admin_dark') === '1',
    toggle() {
      this.enabled = !this.enabled
      localStorage.setItem('admin_dark', this.enabled ? '1' : '0')
      document.documentElement.classList.toggle('dark', this.enabled)
    },
  })

  /* ── Admin auth ────────────────────────────────────────────────────────── */
  Alpine.store('adminAuth', {
    token:    localStorage.getItem('access_token'),
    refresh:  localStorage.getItem('refresh_token'),
    username: localStorage.getItem('username'),

    // Un token de cliente no da acceso al panel (la API responde 403): se trata como no logueado
    get isLoggedIn() { return !!this.token && this.role !== 'customer' },
    get role() {
      if (!this.token) return null
      try {
        const payload = JSON.parse(atob(this.token.split('.')[1].replace(/-/g,'+').replace(/_/g,'/')))
        return payload.role || null
      } catch { return null }
    },
    get tenantId() {
      if (!this.token) return null
      try {
        const payload = JSON.parse(atob(this.token.split('.')[1].replace(/-/g,'+').replace(/_/g,'/')))
        return payload.tenant_id || null
      } catch { return null }
    },

    login(access, refresh, username) {
      localStorage.setItem('access_token', access)
      localStorage.setItem('refresh_token', refresh)
      localStorage.setItem('username', username)
      this.token   = access
      this.refresh = refresh
      this.username = username
    },

    logout() {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('username')
      this.token = this.refresh = this.username = null
      window.location.href = '/admin/login'
    },

    headers() {
      return { 'Content-Type': 'application/json', 'Authorization': `Bearer ${this.token}` }
    },

    async fetchJSON(url, options = {}) {
      const res = await fetch(url, { ...options, headers: { ...this.headers(), ...(options.headers || {}) } })
      if (res.status === 401) { this.logout(); return }
      return res.json()
    },
  })

  /* ── Customer auth ─────────────────────────────────────────────────────── */
  Alpine.store('customerAuth', {
    token:    localStorage.getItem('customer_access'),
    refresh:  localStorage.getItem('customer_refresh'),
    customer: JSON.parse(localStorage.getItem('customer_profile') || 'null'),

    get isLoggedIn() { return !!this.token && !!this.customer },

    login(tokens, profile) {
      localStorage.setItem('customer_access', tokens.access)
      localStorage.setItem('customer_refresh', tokens.refresh)
      localStorage.setItem('customer_profile', JSON.stringify(profile))
      this.token    = tokens.access
      this.refresh  = tokens.refresh
      this.customer = profile
    },

    logout() {
      localStorage.removeItem('customer_access')
      localStorage.removeItem('customer_refresh')
      localStorage.removeItem('customer_profile')
      this.token = this.refresh = this.customer = null
      window.location.href = '/'
    },

    headers() {
      return { 'Content-Type': 'application/json', 'Authorization': `Bearer ${this.token}` }
    },

    setCustomer(c) {
      localStorage.setItem('customer_profile', JSON.stringify(c))
      this.customer = c
    },
  })

})

/* ── Helpers ────────────────────────────────────────────────────────────────── */
function fmtARS(n) {
  return Number(n).toLocaleString('es-AR')
}

function decodeJWT(token) {
  try {
    return JSON.parse(atob(token.split('.')[1].replace(/-/g,'+').replace(/_/g,'/')))
  } catch { return {} }
}
