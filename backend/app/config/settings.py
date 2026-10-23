from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Employee Management System"
    # The registered/legal entity name, shown only on the payslip PDF - deliberately separate from the
    # trade name on the login page (VITE_COMPANY_NAME in the frontend), since a payslip is a statutory
    # document and commonly carries the formal company name rather than the everyday brand name.
    company_name: str = "Sri Annamalai Global Business Service"
    environment: str = "development"
    debug: bool = True

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/employee_management"
    database_url_sync: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/employee_management"
    database_url_test: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/employee_management_test"

    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 5

    # Employee photos: the largest picture accepted, and the square size (in pixels) it is saved at.
    photo_max_upload_mb: int = 5
    photo_size_px: int = 400

    cors_origins: str = "http://localhost:5173"

    timezone: str = "Asia/Kolkata"
    # Attendance policy (all times are in `timezone`). See app/services/attendance_rules.py.
    # Office hours are 9:00 AM - 6:00 PM (9 hours, minus the 30-minute lunch below = 8.5 hours net).
    workday_start_hour: int = 9
    workday_start_minute: int = 0
    late_grace_minutes: int = 10  # checking in up to this long after the start is still on time
    standard_shift_minutes: int = 510  # a full shift (net of lunch); anything beyond it is overtime
    full_day_minimum_minutes: int = 465  # working less than this is a half day
    long_day_flag_minutes: int = 720  # a day longer than this is flagged "please check" (usually a late check-out)
    half_day_checkin_after_hour: int = 13  # checking in after this time is a half day
    half_day_checkin_after_minute: int = 30
    # The company's lunch break. Whatever part of it falls inside someone's check-in to check-out span is
    # deducted from their working minutes automatically - nobody punches out for lunch.
    lunch_start_hour: int = 13
    lunch_start_minute: int = 0
    lunch_break_minutes: int = 30

    # "Permission": a short, approved absence of a few hours that is paid and causes no late mark or half day.
    permission_monthly_limit: int = 2  # per person per calendar month; more than this must be a half-day leave
    permission_max_minutes: int = 120  # the longest a single permission can be

    rate_limit_login_attempts: int = 5
    rate_limit_login_window_seconds: int = 300

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
