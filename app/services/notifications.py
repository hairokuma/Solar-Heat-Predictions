import smtplib
from email.mime.text import MIMEText


class EmailSendError(Exception):
    """Raised when an email could not be delivered via SMTP."""


def send_email(*, host, port, username, password, use_tls, from_addr, to_addr, subject, body, timeout=10):
    message = MIMEText(body)
    message["Subject"] = subject
    message["From"] = from_addr
    message["To"] = to_addr

    try:
        with smtplib.SMTP(host, port, timeout=timeout) as server:
            if use_tls:
                server.starttls()
            if username:
                server.login(username, password)
            server.sendmail(from_addr, [to_addr], message.as_string())
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailSendError(f"Could not send email via {host}:{port}: {exc}") from exc
