interface SortToggleProps<T extends string> {
  value: T
  options: ReadonlyArray<{ value: T; label: string }>
  onChange: (value: T) => void
  label: string
}

/** Segmented control implemented as a radio group for keyboard and screen-reader support. */
export function SortToggle<T extends string>({ value, options, onChange, label }: SortToggleProps<T>) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex border border-line text-sm">
      {options.map((option) => {
        const selected = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(option.value)}
            className={`px-3 py-1.5 transition-colors ${selected ? 'bg-ink text-canvas' : 'text-muted hover:text-ink'}`}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
