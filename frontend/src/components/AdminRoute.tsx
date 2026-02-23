import { Navigate, Outlet } from "react-router-dom";

interface AdminRouteProps {
    userRole?: string;
    redirectPath?: string;
    children?: React.ReactNode;
}

export function AdminRoute({
    userRole,
    redirectPath = "/dashboard",
    children,
}: AdminRouteProps) {
    if (userRole !== "admin") {
        return <Navigate to={redirectPath} replace />;
    }

    return children ? <>{children}</> : <Outlet />;
}
