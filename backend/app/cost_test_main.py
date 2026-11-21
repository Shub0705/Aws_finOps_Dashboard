from app.main import app
from app.cost_management.router import router as cost_management_router

app.include_router(cost_management_router)

from app.employee_activity import router as employee_activity_router
app.include_router(employee_activity_router)
