import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, List, Union
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Fallback manual reading of .env file if environment variables are not set
env_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(env_file_path):
    try:
        with open(env_file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k not in os.environ:
                        os.environ[k] = v
    except Exception:
        pass

logger = logging.getLogger("mailer")

# SMTP Configuration
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SENDER_EMAIL = os.getenv("SMTP_SENDER_EMAIL", "nsaaiisma@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://studiouidesk.ddns.net:12045").rstrip("/")
MOBILE_SCHEME = "employeemonitoring"

# Email HR / Admin Default penerima notifikasi pengajuan cuti, expand, dan akun baru
DEFAULT_HR_EMAILS = [
    "fiismatunnissa@gmail.com",
    "andhini.dini91@gmail.com",
]


def get_task_url(task_id: str, custom_base_url: Optional[str] = None) -> str:
    """Menghasilkan URL web langsung menuju detail task."""
    base = (custom_base_url or APP_BASE_URL).rstrip("/")
    return f"{base}/task/{task_id}"


def get_mobile_task_url(task_id: str) -> str:
    """Menghasilkan URL deep link untuk mobile app."""
    return f"{MOBILE_SCHEME}://task/{task_id}"


def send_html_email(
    to_email: Union[str, List[str]],
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
) -> bool:
    """
    Mengirimkan email berbasis HTML (dengan fallback plain text) melalui Gmail SMTP SSL.
    """
    sender = SENDER_EMAIL.strip()
    password = GMAIL_APP_PASSWORD.strip()

    if not sender or not password:
        logger.error("Email tidak dapat dikirim: SMTP_SENDER_EMAIL atau GMAIL_APP_PASSWORD belum dikonfigurasi.")
        return False

    recipients = [to_email] if isinstance(to_email, str) else to_email
    clean_recipients = [r.strip().lower() for r in recipients if r and "@" in r]

    if not clean_recipients:
        logger.warning("Tidak ada penerima email yang valid.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"PT Tri Cipta Integra <{sender}>"
    msg["To"] = ", ".join(clean_recipients)

    plain_text = text_content or "Silakan buka email ini menggunakan aplikasi email yang mendukung tampilan HTML."
    part_text = MIMEText(plain_text, "plain", "utf-8")
    part_html = MIMEText(html_content, "html", "utf-8")

    msg.attach(part_text)
    msg.attach(part_html)

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(sender, password)
            server.sendmail(sender, clean_recipients, msg.as_string())
        logger.info(f"Email notifikasi berhasil dikirim ke: {clean_recipients} | Subjek: {subject}")
        return True
    except Exception as exc:
        logger.exception(f"Gagal mengirim email ke {clean_recipients}: {exc}")
        return False


# ==============================================================================
# HTML EMAIL TEMPLATES
# ==============================================================================

def render_base_template(header_title: str, badge_text: str, badge_color: str, body_html: str) -> str:
    """Template wrapper konsisten untuk semua notifikasi Tri Cipta Integra."""
    return f"""<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{header_title}</title>
  <style>
    body {{
      margin: 0;
      padding: 0;
      background-color: #F1F5F9;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      color: #1E293B;
      line-height: 1.6;
    }}
    .wrapper {{
      width: 100%;
      background-color: #F1F5F9;
      padding: 30px 10px;
    }}
    .container {{
      max-width: 600px;
      margin: 0 auto;
      background-color: #FFFFFF;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
      border: 1px solid #E2E8F0;
    }}
    .header {{
      background: linear-gradient(135deg, #031930 0%, #0A3663 100%);
      padding: 24px 30px;
      color: #FFFFFF;
    }}
    .company-name {{
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 1.5px;
      text-transform: uppercase;
      color: #93C5FD;
      margin: 0 0 6px 0;
    }}
    .header-title {{
      font-size: 20px;
      font-weight: 700;
      margin: 0;
      color: #FFFFFF;
    }}
    .badge {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 9999px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-top: 10px;
      background-color: {badge_color};
      color: #FFFFFF;
    }}
    .content {{
      padding: 30px;
    }}
    .greeting {{
      font-size: 16px;
      font-weight: 600;
      margin: 0 0 16px 0;
      color: #0F172A;
    }}
    .lead-text {{
      font-size: 14px;
      color: #475569;
      margin-bottom: 24px;
    }}
    .info-card {{
      background-color: #F8FAFC;
      border-left: 4px solid #2563EB;
      border-radius: 6px;
      padding: 16px 20px;
      margin-bottom: 24px;
    }}
    .info-row {{
      margin-bottom: 10px;
      font-size: 13px;
    }}
    .info-row:last-child {{
      margin-bottom: 0;
    }}
    .info-label {{
      font-weight: 600;
      color: #64748B;
      display: inline-block;
      min-width: 120px;
    }}
    .info-value {{
      font-weight: 600;
      color: #0F172A;
    }}
    .description-box {{
      background-color: #FFFFFF;
      border: 1px solid #E2E8F0;
      border-radius: 8px;
      padding: 14px 16px;
      margin-top: 10px;
      font-size: 13px;
      color: #334155;
      white-space: pre-wrap;
    }}
    .btn-container {{
      text-align: center;
      margin: 30px 0 20px 0;
    }}
    .btn-primary {{
      display: inline-block;
      background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%);
      color: #FFFFFF !important;
      font-size: 15px;
      font-weight: 600;
      text-decoration: none;
      padding: 14px 32px;
      border-radius: 8px;
      box-shadow: 0 3px 8px rgba(37, 99, 235, 0.35);
    }}
    .alt-link {{
      font-size: 12px;
      color: #64748B;
      text-align: center;
      margin-top: 12px;
      word-break: break-all;
    }}
    .alt-link a {{
      color: #2563EB;
      text-decoration: underline;
    }}
    .footer {{
      background-color: #F8FAFC;
      border-top: 1px solid #E2E8F0;
      padding: 20px 30px;
      font-size: 12px;
      color: #94A3B8;
      text-align: center;
    }}
    .footer-note {{
      margin: 0 0 6px 0;
    }}
    .footer-copy {{
      margin: 0;
    }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="container">
      <div class="header">
        <div class="company-name">PT Tri Cipta Integra</div>
        <div class="header-title">{header_title}</div>
        <div class="badge">{badge_text}</div>
      </div>
      <div class="content">
        {body_html}
      </div>
      <div class="footer">
        <p class="footer-note">Email ini dibuat otomatis oleh Sistem Monitoring & Manajemen Tugas PT Tri Cipta Integra.</p>
        <p class="footer-copy">&copy; 2026 PT Tri Cipta Integra. All rights reserved.</p>
      </div>
    </div>
  </div>
</body>
</html>"""


def send_task_assignment_email(
    task_id: str,
    task_title: str,
    task_description: str,
    assigned_to_email: str,
    assigned_to_name: str = "Karyawan",
    assigned_by_name: str = "Leader",
    assigned_by_email: str = "",
    project_name: str = "",
    client_name: str = "",
    deadline: str = "",
    start_date: str = "",
    priority: str = "MEDIUM",
    detail_task: str = "",
    endpoint_api: str = "",
    mandays: str = "",
    custom_base_url: Optional[str] = None,
) -> bool:
    """
    Mengirimkan email notifikasi penugasan tugas baru kepada karyawan.
    """
    web_url = get_task_url(task_id, custom_base_url)
    mobile_url = get_mobile_task_url(task_id)

    priority_colors = {
        "HIGH": "#EF4444",
        "MEDIUM": "#F59E0B",
        "LOW": "#10B981",
    }
    badge_color = priority_colors.get(priority.upper(), "#2563EB")

    project_info = ""
    if project_name:
        client_part = f" ({client_name})" if client_name else ""
        project_info = f"""
        <div class="info-row">
          <span class="info-label">Proyek:</span>
          <span class="info-value">{project_name}{client_part}</span>
        </div>
        """

    deadline_info = ""
    if deadline:
        date_range = f"{start_date} s/d {deadline}" if start_date else deadline
        deadline_info = f"""
        <div class="info-row">
          <span class="info-label">Tenggat Waktu:</span>
          <span class="info-value" style="color: #DC2626;">{date_range}</span>
        </div>
        """

    mandays_info = ""
    if mandays:
        mandays_info = f"""
        <div class="info-row">
          <span class="info-label">Estimasi Waktu:</span>
          <span class="info-value">{mandays} Hari Kerja (Mandays)</span>
        </div>
        """

    extra_details = ""
    if detail_task:
        extra_details += f"""
        <div style="margin-top: 12px;">
          <strong style="font-size: 13px; color: #475569;">Detail Pekerjaan:</strong>
          <div class="description-box">{detail_task}</div>
        </div>
        """
    if endpoint_api:
        extra_details += f"""
        <div style="margin-top: 12px;">
          <strong style="font-size: 13px; color: #475569;">Endpoint API Terkait:</strong>
          <div class="description-box" style="font-family: monospace; color: #0369A1;">{endpoint_api}</div>
        </div>
        """

    assigner_display = f"{assigned_by_name}" + (f" ({assigned_by_email})" if assigned_by_email else "")

    body_html = f"""
    <p class="greeting">Halo {assigned_to_name},</p>
    <p class="lead-text">
      Anda telah ditugaskan pekerjaan baru oleh <strong>{assigner_display}</strong>.
      Berikut adalah rincian tugas yang perlu Anda kerjakan:
    </p>

    <div class="info-card">
      <div class="info-row">
        <span class="info-label">Judul Tugas:</span>
        <span class="info-value" style="font-size: 15px; color: #0A3663;">{task_title}</span>
      </div>
      {project_info}
      <div class="info-row">
        <span class="info-label">Prioritas:</span>
        <span class="info-value" style="color: {badge_color}; font-weight: 700;">{priority.upper()}</span>
      </div>
      {deadline_info}
      {mandays_info}
      <div class="info-row">
        <span class="info-label">Penugasan Dari:</span>
        <span class="info-value">{assigner_display}</span>
      </div>
    </div>

    <div>
      <strong style="font-size: 13px; color: #475569;">Deskripsi Tugas:</strong>
      <div class="description-box">{task_description or 'Tidak ada catatan deskripsi tambahan.'}</div>
    </div>

    {extra_details}

    <div class="btn-container">
      <a href="{web_url}" class="btn-primary" target="_blank">Lihat & Kerjakan Tugas</a>
    </div>

    <div class="alt-link">
      Tautan langsung: <a href="{web_url}" target="_blank">{web_url}</a><br>
      <span style="font-size: 11px; color: #94A3B8;">(Atau buka di aplikasi mobile: <a href="{mobile_url}">{mobile_url}</a>)</span>
    </div>
    """

    subject = f"[Tri Cipta Integra] Tugas Baru: {task_title}"
    html = render_base_template(
        header_title="Tugas Baru Ditugaskan",
        badge_text=f"Prioritas: {priority.upper()}",
        badge_color=badge_color,
        body_html=body_html,
    )

    text_fallback = (
        f"Halo {assigned_to_name},\n\n"
        f"Anda telah ditugaskan pekerjaan baru: {task_title}\n"
        f"Oleh: {assigner_display}\n"
        f"Proyek: {project_name or '-'}\n"
        f"Deadline: {deadline or '-'}\n\n"
        f"Deskripsi:\n{task_description}\n\n"
        f"Buka tugas di browser atau aplikasi:\n{web_url}\n"
    )

    return send_html_email(assigned_to_email, subject, html, text_fallback)


def send_daily_task_email(
    task_id: str,
    task_title: str,
    employee_name: str,
    employee_email: str,
    leader_email: Union[str, List[str]],
    report_description: str,
    project_name: str = "",
    work_date: str = "",
    submitted_at: str = "",
    root_task_id: Optional[str] = None,
    custom_base_url: Optional[str] = None,
) -> bool:
    """
    Mengirimkan email notifikasi kepada Leader ketika karyawan mengirimkan daily report / hasil kerja harian.
    """
    target_id = root_task_id or task_id
    web_url = get_task_url(target_id, custom_base_url)
    mobile_url = get_mobile_task_url(target_id)

    body_html = f"""
    <p class="greeting">Halo Leader / Penanggung Jawab,</p>
    <p class="lead-text">
      Karyawan <strong>{employee_name}</strong> (<code>{employee_email}</code>) baru saja mengirimkan laporan harian (<em>Daily Task Report</em>) untuk penugasan berikut:
    </p>

    <div class="info-card" style="border-left-color: #10B981;">
      <div class="info-row">
        <span class="info-label">Nama Karyawan:</span>
        <span class="info-value">{employee_name} ({employee_email})</span>
      </div>
      <div class="info-row">
        <span class="info-label">Judul Tugas:</span>
        <span class="info-value" style="font-size: 15px; color: #0A3663;">{task_title}</span>
      </div>
      {f'''<div class="info-row"><span class="info-label">Proyek:</span><span class="info-value">{project_name}</span></div>''' if project_name else ''}
      <div class="info-row">
        <span class="info-label">Tanggal Kerja:</span>
        <span class="info-value">{work_date or 'Hari ini'}</span>
      </div>
      <div class="info-row">
        <span class="info-label">Waktu Submit:</span>
        <span class="info-value">{submitted_at or 'Baru saja'}</span>
      </div>
    </div>

    <div>
      <strong style="font-size: 13px; color: #475569;">Laporan Hasil Pekerjaan Harian:</strong>
      <div class="description-box" style="border-left: 3px solid #10B981;">{report_description}</div>
    </div>

    <div class="btn-container">
      <a href="{web_url}" class="btn-primary" style="background: linear-gradient(135deg, #10B981 0%, #059669 100%);" target="_blank">
        Tinjau & Review Tugas
      </a>
    </div>

    <div class="alt-link">
      Tautan review: <a href="{web_url}" target="_blank">{web_url}</a><br>
      <span style="font-size: 11px; color: #94A3B8;">(Atau buka di aplikasi mobile: <a href="{mobile_url}">{mobile_url}</a>)</span>
    </div>
    """

    subject = f"[Tri Cipta Integra] Daily Task dari {employee_name}: {task_title}"
    html = render_base_template(
        header_title="Laporan Daily Task Diterima",
        badge_text="Daily Report",
        badge_color="#10B981",
        body_html=body_html,
    )

    text_fallback = (
        f"Halo Leader,\n\n"
        f"{employee_name} ({employee_email}) telah mengumpulkan daily report untuk tugas: {task_title}\n"
        f"Tanggal: {work_date}\n\n"
        f"Hasil Pekerjaan:\n{report_description}\n\n"
        f"Tinjau laporan di:\n{web_url}\n"
    )

    return send_html_email(leader_email, subject, html, text_fallback)


def send_backlog_message_email(
    task_id: str,
    task_title: str,
    sender_name: str,
    sender_role: str,
    message: str,
    recipient_email: Union[str, List[str]],
    root_task_id: Optional[str] = None,
    custom_base_url: Optional[str] = None,
) -> bool:
    """
    Mengirimkan notifikasi email ketika ada komentar atau diskusi backlog baru pada task.
    """
    target_id = root_task_id or task_id
    web_url = get_task_url(target_id, custom_base_url)

    body_html = f"""
    <p class="greeting">Halo,</p>
    <p class="lead-text">
      Ada pesan / catatan diskusi baru pada tugas <strong>{task_title}</strong>:
    </p>

    <div class="info-card" style="border-left-color: #8B5CF6;">
      <div class="info-row">
        <span class="info-label">Pengirim:</span>
        <span class="info-value">{sender_name} ({sender_role.upper()})</span>
      </div>
      <div class="info-row">
        <span class="info-label">Tugas:</span>
        <span class="info-value">{task_title}</span>
      </div>
    </div>

    <div>
      <strong style="font-size: 13px; color: #475569;">Isi Pesan:</strong>
      <div class="description-box">{message}</div>
    </div>

    <div class="btn-container">
      <a href="{web_url}" class="btn-primary" style="background: linear-gradient(135deg, #8B5CF6 0%, #7C3AED 100%);" target="_blank">
        Balas Diskusi Task
      </a>
    </div>

    <div class="alt-link">
      Tautan langsung: <a href="{web_url}" target="_blank">{web_url}</a>
    </div>
    """

    subject = f"[Tri Cipta Integra] Pesan Baru pada Task: {task_title}"
    html = render_base_template(
        header_title="Pesan Backlog Task",
        badge_text="Diskusi Task",
        badge_color="#8B5CF6",
        body_html=body_html,
    )

    text_fallback = (
        f"Ada pesan diskusi baru dari {sender_name} pada task {task_title}:\n\n"
        f'"{message}"\n\n'
        f"Buka task: {web_url}\n"
    )

    return send_html_email(recipient_email, subject, html, text_fallback)


def send_general_notification_email(
    to_email: Union[str, List[str]],
    title: str,
    message: str,
    category: str = "Informasi",
    action_url: Optional[str] = None,
    action_label: str = "Lihat Detail",
) -> bool:
    """
    Mengirimkan notifikasi umum (misal permohonan cuti, perjalanan dinas, akun, dll).
    """
    action_btn = ""
    alt_link = ""
    if action_url:
        action_btn = f"""
        <div class="btn-container">
          <a href="{action_url}" class="btn-primary" target="_blank">{action_label}</a>
        </div>
        """
        alt_link = f"""
        <div class="alt-link">
          Tautan: <a href="{action_url}" target="_blank">{action_url}</a>
        </div>
        """

    body_html = f"""
    <p class="greeting">Halo,</p>
    <p class="lead-text">{message}</p>
    {action_btn}
    {alt_link}
    """

    subject = f"[Tri Cipta Integra] {title}"
    html = render_base_template(
        header_title=title,
        badge_text=category,
        badge_color="#2563EB",
        body_html=body_html,
    )

    return send_html_email(to_email, subject, html, message)


# ==============================================================================
# CUTI (LEAVE REQUEST) & EXPAND / BUSINESS TRIP NOTIFICATIONS
# ==============================================================================

def send_leave_request_submitted_email(
    admin_emails: Union[str, List[str]],
    employee_name: str,
    employee_email: str,
    leave_type: str,
    start_date: str,
    end_date: Optional[str],
    reason: str,
    leave_category: Optional[str] = None,
    custom_base_url: Optional[str] = None,
) -> bool:
    """
    Karyawan -> Admin: Memberitahu Admin/HR bahwa ada pengajuan cuti/izin/WFH baru.
    """
    base = (custom_base_url or APP_BASE_URL).rstrip("/")
    action_url = f"{base}/hr/leave-management"

    periode = f"{start_date} s/d {end_date}" if end_date and end_date != start_date else start_date
    jenis_str = (leave_category or leave_type).upper()

    body_html = f"""
    <p class="greeting">Halo Admin / Tim HRD,</p>
    <p class="lead-text">
      Karyawan <strong>{employee_name}</strong> (<code>{employee_email}</code>) telah mengajukan permohonan <strong>{jenis_str}</strong> baru:
    </p>

    <div class="info-card" style="border-left-color: #3B82F6;">
      <div class="info-row">
        <span class="info-label">Nama Karyawan:</span>
        <span class="info-value">{employee_name} ({employee_email})</span>
      </div>
      <div class="info-row">
        <span class="info-label">Jenis Pengajuan:</span>
        <span class="info-value" style="color: #2563EB; font-weight: 700;">{jenis_str}</span>
      </div>
      <div class="info-row">
        <span class="info-label">Periode Tanggal:</span>
        <span class="info-value">{periode}</span>
      </div>
    </div>

    <div>
      <strong style="font-size: 13px; color: #475569;">Alasan Pengajuan:</strong>
      <div class="description-box">{reason}</div>
    </div>

    <div class="btn-container">
      <a href="{action_url}" class="btn-primary" target="_blank">
        Tinjau & Validasi Cuti
      </a>
    </div>

    <div class="alt-link">
      Tautan langsung: <a href="{action_url}" target="_blank">{action_url}</a>
    </div>
    """

    subject = f"[Tri Cipta Integra] Pengajuan Cuti/Izin Baru: {employee_name} ({jenis_str})"
    html = render_base_template(
        header_title="Permohonan Cuti / Izin Baru",
        badge_text="Menunggu Persetujuan",
        badge_color="#F59E0B",
        body_html=body_html,
    )

    text_fallback = (
        f"Halo Admin/HR,\n\n"
        f"{employee_name} ({employee_email}) telah mengajukan {jenis_str} untuk tanggal {periode}.\n"
        f"Alasan: {reason}\n\n"
        f"Validasi pengajuan di: {action_url}\n"
    )

    targets = [admin_emails] if isinstance(admin_emails, str) else list(admin_emails or [])
    for def_email in DEFAULT_HR_EMAILS:
        if def_email.lower().strip() not in [t.lower().strip() for t in targets]:
            targets.append(def_email)

    return send_html_email(targets, subject, html, text_fallback)


def send_leave_request_status_email(
    employee_email: str,
    employee_name: str,
    status: str,  # APPROVED | REJECTED
    leave_type: str,
    start_date: str,
    end_date: Optional[str] = None,
    approver_notes: Optional[str] = None,
    custom_base_url: Optional[str] = None,
) -> bool:
    """
    Admin -> Karyawan: Memberitahu Karyawan bahwa pengajuan cutinya telah Disetujui / Ditolak oleh HR.
    """
    base = (custom_base_url or APP_BASE_URL).rstrip("/")
    action_url = f"{base}/employee/leave-request"

    is_approved = status.upper() == "APPROVED"
    status_label = "DISETUJUI ✅" if is_approved else "DITOLAK ❌"
    badge_color = "#10B981" if is_approved else "#EF4444"
    periode = f"{start_date} s/d {end_date}" if end_date and end_date != start_date else start_date

    body_html = f"""
    <p class="greeting">Halo {employee_name},</p>
    <p class="lead-text">
      Pengajuan permohonan <strong>{leave_type.upper()}</strong> Anda telah diproses oleh HRD dengan status: 
      <strong style="color: {badge_color};">{status_label}</strong>.
    </p>

    <div class="info-card" style="border-left-color: {badge_color};">
      <div class="info-row">
        <span class="info-label">Jenis Permohonan:</span>
        <span class="info-value">{leave_type.upper()}</span>
      </div>
      <div class="info-row">
        <span class="info-label">Periode Tanggal:</span>
        <span class="info-value">{periode}</span>
      </div>
      <div class="info-row">
        <span class="info-label">Status Keputusan:</span>
        <span class="info-value" style="color: {badge_color}; font-weight: 700;">{status_label}</span>
      </div>
    </div>

    {f'''
    <div>
      <strong style="font-size: 13px; color: #475569;">Catatan HRD:</strong>
      <div class="description-box">{approver_notes}</div>
    </div>
    ''' if approver_notes else ''}

    <div class="btn-container">
      <a href="{action_url}" class="btn-primary" style="background: {badge_color};" target="_blank">
        Lihat Riwayat Permohonan
      </a>
    </div>

    <div class="alt-link">
      Tautan langsung: <a href="{action_url}" target="_blank">{action_url}</a>
    </div>
    """

    subject = f"[Tri Cipta Integra] Pengajuan Cuti Anda Telah {status_label}: {periode}"
    html = render_base_template(
        header_title=f"Status Pengajuan Cuti: {status_label}",
        badge_text=status.upper(),
        badge_color=badge_color,
        body_html=body_html,
    )

    text_fallback = (
        f"Halo {employee_name},\n\n"
        f"Permohonan {leave_type} Anda untuk tanggal {periode} telah {status_label}.\n"
        f"Catatan: {approver_notes or '-'}\n\n"
        f"Cek di: {action_url}\n"
    )

    return send_html_email(employee_email, subject, html, text_fallback)


# ==============================================================================
# PERSETUJUAN AKUN (ACCOUNT APPROVAL) NOTIFICATIONS
# ==============================================================================

def send_account_registration_submitted_email(
    admin_emails: Union[str, List[str]],
    employee_name: str,
    employee_email: str,
    phone: str = "",
    department_id: str = "",
    employee_id: str = "",
    custom_base_url: Optional[str] = None,
) -> bool:
    """
    Karyawan -> Admin: Memberitahu HRD ada akun baru yang telah diverifikasi OTP dan menunggu persetujuan HRD.
    """
    base = (custom_base_url or APP_BASE_URL).rstrip("/")
    action_url = f"{base}/hr/account-approvals"

    body_html = f"""
    <p class="greeting">Halo Tim HRD / Administrator,</p>
    <p class="lead-text">
      Ada calon karyawan baru yang telah mendaftar dan menyelesaikan verifikasi awal. Akun ini memerlukan <strong>Persetujuan (Approval)</strong> dari HRD sebelum dapat digunakan:
    </p>

    <div class="info-card" style="border-left-color: #6366F1;">
      <div class="info-row">
        <span class="info-label">Nama Lengkap:</span>
        <span class="info-value" style="font-size: 15px; color: #0F172A;">{employee_name}</span>
      </div>
      <div class="info-row">
        <span class="info-label">Email Terdaftar:</span>
        <span class="info-value">{employee_email}</span>
      </div>
      {f'''<div class="info-row"><span class="info-label">No. Telepon:</span><span class="info-value">{phone}</span></div>''' if phone else ''}
      {f'''<div class="info-row"><span class="info-label">Departemen:</span><span class="info-value">{department_id.upper()}</span></div>''' if department_id else ''}
      {f'''<div class="info-row"><span class="info-label">ID Karyawan:</span><span class="info-value">{employee_id}</span></div>''' if employee_id else ''}
      <div class="info-row">
        <span class="info-label">Status Akun:</span>
        <span class="info-value" style="color: #F59E0B; font-weight: 700;">Menunggu Approval HRD</span>
      </div>
    </div>

    <div class="btn-container">
      <a href="{action_url}" class="btn-primary" style="background: linear-gradient(135deg, #6366F1 0%, #4F46E5 100%);" target="_blank">
        Buka Persetujuan Akun
      </a>
    </div>

    <div class="alt-link">
      Tautan audit: <a href="{action_url}" target="_blank">{action_url}</a>
    </div>
    """

    subject = f"[Tri Cipta Integra] Pengajuan Akun Baru: {employee_name} ({employee_email})"
    html = render_base_template(
        header_title="Pendaftaran Akun Baru Menunggu Approval",
        badge_text="Approval Akun",
        badge_color="#6366F1",
        body_html=body_html,
    )

    text_fallback = (
        f"Halo HRD,\n\n"
        f"Ada pendaftaran akun baru dari {employee_name} ({employee_email}) untuk departemen {department_id}.\n"
        f"Buka persetujuan akun: {action_url}\n"
    )

    targets = [admin_emails] if isinstance(admin_emails, str) else list(admin_emails or [])
    for def_email in DEFAULT_HR_EMAILS:
        if def_email.lower().strip() not in [t.lower().strip() for t in targets]:
            targets.append(def_email)

    return send_html_email(targets, subject, html, text_fallback)


def send_account_approval_decision_email(
    employee_email: str,
    employee_name: str,
    status: str,  # approved | rejected
    custom_base_url: Optional[str] = None,
) -> bool:
    """
    Admin -> Karyawan: Memberitahu Karyawan bahwa akun mereka telah Disetujui (Approved) atau Ditolak (Rejected).
    """
    base = (custom_base_url or APP_BASE_URL).rstrip("/")
    login_url = f"{base}/login"

    is_approved = status.lower() == "approved"
    status_label = "DISETUJUI ✅" if is_approved else "DITOLAK ❌"
    badge_color = "#10B981" if is_approved else "#EF4444"

    if is_approved:
        content_html = f"""
        <p class="greeting">Halo {employee_name},</p>
        <p class="lead-text">
          Selamat! Pendaftaran akun Employee Monitoring Anda di <strong>PT Tri Cipta Integra</strong> telah 
          <strong style="color: #10B981;">Disetujui oleh HRD</strong>.
        </p>

        <div class="info-card" style="border-left-color: #10B981;">
          <div class="info-row">
            <span class="info-label">Nama:</span>
            <span class="info-value">{employee_name}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Email Login:</span>
            <span class="info-value" style="font-weight: 700; color: #0F172A;">{employee_email}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Status Akun:</span>
            <span class="info-value" style="color: #10B981; font-weight: 700;">AKTIF (DISETUJUI)</span>
          </div>
        </div>

        <p style="font-size: 13px; color: #475569;">
          Anda sekarang dapat login ke portal aplikasi menggunakan email dan kata sandi yang Anda buat saat pendaftaran.
        </p>

        <div class="btn-container">
          <a href="{login_url}" class="btn-primary" style="background: linear-gradient(135deg, #10B981 0%, #059669 100%);" target="_blank">
            Login ke Aplikasi
          </a>
        </div>

        <div class="alt-link">
          Tautan login: <a href="{login_url}" target="_blank">{login_url}</a>
        </div>
        """
    else:
        content_html = f"""
        <p class="greeting">Halo {employee_name},</p>
        <p class="lead-text">
          Pemberitahuan terkait pendaftaran akun Employee Monitoring Anda di <strong>PT Tri Cipta Integra</strong>:
        </p>

        <div class="info-card" style="border-left-color: #EF4444;">
          <div class="info-row">
            <span class="info-label">Nama:</span>
            <span class="info-value">{employee_name}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Email:</span>
            <span class="info-value">{employee_email}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Status Keputusan:</span>
            <span class="info-value" style="color: #EF4444; font-weight: 700;">Ditolak oleh HRD</span>
          </div>
        </div>

        <p style="font-size: 13px; color: #475569;">
          Mohon maaf, pengajuan pendaftaran akun Anda belum dapat disetujui. Jika ini merupakan kekeliruan atau Anda membutuhkan informasi lebih lanjut, silakan hubungi bagian HRD PT Tri Cipta Integra.
        </p>
        """

    subject = f"[Tri Cipta Integra] Akun Anda Telah {status_label}"
    html = render_base_template(
        header_title=f"Status Pendaftaran Akun: {status_label}",
        badge_text="Persetujuan Akun",
        badge_color=badge_color,
        body_html=content_html,
    )

    text_fallback = (
        f"Halo {employee_name},\n\n"
        f"Status pendaftaran akun Anda: {status_label}.\n"
        + (f"Silakan login di: {login_url}\n" if is_approved else "Silakan hubungi HRD untuk informasi lebih lanjut.\n")
    )

    return send_html_email(employee_email, subject, html, text_fallback)



def send_expand_claim_submitted_email(
    admin_emails: Union[str, List[str]],
    employee_name: str,
    employee_email: str,
    claim_type: str,
    amount: float,
    purpose: str,
    claim_date: str,
    client_name: str = "",
    destination: str = "",
    transport_type: str = "",
    trip_start_date: Optional[str] = None,
    trip_end_date: Optional[str] = None,
    custom_base_url: Optional[str] = None,
) -> bool:
    """
    Karyawan -> Admin: Memberitahu Admin/Finance ada pengajuan klaim expand / perjalanan dinas baru.
    """
    base = (custom_base_url or APP_BASE_URL).rstrip("/")
    action_url = f"{base}/hr/business-trip-acc"

    formatted_amount = f"Rp {amount:,.0f}".replace(",", ".")
    periode_trip = f"{trip_start_date} s/d {trip_end_date}" if trip_start_date and trip_end_date else claim_date

    body_html = f"""
    <p class="greeting">Halo Admin / Tim Finance,</p>
    <p class="lead-text">
      Karyawan <strong>{employee_name}</strong> (<code>{employee_email}</code>) telah mengajukan permohonan <strong>Klaim Expand / Biaya Operasional</strong> baru:
    </p>

    <div class="info-card" style="border-left-color: #0284C7;">
      <div class="info-row">
        <span class="info-label">Nama Karyawan:</span>
        <span class="info-value">{employee_name} ({employee_email})</span>
      </div>
      <div class="info-row">
        <span class="info-label">Jenis Klaim / Expand:</span>
        <span class="info-value" style="font-weight: 700; color: #0369A1;">{claim_type} {f'({transport_type})' if transport_type else ''}</span>
      </div>
      <div class="info-row">
        <span class="info-label">Nominal Diajukan:</span>
        <span class="info-value" style="font-size: 16px; color: #0F172A; font-weight: 800;">{formatted_amount}</span>
      </div>
      <div class="info-row">
        <span class="info-label">Tanggal / Periode:</span>
        <span class="info-value">{periode_trip}</span>
      </div>
      {f'''<div class="info-row"><span class="info-label">Klien / Tujuan:</span><span class="info-value">{client_name} {f'- {destination}' if destination else ''}</span></div>''' if client_name or destination else ''}
    </div>

    <div>
      <strong style="font-size: 13px; color: #475569;">Keperluan / Deskripsi Pengeluaran:</strong>
      <div class="description-box">{purpose}</div>
    </div>

    <div class="btn-container">
      <a href="{action_url}" class="btn-primary" style="background: linear-gradient(135deg, #0284C7 0%, #0369A1 100%);" target="_blank">
        Audit & Proses Pencairan Expand
      </a>
    </div>

    <div class="alt-link">
      Tautan langsung: <a href="{action_url}" target="_blank">{action_url}</a>
    </div>
    """

    subject = f"[Tri Cipta Integra] Pengajuan Klaim Expand Baru: {employee_name} ({formatted_amount})"
    html = render_base_template(
        header_title="Pengajuan Klaim Biaya Expand Baru",
        badge_text=f"Total: {formatted_amount}",
        badge_color="#0284C7",
        body_html=body_html,
    )

    text_fallback = (
        f"Halo Admin/Finance,\n\n"
        f"{employee_name} ({employee_email}) telah mengajukan klaim {claim_type} sebesar {formatted_amount}.\n"
        f"Keperluan: {purpose}\n"
        f"Tanggal: {periode_trip}\n\n"
        f"Audit di: {action_url}\n"
    )

    targets = [admin_emails] if isinstance(admin_emails, str) else list(admin_emails or [])
    for def_email in DEFAULT_HR_EMAILS:
        if def_email.lower().strip() not in [t.lower().strip() for t in targets]:
            targets.append(def_email)

    return send_html_email(targets, subject, html, text_fallback)


def send_expand_claim_status_email(
    employee_email: str,
    employee_name: str,
    status: str,  # APPROVED | REJECTED
    claim_type: str,
    amount: float,
    approved_amount: Optional[float] = None,
    purpose: str = "",
    approver_notes: Optional[str] = None,
    custom_base_url: Optional[str] = None,
) -> bool:
    """
    Admin -> Karyawan: Memberitahu Karyawan bahwa klaim expand telah Disetujui / Ditolak oleh Admin/Finance.
    """
    base = (custom_base_url or APP_BASE_URL).rstrip("/")
    action_url = f"{base}/employee/business-trip"

    is_approved = status.upper() == "APPROVED"
    status_label = "DISETUJUI / DICAIRKAN ✅" if is_approved else "DITOLAK ❌"
    badge_color = "#10B981" if is_approved else "#EF4444"

    final_amount = approved_amount if approved_amount is not None else amount
    formatted_final = f"Rp {final_amount:,.0f}".replace(",", ".")

    body_html = f"""
    <p class="greeting">Halo {employee_name},</p>
    <p class="lead-text">
      Pengajuan klaim expand / perjalanan dinas Anda untuk <strong>{claim_type}</strong> telah diperiksa oleh Admin/Finance dengan keputusan: 
      <strong style="color: {badge_color};">{status_label}</strong>.
    </p>

    <div class="info-card" style="border-left-color: {badge_color};">
      <div class="info-row">
        <span class="info-label">Jenis Klaim:</span>
        <span class="info-value">{claim_type}</span>
      </div>
      <div class="info-row">
        <span class="info-label">Nominal {'Disetujui' if is_approved else 'Diajukan'}:</span>
        <span class="info-value" style="font-size: 16px; font-weight: 800; color: {'#15803D' if is_approved else '#DC2626'};">{formatted_final}</span>
      </div>
      <div class="info-row">
        <span class="info-label">Status Keputusan:</span>
        <span class="info-value" style="color: {badge_color}; font-weight: 700;">{status_label}</span>
      </div>
      {f'''<div class="info-row"><span class="info-label">Keperluan:</span><span class="info-value">{purpose}</span></div>''' if purpose else ''}
    </div>

    {f'''
    <div>
      <strong style="font-size: 13px; color: #475569;">Catatan Finance / Verifikator:</strong>
      <div class="description-box">{approver_notes}</div>
    </div>
    ''' if approver_notes else ''}

    <div class="btn-container">
      <a href="{action_url}" class="btn-primary" style="background: {badge_color};" target="_blank">
        Buka Status Klaim di Aplikasi
      </a>
    </div>

    <div class="alt-link">
      Tautan langsung: <a href="{action_url}" target="_blank">{action_url}</a>
    </div>
    """

    subject = f"[Tri Cipta Integra] Pengajuan Expand Anda {status_label}: {formatted_final}"
    html = render_base_template(
        header_title=f"Status Klaim Expand: {status_label}",
        badge_text=status.upper(),
        badge_color=badge_color,
        body_html=body_html,
    )

    text_fallback = (
        f"Halo {employee_name},\n\n"
        f"Klaim expand {claim_type} Anda sebesar {formatted_final} telah {status_label}.\n"
        f"Catatan: {approver_notes or '-'}\n\n"
        f"Cek di: {action_url}\n"
    )

    return send_html_email(employee_email, subject, html, text_fallback)


# ==============================================================================
# PERSETUJUAN AKUN (ACCOUNT APPROVAL) NOTIFICATIONS
# ==============================================================================

def send_account_registration_submitted_email(
    admin_emails: Union[str, List[str]],
    employee_name: str,
    employee_email: str,
    phone: str = "",
    department_id: str = "",
    employee_id: str = "",
    custom_base_url: Optional[str] = None,
) -> bool:
    """
    Karyawan -> Admin: Memberitahu HRD ada akun baru yang telah diverifikasi OTP dan menunggu persetujuan HRD.
    """
    base = (custom_base_url or APP_BASE_URL).rstrip("/")
    action_url = f"{base}/hr/account-approvals"

    body_html = f"""
    <p class="greeting">Halo Tim HRD / Administrator,</p>
    <p class="lead-text">
      Ada calon karyawan baru yang telah mendaftar dan menyelesaikan verifikasi awal. Akun ini memerlukan <strong>Persetujuan (Approval)</strong> dari HRD sebelum dapat digunakan:
    </p>

    <div class="info-card" style="border-left-color: #6366F1;">
      <div class="info-row">
        <span class="info-label">Nama Lengkap:</span>
        <span class="info-value" style="font-size: 15px; color: #0F172A;">{employee_name}</span>
      </div>
      <div class="info-row">
        <span class="info-label">Email Terdaftar:</span>
        <span class="info-value">{employee_email}</span>
      </div>
      {f'''<div class="info-row"><span class="info-label">No. Telepon:</span><span class="info-value">{phone}</span></div>''' if phone else ''}
      {f'''<div class="info-row"><span class="info-label">Departemen:</span><span class="info-value">{department_id.upper()}</span></div>''' if department_id else ''}
      {f'''<div class="info-row"><span class="info-label">ID Karyawan:</span><span class="info-value">{employee_id}</span></div>''' if employee_id else ''}
      <div class="info-row">
        <span class="info-label">Status Akun:</span>
        <span class="info-value" style="color: #F59E0B; font-weight: 700;">Menunggu Approval HRD</span>
      </div>
    </div>

    <div class="btn-container">
      <a href="{action_url}" class="btn-primary" style="background: linear-gradient(135deg, #6366F1 0%, #4F46E5 100%);" target="_blank">
        Buka Persetujuan Akun
      </a>
    </div>

    <div class="alt-link">
      Tautan audit: <a href="{action_url}" target="_blank">{action_url}</a>
    </div>
    """

    subject = f"[Tri Cipta Integra] Pengajuan Akun Baru: {employee_name} ({employee_email})"
    html = render_base_template(
        header_title="Pendaftaran Akun Baru Menunggu Approval",
        badge_text="Approval Akun",
        badge_color="#6366F1",
        body_html=body_html,
    )

    text_fallback = (
        f"Halo HRD,\n\n"
        f"Ada pendaftaran akun baru dari {employee_name} ({employee_email}) untuk departemen {department_id}.\n"
        f"Buka persetujuan akun: {action_url}\n"
    )

    targets = [admin_emails] if isinstance(admin_emails, str) else list(admin_emails or [])
    for def_email in DEFAULT_HR_EMAILS:
        if def_email.lower().strip() not in [t.lower().strip() for t in targets]:
            targets.append(def_email)

    return send_html_email(targets, subject, html, text_fallback)


def send_account_approval_decision_email(
    employee_email: str,
    employee_name: str,
    status: str,  # approved | rejected
    custom_base_url: Optional[str] = None,
) -> bool:
    """
    Admin -> Karyawan: Memberitahu Karyawan bahwa akun mereka telah Disetujui (Approved) atau Ditolak (Rejected).
    """
    base = (custom_base_url or APP_BASE_URL).rstrip("/")
    login_url = f"{base}/login"

    is_approved = status.lower() == "approved"
    status_label = "DISETUJUI ✅" if is_approved else "DITOLAK ❌"
    badge_color = "#10B981" if is_approved else "#EF4444"

    if is_approved:
        content_html = f"""
        <p class="greeting">Halo {employee_name},</p>
        <p class="lead-text">
          Selamat! Pendaftaran akun Employee Monitoring Anda di <strong>PT Tri Cipta Integra</strong> telah 
          <strong style="color: #10B981;">Disetujui oleh HRD</strong>.
        </p>

        <div class="info-card" style="border-left-color: #10B981;">
          <div class="info-row">
            <span class="info-label">Nama:</span>
            <span class="info-value">{employee_name}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Email Login:</span>
            <span class="info-value" style="font-weight: 700; color: #0F172A;">{employee_email}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Status Akun:</span>
            <span class="info-value" style="color: #10B981; font-weight: 700;">AKTIF (DISETUJUI)</span>
          </div>
        </div>

        <p style="font-size: 13px; color: #475569;">
          Anda sekarang dapat login ke portal aplikasi menggunakan email dan kata sandi yang Anda buat saat pendaftaran.
        </p>

        <div class="btn-container">
          <a href="{login_url}" class="btn-primary" style="background: linear-gradient(135deg, #10B981 0%, #059669 100%);" target="_blank">
            Login ke Aplikasi
          </a>
        </div>

        <div class="alt-link">
          Tautan login: <a href="{login_url}" target="_blank">{login_url}</a>
        </div>
        """
    else:
        content_html = f"""
        <p class="greeting">Halo {employee_name},</p>
        <p class="lead-text">
          Pemberitahuan terkait pendaftaran akun Employee Monitoring Anda di <strong>PT Tri Cipta Integra</strong>:
        </p>

        <div class="info-card" style="border-left-color: #EF4444;">
          <div class="info-row">
            <span class="info-label">Nama:</span>
            <span class="info-value">{employee_name}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Email:</span>
            <span class="info-value">{employee_email}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Status Keputusan:</span>
            <span class="info-value" style="color: #EF4444; font-weight: 700;">Ditolak oleh HRD</span>
          </div>
        </div>

        <p style="font-size: 13px; color: #475569;">
          Mohon maaf, pengajuan pendaftaran akun Anda belum dapat disetujui. Jika ini merupakan kekeliruan atau Anda membutuhkan informasi lebih lanjut, silakan hubungi bagian HRD PT Tri Cipta Integra.
        </p>
        """

    subject = f"[Tri Cipta Integra] Akun Anda Telah {status_label}"
    html = render_base_template(
        header_title=f"Status Pendaftaran Akun: {status_label}",
        badge_text="Persetujuan Akun",
        badge_color=badge_color,
        body_html=content_html,
    )

    text_fallback = (
        f"Halo {employee_name},\n\n"
        f"Status pendaftaran akun Anda: {status_label}.\n"
        + (f"Silakan login di: {login_url}\n" if is_approved else "Silakan hubungi HRD untuk informasi lebih lanjut.\n")
    )

    return send_html_email(employee_email, subject, html, text_fallback)


