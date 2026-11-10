// Minimal in-memory localStorage + Storage for jsdom environments that don't
// expose a real one. Realistic: many teams shim storage in tests.
class MemoryStorage {
  constructor() {
    this.map = new Map()
  }
  get length() {
    return this.map.size
  }
  key(i) {
    return Array.from(this.map.keys())[i] ?? null
  }
  getItem(k) {
    return this.map.has(k) ? this.map.get(k) : null
  }
  setItem(k, v) {
    this.map.set(k, String(v))
  }
  removeItem(k) {
    this.map.delete(k)
  }
  clear() {
    this.map.clear()
  }
}

const store = new MemoryStorage()
Object.defineProperty(globalThis, 'localStorage', {
  value: store,
  writable: true,
  configurable: true,
})
// Some jsdom windows keep their own global; make sure `window.localStorage` too.
if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'localStorage', {
    value: store,
    writable: true,
    configurable: true,
  })
}
