"""login_failures: failed password sign-ins, so POST /login can turn away guessing (ophir_figures/auth.py).

One row per failed attempt: the client's address, the username as typed in lower case and when.
Rows older than the window are deleted whenever a new one is written. A table rather than memory,
so both gunicorn workers count together and a restart forgives nothing.
"""

NAME = "login failures"


def apply(connection, context):
    context.run_script("""
CREATE TABLE login_failures (
  ip TEXT NOT NULL, username TEXT NOT NULL, failed_at TEXT NOT NULL
);
CREATE INDEX idx_login_failures_ip ON login_failures(ip, failed_at);
CREATE INDEX idx_login_failures_username ON login_failures(username, failed_at);
""")
