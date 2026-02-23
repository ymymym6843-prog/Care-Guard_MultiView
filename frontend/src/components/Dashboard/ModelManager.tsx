import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Brain, Check, Loader2 } from "lucide-react";
import { apiCall } from "@/lib/auth";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

interface ModelInfo {
    name: string;
    size: number;
    modified: number;
    is_active: boolean;
}

export function ModelManager() {
    const { t } = useTranslation();
    const [models, setModels] = useState<ModelInfo[]>([]);
    const [loading, setLoading] = useState(false);
    const [switching, setSwitching] = useState<string | null>(null);

    const fetchModels = async () => {
        try {
            setLoading(true);
            const res = await apiCall("/api/models/");
            if (res.ok) {
                const data = await res.json();
                setModels(data);
            } else {
                toast.error(t("dashboard.modelManager.toasts.listError"));
            }
        } catch (error) {
            console.error("모델 목록 로드 실패:", error);
            toast.error(t("dashboard.modelManager.toasts.connectionError"));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchModels();
    }, []);

    const handleSwitchModel = async (modelName: string) => {
        if (!confirm(`${t("dashboard.modelManager.toasts.switchConfirm")}\n\n${t("dashboard.modelManager.target")}: ${modelName}\n\n${t("dashboard.modelManager.toasts.switchWarning")}`)) return;

        try {
            setSwitching(modelName);
            const res = await apiCall("/api/models/active", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ model_name: modelName }),
            });

            if (res.ok) {
                toast.success(t("dashboard.modelManager.toasts.switchSuccess"));
                fetchModels();
            } else {
                toast.error(t("dashboard.modelManager.toasts.switchError"));
            }
        } catch {
            toast.error(t("dashboard.modelManager.toasts.serverError"));
        } finally {
            setSwitching(null);
        }
    };

    const formatSize = (bytes: number) => {
        return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    };

    const getModelInfo = (modelName: string) => {
        if (modelName.includes("yolo11n")) {
            return {
                title: t("dashboard.modelManager.models.nano.title"),
                speed: t("dashboard.modelManager.models.nano.speed"),
                accuracy: t("dashboard.modelManager.models.nano.accuracy"),
                description: t("dashboard.modelManager.models.nano.description"),
                badge: t("dashboard.modelManager.models.nano.badge"),
                badgeVariant: "default" as const
            };
        } else if (modelName.includes("yolo11s")) {
            return {
                title: t("dashboard.modelManager.models.small.title"),
                speed: t("dashboard.modelManager.models.small.speed"),
                accuracy: t("dashboard.modelManager.models.small.accuracy"),
                description: t("dashboard.modelManager.models.small.description"),
                badge: t("dashboard.modelManager.models.small.badge"),
                badgeVariant: "secondary" as const
            };
        } else if (modelName.includes("yolo26n")) {
            return {
                title: t("dashboard.modelManager.models.yolo26n.title"),
                speed: t("dashboard.modelManager.models.yolo26n.speed"),
                accuracy: t("dashboard.modelManager.models.yolo26n.accuracy"),
                description: t("dashboard.modelManager.models.yolo26n.description"),
                badge: t("dashboard.modelManager.models.yolo26n.badge"),
                badgeVariant: "default" as const
            };
        } else if (modelName.includes("yolo26s")) {
            return {
                title: t("dashboard.modelManager.models.yolo26s.title"),
                speed: t("dashboard.modelManager.models.yolo26s.speed"),
                accuracy: t("dashboard.modelManager.models.yolo26s.accuracy"),
                description: t("dashboard.modelManager.models.yolo26s.description"),
                badge: t("dashboard.modelManager.models.yolo26s.badge"),
                badgeVariant: "secondary" as const
            };
        } else if (modelName.includes("fall_classifier") || modelName.includes("gru")) {
            return {
                title: t("dashboard.modelManager.models.gru.title"),
                speed: t("dashboard.modelManager.models.gru.speed"),
                accuracy: t("dashboard.modelManager.models.gru.accuracy"),
                description: t("dashboard.modelManager.models.gru.description"),
                badge: t("dashboard.modelManager.models.gru.badge"),
                badgeVariant: "outline" as const
            };
        }
        return {
            title: t("dashboard.modelManager.models.custom.title") + " (" + modelName + ")",
            speed: t("dashboard.modelManager.models.custom.speed"),
            accuracy: t("dashboard.modelManager.models.custom.accuracy"),
            description: t("dashboard.modelManager.models.custom.description"),
            badge: t("dashboard.modelManager.models.custom.badge"),
            badgeVariant: "outline" as const
        };
    };


    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Brain className="h-5 w-5 text-primary" />
                    {t("dashboard.modelManager.title")}
                </CardTitle>
                <CardDescription>
                    {t("dashboard.modelManager.description")}
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
                {/* YOLO 포즈 감지 모델 */}
                <div className="space-y-4">
                    <h3 className="text-sm font-medium text-muted-foreground">{t("dashboard.modelManager.yoloModels")}</h3>
                    {loading ? (
                        <div className="flex justify-center p-4">
                            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                        </div>
                    ) : (
                        <div className="grid gap-3">
                            {models
                                .filter(model => model.name.includes("yolo"))
                                .map((model) => {
                                    const modelInfo = getModelInfo(model.name);
                                    return (
                                        <div
                                            key={model.name}
                                            className={`p-4 rounded-lg border transition-all ${model.is_active ? "bg-primary/5 border-primary shadow-sm" : "border-border hover:bg-muted/50"
                                                }`}
                                        >
                                            <div className="flex items-start justify-between gap-4">
                                                <div className="flex items-start gap-3 flex-1">
                                                    <div className={`p-2 rounded-full shrink-0 ${model.is_active ? "bg-primary/20" : "bg-muted"}`}>
                                                        <Brain className="h-4 w-4" />
                                                    </div>
                                                    <div className="space-y-2 flex-1">
                                                        <div className="flex items-center gap-2 flex-wrap">
                                                            <p className="font-semibold text-sm">{modelInfo.title}</p>
                                                            <Badge variant={modelInfo.badgeVariant} className="text-[10px] h-5">
                                                                {modelInfo.badge}
                                                            </Badge>
                                                            {model.is_active && (
                                                                <Badge variant="default" className="text-[10px] h-5 bg-primary">
                                                                    {t("dashboard.modelManager.active")}
                                                                </Badge>
                                                            )}
                                                        </div>
                                                        <p className="text-xs text-muted-foreground">{model.name}</p>
                                                        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                                                            <div>
                                                                <span className="text-muted-foreground">{t("dashboard.modelManager.speed")}:</span>{" "}
                                                                <span className="font-medium">{modelInfo.speed}</span>
                                                            </div>
                                                            <div>
                                                                <span className="text-muted-foreground">{t("dashboard.modelManager.accuracy")}:</span>{" "}
                                                                <span className="font-medium">{modelInfo.accuracy}</span>
                                                            </div>
                                                            <div className="col-span-2">
                                                                <span className="text-muted-foreground">{t("dashboard.modelManager.size")}:</span>{" "}
                                                                <span className="font-medium">{formatSize(model.size)}</span>
                                                            </div>
                                                        </div>
                                                        <p className="text-xs text-muted-foreground italic pt-1">
                                                            💡 {modelInfo.description}
                                                        </p>
                                                    </div>
                                                </div>

                                                <div className="shrink-0">
                                                    {model.is_active ? (
                                                        <Button size="sm" variant="ghost" disabled className="text-primary">
                                                            <Check className="h-4 w-4 mr-1" />
                                                            {t("dashboard.modelManager.active")}
                                                        </Button>
                                                    ) : (
                                                        <Button
                                                            size="sm"
                                                            variant="outline"
                                                            disabled={switching === model.name}
                                                            onClick={() => handleSwitchModel(model.name)}
                                                        >
                                                            {switching === model.name ? (
                                                                <Loader2 className="h-4 w-4 animate-spin" />
                                                            ) : (
                                                                t("dashboard.modelManager.switch")
                                                            )}
                                                        </Button>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                        </div>
                    )}

                    {/* YOLO26 정보 메시지 */}
                    <div className="mt-4 p-3 rounded-lg bg-muted/50 border border-border">
                        <div className="flex items-start gap-2">
                            <div className="text-muted-foreground text-xs mt-0.5">ℹ️</div>
                            <div className="flex-1 text-xs text-muted-foreground">
                                <p className="font-medium mb-1">{t("dashboard.modelManager.yolo26Info.title")}</p>
                                <p>{t("dashboard.modelManager.yolo26Info.description")}</p>
                            </div>
                        </div>
                    </div>
                </div>

                {/* GRU 낙상 분류기 (항상 활성화) */}
                {models.filter(model => model.name.includes("fall_classifier") || model.name.includes("gru")).length > 0 && (
                    <>
                        <div className="h-px bg-border my-4" />
                        <div className="space-y-4">
                            <div className="flex items-center gap-2">
                                <Check className="h-4 w-4 text-primary" />
                                <h3 className="text-sm font-medium text-muted-foreground">{t("dashboard.modelManager.classifierTitle")}</h3>
                            </div>
                            <div className="grid gap-3">
                                {models
                                    .filter(model => model.name.includes("fall_classifier") || model.name.includes("gru"))
                                    .map((model) => {
                                        const modelInfo = getModelInfo(model.name);
                                        return (
                                            <div
                                                key={model.name}
                                                className="p-4 rounded-lg border border-primary/30 bg-primary/5"
                                            >
                                                <div className="flex items-start gap-3">
                                                    <div className="p-2 rounded-full bg-primary/20 shrink-0">
                                                        <Brain className="h-4 w-4 text-primary" />
                                                    </div>
                                                    <div className="space-y-2 flex-1">
                                                        <div className="flex items-center gap-2 flex-wrap">
                                                            <p className="font-semibold text-sm">{modelInfo.title}</p>
                                                            <Badge variant="default" className="text-[10px] h-5 bg-primary">
                                                                {t("dashboard.modelManager.alwaysActive")}
                                                            </Badge>
                                                        </div>
                                                        <p className="text-xs text-muted-foreground">{model.name}</p>
                                                        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                                                            <div>
                                                                <span className="text-muted-foreground">{t("dashboard.modelManager.accuracy")}:</span>{" "}
                                                                <span className="font-medium">{modelInfo.accuracy}</span>
                                                            </div>
                                                            <div>
                                                                <span className="text-muted-foreground">{t("dashboard.modelManager.size")}:</span>{" "}
                                                                <span className="font-medium">{formatSize(model.size)}</span>
                                                            </div>
                                                        </div>
                                                        <p className="text-xs text-muted-foreground italic pt-1">
                                                            💡 {modelInfo.description}
                                                        </p>
                                                        <p className="text-xs text-primary/80 pt-1">
                                                            ℹ️ {t("dashboard.modelManager.classifierInfo")}
                                                        </p>
                                                    </div>
                                                </div>
                                            </div>
                                        );
                                    })}
                            </div>
                        </div>
                    </>
                )}

            </CardContent>
        </Card>
    );
}
