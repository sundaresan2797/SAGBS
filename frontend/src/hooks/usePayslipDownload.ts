import { useState } from "react";

import { useToast } from "@/hooks/useToast";
import { getBlobErrorMessage } from "@/services/api";
import { payrollService } from "@/services/payrollService";
import { triggerBlobDownload } from "@/utils/downloadFile";

/** One place that knows how to fetch a payslip PDF, save it, and explain a failure kindly. */
export function usePayslipDownload() {
  const { showToast } = useToast();
  const [downloadingId, setDownloadingId] = useState<number | null>(null);

  const download = async (paymentId: number) => {
    setDownloadingId(paymentId);
    try {
      const { blob, filename } = await payrollService.downloadPayslip(paymentId);
      triggerBlobDownload(blob, filename);
    } catch (err) {
      showToast(await getBlobErrorMessage(err, "Couldn't download this payslip."), "error");
    } finally {
      setDownloadingId(null);
    }
  };

  return { download, downloadingId };
}
