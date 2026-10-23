import { CheckCircle2, FileWarning } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Card } from "@/components/ui/Card";
import { documentService } from "@/services/documentService";
import type { ExpiringDocuments } from "@/types";
import { EXPIRY_WARNING_DAYS } from "@/utils/documentExpiry";
import { formatDateLong, plural } from "@/utils/friendly";

// Company-wide view of papers that need renewing, for whoever can open other people's documents
// (document:manage_all). Each person only ever saw their own warning before.
export function DocumentsToRenew() {
  const [data, setData] = useState<ExpiringDocuments | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    documentService
      .expiring(EXPIRY_WARNING_DAYS)
      .then((result) => !cancelled && setData(result))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, []);

  if (failed) return null;
  if (!data) return null;

  if (data.total === 0) {
    return (
      <Card className="flex items-center gap-3">
        <CheckCircle2 className="h-5 w-5 flex-shrink-0 text-success-500" aria-hidden="true" />
        <p className="text-sm text-stone-600">No document has expired or expires in the next {EXPIRY_WARNING_DAYS} days.</p>
      </Card>
    );
  }

  return (
    <Card>
      <div className="mb-3 flex items-center gap-2">
        <FileWarning className="h-4 w-4 text-amber-600" aria-hidden="true" />
        <h2 className="font-display text-sm font-semibold text-stone-700">
          Documents to renew ({data.total})
        </h2>
        <span className="text-xs text-stone-400">expired, or expiring within {plural(EXPIRY_WARNING_DAYS, "day")}</span>
      </div>
      <ul className="flex max-h-72 flex-col divide-y divide-sand-100 overflow-y-auto">
        {data.items.map((doc) => (
          <li key={doc.document_id}>
            <Link to={`/employees/${doc.employee_id}`} className="flex flex-wrap items-center justify-between gap-2 py-2.5 hover:bg-sand-50">
              <span className="text-sm text-stone-800">
                <span className="font-semibold">{doc.employee_name}</span>
                <span className="text-stone-400"> · {doc.employee_code}</span>
                <span className="text-stone-500"> · {doc.document_type_name}</span>
              </span>
              <span className={doc.days_left < 0 ? "text-sm font-semibold text-sunset-600" : "text-sm font-semibold text-amber-700"}>
                {doc.days_left < 0
                  ? `Expired ${formatDateLong(doc.expiry_date)} (${plural(-doc.days_left, "day")} ago)`
                  : doc.days_left === 0
                    ? "Expires today"
                    : `Expires ${formatDateLong(doc.expiry_date)} (in ${plural(doc.days_left, "day")})`}
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {data.total > data.items.length && (
        <p className="mt-2 text-xs text-stone-400">Showing the {data.items.length} soonest of {data.total}.</p>
      )}
    </Card>
  );
}
