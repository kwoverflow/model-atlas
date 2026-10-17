import {
  fieldNames,
  operationNames,
  type Fields,
} from "@/lib/personalAssistant";

export const assistantFieldClass =
  "w-full min-w-0 rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm disabled:bg-neutral-100";

type Props = {
  fields: Fields;
  disabled: boolean;
  onChange: (key: string, value: string | number | null) => void;
  onOperation: (value: string) => void;
};

function text(value: unknown) {
  return value === null || value === undefined ? "" : String(value);
}

export function ReviewFields({
  fields,
  disabled,
  onChange,
  onOperation,
}: Props) {
  const operation = text(fields.operation) || "todo.create";
  function input(
    key: string,
    label = fieldNames[key],
    type = "text",
    required = false,
  ) {
    return (
      <label className="grid min-w-0 gap-1.5 text-sm" key={key}>
        <span className="font-medium">
          {label}
          {required ? <span className="ml-1 text-rose">*</span> : null}
        </span>
        <input
          aria-label={label}
          className={assistantFieldClass}
          type={type}
          value={text(fields[key])}
          disabled={disabled}
          min={type === "number" ? 1 : undefined}
          max={type === "number" ? 1440 : undefined}
          placeholder={
            key.startsWith("local_") ? "2026-11-05T08:10:00" : undefined
          }
          onChange={(event) =>
            onChange(
              key,
              type === "number"
                ? event.target.value
                  ? Number(event.target.value)
                  : null
                : event.target.value || (required ? "" : null),
            )
          }
        />
      </label>
    );
  }
  const zones = [
    ...new Set(
      [
        "Asia/Tokyo",
        "America/New_York",
        "UTC",
        text(fields.source_timezone),
      ].filter(Boolean),
    ),
  ];
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <label className="grid gap-1.5 text-sm">
        <span className="font-medium">작업</span>
        <select
          aria-label="작업"
          className={assistantFieldClass}
          value={operation}
          disabled={disabled}
          onChange={(event) => onOperation(event.target.value)}
        >
          {Object.entries(operationNames)
            .filter(([key]) => key !== "files.restore")
            .map(([key, name]) => (
              <option key={key} value={key}>
                {name}
              </option>
            ))}
        </select>
      </label>
      {["calendar.create", "todo.create"].includes(operation)
        ? input("title", "제목", "text", true)
        : null}
      {operation === "calendar.create" ? (
        <>
          {input("local_start", undefined, "text", true)}
          {input("duration_minutes", undefined, "number", true)}
        </>
      ) : null}
      {operation === "todo.create" ? (
        <>
          {input("local_due")}
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium">우선순위</span>
            <select
              aria-label="우선순위"
              className={assistantFieldClass}
              value={text(fields.priority)}
              disabled={disabled}
              onChange={(event) =>
                onChange("priority", event.target.value || null)
              }
            >
              <option value="">생략</option>
              <option value="low">낮음</option>
              <option value="normal">보통</option>
              <option value="high">높음</option>
            </select>
          </label>
        </>
      ) : null}
      {["calendar.create", "todo.create"].includes(operation) ? (
        <label className="grid gap-1.5 text-sm">
          <span className="font-medium">시간대</span>
          <select
            aria-label="시간대"
            className={assistantFieldClass}
            value={text(fields.source_timezone) || "Asia/Tokyo"}
            disabled={disabled}
            onChange={(event) =>
              onChange("source_timezone", event.target.value)
            }
          >
            {zones.map((zone) => (
              <option key={zone}>{zone}</option>
            ))}
          </select>
        </label>
      ) : null}
      {operation === "todo.complete" ? (
        <>
          {input("task_id", "할 일 ID")}
          {input("title", "할 일 제목")}
        </>
      ) : null}
      {operation === "files.move" ? (
        <>
          {input("source", undefined, "text", true)}
          {input("destination", undefined, "text", true)}
        </>
      ) : null}
      {operation === "files.trash"
        ? input("path", undefined, "text", true)
        : null}
    </div>
  );
}
