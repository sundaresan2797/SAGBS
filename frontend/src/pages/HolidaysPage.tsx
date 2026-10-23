import clsx from "clsx";
import { CalendarDays, ChevronDown, Pencil, PartyPopper, Plus, Sun, Trash2, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { InputField, TextareaField } from "@/components/ui/FormField";
import { Sheet } from "@/components/ui/Sheet";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { holidayService } from "@/services/holidayService";
import type { Holiday } from "@/types";
import { formatDay, inDaysLabel, monthName, parseIsoDate, weekdayName } from "@/utils/friendly";
import { toIsoDate } from "@/utils/taskHelpers";
import type { YearValue } from "@/components/YearFilter";

function DateTile({ iso, muted = false }: { iso: string; muted?: boolean }) {
  const d = parseIsoDate(iso);
  return (
    <div
      className={clsx(
        "flex h-16 w-16 flex-shrink-0 flex-col items-center justify-center rounded-2xl",
        muted ? "bg-stone-100 text-stone-500" : "bg-brand-50 text-brand-700",
      )}
    >
      <span className="font-display text-2xl font-bold leading-none">{d.getDate()}</span>
      <span className="mt-1 text-sm font-semibold uppercase leading-none">{monthName(d.getMonth() + 1).slice(0, 3)}</span>
    </div>
  );
}

export function HolidaysPage() {
  const { hasPermission } = useAuth();
  const { showToast } = useToast();
  const canManage = hasPermission("holiday:manage");

  const [holidays, setHolidays] = useState<Holiday[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showPast, setShowPast] = useState(false);
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState<YearValue>(thisYear); // this year to begin with

  const [isSheetOpen, setIsSheetOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Holiday | null>(null); // null = adding a new one
  const [name, setName] = useState("");
  const [date, setDate] = useState("");
  const [description, setDescription] = useState("");
  const [isOptional, setIsOptional] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Holiday | null>(null);

  const load = async () => {
    setIsLoading(true);
    setError(null);
    try {
      setHolidays(await holidayService.list());
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't load the holiday list."));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const openCreate = () => {
    setEditTarget(null);
    setName("");
    setDate("");
    setDescription("");
    setIsOptional(false);
    setFormError(null);
    setIsSheetOpen(true);
  };

  const openEdit = (holiday: Holiday) => {
    setEditTarget(holiday);
    setName(holiday.name);
    setDate(holiday.holiday_date);
    setDescription(holiday.description ?? "");
    setIsOptional(holiday.is_optional);
    setFormError(null);
    setIsSheetOpen(true);
  };

  const handleSave = async () => {
    if (!name.trim()) return setFormError("Please type the name of the holiday.");
    if (!date) return setFormError("Please choose the date.");
    setFormError(null);
    setIsSaving(true);
    try {
      if (editTarget) {
        await holidayService.update(editTarget.id, {
          name: name.trim(),
          holiday_date: date,
          description,
          is_optional: isOptional,
        });
        showToast("Holiday updated", "success");
      } else {
        await holidayService.create({ name: name.trim(), holiday_date: date, description, is_optional: isOptional });
        showToast("Holiday added", "success");
      }
      setIsSheetOpen(false);
      load();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setIsSaving(true);
    try {
      await holidayService.remove(deleteTarget.id);
      showToast("Holiday removed", "success");
      load();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setIsSaving(false);
      setDeleteTarget(null);
    }
  };

  const todayIso = toIsoDate(new Date());

  // A reminder for whoever keeps the calendar: from October, if nothing is listed for next year yet, every
  // holiday of that year would count as an ordinary working day once it starts.
  const nextYear = thisYear + 1;
  const showNextYearReminder =
    canManage &&
    new Date().getMonth() >= 9 &&
    !holidays.some((h) => Number(h.holiday_date.slice(0, 4)) >= nextYear);

  // The tabs are the years that actually have holidays (plus this year), newest first.
  const years = useMemo(() => {
    const found = new Set(holidays.map((h) => Number(h.holiday_date.slice(0, 4))));
    found.add(thisYear);
    return [...found].sort((a, b) => b - a);
  }, [holidays, thisYear]);

  const sortedAll = useMemo(() => [...holidays].sort((a, b) => a.holiday_date.localeCompare(b.holiday_date)), [holidays]);
  const visible = useMemo(
    () => (year === "ALL" ? sortedAll : sortedAll.filter((h) => Number(h.holiday_date.slice(0, 4)) === year)),
    [sortedAll, year],
  );
  const upcoming = visible.filter((h) => h.holiday_date >= todayIso);
  const past = visible.filter((h) => h.holiday_date < todayIso).reverse();
  // A past year has nothing coming up, so its holidays are shown straight away instead of behind a button.
  const pastOpen = showPast || (upcoming.length === 0 && past.length > 0);

  // Next day off = the first coming holiday that everyone gets (optional ones are your choice) - whatever year is shown.
  const nextDayOff = sortedAll.find((h) => h.holiday_date >= todayIso && !h.is_optional) ?? null;

  // Upcoming holidays grouped under their month heading.
  const months = useMemo(() => {
    const groups: { key: string; title: string; items: Holiday[] }[] = [];
    for (const holiday of upcoming) {
      const d = parseIsoDate(holiday.holiday_date);
      const key = `${d.getFullYear()}-${d.getMonth()}`;
      const last = groups[groups.length - 1];
      if (last && last.key === key) last.items.push(holiday);
      else groups.push({ key, title: `${monthName(d.getMonth() + 1)} ${d.getFullYear()}`, items: [holiday] });
    }
    return groups;
  }, [upcoming]);

  const row = (holiday: Holiday, muted = false) => (
    <li key={holiday.id} className="flex items-center gap-4 rounded-2xl border border-sand-200 bg-white p-3 shadow-sm">
      <DateTile iso={holiday.holiday_date} muted={muted} />
      <div className="min-w-0 flex-1">
        <p className="break-words font-display text-lg font-bold text-stone-800">{holiday.name}</p>
        <p className="text-base text-stone-500">
          {weekdayName(holiday.holiday_date)}
          {!muted && ` · ${inDaysLabel(holiday.holiday_date)}`}
        </p>
        {holiday.is_optional ? (
          <p className="text-base font-semibold text-amber-700">Optional. You may choose to work.</p>
        ) : (
          <p className="text-base font-semibold text-brand-700">Day off for everyone</p>
        )}
        {holiday.description && <p className="break-words text-base text-stone-500">{holiday.description}</p>}
      </div>
      {canManage && (
        <div className="flex flex-shrink-0 items-center gap-1">
          <button
            type="button"
            aria-label={`Edit ${holiday.name}`}
            className="flex h-11 w-11 items-center justify-center rounded-xl text-stone-400 hover:bg-brand-50 hover:text-brand-600"
            onClick={() => openEdit(holiday)}
          >
            <Pencil className="h-5 w-5" aria-hidden="true" />
          </button>
          <button
            type="button"
            aria-label={`Delete ${holiday.name}`}
            className="flex h-11 w-11 items-center justify-center rounded-xl text-stone-400 hover:bg-sunset-50 hover:text-sunset-600"
            onClick={() => setDeleteTarget(holiday)}
          >
            <Trash2 className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
      )}
    </li>
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        icon={PartyPopper}
        title="Holidays"
        subtitle="Days when the company is closed"
        action={
          canManage && (
            <Button size="lg" className="w-full sm:w-auto" onClick={openCreate} icon={<Plus className="h-5 w-5" />}>
              Add a holiday
            </Button>
          )
        }
      />

      {!isLoading && !error && showNextYearReminder && (
        <div role="status" className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4">
          <CalendarDays className="mt-0.5 h-6 w-6 flex-shrink-0 text-amber-600" aria-hidden="true" />
          <p className="text-base text-amber-900">
            <span className="font-semibold">No holidays are set for {nextYear} yet.</span> Until they are added, every {nextYear}{" "}
            holiday will count as a normal working day in leave, attendance and pay.
          </p>
        </div>
      )}

      {isLoading ? (
        <LoadingState label="Loading the holidays..." />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <Card className="flex items-center gap-4 bg-brand-50/60">
              {nextDayOff ? (
                <>
                  <DateTile iso={nextDayOff.holiday_date} />
                  <div className="min-w-0">
                    <p className="text-base font-semibold text-stone-500">Your next holiday</p>
                    <p className="break-words font-display text-xl font-bold text-stone-800">{nextDayOff.name}</p>
                    <p className="text-base text-stone-600">
                      {formatDay(nextDayOff.holiday_date)} · {inDaysLabel(nextDayOff.holiday_date)}
                    </p>
                  </div>
                </>
              ) : (
                <p className="text-base text-stone-600">No more holidays are listed. Check again later.</p>
              )}
            </Card>
            <Card className="flex items-center gap-4">
              <span className="flex h-16 w-16 flex-shrink-0 items-center justify-center rounded-2xl bg-sand-100 text-stone-500">
                <Sun className="h-7 w-7" aria-hidden="true" />
              </span>
              <div>
                <p className="font-display text-lg font-bold text-stone-800">Every Sunday is a holiday</p>
                <p className="text-base text-stone-500">These are in addition to the days listed below.</p>
              </div>
            </Card>
          </div>

          {holidays.length > 0 && (
            <div role="group" aria-label="Show holidays of" className="flex flex-wrap gap-2">
              {[...years, "ALL" as const].map((y) => (
                <button
                  key={y}
                  type="button"
                  aria-pressed={year === y}
                  onClick={() => setYear(y)}
                  className={clsx(
                    "min-h-[44px] rounded-full px-5 text-base font-semibold ring-1 ring-inset transition-colors",
                    year === y ? "bg-stone-800 text-white ring-stone-800" : "bg-white text-stone-600 ring-sand-200 hover:bg-sand-50",
                  )}
                >
                  {y === "ALL" ? "All years" : y}
                  <span className="ml-1.5 opacity-70">
                    {y === "ALL" ? holidays.length : holidays.filter((h) => Number(h.holiday_date.slice(0, 4)) === y).length}
                  </span>
                </button>
              ))}
            </div>
          )}

          {holidays.length === 0 ? (
            <Card>
              <EmptyState title="No holidays listed yet" description={canManage ? "Tap “Add a holiday” to add the first one." : "The office has not added any holidays yet."} />
            </Card>
          ) : (
            <>
              {visible.length === 0 && (
                <Card>
                  <EmptyState title={`No holidays listed for ${year}`} description="Pick another year, or All years." />
                </Card>
              )}
              {months.length === 0 && past.length > 0 && year === thisYear && (
                <Card>
                  <EmptyState title="No more holidays this year" description="Past holidays are listed below." />
                </Card>
              )}
              {months.map((group) => (
                <section key={group.key} aria-label={group.title} className="flex flex-col gap-3">
                  <h2 className="font-display text-lg font-bold text-stone-800">{group.title}</h2>
                  <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">{group.items.map((h) => row(h))}</ul>
                </section>
              ))}

              {past.length > 0 && (
                <section aria-label="Holidays that have passed" className="flex flex-col gap-3">
                  <button
                    type="button"
                    aria-expanded={pastOpen}
                    onClick={() => setShowPast((s) => !s)}
                    className="flex min-h-[48px] w-fit items-center gap-2 rounded-xl px-3 text-base font-semibold text-stone-600 hover:bg-sand-100"
                  >
                    <ChevronDown className={clsx("h-5 w-5 transition-transform", pastOpen && "rotate-180")} aria-hidden="true" />
                    {pastOpen ? "Hide" : "Show"} holidays that have passed ({past.length})
                  </button>
                  {pastOpen && <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">{past.map((h) => row(h, true))}</ul>}
                </section>
              )}
            </>
          )}
        </>
      )}

      <Sheet
        title={editTarget ? "Edit holiday" : "Add a holiday"}
        isOpen={isSheetOpen}
        onClose={() => setIsSheetOpen(false)}
        footer={
          <>
            <Button variant="secondary" size="lg" onClick={() => setIsSheetOpen(false)}>Not now</Button>
            <Button size="lg" isLoading={isSaving} onClick={handleSave} icon={<CalendarDays className="h-5 w-5" />}>
              {editTarget ? "Save changes" : "Save holiday"}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-5">
          <InputField label="Name of the holiday" name="name" required value={name} onChange={(e) => setName(e.target.value)} />
          <InputField label="Date" name="holiday_date" type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
          <TextareaField label="Note (optional)" name="description" value={description} onChange={(e) => setDescription(e.target.value)} />
          <label className="flex min-h-[48px] cursor-pointer items-center gap-3 rounded-xl border-2 border-sand-200 px-4 text-base font-medium text-stone-700">
            <input
              type="checkbox"
              className="h-6 w-6 rounded border-2 border-sand-300 text-brand-600 focus:ring-brand-300"
              checked={isOptional}
              onChange={(e) => setIsOptional(e.target.checked)}
            />
            Optional holiday (staff may choose to work)
          </label>
          {formError && (
            <div role="alert" className="flex items-start gap-2 rounded-xl bg-rose-50 p-3 text-base font-medium text-rose-800">
              <XCircle className="mt-0.5 h-5 w-5 flex-shrink-0" aria-hidden="true" />
              {formError}
            </div>
          )}
        </div>
      </Sheet>

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        title="Delete this holiday?"
        message={`"${deleteTarget?.name}" will be removed for everyone, and attendance will treat that day as a normal working day. This can't be undone.`}
        confirmLabel="Yes, delete it"
        isDangerous
        isLoading={isSaving}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
