/**
 * 基于 HeroUI v3（React Aria 组合式 API）的表单级兼容组件层 + 品牌设计系统。
 * v3 的 Switch 为组合式组件（缺 Content/Control/Thumb 时轨道不渲染），
 * 因此开关采用品牌样式自绘实现，其余组件仍基于 HeroUI。
 */
import type { ReactNode } from "react";
import {
  Button as HeroButton,
  Card,
  Chip as HeroChip,
  Spinner as HeroSpinner,
} from "@heroui/react";

export { Card };

const cn = (...xs: (string | false | undefined)[]) => xs.filter(Boolean).join(" ");

/* ---------------------------------- Button --------------------------------- */

type ButtonColor = "primary" | "secondary" | "danger" | "success" | "default";
type ButtonVariant = "solid" | "flat" | "light";

export function Button({
  color = "primary",
  variant = "solid",
  size = "md",
  isLoading,
  isDisabled,
  onPress,
  onClick,
  className,
  children,
  title,
  type,
  style,
}: {
  color?: ButtonColor;
  variant?: ButtonVariant;
  size?: "sm" | "md" | "lg";
  isLoading?: boolean;
  isIconOnly?: boolean;
  isDisabled?: boolean;
  onPress?: () => void;
  onClick?: () => void;
  className?: string;
  children?: ReactNode;
  title?: string;
  type?: "button" | "submit";
  style?: React.CSSProperties;
}) {
  let v3variant: "primary" | "secondary" | "tertiary" | "danger" | "danger-soft" | "ghost" | "outline" =
    "primary";
  let extra = "";
  if (variant === "light") {
    v3variant = "ghost";
  } else if (variant === "flat" && color === "danger") {
    v3variant = "danger-soft";
  } else if (variant === "flat") {
    v3variant = "ghost";
    const map: Record<ButtonColor, string> = {
      primary: "bg-accent-soft text-accent hover:bg-accent-soft-hover",
      secondary: "bg-white/5 text-foreground hover:bg-white/10",
      danger: "bg-danger-soft text-danger hover:bg-danger-soft-hover",
      success: "bg-success-soft text-success hover:bg-success-soft-hover",
      default: "bg-white/5 text-foreground hover:bg-white/10",
    };
    extra = map[color];
  } else if (color === "danger") {
    v3variant = "danger";
  } else if (color === "primary") {
    // 主按钮：品牌渐变
    v3variant = "ghost";
    extra = "brand-gradient brand-glow text-white hover:brightness-110";
  } else {
    v3variant = "secondary";
  }
  const sizeCls = { sm: "h-8 px-3.5 text-small", md: "h-10 px-4 text-medium", lg: "h-12 px-6" }[size];
  return (
    <HeroButton
      variant={v3variant}
      isDisabled={isDisabled || isLoading}
      onPress={onPress ?? onClick}
      type={type}
      style={style}
      className={cn(sizeCls, extra, isLoading && "gap-2", className)}
    >
      {isLoading && <HeroSpinner size="sm" className="text-white" />}
      {children}
    </HeroButton>
  );
}

/* ----------------------------------- Card ---------------------------------- */

export function CardBody({ className, children }: { className?: string; children?: ReactNode }) {
  return <Card.Content className={cn("p-5", className)}>{children}</Card.Content>;
}

export function CardHeader({ className, children }: { className?: string; children?: ReactNode }) {
  return <Card.Header className={cn("p-5 pb-0", className)}>{children}</Card.Header>;
}

/* -------------------------------- PageHeader ------------------------------- */

export function PageHeader({
  title,
  desc,
  actions,
}: {
  title: string;
  desc?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-gradient text-2xl font-bold tracking-wide">{title}</h1>
        {desc && <p className="mt-1 text-small text-muted">{desc}</p>}
      </div>
      {actions}
    </div>
  );
}

/* ---------------------------------- Chip ----------------------------------- */

export function Chip({
  color = "default",
  children,
  className,
}: {
  color?: "default" | "success" | "danger" | "warning" | "accent";
  children?: ReactNode;
  className?: string;
}) {
  return (
    <HeroChip variant="soft" color={color} className={cn("h-5", className)}>
      {children}
    </HeroChip>
  );
}

/* --------------------------------- Spinner --------------------------------- */

export function Spinner({ label, className }: { label?: string; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 text-muted", className)}>
      <HeroSpinner size="sm" />
      {label}
    </span>
  );
}

/* ---------------------------------- Input ---------------------------------- */

export function Input({
  label,
  size: _size,
  description,
  value,
  onValueChange,
  defaultValue,
  isInvalid,
  errorMessage,
  className,
  type = "text",
  placeholder,
  autoFocus,
  autoComplete,
  min,
  max,
  step,
}: {
  label?: string;
  size?: string;
  description?: string;
  value?: string;
  onValueChange?: (v: string) => void;
  defaultValue?: string;
  isInvalid?: boolean;
  errorMessage?: string;
  className?: string;
  type?: string;
  placeholder?: string;
  autoFocus?: boolean;
  autoComplete?: string;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <label className={cn("flex flex-col gap-1.5", className)}>
      {label && <span className="text-tiny font-medium text-muted">{label}</span>}
      <input
        type={type}
        value={value}
        defaultValue={defaultValue}
        onChange={(e) => onValueChange?.(e.target.value)}
        placeholder={placeholder}
        autoFocus={autoFocus}
        autoComplete={autoComplete}
        min={min}
        max={max}
        step={step}
        className={cn("field-input", isInvalid && "!border-danger")}
      />
      {isInvalid && errorMessage ? (
        <span className="text-tiny text-danger">{errorMessage}</span>
      ) : description ? (
        <span className="text-tiny text-muted/80">{description}</span>
      ) : null}
    </label>
  );
}

