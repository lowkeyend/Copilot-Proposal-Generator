"use client";

import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";

type Option = string;

interface Props {
  label: string;
  options: Option[];
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  helper?: string;
  disabledOptions?: string[];
}

export function DropdownMultiSelect({
  label,
  options,
  value,
  onChange,
  placeholder = "Select an option",
  helper,
  disabledOptions = [],
}: Props) {
  const available = options.filter((option) => !value.includes(option));
  return (
    <div className="space-y-2">
      <div className="space-y-1">
        <div className="text-sm font-medium">{label}</div>
        {helper ? <p className="text-xs text-muted-foreground">{helper}</p> : null}
      </div>
      <Select
        value=""
        onChange={(e) => {
          const next = e.target.value;
          if (!next) return;
          onChange([...value, next]);
        }}
        className="bg-background"
      >
        <option value="">{placeholder}</option>
        {available.map((option) => (
          <option key={option} value={option} disabled={disabledOptions.includes(option)}>
            {option}
          </option>
        ))}
      </Select>
      {value.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {value.map((item) => (
            <span
              key={item}
              className={cn(
                "inline-flex items-center gap-2 rounded-full border border-border bg-muted px-3 py-1 text-xs text-foreground"
              )}
            >
              {item}
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-5 w-5"
                onClick={() => onChange(value.filter((current) => current !== item))}
                aria-label={`Remove ${item}`}
              >
                <X className="h-3 w-3" />
              </Button>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
