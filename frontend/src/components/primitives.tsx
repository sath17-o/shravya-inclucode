import { type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, useId, useState } from "react";
import { NavLink, type NavLinkProps } from "react-router-dom";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { children: ReactNode };

export function Button({ children, className = "", ...props }: ButtonProps) {
  return (
    <button className={`button ${className}`.trim()} {...props}>
      {children}
    </button>
  );
}

export function Link({ children, className = "", ...props }: NavLinkProps) {
  return (
    <NavLink className={({ isActive }) => `nav-link ${isActive ? "active" : ""} ${className}`.trim()} {...props}>
      {children}
    </NavLink>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`card ${className}`.trim()}>{children}</section>;
}

export type StatusKind = "approved" | "needs-review" | "outdated" | "source";

export function StatusBadge({ children, kind }: { children: ReactNode; kind: StatusKind }) {
  return <span className={`status-badge status-${kind}`}>{children}</span>;
}

export function Notice({ children }: { children: ReactNode }) {
  return <div className="notice">{children}</div>;
}

export function StatusMessage({ children }: { children: ReactNode }) {
  return <div className="status-message" role="status">{children}</div>;
}

export function ErrorAlert({ children }: { children: ReactNode }) {
  return <div className="error-alert" role="alert">{children}</div>;
}

export function FormField({
  label,
  children,
}: {
  label: ReactNode;
  children: ReactNode;
}) {
  return (
    <label className="form-field">
      <span>{label}</span>
      {children}
    </label>
  );
}

export type RadioOption = { value: string; label: ReactNode; description?: ReactNode };

export function RadioGroup({
  label,
  name,
  options,
  value,
  onChange,
}: {
  label: ReactNode;
  name: string;
  options: RadioOption[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <fieldset className="radio-group">
      <legend>{label}</legend>
      {options.map((option) => (
        <label key={option.value} className="radio-option">
          <input
            checked={value === option.value}
            name={name}
            onChange={() => onChange(option.value)}
            type="radio"
            value={option.value}
          />
          <span>
            <strong>{option.label}</strong>
            {option.description ? <small>{option.description}</small> : null}
          </span>
        </label>
      ))}
    </fieldset>
  );
}

export function ExpandableTrustPanel({ title, children }: { title: ReactNode; children: ReactNode }) {
  const [expanded, setExpanded] = useState(false);
  const panelId = useId();
  return (
    <section className="trust-panel">
      <Button aria-controls={panelId} aria-expanded={expanded} onClick={() => setExpanded(!expanded)} type="button">
        {title}
      </Button>
      {expanded ? <div id={panelId} className="trust-panel-content">{children}</div> : null}
    </section>
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className="text-input" {...props} />;
}