/* ---------------------------------- Switch --------------------------------- */
/* 品牌滑块开关：自绘动画（48×28），开启态品牌渐变 + 光晕 */

export function Switch({
  isSelected,
  onValueChange,
  children,
}: {
  isSelected?: boolean;
  onValueChange?: (v: boolean) => void;
  children?: ReactNode;
  size?: string;
}) {
  return (
    <label className="inline-flex cursor-pointer select-none items-center gap-2.5">
      <button
        type="button"
        role="switch"
        aria-checked={!!isSelected}
        onClick={() => onValueChange?.(!isSelected)}
        className={cn(
          "relative h-7 w-12 shrink-0 rounded-full transition-all duration-300",
          isSelected
            ? "brand-gradient brand-glow"
            : "border border-white/12 bg-white/8 hover:bg-white/12",
        )}
      >
        <span
          className={cn(
            "absolute top-1/2 h-5 w-5 -translate-y-1/2 rounded-full bg-white shadow-md transition-all duration-300",
            isSelected ? "left-[25px]" : "left-[3px]",
          )}
        />
      </button>
      {children && <span className="text-small text-foreground">{children}</span>}
    </label>
  );
}

/* --------------------------------- Select ---------------------------------- */

export interface SelectOption {
  value: string;
  label: string;
}

export function Select({
  label,
  options,
  value,
  onChange,
  className,
}: {
  label?: string;
  options: SelectOption[];
  value: string;
  onChange: (v: string) => void;
  className?: string;
}) {
  return (
    <label className={cn("flex flex-col gap-1.5", className)}>
      {label && <span className="text-tiny font-medium text-muted">{label}</span>}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="field-input appearance-none"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/* --------------------------------- Slider ---------------------------------- */

export function Slider({
  label,
  minValue,
  maxValue,
  step = 1,
  value,
  onChange,
  formatValue,
  className,
}: {
  label?: string;
  minValue: number;
  maxValue: number;
  step?: number;
  value: number;
  onChange: (v: number) => void;
  formatValue?: (v: number) => string;
  className?: string;
}) {
  const pct = Math.min(100, Math.max(0, ((value - minValue) / (maxValue - minValue)) * 100));
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <div className="flex items-center justify-between">
        {label && <span className="text-tiny font-medium text-muted">{label}</span>}
        <span className="text-tiny tabular-nums text-accent">
          {formatValue ? formatValue(value) : value}
        </span>
      </div>
      <input
        type="range"
        min={minValue}
        max={maxValue}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-2 w-full cursor-pointer appearance-none rounded-full outline-none [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:shadow-[0_0_8px_rgba(139,92,246,.6)]"
        style={{
          background: `linear-gradient(90deg, #6366f1 0%, #a855f7 ${pct}%, rgba(255,255,255,.10) ${pct}%)`,
        }}
      />
    </div>
  );
}

/* ---------------------------------- Modal ---------------------------------- */

export function Modal({
  isOpen,
  onClose,
  title,
  children,
  footer,
  wide,
}: {
  isOpen: boolean;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  if (!isOpen) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 p-4 backdrop-blur-md"
      onClick={onClose}
    >
      <div
        className={cn(
          "glass flex max-h-[88vh] w-full flex-col rounded-2xl shadow-2xl",
          wide ? "max-w-4xl" : "max-w-md",
        )}
        style={{ background: "linear-gradient(180deg,#161a26,#11141d)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {title && <div className="border-b border-white/8 px-5 py-3.5 font-semibold">{title}</div>}
        <div className="min-h-0 flex-1 overflow-y-auto p-5">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2 border-t border-white/8 px-5 py-3">{footer}</div>
        )}
      </div>
    </div>
  );
}

/* --------------------------------- Tooltip --------------------------------- */

export function Tip({ content, children }: { content: ReactNode; children: ReactNode }) {
  return <span title={typeof content === "string" ? content : ""}>{children}</span>;
}

/* ---------------------------------- Tabs ----------------------------------- */

export function SegTabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { key: string; label: string }[];
  active: string;
  onChange: (key: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1 rounded-2xl border border-white/8 bg-white/4 p-1">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={cn(
            "rounded-xl px-3.5 py-1.5 text-small transition-all duration-200",
            active === t.key
              ? "brand-gradient font-semibold text-white shadow"
              : "text-muted hover:bg-white/6 hover:text-foreground",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

/* --------------------------------- Divider --------------------------------- */

export function Divider({ className }: { className?: string }) {
  return <hr className={cn("border-0 border-t border-white/8", className)} />;
}
