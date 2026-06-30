"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowRight, ClipboardCopy, GripVertical, Layers3, Plus, Sparkles, Trash2 } from "lucide-react";
import { useProposalStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";

type Task = {
  id: string;
  title: string;
  start: number;
  duration: number;
  color: string;
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DEFAULT_START_YEAR = 2026;
const DEFAULT_END_YEAR = 2029;
const TASK_COLUMN_WIDTH = 180;
const ROW_HEIGHT = 92;
const TASK_HEIGHT = 58;
const TASK_GAP = 10;
const MONTH_CELL_WIDTH = 64;
const PALETTE = [
  "from-emerald-600 to-lime-400",
  "from-sky-600 to-cyan-400",
  "from-violet-600 to-fuchsia-400",
  "from-amber-600 to-orange-400",
  "from-rose-600 to-red-400",
  "from-indigo-600 to-blue-400",
];

function uid(title: string) {
  return `${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${Math.random().toString(16).slice(2, 7)}`;
}

function clampIndex(value: number, maxIndex: number) {
  return Math.max(0, Math.min(maxIndex, value));
}

function getMonthMeta(index: number, startYear: number) {
  const monthIndex = ((index % 12) + 12) % 12;
  const year = startYear + Math.floor(index / 12);
  return {
    month: MONTHS[monthIndex] || "",
    year,
  };
}

function monthLabel(index: number, startYear: number) {
  const meta = getMonthMeta(index, startYear);
  return `${meta.month} ${meta.year}`;
}

function defaultDurationFor(title: string) {
  const name = title.toLowerCase();
  if (name.includes("discovery")) return 2;
  if (name.includes("testing") || name.includes("uat")) return 2;
  if (name.includes("hypercare")) return 1;
  if (name.includes("data") || name.includes("migration")) return 3;
  return 2;
}

function phaseFromMonth(start: number) {
  const monthIndex = start % 12;
  if (monthIndex <= 2) return "Discovery";
  if (monthIndex <= 5) return "Phase 1";
  if (monthIndex <= 8) return "Phase 2";
  return "Hypercare";
}

export default function TimelineBuilderPage() {
  const store = useProposalStore();
  const intakeModules = store.context.intake?.module_list ?? [];
  const parsedModules = store.parsedRfp?.intake?.module_list ?? [];
  const library = useMemo(() => {
    const fromIntake = intakeModules.length ? intakeModules : parsedModules;
    return Array.from(
      new Set(
        fromIntake.length
          ? fromIntake
          : ["Requirements Analysis", "Core Banking", "Payments", "Integration", "UAT", "Training"]
      )
    );
  }, [intakeModules, parsedModules]);

  const [tasks, setTasks] = useState<Task[]>([]);
  const [customModule, setCustomModule] = useState("");
  const [dragPayload, setDragPayload] = useState<string>("");
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [startYear, setStartYear] = useState(DEFAULT_START_YEAR);
  const [endYear, setEndYear] = useState(DEFAULT_END_YEAR);

  const safeStartYear = Math.min(startYear, endYear);
  const safeEndYear = Math.max(startYear, endYear);
  const totalMonths = Math.max(12, (safeEndYear - safeStartYear + 1) * 12);
  const yearCount = safeEndYear - safeStartYear + 1;
  const timelineYears = useMemo(
    () => Array.from({ length: yearCount }, (_, index) => safeStartYear + index),
    [safeStartYear, yearCount]
  );
  const timelineMonths = useMemo(
    () =>
      Array.from({ length: totalMonths }, (_, index) => {
        const meta = getMonthMeta(index, safeStartYear);
        return { index, ...meta };
      }),
    [safeStartYear, totalMonths]
  );

  useEffect(() => {
    setTasks((current) => {
      let changed = false;
      const next = current.map((task) => {
        const start = clampIndex(task.start, totalMonths - 1);
        const duration = Math.max(1, Math.min(totalMonths - start, task.duration));
        if (start === task.start && duration === task.duration) return task;
        changed = true;
        return { ...task, start, duration };
      });
      return changed ? next : current;
    });
  }, [totalMonths]);

  const placedTitles = useMemo(() => new Set(tasks.map((task) => task.title)), [tasks]);

  function addTask(title: string, start = 0, duration = defaultDurationFor(title)) {
    setTasks((current) => {
      if (current.some((task) => task.title === title)) return current;
      return [
        ...current,
        {
          id: uid(title),
          title,
          start: clampIndex(start, totalMonths - 1),
          duration: Math.max(1, Math.min(totalMonths, duration)),
          color: PALETTE[current.length % PALETTE.length],
        },
      ];
    });
  }

  function moveTask(taskId: string, start: number) {
    setTasks((current) =>
      current.map((task) =>
        task.id === taskId
          ? {
              ...task,
              start: clampIndex(start, totalMonths - 1),
              duration: Math.max(1, Math.min(totalMonths - clampIndex(start, totalMonths - 1), task.duration)),
            }
          : task
      )
    );
  }

  function nudgeTask(taskId: string, delta: number) {
    const currentTask = tasks.find((task) => task.id === taskId);
    if (!currentTask) return;
    moveTask(taskId, currentTask.start + delta);
  }

  function resizeTask(taskId: string, delta: number) {
    setTasks((current) =>
      current.map((task) =>
        task.id === taskId
          ? { ...task, duration: Math.max(1, Math.min(12 - task.start, task.duration + delta)) }
          : task
      )
    );
  }

  function removeTask(taskId: string) {
    setTasks((current) => current.filter((task) => task.id !== taskId));
  }

  function addCustomModule() {
    const value = customModule.trim();
    if (!value) return;
    addTask(value, 0, defaultDurationFor(value));
    setCustomModule("");
  }

  function handlePromptCopy() {
    const lines = tasks.map((task) => {
      const start = monthLabel(task.start, safeStartYear);
      const end = monthLabel(task.start + task.duration - 1, safeStartYear);
      return `${task.title}: ${start} to ${end} (${phaseFromMonth(task.start)})`;
    });
    const prompt = [
      "Use this Gantt chart as the delivery timeline backbone for the proposal.",
      `Client: ${store.context.client_name || "Unknown client"}`,
      ...lines,
      "Preserve the visible sequencing, dependencies, and staging in the proposal narrative.",
    ].join("\n");
    store.setPrompt(prompt);
    navigator.clipboard?.writeText(prompt).catch(() => undefined);
  }

  function handleDropOnMonth(monthIdx: number) {
    const payload = dragPayload.trim();
    if (!payload) return;
    const existing = tasks.find((task) => task.title === payload);
    if (existing) {
      moveTask(existing.id, monthIdx);
    } else {
      addTask(payload, monthIdx, defaultDurationFor(payload));
    }
    setDragPayload("");
  }

  function handleYearRangeChange(nextStart: number, nextEnd: number) {
    const normalizedStart = Number.isFinite(nextStart) ? nextStart : DEFAULT_START_YEAR;
    const normalizedEnd = Number.isFinite(nextEnd) ? nextEnd : normalizedStart;
    setStartYear(normalizedStart);
    setEndYear(Math.max(normalizedStart, normalizedEnd));
  }

  return (
    <main className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-none flex-col gap-6 px-4 py-4 lg:px-6 xl:px-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="max-w-3xl">
          <h1 className="text-3xl font-bold tracking-tight">Timeline Builder</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Work on a full-width canvas, place modules with drag-and-drop, and fine-tune them with arrow keys.
            Left/Right moves by one month, Up/Down moves by one quarter.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={handlePromptCopy}>
            <ClipboardCopy className="h-4 w-4" />
            Copy timeline to prompt
          </Button>
        </div>
      </div>

      <div className="grid flex-1 gap-6 xl:grid-cols-[288px_minmax(0,1.3fr)]">
        <Card className="border-border/80 bg-gradient-to-b from-card via-card to-muted/20 shadow-sm">
          <CardContent className="space-y-4 p-5">
            <div className="flex items-center gap-2">
              <Layers3 className="h-4 w-4" />
              <h2 className="font-semibold">Module Library</h2>
            </div>
            <p className="text-xs leading-5 text-muted-foreground">
              Drag a module onto the chart, or click it to place it immediately. Placed modules stay selectable for keyboard movement.
            </p>

            <div className="space-y-2 rounded-2xl border border-border bg-background/70 p-3">
              {library.map((title) => (
                <button
                  key={title}
                  type="button"
                  draggable
                  onDragStart={() => setDragPayload(title)}
                  onClick={() => {
                    addTask(title, 0, defaultDurationFor(title));
                    setActiveTaskId(null);
                  }}
                  className="flex w-full items-center justify-between rounded-xl border border-border px-3 py-3 text-left text-sm transition hover:border-primary/40 hover:bg-muted"
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="truncate">{title}</span>
                    {placedTitles.has(title) ? (
                      <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-primary">
                        Placed
                      </span>
                    ) : (
                      <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                        Available
                      </span>
                    )}
                  </span>
                  <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                </button>
              ))}
            </div>

            <div className="space-y-2">
              <Label>Add custom module</Label>
              <div className="flex gap-2">
                <Input
                  value={customModule}
                  onChange={(e) => setCustomModule(e.target.value)}
                  placeholder="Regulatory reporting pack"
                />
                <Button type="button" onClick={addCustomModule}>
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
            </div>

            <div className="rounded-2xl border border-border bg-background/70 p-4">
              <div className="text-sm font-semibold">Keyboard controls</div>
              <ul className="mt-2 space-y-1 text-sm leading-6 text-muted-foreground">
                <li>Arrow Left / Right: move the selected module by 1 month</li>
                <li>Arrow Up / Down: move the selected module by 1 quarter</li>
                <li>Use + / - inside a module to resize its duration</li>
              </ul>
            </div>
          </CardContent>
        </Card>

        <Card className="min-h-0 overflow-hidden border-border/80 shadow-sm">
          <CardContent className="flex h-full min-h-0 flex-col gap-4 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4" />
                  <h2 className="font-semibold">Gantt Chart</h2>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  Full-screen working board with larger rows, wider months, and a keyboard-friendly task canvas.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                <span>{tasks.length} tasks placed</span>
                <div className="flex items-center gap-2 rounded-full border border-border bg-background px-3 py-1">
                  <span className="uppercase tracking-wide text-[10px]">Years</span>
                  <Input
                    type="number"
                    value={startYear}
                    onChange={(e) => handleYearRangeChange(Number(e.target.value), endYear)}
                    className="h-8 w-20"
                  />
                  <span>to</span>
                  <Input
                    type="number"
                    value={endYear}
                    onChange={(e) => handleYearRangeChange(startYear, Number(e.target.value))}
                    className="h-8 w-20"
                  />
                </div>
              </div>
            </div>

            <div className="flex-1 overflow-x-auto overflow-y-hidden rounded-3xl border border-border bg-[#f5f7ef] shadow-[0_18px_50px_rgba(12,75,29,0.12)]">
              <div className="w-max min-w-full pr-12">
                <div
                  className="sticky top-0 z-30 grid border-b border-[#d7dfc7] bg-[#173d1e] text-[#eef6e5]"
                  style={{ gridTemplateColumns: `${TASK_COLUMN_WIDTH}px repeat(${totalMonths}, minmax(${MONTH_CELL_WIDTH}px, ${MONTH_CELL_WIDTH}px))` }}
                >
                  <div className="border-r border-[#2f6a3b] p-2.5">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#d9f0d2]">Progress / Task</div>
                    <div className="mt-1 text-[10px] uppercase tracking-[0.22em] text-[#bfe1b2]">
                      Enterprise resource planning
                    </div>
                  </div>
                  {timelineYears.map((year) => (
                    <div
                      key={year}
                      className="border-l border-[#2f6a3b] px-2 py-3 text-center"
                      style={{ gridColumn: "span 12" }}
                    >
                      <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#d9f0d2]">{year}</div>
                      <div className="mt-1 text-[10px] text-[#bfe1b2]">12-month plan</div>
                    </div>
                  ))}
                </div>

                <div
                  className="sticky top-[68px] z-20 grid border-b border-[#d7dfc7] bg-[#0c4b1d] text-[#eef6e5]"
                  style={{ gridTemplateColumns: `${TASK_COLUMN_WIDTH}px repeat(${totalMonths}, minmax(${MONTH_CELL_WIDTH}px, ${MONTH_CELL_WIDTH}px))` }}
                >
                  <div className="border-r border-[#2f6a3b] px-2.5 py-2 text-[10px] uppercase tracking-[0.2em] text-[#bfe1b2]">
                    Months
                  </div>
                  {timelineMonths.map((month) => (
                    <div key={`${month.year}-${month.month}-${month.index}`} className="border-l border-[#2f6a3b] px-1 py-2 text-center">
                      <div className="text-[9px] font-semibold">{month.month}</div>
                    </div>
                  ))}
                </div>

                <div
                  className="grid"
                  style={{
                    gridTemplateColumns: `${TASK_COLUMN_WIDTH}px repeat(${totalMonths}, minmax(${MONTH_CELL_WIDTH}px, ${MONTH_CELL_WIDTH}px))`,
                    minHeight: Math.max(300, tasks.length * ROW_HEIGHT),
                  }}
                >
                  <div className="bg-[#eef4e1]">
                    {tasks.map((task) => (
                      <div
                        key={task.id}
                        className="flex items-center border-b border-[#dbe5cb] px-2.5 text-[11px] font-medium leading-5 text-[#28411f]"
                        style={{ height: ROW_HEIGHT }}
                      >
                        <span className="line-clamp-2">{task.title}</span>
                      </div>
                    ))}
                    {!tasks.length ? (
                      <div className="flex min-h-[300px] items-center px-2.5 text-[11px] text-[#5e6d54]">
                        Drop modules here to start building the Gantt chart.
                      </div>
                    ) : null}
                  </div>

                  <div className="relative" style={{ gridColumn: `2 / span ${totalMonths}` }}>
                    <div className="grid h-full" style={{ gridTemplateColumns: `repeat(${totalMonths}, minmax(${MONTH_CELL_WIDTH}px, ${MONTH_CELL_WIDTH}px))` }}>
                      {timelineMonths.map((_, monthIdx) => (
                        <div
                          key={monthIdx}
                          onDragOver={(e) => e.preventDefault()}
                          onDrop={() => handleDropOnMonth(monthIdx)}
                          className={cn(
                            "border-l border-[#d7dfc7] transition",
                            monthIdx % 2 === 0 ? "bg-[#f7f9ef]" : "bg-[#eff4e2]",
                            "hover:bg-[#e2eed1]"
                          )}
                          style={{ minHeight: Math.max(300, tasks.length * ROW_HEIGHT) }}
                        />
                      ))}
                    </div>

                    <div
                      className="pointer-events-none absolute inset-0 grid"
                      style={{ gridTemplateColumns: `repeat(${totalMonths}, minmax(${MONTH_CELL_WIDTH}px, ${MONTH_CELL_WIDTH}px))` }}
                    >
                      {timelineMonths.map((_, monthIdx) => (
                        <div key={monthIdx} className="border-l border-[#d7dfc7]/70" />
                      ))}
                    </div>

                    {tasks.map((task, rowIdx) => {
                      const top = rowIdx * ROW_HEIGHT + TASK_GAP;
                      const left = `${(task.start / totalMonths) * 100}%`;
                      const width = `${(task.duration / totalMonths) * 100}%`;
                      const isActive = activeTaskId === task.id;

                      return (
                        <div
                          key={task.id}
                          className="absolute left-0 right-0"
                          style={{ top, height: TASK_HEIGHT }}
                        >
                          <div
                            role="button"
                            tabIndex={0}
                            draggable
                            onFocus={() => setActiveTaskId(task.id)}
                            onClick={() => setActiveTaskId(task.id)}
                            onDragStart={() => {
                              setDragPayload(task.title);
                              setActiveTaskId(task.id);
                            }}
                            onKeyDown={(e) => {
                              if (e.key === "ArrowLeft") {
                                e.preventDefault();
                                nudgeTask(task.id, -1);
                              }
                              if (e.key === "ArrowRight") {
                                e.preventDefault();
                                nudgeTask(task.id, 1);
                              }
                              if (e.key === "ArrowUp") {
                                e.preventDefault();
                                nudgeTask(task.id, -3);
                              }
                              if (e.key === "ArrowDown") {
                                e.preventDefault();
                                nudgeTask(task.id, 3);
                              }
                              if (e.key === "Delete" || e.key === "Backspace") {
                                e.preventDefault();
                                removeTask(task.id);
                              }
                            }}
                            className={cn(
                              "group absolute top-0 flex h-[58px] items-center rounded-2xl px-2 shadow-md transition",
                              "cursor-grab active:cursor-grabbing outline-none",
                              "bg-gradient-to-r",
                              task.color,
                              isActive && "ring-4 ring-white/80 ring-offset-2 ring-offset-[#dbe8c5]"
                            )}
                            style={{ left, width, minWidth: "72px" }}
                          >
                            <div className="flex w-full items-center gap-2 rounded-xl bg-black/10 px-3 py-2 text-white">
                              <GripVertical className="h-5 w-5 shrink-0 opacity-80" />
                              <div className="min-w-0 flex-1">
                                <div className="truncate text-[11px] font-semibold">{task.title}</div>
                                <div className="text-[10px] opacity-80">
                                  {monthLabel(task.start, safeStartYear)} - {monthLabel(task.start + task.duration - 1, safeStartYear)}
                                </div>
                              </div>
                            </div>
                          </div>

                          <div className="sticky right-2 top-2 z-30 ml-auto flex w-fit gap-1 rounded-full border border-white/25 bg-[#0f3b1c]/85 p-1 shadow-lg backdrop-blur-sm">
                            <button
                              type="button"
                              onClick={() => resizeTask(task.id, -1)}
                              className="rounded-full bg-black/15 px-2 py-0.5 text-[10px] font-semibold text-white transition hover:bg-black/25"
                            >
                              -
                            </button>
                            <button
                              type="button"
                              onClick={() => resizeTask(task.id, 1)}
                              className="rounded-full bg-black/15 px-2 py-0.5 text-[10px] font-semibold text-white transition hover:bg-black/25"
                            >
                              +
                            </button>
                            <button
                              type="button"
                              onClick={() => removeTask(task.id)}
                              className="rounded-full bg-black/15 p-1 text-white transition hover:bg-black/25"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {timelineYears.map((year) => (
                <div key={year} className="rounded-2xl border border-border bg-muted/20 p-4">
                  <div className="text-sm font-semibold">{year}</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    Year plan and assigned modules
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {tasks
                      .filter((task) => {
                        const taskYear = safeStartYear + Math.floor(task.start / 12);
                        return taskYear === year;
                      })
                      .slice(0, 5)
                      .map((task) => (
                        <span key={task.id} className="rounded-full bg-background px-2.5 py-1 text-xs border border-border">
                          {task.title}
                        </span>
                      ))}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
