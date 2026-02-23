/**
 * 리포트 생성 및 다운로드
 *
 * PDF 리포트 생성, 이벤트 데이터 CSV/Excel 내보내기
 */

import { useState, useEffect, useCallback } from "react";
import { FileText, Download, FileSpreadsheet, RefreshCcw, Calendar, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { apiCall } from "@/lib/auth";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { useMonitoringStore } from "@/store/monitoring";

interface Report {
  filename: string;
  created_at: string;
  size: number;
}

export function ReportView() {
  const { t, i18n } = useTranslation();
  const selectedRoomId = useMonitoringStore((s) => s.selectedRoomId);
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [days, setDays] = useState(30);
  const [exportFormat, setExportFormat] = useState<"csv" | "xlsx">("csv");

  const fetchReports = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiCall("/api/reports");
      if (res.ok) {
        const data = await res.json();
        setReports(data);
      }
    } catch {
      toast.error(t("report.listError"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchReports();
  }, [fetchReports]);

  const handleGenerate = async () => {
    setGenerating(true);
    const roomParam = selectedRoomId !== null ? `&room_id=${selectedRoomId}` : "";
    try {
      const res = await apiCall(`/api/reports/generate?days=${days}${roomParam}`, {
        method: "POST",
      });
      if (res.ok) {
        toast.success(t("report.generateSuccess", { days }));
        fetchReports();
      } else {
        toast.error(t("report.generateError"));
      }
    } catch {
      toast.error(t("report.generateException"));
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = async (filename: string) => {
    try {
      const res = await apiCall(`/api/reports/${filename}`);
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        toast.success(t("report.downloadSuccess"));
      } else {
        toast.error(t("report.downloadError"));
      }
    } catch {
      toast.error(t("report.downloadException"));
    }
  };

  const handleExport = async () => {
    const roomParam = selectedRoomId !== null ? `&room_id=${selectedRoomId}` : "";
    try {
      const res = await apiCall(`/api/events/export?format=${exportFormat}&days=${days}${roomParam}`);
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `events_${days}days.${exportFormat}`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        toast.success(t("report.exportSuccess", { format: exportFormat.toUpperCase() }));
      } else {
        toast.error(t("report.exportError"));
      }
    } catch {
      toast.error(t("report.exportException"));
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">{t("report.title")}</h2>
          <p className="text-sm text-muted-foreground">
            {t("report.subtitle")}
          </p>
        </div>
        <Button size="sm" variant="ghost" onClick={fetchReports}>
          <RefreshCcw className="h-4 w-4" />
        </Button>
      </div>

      {/* 리포트 생성 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <FileText className="h-4 w-4 text-primary" />
            {t("report.generate")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <Calendar className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">{t("report.period")}:</span>
            </div>
            <div className="flex gap-2">
              {[7, 14, 30, 90].map((d) => (
                <Button
                  key={d}
                  size="sm"
                  variant={days === d ? "default" : "outline"}
                  onClick={() => setDays(d)}
                >
                  {d}{t("report.days")}
                </Button>
              ))}
            </div>
          </div>
          <Button
            className="w-full"
            onClick={handleGenerate}
            disabled={generating}
          >
            {generating ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <FileText className="h-4 w-4 mr-2" />
            )}
            {generating ? t("report.generating") : t("report.generateDays", { days })}
          </Button>
        </CardContent>
      </Card>

      {/* 이벤트 데이터 내보내기 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <FileSpreadsheet className="h-4 w-4 text-primary" />
            {t("common.export")} {t("report.exportData")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant={exportFormat === "csv" ? "default" : "outline"}
              onClick={() => setExportFormat("csv")}
            >
              CSV
            </Button>
            <Button
              size="sm"
              variant={exportFormat === "xlsx" ? "default" : "outline"}
              onClick={() => setExportFormat("xlsx")}
            >
              Excel
            </Button>
          </div>
          <Button className="w-full" variant="outline" onClick={handleExport}>
            <Download className="h-4 w-4 mr-2" />
            {exportFormat === "csv" ? t("report.exportCSV") : t("report.exportExcel")} ({days}{t("report.days")})
          </Button>
        </CardContent>
      </Card>

      {/* 생성된 리포트 목록 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">
            {t("report.availableReports")}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading && !reports.length ? (
            <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
              {t("common.loading")}
            </div>
          ) : reports.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 text-muted-foreground text-sm">
              <FileText className="h-8 w-8 mb-2 opacity-50" />
              {t("report.noReports")}
            </div>
          ) : (
            <div className="space-y-2">
              {reports.map((report) => (
                <div
                  key={report.filename}
                  className="flex items-center justify-between p-3 border rounded-lg hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <FileText className="h-5 w-5 text-muted-foreground" />
                    <div>
                      <p className="text-sm font-medium">{report.filename}</p>
                      <p className="text-xs text-muted-foreground">
                        {new Date(report.created_at).toLocaleString(i18n.language === "ko" ? "ko-KR" : "en-US")}
                        {" · "}
                        {formatFileSize(report.size)}
                      </p>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleDownload(report.filename)}
                  >
                    <Download className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
