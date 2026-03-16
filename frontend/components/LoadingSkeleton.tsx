'use client'

import { motion } from 'framer-motion'

export default function LoadingSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3].map((i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: i * 0.1 }}
          className="rounded-xl bg-gray-50 p-4 space-y-3 border border-gray-200"
        >
          <div className="shimmer h-4 bg-gray-200 rounded w-3/4" />
          <div className="shimmer h-3 bg-gray-200 rounded w-1/2" />
          <div className="grid grid-cols-4 gap-2">
            {[1, 2, 3, 4].map((j) => (
              <div key={j} className="shimmer h-12 bg-gray-200 rounded" />
            ))}
          </div>
        </motion.div>
      ))}
    </div>
  )
}
