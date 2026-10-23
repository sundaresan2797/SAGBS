import clsx from "clsx";
import { ChevronDown } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { FieldWrapper, inputClasses } from "@/components/ui/FormField";

interface SearchableSelectProps<T> {
  label: string;
  name: string;
  required?: boolean;
  placeholder?: string;
  emptyLabel?: string;
  noResultsLabel?: string;
  value: string;
  onChange: (value: string) => void;
  options: T[];
  getId: (option: T) => string;
  getLabel: (option: T) => string;
  getDescription?: (option: T) => string;
  getSearchText: (option: T) => string;
}

// A filter-as-you-type dropdown for picking one item out of a long list
// (dozens of employees, say) where a plain <select> forces scanning through
// every option one at a time. Matches FormField's visual language so it
// drops into the same forms as InputField/SelectField.
export function SearchableSelect<T>({
  label,
  name,
  required,
  placeholder = "Type to search...",
  emptyLabel = "Choose an option",
  noResultsLabel = "No matches found",
  value,
  onChange,
  options,
  getId,
  getLabel,
  getDescription,
  getSearchText,
}: SearchableSelectProps<T>) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const selected = options.find((o) => getId(o) === value);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter((o) => getSearchText(o).toLowerCase().includes(q));
  }, [options, query, getSearchText]);

  useEffect(() => {
    setHighlightedIndex(0);
  }, [query, isOpen]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        setQuery("");
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const openList = () => {
    setIsOpen(true);
    setQuery("");
  };

  const selectOption = (option: T) => {
    onChange(getId(option));
    setIsOpen(false);
    setQuery("");
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (!isOpen) {
      if (event.key === "ArrowDown" || event.key === "Enter") {
        event.preventDefault();
        openList();
      }
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlightedIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlightedIndex((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const option = filtered[highlightedIndex];
      if (option) selectOption(option);
    } else if (event.key === "Escape") {
      setIsOpen(false);
      setQuery("");
    }
  };

  const displayValue = isOpen ? query : selected ? getLabel(selected) : "";

  return (
    <FieldWrapper label={label} htmlFor={name} required={required}>
      <div ref={containerRef} className="relative">
        <input
          id={name}
          name={name}
          autoComplete="off"
          className={clsx(inputClasses, "pr-9")}
          placeholder={isOpen ? placeholder : emptyLabel}
          value={displayValue}
          onFocus={openList}
          onChange={(event) => {
            setQuery(event.target.value);
            if (!isOpen) setIsOpen(true);
          }}
          onKeyDown={handleKeyDown}
        />
        <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" />

        {isOpen && (
          <div className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-xl border-2 border-sand-200 bg-white p-1 shadow-lg">
            {filtered.length === 0 ? (
              <p className="px-3 py-2 text-sm text-stone-400">{noResultsLabel}</p>
            ) : (
              filtered.map((option, index) => {
                const id = getId(option);
                const isHighlighted = index === highlightedIndex;
                const isSelected = id === value;
                return (
                  <button
                    key={id}
                    type="button"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => selectOption(option)}
                    onMouseEnter={() => setHighlightedIndex(index)}
                    className={clsx(
                      "flex w-full flex-col items-start gap-0.5 rounded-lg px-3 py-2 text-left text-sm",
                      isHighlighted ? "bg-brand-50" : "hover:bg-sand-50",
                      isSelected && "font-semibold text-brand-700",
                    )}
                  >
                    <span className="text-stone-800">{getLabel(option)}</span>
                    {getDescription && <span className="text-xs text-stone-400">{getDescription(option)}</span>}
                  </button>
                );
              })
            )}
          </div>
        )}
      </div>
    </FieldWrapper>
  );
}
