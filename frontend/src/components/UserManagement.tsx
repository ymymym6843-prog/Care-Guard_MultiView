/**
 * 사용자 관리 컴포넌트 (admin 전용)
 *
 * 사용자 목록 조회 및 새 사용자 추가 폼.
 */

import { useState, useEffect, useCallback } from "react";
import { UserPlus, Users, Shield, User as UserIcon, RefreshCcw } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { apiCall } from "@/lib/auth";
import { useTranslation } from "react-i18next";

interface UserInfo {
  id: number;
  username: string;
  full_name: string;
  role: string;
  is_active: boolean;
  created_at: string | null;
}

export function UserManagement() {
  const { t } = useTranslation();
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [error, setError] = useState("");

  // 새 사용자 폼 상태
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newFullName, setNewFullName] = useState("");
  const [newRole, setNewRole] = useState<"staff" | "admin">("staff");
  const [addLoading, setAddLoading] = useState(false);
  const [addError, setAddError] = useState("");
  const [addSuccess, setAddSuccess] = useState("");

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiCall("/api/auth/users");
      if (res.ok) {
        const data = await res.json();
        setUsers(data);
        setError("");
      } else {
        setError(t("userManagement.toasts.listError"));
      }
    } catch {
      setError(t("userManagement.toasts.connectionError"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleAddUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setAddError("");
    setAddSuccess("");

    if (newPassword.length < 8) {
      setAddError(t("userManagement.toasts.passwordShort"));
      return;
    }

    setAddLoading(true);
    try {
      const res = await apiCall("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: newUsername,
          password: newPassword,
          full_name: newFullName,
          role: newRole,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => null);
        setAddError(data?.detail ?? t("userManagement.toasts.addError"));
        return;
      }

      setAddSuccess(`${newUsername} ${t("userManagement.toasts.addSuccess")}`);
      setNewUsername("");
      setNewPassword("");
      setNewFullName("");
      setNewRole("staff");
      setShowAddForm(false);
      fetchUsers();
    } catch {
      setAddError(t("userManagement.toasts.connectionError"));
    } finally {
      setAddLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Users className="h-4 w-4 text-primary" />
            {t("userManagement.title")}
          </CardTitle>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="ghost" onClick={fetchUsers} aria-label={t("userManagement.refresh")}>
              <RefreshCcw className="h-4 w-4" />
            </Button>
            <Button size="sm" onClick={() => setShowAddForm(!showAddForm)}>
              <UserPlus className="h-4 w-4 mr-1" />
              {t("userManagement.addUser")}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {error && <p className="text-sm text-danger mb-3">{error}</p>}
          {addSuccess && <p className="text-sm text-safe mb-3">{addSuccess}</p>}

          {/* 사용자 추가 폼 */}
          {showAddForm && (
            <form onSubmit={handleAddUser} className="mb-4 p-4 rounded-lg border bg-muted/30 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label htmlFor="add-username" className="text-xs font-medium">
                    {t("userManagement.username")}
                  </label>
                  <input
                    id="add-username"
                    type="text"
                    value={newUsername}
                    onChange={(e) => setNewUsername(e.target.value)}
                    required
                    pattern="^[a-zA-Z0-9_]+$"
                    minLength={3}
                    maxLength={50}
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                    placeholder={t("userManagement.placeholders.username")}
                  />
                </div>
                <div className="space-y-1">
                  <label htmlFor="add-fullname" className="text-xs font-medium">
                    {t("userManagement.fullName")}
                  </label>
                  <input
                    id="add-fullname"
                    type="text"
                    value={newFullName}
                    onChange={(e) => setNewFullName(e.target.value)}
                    maxLength={100}
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                    placeholder={t("userManagement.placeholders.fullName")}
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label htmlFor="add-password" className="text-xs font-medium">
                    {t("userManagement.password")}
                  </label>
                  <input
                    id="add-password"
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                    minLength={8}
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                  />
                </div>
                <div className="space-y-1">
                  <label htmlFor="add-role" className="text-xs font-medium">
                    {t("userManagement.role")}
                  </label>
                  <select
                    id="add-role"
                    value={newRole}
                    onChange={(e) => setNewRole(e.target.value as "staff" | "admin")}
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                  >
                    <option value="staff">{t("userManagement.staff")}</option>
                    <option value="admin">{t("userManagement.admin")}</option>
                  </select>
                </div>
              </div>

              {addError && <p className="text-xs text-danger">{addError}</p>}

              <div className="flex gap-2">
                <Button type="submit" size="sm" disabled={addLoading}>
                  {addLoading ? t("userManagement.loading") : t("userManagement.add")}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setShowAddForm(false)}
                >
                  {t("userManagement.cancel")}
                </Button>
              </div>
            </form>
          )}

          {/* 사용자 목록 */}
          {loading ? (
            <p className="text-sm text-muted-foreground py-4 text-center">{t("userManagement.loading")}</p>
          ) : users.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">{t("userManagement.noUsers")}</p>
          ) : (
            <div className="divide-y divide-border">
              {users.map((user) => (
                <div key={user.id} className="flex items-center justify-between py-3">
                  <div className="flex items-center gap-3">
                    <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center">
                      {user.role === "admin" ? (
                        <Shield className="h-4 w-4 text-primary" />
                      ) : (
                        <UserIcon className="h-4 w-4 text-muted-foreground" />
                      )}
                    </div>
                    <div>
                      <p className="text-sm font-medium">
                        {user.full_name || user.username}
                      </p>
                      <p className="text-xs text-muted-foreground">@{user.username}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={user.role === "admin" ? "default" : "secondary"} className="text-xs">
                      {user.role === "admin" ? t("userManagement.admin") : t("userManagement.staff")}
                    </Badge>
                    {!user.is_active && (
                      <Badge variant="outline" className="text-xs text-danger">
                        {t("userManagement.inactive")}
                      </Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
