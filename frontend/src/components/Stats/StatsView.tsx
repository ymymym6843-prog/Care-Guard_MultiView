/**
 * 통계 대시보드
 *
 * 일별/시간대별 낙상 이벤트 차트와 요약 통계를 표시합니다.
 */

import { useState, useEffect, useCallback } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip,
  ResponsiveContainer, Cell,
} from "recharts";
import {
  TrendingDown, AlertTriangle, Clock, CheckCircle,
  Calendar, RefreshCcw,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { apiCall } from "@/lib/auth";
import { useTranslation } from "react-i18next";
import { useMonitoringStore } from "@/store/monitoring";

interface DailyData {
  date: string;
  warning: number;
  danger: number;
  total: number;
}

interface HourlyData {
  hour: number;
  count: number;
}

interface SummaryData {
  period_days: number;
  total_events: number;
  danger_events: number;
  warning_events: number;
  acknowledged: number;
  unacknowledged: number;
  avg_response_seconds: number;
  acknowledgment_rate: number;
}

function SummaryCard({
  icon,
  label,
  value,
  subtext,
  variant = "default",
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  subtext?: string;
  variant?: "default" | "danger" | "warning" | "safe";
}) {
  const colorMap = {
    default: "text-foreground",
    danger: "text-danger",
    warning: "text-warning",
    safe: "text-safe",
  };

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className={`text-2xl font-bold font-mono ${colorMap[variant]}`}>
              {value}
            </p>
            {subtext && (
              <p className="text-xs text-muted-foreground mt-1">{subtext}</p>
            )}
          </div>
          <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center">
            {icon}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function StatsView() {
  const { t } = useTranslation();
  const selectedRoomId = useMonitoringStore((s) => s.selectedRoomId);
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [daily, setDaily] = useState<DailyData[]>([]);
  const [hourly, setHourly] = useState<HourlyData[]>([]);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);

  const fetchStats = useCallback(async () => {
    setLoading(true);

    const roomParam = selectedRoomId !== null ? `&room_id=${selectedRoomId}` : "";

    try {
      const [summaryRes, dailyRes, hourlyRes] = await Promise.all([
        apiCall(`/api/stats/summary?days=${days}${roomParam}`),
        apiCall(`/api/stats/daily?days=${days}${roomParam}`),
        apiCall(`/api/stats/hourly?days=${Math.min(days, 30)}${roomParam}`),
      ]);

      if (summaryRes.ok) setSummary(await summaryRes.json());
      if (dailyRes.ok) setDaily(await dailyRes.json());
      if (hourlyRes.ok) setHourly(await hourlyRes.json());
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [days, selectedRoomId]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  if (loading && !summary) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground text-sm">{t("stats.loading")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">{t("stats.title")}</h2>
          <p className="text-sm text-muted-foreground">
            {t("stats.subtitle", { days })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {[7, 14, 30, 90].map((d) => (
            <Button
              key={d}
              size="sm"
              variant={days === d ? "default" : "outline"}
              onClick={() => setDays(d)}
            >
              {d}{t("stats.days")}
            </Button>
          ))}
          <Button size="sm" variant="ghost" onClick={fetchStats}>
            <RefreshCcw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* 요약 카드 */}
      {summary && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <SummaryCard
            icon={<AlertTriangle className="h-5 w-5 text-muted-foreground" />}
            label={t("stats.totalEvents")}
            value={summary.total_events}
            subtext={`${t("dashboard.status.danger")} ${summary.danger_events} / ${t("dashboard.status.warning")} ${summary.warning_events}`}
          />
          <SummaryCard
            icon={<TrendingDown className="h-5 w-5 text-danger" />}
            label={t("stats.dangerEvents")}
            value={summary.danger_events}
            variant="danger"
          />
          <SummaryCard
            icon={<CheckCircle className="h-5 w-5 text-safe" />}
            label={t("stats.acknowledgmentRate")}
            value={`${summary.acknowledgment_rate}%`}
            subtext={`${summary.acknowledged}${t("stats.acknowledged")}`}
            variant="safe"
          />
          <SummaryCard
            icon={<Clock className="h-5 w-5 text-warning" />}
            label={t("stats.avgResponseTime")}
            value={`${summary.avg_response_seconds}${t("dashboard.units.seconds")}`}
            variant="warning"
          />
        </div>
      )}

      {/* 차트 영역 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 일별 이벤트 차트 */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Calendar className="h-4 w-4 text-primary" />
              {t("stats.dailyTrend")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {daily.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={daily}>
                  <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10 }}
                    tickFormatter={(v: string) => v.slice(5)} // MM-DD
                  />
                  <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                  <RechartsTooltip
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px",
                      fontSize: "12px",
                    }}
                  />
                  <Bar dataKey="warning" fill="hsl(40, 96%, 53%)" name={t("dashboard.status.warning")} radius={[2, 2, 0, 0]} />
                  <Bar dataKey="danger" fill="hsl(0, 84%, 60%)" name={t("dashboard.status.danger")} radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[250px] text-muted-foreground text-sm">
                {t("stats.noData")}
              </div>
            )}
          </CardContent>
        </Card>

        {/* 시간대별 히트맵 */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Clock className="h-4 w-4 text-primary" />
              {t("stats.hourlyFrequency")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {hourly.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={hourly}>
                  <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                  <XAxis
                    dataKey="hour"
                    tick={{ fontSize: 10 }}
                    tickFormatter={(v: number) => `${v}${t("dashboard.units.hour")}`}
                  />
                  <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                  <RechartsTooltip
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px",
                      fontSize: "12px",
                    }}
                    formatter={(value: number) => [`${value}${t("dashboard.units.count")}`, t("stats.event")]}
                    labelFormatter={(hour: number) => `${hour}${t("dashboard.units.hour")}`}
                  />
                  <Bar dataKey="count" name={t("stats.event")} radius={[2, 2, 0, 0]}>
                    {hourly.map((entry, index) => (
                      <Cell
                        key={index}
                        fill={
                          entry.count === 0
                            ? "hsl(var(--muted))"
                            : entry.count > 5
                              ? "hsl(0, 84%, 60%)"
                              : entry.count > 2
                                ? "hsl(40, 96%, 53%)"
                                : "hsl(142, 76%, 36%)"
                        }
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[250px] text-muted-foreground text-sm">
                {t("stats.noData")}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
