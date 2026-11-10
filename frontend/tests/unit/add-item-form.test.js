import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AddItemForm from '../../src/components/AddItemForm.vue'

describe('AddItemForm.vue', () => {
  it('emits an item with name + numeric target when the form is submitted', async () => {
    const w = mount(AddItemForm)
    // fill the two required inputs by order: name, then target
    await w.find('input').setValue('Chiikawa 徽章')
    await w.findAll('input')[1].setValue('100')
    await w.find('form').trigger('submit')

    const emitted = w.emitted('add')
    expect(emitted).toBeTruthy()
    const item = emitted[emitted.length - 1][0]
    expect(item.name).toBe('Chiikawa 徽章')
    expect(item.target).toBe(100)
    expect(item.id).toMatch(/^item-/)
    expect(item.currency).toBe('TWD')
  })

  it('does not emit when the name is empty', async () => {
    const w = mount(AddItemForm)
    await w.findAll('input')[1].setValue('50')
    await w.find('form').trigger('submit')
    expect(w.emitted('add')).toBeUndefined()
  })

  it('does not emit when target is not numeric', async () => {
    const w = mount(AddItemForm)
    await w.find('input').setValue('Bad')
    await w.findAll('input')[1].setValue('abc')
    await w.find('form').trigger('submit')
    expect(w.emitted('add')).toBeUndefined()
  })
})
