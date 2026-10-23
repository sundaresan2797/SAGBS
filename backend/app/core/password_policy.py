"""What counts as a strong enough password for the people who set up and run the system.

Used by the first-time setup (`python -m app.setup_live`). Kept separate and plain so the sign-in rules
can adopt the same check later without changing how it works.
"""

MIN_LENGTH = 12

# A short list of the passwords people reach for first. It is a floor, not a full dictionary.
_COMMON = {
    "password", "password1", "password123", "changeme123", "changeme123!", "admin123", "admin@123", "welcome123",
    "qwerty123", "letmein123", "iloveyou123", "123456789012", "abcdefghijkl", "temp-password",
}


def password_problems(password: str, email: str = "") -> list[str]:
    """Plain-language reasons this password is too weak (an empty list means it is acceptable)."""
    problems: list[str] = []
    if len(password) < MIN_LENGTH:
        problems.append(f"It must be at least {MIN_LENGTH} characters long.")
    if not any(c.isalpha() for c in password):
        problems.append("It must contain letters.")
    if not any(c.isdigit() for c in password):
        problems.append("It must contain at least one number.")
    if password.lower() in _COMMON:
        problems.append("That is a very common password.")
    local_part = email.split("@")[0].lower() if email else ""
    if len(local_part) >= 4 and local_part in password.lower():
        problems.append("It must not contain your email name.")
    if len(set(password)) < 5:
        problems.append("It uses too few different characters.")
    return problems
