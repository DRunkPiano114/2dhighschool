import { motion, AnimatePresence } from 'framer-motion'

interface WhisperLineProps {
  fromName: string
  toName: string
  content: string
  revealed: boolean
}

export function WhisperLine({ fromName, toName, content, revealed }: WhisperLineProps) {
  return (
    <div className="ml-11 my-1">
      <AnimatePresence mode="wait">
        {revealed ? (
          <motion.div
            key="revealed"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="thought-cloud"
          >
            <span className="text-xs text-amber font-medium">🤫 悄悄话</span>
            <p className="text-sm mt-1">
              <span className="text-ink-light">{fromName} → {toName}：</span>
              <span className="font-hand">{content}</span>
            </p>
          </motion.div>
        ) : (
          <motion.p
            key="hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="text-sm text-ink-light italic"
          >
            [{fromName} 对 {toName} 说了悄悄话]
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  )
}
