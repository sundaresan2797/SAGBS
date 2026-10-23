from pydantic import BaseModel


class DashboardSummary(BaseModel):
    total_employees: int
    active_employees: int
    employees_on_leave: int
    new_joiners_this_month: int
    present_today: int
    absent_today: int
    pending_leave_requests: int
    pending_tasks: int  # company-wide: not done yet (To Do, In Progress, or Stuck)
    overdue_tasks: int  # of those, how many are already past their due date


class AttendanceTrendPoint(BaseModel):
    date: str
    present: int
    absent: int
    late: int
    on_leave: int


class LeaveTrendPoint(BaseModel):
    month: str
    approved: int
    pending: int
    rejected: int


class DepartmentHeadcount(BaseModel):
    department_id: int
    department_name: str
    employee_count: int
