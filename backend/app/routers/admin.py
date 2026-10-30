from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..db import one, rows, transaction
from ..deps import Principal, require_admin, require_staff

router = APIRouter(tags=["admin"])


class RoleIn(BaseModel):
    role: str = Field(pattern="^(user|staff|admin)$")


@router.get("/admin/users")
def list_users(admin: Principal = Depends(require_admin)):
    with transaction(admin.id) as conn:
        return {"users": rows(conn, """SELECT u.user_id AS id, u.name, u.email, u.phone, u.role::text AS role, u.created_at,
                                              (SELECT count(*) FROM item i WHERE i.reporter_id = u.user_id) AS items
                                       FROM users u ORDER BY u.user_id""")}


@router.patch("/admin/users/{user_id}/role")
def set_role(user_id: int, body: RoleIn, admin: Principal = Depends(require_admin)):
    with transaction(admin.id) as conn:
        u = one(conn, "SELECT user_id AS id, name, email, role::text AS role FROM set_user_role(:a, :u, CAST(:r AS user_role))",
                a=admin.id, u=user_id, r=body.role)
    return u


@router.get("/analytics/summary")
def analytics(user: Principal = Depends(require_staff)):
    """Read from the materialized views; they lag writes by at most ANALYTICS_REFRESH_SECONDS."""
    with transaction(user.id) as conn:
        return {
            "status_counts": rows(conn, "SELECT item_type::text AS item_type, status::text AS status, n FROM mv_status_counts"),
            "recovery": rows(conn, "SELECT * FROM mv_recovery_stats ORDER BY (category = 'ALL') DESC, found_items DESC"),
            "hotspots": rows(conn, "SELECT * FROM mv_location_hotspots ORDER BY hotspot_rank, location_name LIMIT 10"),
            "match_quality": rows(conn, "SELECT * FROM mv_match_quality ORDER BY score_bucket"),
            "queue": one(conn, "SELECT count(*) AS pending_claims FROM claim WHERE result = 'pending'"),
        }


@router.post("/analytics/refresh", status_code=202)
def refresh(user: Principal = Depends(require_staff)):
    with transaction(user.id) as conn:
        one(conn, "SELECT refresh_analytics() AS ok")
    return {"ok": True}
