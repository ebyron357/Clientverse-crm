import { Button } from "@/components/ui/button";

export function taskSchedulePreset(preset, now = new Date()) {
  if (preset === "clear") return null;
  if (preset === "hour") return new Date(now.getTime() + 60 * 60 * 1000).toISOString();
  if (preset === "tomorrow") {
    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);
    tomorrow.setHours(9, 0, 0, 0);
    return tomorrow.toISOString();
  }
  throw new Error("Unknown task schedule preset");
}

export default function TaskScheduleShortcuts({ onChange, disabled }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm font-medium text-foreground" id="task-quick-schedule">Reschedule</p>
      <div className="flex flex-wrap gap-2" role="group" aria-labelledby="task-quick-schedule">
        {[["hour", "In 1 hour"], ["tomorrow", "Tomorrow, 9 am"], ["clear", "No due date"]].map(([preset, label]) => (
          <Button key={preset} type="button" variant="outline" size="sm" disabled={disabled}
            onClick={() => onChange(taskSchedulePreset(preset))} data-testid={`task-schedule-${preset}`}>
            {label}
          </Button>
        ))}
      </div>
      <p className="text-sm text-muted-foreground">Your local time. Review the date below, then save.</p>
    </div>
  );
}
