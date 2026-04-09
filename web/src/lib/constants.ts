import type { Emotion } from './types'

// Classroom: 5 columns × 4 rows, seats 1-20 (left-to-right, front-to-back)
// Row 0 = front (near blackboard), Row 3 = back
export const SEAT_LAYOUT: Record<number, { row: number; col: number }> = {
  1: { row: 0, col: 0 }, 2: { row: 0, col: 1 }, 3: { row: 0, col: 2 }, 4: { row: 0, col: 3 }, 5: { row: 0, col: 4 },
  6: { row: 1, col: 0 }, 7: { row: 1, col: 1 }, 8: { row: 1, col: 2 }, 9: { row: 1, col: 3 }, 10: { row: 1, col: 4 },
  11: { row: 2, col: 0 }, 12: { row: 2, col: 1 }, 13: { row: 2, col: 2 }, 14: { row: 2, col: 3 }, 15: { row: 2, col: 4 },
  16: { row: 3, col: 0 }, 17: { row: 3, col: 1 }, 18: { row: 3, col: 2 }, 19: { row: 3, col: 3 }, 20: { row: 3, col: 4 },
}

export const EMOTION_COLORS: Record<Emotion, string> = {
  happy: '#FFD700',
  sad: '#6B7B8D',
  anxious: '#E8A838',
  angry: '#D94848',
  excited: '#FF8C42',
  calm: '#7AB893',
  embarrassed: '#E88B8B',
  bored: '#A0A0A0',
  neutral: '#B8B8B8',
  jealous: '#8B6FB0',
  proud: '#E8C547',
}

export const EMOTION_LABELS: Record<Emotion, string> = {
  happy: '开心',
  sad: '难过',
  anxious: '焦虑',
  angry: '生气',
  excited: '兴奋',
  calm: '平静',
  embarrassed: '尴尬',
  bored: '无聊',
  neutral: '平常',
  jealous: '嫉妒',
  proud: '自豪',
}

// Emotion sentiment score for timeline (positive = up, negative = down)
export const EMOTION_SENTIMENT: Record<Emotion, number> = {
  happy: 0.8,
  excited: 0.9,
  proud: 0.7,
  calm: 0.3,
  neutral: 0,
  bored: -0.2,
  curious: 0.4,
  anxious: -0.6,
  sad: -0.7,
  angry: -0.8,
  embarrassed: -0.4,
  jealous: -0.5,
} as Record<Emotion, number>

export const EMOTION_EMOJIS: Record<string, string> = {
  happy: '😊',
  sad: '😢',
  anxious: '😰',
  angry: '😤',
  excited: '🤩',
  calm: '😌',
  embarrassed: '😳',
  bored: '😑',
  neutral: '😐',
  jealous: '😒',
  proud: '😏',
  curious: '🤔',
}

export const LOCATION_ICONS: Record<string, string> = {
  '教室': '🏫',
  '食堂': '🍜',
  '宿舍': '🏠',
  '操场': '⚽',
  '走廊': '🚶',
  '图书馆': '📚',
  '小卖部': '🛒',
  '天台': '🌅',
}
