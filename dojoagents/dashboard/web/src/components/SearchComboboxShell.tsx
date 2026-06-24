import type { ChangeEventHandler, FocusEventHandler, ReactNode, Ref } from 'react';

interface SearchComboboxShellProps {
  className: string;
  controlsId?: string;
  expanded: boolean;
  iconClassName: string;
  inputClassName: string;
  inputRef?: Ref<HTMLInputElement>;
  onChange: ChangeEventHandler<HTMLInputElement>;
  onFocus?: FocusEventHandler<HTMLInputElement>;
  placeholder: string;
  rootRef?: Ref<HTMLDivElement>;
  value: string;
  children?: ReactNode;
}

export function SearchComboboxShell({
  children,
  className,
  controlsId,
  expanded,
  iconClassName,
  inputClassName,
  inputRef,
  onChange,
  onFocus,
  placeholder,
  rootRef,
  value,
}: SearchComboboxShellProps) {
  return (
    <div className={`search-combobox ${className}`} ref={rootRef}>
      <span className={`search-combobox__icon ${iconClassName}`} aria-hidden>
        ⌕
      </span>
      <input
        ref={inputRef}
        type="search"
        className={`search-combobox__input ${inputClassName}`}
        value={value}
        placeholder={placeholder}
        aria-controls={controlsId}
        aria-expanded={expanded}
        aria-haspopup="listbox"
        onChange={onChange}
        onFocus={onFocus}
      />
      {children}
    </div>
  );
}
