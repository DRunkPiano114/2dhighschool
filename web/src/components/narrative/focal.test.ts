import { describe, expect, it } from 'vitest'
import { pickFocal, partitionObservers, findFirstSpeechTick } from './focal'
import type { MindState, SceneGroup, Tick } from '../../lib/types'

const baseMind = (overrides: Partial<MindState> = {}): MindState => ({
  inner_thought: '...',
  observation: '',
  emotion: 'neutral',
  action_type: 'observe',
  action_content: null,
  action_target: null,
  urgency: 0,
  is_disruptive: false,
  ...overrides,
})

const makeTick = (overrides: Partial<Tick> = {}): Tick => ({
  tick: 1,
  public: { speech: null, actions: [], environmental_event: null, exits: [] },
  minds: {},
  ...overrides,
})

const makeGroup = (participants = ['a', 'b', 'c']): SceneGroup => ({
  group_index: 0,
  participants,
  ticks: [],
  narrative: { key_moments: [], fulfilled_intentions: [], events_discussed: [], new_events: [] },
  reflections: {},
})

describe('pickFocal', () => {
  it('returns speaker when tick has public speech', () => {
    const tick = makeTick({
      public: { speech: { agent: 'a', target: 'b', content: 'hi' }, actions: [], environmental_event: null, exits: [] },
      minds: { a: baseMind(), b: baseMind(), c: baseMind({ is_disruptive: true, urgency: 9 }) },
    })
    const focal = pickFocal(tick, makeGroup())
    expect(focal.kind).toBe('speaker')
    expect(focal.agentId).toBe('a')
    expect(focal.target).toBe('b')
    expect(focal.content).toBe('hi')
  })

  it('returns disruptive non-speaker when no speech', () => {
    const tick = makeTick({
      minds: {
        a: baseMind({ urgency: 5 }),
        b: baseMind({ is_disruptive: true, action_type: 'non_verbal', action_content: '猛地站起', urgency: 3 }),
      },
    })
    const focal = pickFocal(tick, makeGroup())
    expect(focal.kind).toBe('non_verbal')
    expect(focal.agentId).toBe('b')
    expect(focal.content).toBe('猛地站起')
  })

  it('returns highest-urgency non_verbal when no speech / disruptive', () => {
    const tick = makeTick({
      minds: {
        a: baseMind({ action_type: 'non_verbal', action_content: '敲桌', urgency: 2 }),
        b: baseMind({ action_type: 'non_verbal', action_content: '起立', urgency: 7 }),
        c: baseMind({ urgency: 8 }),
      },
    })
    const focal = pickFocal(tick, makeGroup())
    expect(focal.kind).toBe('non_verbal')
    expect(focal.agentId).toBe('b')
  })

  it('returns top-urgency observation for pure-observation ticks', () => {
    const tick = makeTick({
      minds: {
        a: baseMind({ urgency: 2 }),
        b: baseMind({ urgency: 6, inner_thought: '好紧张' }),
        c: baseMind({ urgency: 4 }),
      },
    })
    const focal = pickFocal(tick, makeGroup())
    expect(focal.kind).toBe('observation')
    expect(focal.agentId).toBe('b')
    expect(focal.content).toBe('好紧张')
  })

  it('falls back to first participant when minds is empty', () => {
    const tick = makeTick({ minds: {} })
    const focal = pickFocal(tick, makeGroup(['alice', 'bob']))
    expect(focal.kind).toBe('observation')
    expect(focal.agentId).toBe('alice')
  })
})

describe('partitionObservers', () => {
  it('sorts disruptive first, then by descending urgency', () => {
    const tick = makeTick({
      minds: {
        a: baseMind({ urgency: 9 }),
        b: baseMind({ is_disruptive: true, urgency: 2 }),
        c: baseMind({ urgency: 5 }),
        d: baseMind({ urgency: 7 }),
      },
    })
    const sorted = partitionObservers(tick, 'nobody')
    expect(sorted.map(([id]) => id)).toEqual(['b', 'a', 'd', 'c'])
  })

  it('filters out the focal agent', () => {
    const tick = makeTick({
      minds: { a: baseMind({ urgency: 9 }), b: baseMind({ urgency: 5 }) },
    })
    const sorted = partitionObservers(tick, 'a')
    expect(sorted.map(([id]) => id)).toEqual(['b'])
  })

  it('keeps original insertion order for equal urgency (stable)', () => {
    const tick = makeTick({
      minds: {
        first: baseMind({ urgency: 3 }),
        second: baseMind({ urgency: 3 }),
        third: baseMind({ urgency: 3 }),
      },
    })
    const sorted = partitionObservers(tick, 'nobody')
    expect(sorted.map(([id]) => id)).toEqual(['first', 'second', 'third'])
  })
})

describe('findFirstSpeechTick', () => {
  it('returns index of first tick with public speech', () => {
    const group = makeGroup()
    group.ticks = [
      makeTick({ tick: 1 }),
      makeTick({ tick: 2, public: { speech: { agent: 'a', target: null, content: 'hi' }, actions: [], environmental_event: null, exits: [] } }),
      makeTick({ tick: 3 }),
    ]
    expect(findFirstSpeechTick(group)).toBe(1)
  })

  it('returns 0 when no tick has speech', () => {
    const group = makeGroup()
    group.ticks = [makeTick({ tick: 1 }), makeTick({ tick: 2 })]
    expect(findFirstSpeechTick(group)).toBe(0)
  })

  it('returns 0 for solo / undefined group', () => {
    expect(findFirstSpeechTick(undefined)).toBe(0)
    expect(findFirstSpeechTick({ is_solo: true })).toBe(0)
  })
})
