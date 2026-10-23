import clsx from "clsx";
import { forwardRef, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

interface FieldWrapperProps {
  label: string;
  error?: string;
  htmlFor: string;
  children: ReactNode;
  required?: boolean;
}

export function FieldWrapper({ label, error, htmlFor, children, required }: FieldWrapperProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-base font-semibold text-stone-700">
        {label}
        {required && <span className="text-sunset-500"> *</span>}
      </label>
      {children}
      {error && (
        <p role="alert" className="text-sm font-medium text-sunset-600">
          {error}
        </p>
      )}
    </div>
  );
}

export const inputClasses =
  "w-full rounded-xl border-2 border-sand-200 min-h-[48px] px-3.5 py-2.5 text-base text-stone-800 shadow-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100 disabled:bg-sand-50 disabled:text-stone-400";

type InputFieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  error?: string;
  name: string;
};

// forwardRef is required here: react-hook-form's register() returns a ref
// callback that must reach the real <input> DOM node. Without forwardRef,
// React silently drops that ref (function components can't receive one),
// so RHF never sees the field's value and every submit looks empty.
export const InputField = forwardRef<HTMLInputElement, InputFieldProps>(function InputField(
  { label, error, name, className, ...props },
  ref,
) {
  return (
    <FieldWrapper label={label} error={error} htmlFor={name} required={props.required}>
      <input ref={ref} id={name} name={name} className={clsx(inputClasses, className)} {...props} />
    </FieldWrapper>
  );
});

type TextareaFieldProps = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  label: string;
  error?: string;
  name: string;
};

export const TextareaField = forwardRef<HTMLTextAreaElement, TextareaFieldProps>(function TextareaField(
  { label, error, name, className, ...props },
  ref,
) {
  return (
    <FieldWrapper label={label} error={error} htmlFor={name} required={props.required}>
      <textarea ref={ref} id={name} name={name} className={clsx(inputClasses, className)} rows={3} {...props} />
    </FieldWrapper>
  );
});

type SelectFieldProps = SelectHTMLAttributes<HTMLSelectElement> & {
  label: string;
  error?: string;
  name: string;
  children: ReactNode;
};

export const SelectField = forwardRef<HTMLSelectElement, SelectFieldProps>(function SelectField(
  { label, error, name, className, children, ...props },
  ref,
) {
  return (
    <FieldWrapper label={label} error={error} htmlFor={name} required={props.required}>
      <select ref={ref} id={name} name={name} className={clsx(inputClasses, "bg-white", className)} {...props}>
        {children}
      </select>
    </FieldWrapper>
  );
});
