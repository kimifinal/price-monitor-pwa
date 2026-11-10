import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ItemCard from '../../src/components/ItemCard.vue'

describe('ItemCard.vue', () => {
  it('renders name, price and target', () => {
    const w = mount(ItemCard, {
      props: { item: { id: '1', name: 'Chiikawa 徽章', price: 100, target: 120 } },
    })
    expect(w.text()).toContain('Chiikawa 徽章')
    expect(w.text()).toContain('$100.00')
    expect(w.text()).toContain('$120.00')
  })

  it('marks the card hot (data-alert=true) when price <= target', () => {
    const w = mount(ItemCard, {
      props: { item: { id: '2', name: 'X', price: 100, target: 100 } },
    })
    expect(w.find('.item-card').attributes('data-alert')).toBe('true')
  })

  it('marks the card normal when price > target', () => {
    const w = mount(ItemCard, {
      props: { item: { id: '3', name: 'Y', price: 200, target: 100 } },
    })
    expect(w.find('.item-card').attributes('data-alert')).toBe('false')
  })

  it('emits remove with the item id when the delete button is clicked', async () => {
    const w = mount(ItemCard, {
      props: { item: { id: 'del-9', name: 'Z', price: 50, target: 100 } },
    })
    await w.find('.remove-btn').trigger('click')
    expect(w.emitted('remove')[0]).toEqual(['del-9'])
  })

  it('renders a product link when url is present', () => {
    const w = mount(ItemCard, {
      props: {
        item: { id: '4', name: 'L', price: 10, target: 100, url: 'https://example.com' },
      },
    })
    expect(w.get('a').attributes('href')).toBe('https://example.com')
  })
})
