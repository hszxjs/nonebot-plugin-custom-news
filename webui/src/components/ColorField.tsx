import { Input } from "../ui";

interface Props {
  label: string;
  value: string;
  onChange: (v: string) => void;
  description?: string;
}

function isValidColor(v: string) {
  return /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(v) || v.startsWith("rgba");
}

/** 颜色编辑：原生取色器 + 文本输入 */
export default function ColorField({ label, value, onChange, description }: Props) {
  const pickerValue = value.startsWith("#") ? value : "#ffffff";
  return (
    <div className="flex items-center gap-2">
      <input
        type="color"
        className="h-9 w-9 shrink-0 cursor-pointer rounded-lg border-2 border-border bg-transparent p-0.5"
        value={pickerValue}
        onChange={(e) => onChange(e.target.value)}
        title={`${label} 取色器`}
      />
      <Input
        size="sm"
        label={label}
        description={description}
        value={value}
        isInvalid={!isValidColor(value)}
        onValueChange={onChange}
      />
    </div>
  );
}
