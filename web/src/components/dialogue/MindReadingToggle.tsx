import { motion } from 'framer-motion'
import { useAppStore } from '../../stores/useAppStore'

export function MindReadingToggle() {
  const enabled = useAppStore((s) => s.mindReadingEnabled)
  const toggle = useAppStore((s) => s.toggleMindReading)

  return (
    <motion.button
      onClick={toggle}
      className={`fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-2.5 rounded-full shadow-lg transition-colors duration-300 ${
        enabled
          ? 'bg-amber text-white shadow-amber/30'
          : 'bg-white text-ink-light border border-thought-border hover:border-amber/50'
      }`}
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
    >
      {/* Eye icon */}
      <span className="relative text-lg">
        {enabled ? '👁' : '👁‍🗨'}
        {enabled && (
          <motion.span
            className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-white"
            animate={{ opacity: [1, 0.3, 1] }}
            transition={{ duration: 2, repeat: Infinity }}
          />
        )}
      </span>
      <span className="text-sm font-medium">
        {enabled ? '读心模式' : '普通模式'}
      </span>
    </motion.button>
  )
}
