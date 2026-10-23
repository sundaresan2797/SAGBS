import { useEffect, useState } from "react";

import { documentService } from "@/services/documentService";
import type { DocumentUploadPolicy } from "@/types";

// The rule changes rarely, so one fetch per page load is plenty.
let cached: DocumentUploadPolicy | null = null;

/** The server's real upload rules (max size, allowed file types), or null while loading / if they
 * could not be loaded (screens then fall back to a conservative default - see DocumentsPage). */
export function useDocumentPolicy(): DocumentUploadPolicy | null {
  const [policy, setPolicy] = useState<DocumentUploadPolicy | null>(cached);

  useEffect(() => {
    if (cached) return;
    let cancelled = false;
    documentService
      .policy()
      .then((result) => {
        cached = result;
        if (!cancelled) setPolicy(result);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  return policy;
}
