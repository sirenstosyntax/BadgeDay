type ChooseProps = {
  onOralBoard: () => void
  onReadingList: () => void
}

/** First screen after sign-in. Two doors, no new product surface. */
export function Choose({ onOralBoard, onReadingList }: ChooseProps) {
  return (
    <div className="space-y-6">
      <p className="text-sm text-stone-600 dark:text-stone-400">
        Sign in, then pick Oral board or reading list.
      </p>
      <p className="text-sm text-stone-600 dark:text-stone-400">
        Oral board: you answer out loud. You get notes on what went well and what to improve.
      </p>
      <p className="text-sm text-stone-600 dark:text-stone-400">
        Reading list: add the material you’re testing on. The practice questions come from that.
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          onClick={onOralBoard}
          className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white dark:bg-stone-100 dark:text-stone-900"
        >
          Oral board
        </button>
        <button
          onClick={onReadingList}
          className="rounded-lg border border-stone-300 px-4 py-2 text-sm dark:border-stone-700"
        >
          Reading list
        </button>
      </div>
    </div>
  )
}
