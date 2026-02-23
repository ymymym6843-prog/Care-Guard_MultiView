import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AlertTriangle, Upload, Trash2, Loader2, ChevronLeft, ChevronRight, Image, X, AlertCircle } from "lucide-react";
import { apiCall } from "@/lib/auth";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

interface FalseReport {
  id: number;
  report_type: string;
  notes: string | null;
  image_path: string | null;
  event_id: number | null;
  uploaded_by: string;
  created_at: string;
}

interface FalseReportListResponse {
  items: FalseReport[];
  total: number;
  page: number;
  size: number;
}

interface FalseReportSummary {
  total: number;
  false_positive: number;
  false_negative: number;
  this_week: number;
  needs_attention: boolean;
}

export function FalseReportManager() {
  const { t } = useTranslation();

  // Form state
  const [reportType, setReportType] = useState<string>("false_positive");
  const [notes, setNotes] = useState("");
  const [eventId, setEventId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Summary state
  const [summary, setSummary] = useState<FalseReportSummary | null>(null);

  // List state
  const [reports, setReports] = useState<FalseReport[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filterType, setFilterType] = useState<string>("all");
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [previewId, setPreviewId] = useState<number | null>(null);

  const PAGE_SIZE = 5;

  const fetchSummary = async () => {
    try {
      const res = await apiCall("/api/false-reports/summary");
      if (res.ok) {
        const data: FalseReportSummary = await res.json();
        setSummary(data);
      }
    } catch {
      // silent - summary is non-critical
    }
  };

  const fetchReports = async (p = page) => {
    try {
      setLoading(true);
      const params = new URLSearchParams({ page: String(p), size: String(PAGE_SIZE) });
      if (filterType !== "all") params.set("report_type", filterType);

      const res = await apiCall(`/api/false-reports/?${params}`);
      if (res.ok) {
        const data: FalseReportListResponse = await res.json();
        setReports(data.items);
        setTotal(data.total);
        setPage(data.page);
      }
    } catch {
      console.error("보고 목록 로드 실패");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSummary();
    fetchReports(1);
  }, [filterType]);

  const handleSubmit = async () => {
    if (!reportType) return;

    try {
      setSubmitting(true);
      const formData = new FormData();
      formData.append("report_type", reportType);
      formData.append("notes", notes);
      if (eventId) formData.append("event_id", eventId);
      if (file) formData.append("file", file);

      const res = await apiCall("/api/false-reports/", {
        method: "POST",
        body: formData,
      });

      if (res.ok) {
        const data = await res.json();
        toast.success(t("dashboard.falseReport.toasts.createSuccess"));
        if (data.alert) {
          toast.info(data.alert, { duration: 6000 });
        }
        setNotes("");
        setEventId("");
        setFile(null);
        // Reset file input
        const fileInput = document.getElementById("false-report-file") as HTMLInputElement;
        if (fileInput) fileInput.value = "";
        fetchSummary();
        fetchReports(1);
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || t("dashboard.falseReport.toasts.createError"));
      }
    } catch {
      toast.error(t("dashboard.falseReport.toasts.createError"));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm(t("dashboard.falseReport.toasts.deleteConfirm"))) return;

    try {
      setDeleting(id);
      const res = await apiCall(`/api/false-reports/${id}`, { method: "DELETE" });
      if (res.ok) {
        toast.success(t("dashboard.falseReport.toasts.deleteSuccess"));
        fetchSummary();
        fetchReports();
      } else {
        toast.error(t("dashboard.falseReport.toasts.deleteError"));
      }
    } catch {
      toast.error(t("dashboard.falseReport.toasts.deleteError"));
    } finally {
      setDeleting(null);
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleString();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-orange-500" />
          {t("dashboard.falseReport.title")}
        </CardTitle>
        <CardDescription>
          {t("dashboard.falseReport.description")}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Summary Stats */}
        {summary && (
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-3">
              <div className={`rounded-lg border p-3 text-center ${summary.needs_attention ? "border-orange-400 bg-orange-50 dark:bg-orange-950/30" : ""}`}>
                <p className="text-2xl font-bold">{summary.total}</p>
                <p className="text-xs text-muted-foreground">{t("dashboard.falseReport.summary.total")}</p>
              </div>
              <div className="rounded-lg border p-3 text-center">
                <p className="text-2xl font-bold text-red-500">{summary.false_positive}</p>
                <p className="text-xs text-muted-foreground">{t("dashboard.falseReport.summary.falsePositive")}</p>
              </div>
              <div className="rounded-lg border p-3 text-center">
                <p className="text-2xl font-bold text-blue-500">{summary.false_negative}</p>
                <p className="text-xs text-muted-foreground">{t("dashboard.falseReport.summary.falseNegative")}</p>
              </div>
            </div>
            {summary.this_week > 0 && (
              <p className="text-xs text-muted-foreground text-center">
                {t("dashboard.falseReport.summary.thisWeek", { count: summary.this_week })}
              </p>
            )}
            {summary.needs_attention && (
              <div className="flex items-center gap-2 rounded-lg border border-orange-400 bg-orange-50 dark:bg-orange-950/30 p-3">
                <AlertCircle className="h-4 w-4 text-orange-500 shrink-0" />
                <p className="text-sm text-orange-700 dark:text-orange-400">
                  {t("dashboard.falseReport.summary.attentionBanner")}
                </p>
              </div>
            )}
          </div>
        )}

        {/* Report Form */}
        <div className="space-y-4 p-4 rounded-lg border bg-muted/30">
          <h3 className="text-sm font-medium">{t("dashboard.falseReport.newReport")}</h3>

          <div className="grid gap-4 sm:grid-cols-2">
            {/* Report Type */}
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground font-medium">
                {t("dashboard.falseReport.reportType")}
              </label>
              <Select value={reportType} onValueChange={setReportType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="false_positive">
                    {t("dashboard.falseReport.types.falsePositive")}
                  </SelectItem>
                  <SelectItem value="false_negative">
                    {t("dashboard.falseReport.types.falseNegative")}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Event ID */}
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground font-medium">
                {t("dashboard.falseReport.eventId")}
              </label>
              <input
                type="number"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                placeholder={t("dashboard.falseReport.eventIdPlaceholder")}
                value={eventId}
                onChange={(e) => setEventId(e.target.value)}
              />
            </div>
          </div>

          {/* Notes */}
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground font-medium">
              {t("dashboard.falseReport.notes")}
            </label>
            <textarea
              className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 resize-none"
              placeholder={t("dashboard.falseReport.notesPlaceholder")}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>

          {/* File Upload */}
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground font-medium">
              {t("dashboard.falseReport.image")}
            </label>
            <div className="flex items-center gap-3">
              <div className="relative">
                <input
                  id="false-report-file"
                  type="file"
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                  accept="image/*"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                />
                <Button size="sm" variant="outline" type="button">
                  <Upload className="h-4 w-4 mr-1" />
                  {t("dashboard.falseReport.selectImage")}
                </Button>
              </div>
              {file && (
                <span className="text-xs text-muted-foreground truncate max-w-[200px]">
                  {file.name}
                </span>
              )}
            </div>
          </div>

          {/* Submit */}
          <Button onClick={handleSubmit} disabled={submitting} className="w-full sm:w-auto">
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-1" />
                {t("dashboard.falseReport.submitting")}
              </>
            ) : (
              t("dashboard.falseReport.submit")
            )}
          </Button>
        </div>

        {/* Report List */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium">
              {t("dashboard.falseReport.reportList")} ({total})
            </h3>
            <Select value={filterType} onValueChange={setFilterType}>
              <SelectTrigger className="w-[160px] h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("dashboard.falseReport.filter.all")}</SelectItem>
                <SelectItem value="false_positive">{t("dashboard.falseReport.filter.falsePositive")}</SelectItem>
                <SelectItem value="false_negative">{t("dashboard.falseReport.filter.falseNegative")}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {loading ? (
            <div className="flex justify-center p-6">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : reports.length === 0 ? (
            <div className="text-center text-sm text-muted-foreground py-8">
              {t("dashboard.falseReport.noReports")}
            </div>
          ) : (
            <div className="space-y-3">
              {reports.map((r) => (
                <div
                  key={r.id}
                  className="p-3 rounded-lg border bg-card flex items-start justify-between gap-3"
                >
                  <div className="space-y-1 flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge
                        variant={r.report_type === "false_positive" ? "destructive" : "secondary"}
                        className="text-[10px] h-5"
                      >
                        {r.report_type === "false_positive"
                          ? t("dashboard.falseReport.types.falsePositive")
                          : t("dashboard.falseReport.types.falseNegative")}
                      </Badge>
                      {r.event_id && (
                        <span className="text-[10px] text-muted-foreground">
                          Event #{r.event_id}
                        </span>
                      )}
                      {r.image_path && (
                        <Badge
                          variant="outline"
                          className="text-[10px] h-5 cursor-pointer hover:bg-muted"
                          onClick={() => setPreviewId(previewId === r.id ? null : r.id)}
                        >
                          <Image className="h-3 w-3 mr-0.5" />
                          {t("dashboard.falseReport.hasImage")}
                        </Badge>
                      )}
                    </div>
                    {r.notes && (
                      <p className="text-xs text-foreground break-all">{r.notes}</p>
                    )}
                    {/* 이미지 미리보기 */}
                    {previewId === r.id && r.image_path && (
                      <div className="relative mt-2">
                        <img
                          src={`/api/false-reports/${r.id}/image`}
                          alt="Report screenshot"
                          className="rounded-md border max-h-[300px] object-contain bg-muted"
                          loading="lazy"
                        />
                        <Button
                          size="sm"
                          variant="ghost"
                          className="absolute top-1 right-1 h-6 w-6 p-0 bg-background/80"
                          onClick={() => setPreviewId(null)}
                        >
                          <X className="h-3 w-3" />
                        </Button>
                      </div>
                    )}
                    <p className="text-[10px] text-muted-foreground">
                      {r.uploaded_by} &middot; {formatDate(r.created_at)}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive hover:text-destructive shrink-0"
                    disabled={deleting === r.id}
                    onClick={() => handleDelete(r.id)}
                  >
                    {deleting === r.id ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Trash2 className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              ))}
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-2">
              <Button
                size="sm"
                variant="outline"
                disabled={page <= 1}
                onClick={() => fetchReports(page - 1)}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-xs text-muted-foreground">
                {page} / {totalPages}
              </span>
              <Button
                size="sm"
                variant="outline"
                disabled={page >= totalPages}
                onClick={() => fetchReports(page + 1)}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
