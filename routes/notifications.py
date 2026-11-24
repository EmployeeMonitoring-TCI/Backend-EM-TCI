import logging
from typing import Optional, List, Union
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, EmailStr
import firebase_admin
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from services.mailer import (
    send_task_assignment_email,
    send_daily_task_email,
    send_backlog_message_email,
    send_general_notification_email,
    send_leave_request_submitted_email,
    send_leave_request_status_email,
    send_expand_claim_submitted_email,
    send_expand_claim_status_email,
    send_account_registration_submitted_email,
    send_account_approval_decision_email,
)

logger = logging.getLogger("notifications_route")
router = APIRouter(prefix="/api/notifications", tags=["Notification Email Service"])


def get_db():
    app = firebase_admin.get_app()
    return firestore.client(app=app)


# ==============================================================================
# PYDANTIC SCHEMAS
# ==============================================================================

class TaskAssignedNotificationRequest(BaseModel):
    taskId: str
    taskTitle: str
    taskDescription: Optional[str] = ""
    detailTask: Optional[str] = ""
    endpointApi: Optional[str] = ""
    mandays: Optional[str] = ""
    projectName: Optional[str] = ""
    clientName: Optional[str] = ""
    priority: Optional[str] = "MEDIUM"
    deadline: Optional[str] = ""
    startDate: Optional[str] = ""
    assignedToEmail: str
    assignedToName: Optional[str] = "Karyawan"
    assignedByEmail: Optional[str] = ""
    assignedByName: Optional[str] = "Leader"
    webUrl: Optional[str] = None


class DailyReportNotificationRequest(BaseModel):
    taskId: str
    rootTaskId: Optional[str] = None
    taskTitle: str
    projectName: Optional[str] = ""
    employeeName: str
    employeeEmail: str
    leaderEmail: Optional[Union[str, List[str]]] = None
    reportDescription: str
    workDate: Optional[str] = ""
    submittedAt: Optional[str] = ""
    webUrl: Optional[str] = None


class BacklogNotificationRequest(BaseModel):
    taskId: str
    rootTaskId: Optional[str] = None
    taskTitle: str
    senderName: str
    senderRole: Optional[str] = "Pengguna"
    senderEmail: Optional[str] = ""
    recipientEmails: Union[str, List[str]]
    message: str
    webUrl: Optional[str] = None


class GeneralNotificationRequest(BaseModel):
    recipientEmail: Union[str, List[str]]
    title: str
    message: str
    category: Optional[str] = "Informasi"
    actionUrl: Optional[str] = None
    actionLabel: Optional[str] = "Lihat Detail"


class LeaveRequestSubmittedRequest(BaseModel):
    requestId: Optional[str] = None
    employeeName: str
    employeeEmail: str
    leaveType: str  # leave | wfh
    leaveCategory: Optional[str] = None  # annual | sick | special
    startDate: str
    endDate: Optional[str] = None
    reason: str
    adminEmail: Optional[Union[str, List[str]]] = None
    webUrl: Optional[str] = None


class LeaveRequestStatusRequest(BaseModel):
    requestId: Optional[str] = None
    employeeName: str
    employeeEmail: str
    leaveType: str
    status: str  # APPROVED | REJECTED
    startDate: str
    endDate: Optional[str] = None
    approverNotes: Optional[str] = None
    webUrl: Optional[str] = None


class ExpandClaimSubmittedRequest(BaseModel):
    claimId: Optional[str] = None
    employeeName: str
    employeeEmail: str
    claimType: str  # TRANSPORT | OVERTIME | STANDBY | ALLOWANCE
    amount: float
    purpose: str
    claimDate: str
    clientName: Optional[str] = ""
    destination: Optional[str] = ""
    transportType: Optional[str] = ""
    tripStartDate: Optional[str] = None
    tripEndDate: Optional[str] = None
    adminEmail: Optional[Union[str, List[str]]] = None
    webUrl: Optional[str] = None


class ExpandClaimStatusRequest(BaseModel):
    claimId: Optional[str] = None
    employeeName: str
    employeeEmail: str
    status: str  # APPROVED | REJECTED
    claimType: str
    amount: float
    approvedAmount: Optional[float] = None
    purpose: Optional[str] = ""
    approverNotes: Optional[str] = None
    webUrl: Optional[str] = None


class AccountRegistrationSubmittedRequest(BaseModel):
    employeeName: str
    employeeEmail: str
    phone: Optional[str] = ""
    departmentId: Optional[str] = ""
    employeeId: Optional[str] = ""
    adminEmail: Optional[Union[str, List[str]]] = None
    webUrl: Optional[str] = None


class AccountApprovalDecisionRequest(BaseModel):
    employeeEmail: str
    employeeName: str
    status: str  # approved | rejected
    webUrl: Optional[str] = None


class TestEmailRequest(BaseModel):
    targetEmail: EmailStr


# ==============================================================================
# HELPER: LOOKUP LEADER EMAILS FROM FIRESTORE
# ==============================================================================

def find_leader_emails_for_task(task_id: str, root_task_id: Optional[str] = None) -> List[str]:
    """
    Mencari email Leader / Lead Department penanggung jawab task dari Firestore:
    1. Dari dokumen task / root task itu sendiri (createdByEmail, assignedByEmail, sourceLeaderEmail).
    2. Fallback: semua user dengan role 'leader'.
    """
    emails: List[str] = []
    db = get_db()

    target_ids = [tid for tid in [root_task_id, task_id] if tid]
    for tid in target_ids:
        try:
            doc = db.collection("tasks").document(tid).get()
            if doc.exists:
                data = doc.to_dict() or {}
                for key in ["sourceLeaderEmail", "createdByEmail", "assignedByEmail", "leaderEmail"]:
                    val = data.get(key)
                    if val and isinstance(val, str) and "@" in val:
                        clean = val.strip().lower()
                        if clean not in emails:
                            emails.append(clean)
        except Exception as e:
            logger.warning(f"Gagal mengambil task {tid} untuk pencarian leader email: {e}")

    # Jika masih tidak ada email leader, fallback cari semua user yang memiliki role 'leader'
    if not emails:
        try:
            users_ref = db.collection("users")
            leaders = users_ref.where(filter=FieldFilter("role", "==", "leader")).stream()
            for l_doc in leaders:
                l_data = l_doc.to_dict() or {}
                email = l_data.get("email")
                if email and "@" in email and email.lower().strip() not in emails:
                    emails.append(email.lower().strip())
        except Exception as e:
            logger.warning(f"Gagal mencari fallback leader users: {e}")

    return emails


DEFAULT_HR_EMAILS = [
    "fiismatunnissa@gmail.com",
    "andhini.dini91@gmail.com",
]


def find_admin_emails() -> List[str]:
    """
    Mencari semua email HR/Admin di database Firestore untuk dikirimi notifikasi persetujuan.
    Selalu mengikutsertakan DEFAULT_HR_EMAILS (fiismatunnissa@gmail.com, andhini.dini91@gmail.com).
    """
    emails: List[str] = list(DEFAULT_HR_EMAILS)
    db = get_db()
    try:
        users_ref = db.collection("users")
        for role_val in ["hr", "admin"]:
            docs = users_ref.where(filter=FieldFilter("role", "==", role_val)).stream()
            for doc in docs:
                data = doc.to_dict() or {}
                email = data.get("email")
                if email and "@" in email:
                    clean = email.lower().strip()
                    if clean not in emails:
                        emails.append(clean)
    except Exception as e:
        logger.warning(f"Gagal mengambil admin emails dari Firestore: {e}")

    # Fallback jika belum ada user HR di database
    from services.mailer import SENDER_EMAIL
    if not emails and SENDER_EMAIL and "@" in SENDER_EMAIL:
        clean_sender = SENDER_EMAIL.lower().strip()
        if clean_sender not in emails:
            emails.append(clean_sender)

    return emails


def find_task_participant_emails(task_id: str, root_task_id: Optional[str] = None, exclude_email: Optional[str] = None) -> List[str]:
    """
    Mengambil semua email pengguna yang terlibat dalam task (penerima tugas, pembuat tugas, leader, rekan tim).
    Mengecualikan email pengirim pesan (exclude_email) agar tidak menerima email pesannya sendiri.
    """
    emails: List[str] = []
    clean_exclude = (exclude_email or "").strip().lower()
    db = get_db()

    target_ids = [tid for tid in [task_id, root_task_id] if tid]
    for tid in target_ids:
        try:
            doc = db.collection("tasks").document(tid).get()
            if doc.exists:
                data = doc.to_dict() or {}
                for key in [
                    "assignedToEmail",
                    "userEmail",
                    "createdByEmail",
                    "assignedByEmail",
                    "sourceLeaderEmail",
                    "leaderEmail",
                    "departmentLeadEmail",
                ]:
                    val = data.get(key)
                    if val and isinstance(val, str) and "@" in val:
                        clean = val.strip().lower()
                        if clean != clean_exclude and clean not in emails:
                            emails.append(clean)
        except Exception as e:
            logger.warning(f"Gagal mengambil participant task {tid}: {e}")

    # Ambil juga email dari sub-task turunan jika root_task_id ada
    effective_root = root_task_id or task_id
    if effective_root:
        seen_subtask_ids: set[str] = set()
        for field in ("rootTaskId", "parentTaskId"):
            try:
                subtasks = db.collection("tasks").where(
                    filter=FieldFilter(field, "==", effective_root)
                ).stream()
                for s_doc in subtasks:
                    if s_doc.id in seen_subtask_ids:
                        continue
                    seen_subtask_ids.add(s_doc.id)
                    s_data = s_doc.to_dict() or {}
                    for key in [
                        "assignedToEmail",
                        "userEmail",
                        "createdByEmail",
                        "assignedByEmail",
                        "departmentLeadEmail",
                    ]:
                        val = s_data.get(key)
                        if val and isinstance(val, str) and "@" in val:
                            clean = val.strip().lower()
                            if clean != clean_exclude and clean not in emails:
                                emails.append(clean)
            except Exception as e:
                logger.warning(
                    f"Gagal mengambil subtask participants {effective_root} via {field}: {e}"
                )

    return emails


# ==============================================================================
# ENDPOINTS
# ==============================================================================

@router.post("/task-assigned")
def notify_task_assigned(req: TaskAssignedNotificationRequest, background_tasks: BackgroundTasks):
    """
    Kirim email notifikasi saat ada task baru yang ditugaskan ke Karyawan (misal Leader -> Arya).
    """
    clean_target = req.assignedToEmail.strip().lower()
    if not clean_target or "@" not in clean_target:
        raise HTTPException(status_code=400, detail="assignedToEmail tidak valid.")

    def run_send():
        try:
            send_task_assignment_email(
                task_id=req.taskId,
                task_title=req.taskTitle,
                task_description=req.taskDescription or "",
                assigned_to_email=clean_target,
                assigned_to_name=req.assignedToName or "Karyawan",
                assigned_by_name=req.assignedByName or "Leader",
                assigned_by_email=req.assignedByEmail or "",
                project_name=req.projectName or "",
                client_name=req.clientName or "",
                deadline=req.deadline or "",
                start_date=req.startDate or "",
                priority=req.priority or "MEDIUM",
                detail_task=req.detailTask or "",
                endpoint_api=req.endpointApi or "",
                mandays=req.mandays or "",
                custom_base_url=req.webUrl,
            )
        except Exception as err:
            logger.exception(f"Background task-assigned email failed: {err}")

    background_tasks.add_task(run_send)

    return {
        "status": "success",
        "message": f"Notifikasi email penugasan task '{req.taskTitle}' sedang dikirim ke {clean_target}.",
        "taskId": req.taskId,
        "recipient": clean_target,
    }


@router.post("/daily-report-submitted")
def notify_daily_report_submitted(req: DailyReportNotificationRequest, background_tasks: BackgroundTasks):
    """
    Kirim email notifikasi saat Karyawan submit daily task report ke Leader penanggung jawab.
    """
    leader_recipients: List[str] = []

    if req.leaderEmail:
        if isinstance(req.leaderEmail, list):
            leader_recipients.extend([e.strip().lower() for e in req.leaderEmail if "@" in e])
        elif isinstance(req.leaderEmail, str):
            for part in req.leaderEmail.split(","):
                clean = part.strip().lower()
                if clean and "@" in clean and clean not in leader_recipients:
                    leader_recipients.append(clean)

    # Jika leader email belum didapatkan, otomatis cari dari Firestore
    if not leader_recipients:
        leader_recipients = find_leader_emails_for_task(req.taskId, req.rootTaskId)

    if not leader_recipients:
        logger.warning(f"Tidak ada email Leader yang ditemukan untuk task {req.taskId}. Menggunakan fallback admin.")

    def run_send():
        try:
            if not leader_recipients:
                # Coba cari sekali lagi jika di request belum ada
                recipients = find_leader_emails_for_task(req.taskId, req.rootTaskId)
            else:
                recipients = leader_recipients

            if recipients:
                send_daily_task_email(
                    task_id=req.taskId,
                    task_title=req.taskTitle,
                    employee_name=req.employeeName,
                    employee_email=req.employeeEmail,
                    leader_email=recipients,
                    report_description=req.reportDescription,
                    project_name=req.projectName or "",
                    work_date=req.workDate or "",
                    submitted_at=req.submittedAt or "",
                    root_task_id=req.rootTaskId,
                    custom_base_url=req.webUrl,
                )
            else:
                logger.error(f"Gagal mengirim notifikasi daily task: Leader email tidak dapat ditentukan.")
        except Exception as err:
            logger.exception(f"Background daily-report email failed: {err}")

    background_tasks.add_task(run_send)

    return {
        "status": "success",
        "message": f"Notifikasi daily report dari {req.employeeName} sedang dikirim ke Leader.",
        "taskId": req.taskId,
        "potentialRecipients": leader_recipients,
    }


@router.post("/backlog-message")
def notify_backlog_message(req: BacklogNotificationRequest, background_tasks: BackgroundTasks):
    """
    Kirim email notifikasi jika ada pesan diskusi / backlog baru pada task.
    """
    recipients = [req.recipientEmails] if isinstance(req.recipientEmails, str) else req.recipientEmails
    clean_recipients = [r.strip().lower() for r in recipients if r and "@" in r]

    # Jangan kirim ke si pengirim itu sendiri
    sender_clean = (req.senderEmail or "").strip().lower()

    # Otomatis lengkapi dengan anggota task lain dari Firestore database
    db_recipients = find_task_participant_emails(req.taskId, req.rootTaskId, sender_clean)
    for email in db_recipients:
        if email not in clean_recipients and email != sender_clean:
            clean_recipients.append(email)

    if sender_clean:
        clean_recipients = [r for r in clean_recipients if r != sender_clean]

    if not clean_recipients:
        return {"status": "skipped", "message": "Tidak ada penerima backlog yang perlu dikirimi email."}

    def run_send():
        try:
            send_backlog_message_email(
                task_id=req.taskId,
                task_title=req.taskTitle,
                sender_name=req.senderName,
                sender_role=req.senderRole or "Pengguna",
                message=req.message,
                recipient_email=clean_recipients,
                root_task_id=req.rootTaskId,
                custom_base_url=req.webUrl,
            )
        except Exception as err:
            logger.exception(f"Background backlog email failed: {err}")

    background_tasks.add_task(run_send)

    return {
        "status": "success",
        "message": f"Notifikasi backlog task '{req.taskTitle}' sedang dikirim ke {len(clean_recipients)} pengguna.",
        "recipients": clean_recipients,
    }


@router.post("/general")
def notify_general(req: GeneralNotificationRequest, background_tasks: BackgroundTasks):
    """
    Kirim notifikasi email umum (cuti, izin, dsb).
    """
    def run_send():
        try:
            send_general_notification_email(
                to_email=req.recipientEmail,
                title=req.title,
                message=req.message,
                category=req.category or "Informasi",
                action_url=req.actionUrl,
                action_label=req.actionLabel or "Lihat Detail",
            )
        except Exception as err:
            logger.exception(f"Background general email failed: {err}")

    background_tasks.add_task(run_send)

    return {"status": "success", "message": "Email notifikasi umum sedang dikirim."}


# ------------------------------------------------------------------------------
# CUTI (LEAVE REQUESTS): KARYAWAN -> ADMIN & ADMIN -> KARYAWAN
# ------------------------------------------------------------------------------

@router.post("/leave-request-submitted")
def notify_leave_request_submitted(req: LeaveRequestSubmittedRequest, background_tasks: BackgroundTasks):
    """
    Karyawan -> Admin: Notifikasi pengajuan cuti/izin/WFH baru.
    """
    admin_targets: List[str] = []
    if req.adminEmail:
        if isinstance(req.adminEmail, list):
            admin_targets.extend([e.strip().lower() for e in req.adminEmail if "@" in e])
        elif isinstance(req.adminEmail, str):
            for part in req.adminEmail.split(","):
                clean = part.strip().lower()
                if clean and "@" in clean and clean not in admin_targets:
                    admin_targets.append(clean)

    if not admin_targets:
        admin_targets = find_admin_emails()

    def run_send():
        try:
            send_leave_request_submitted_email(
                admin_emails=admin_targets,
                employee_name=req.employeeName,
                employee_email=req.employeeEmail,
                leave_type=req.leaveType,
                start_date=req.startDate,
                end_date=req.endDate,
                reason=req.reason,
                leave_category=req.leaveCategory,
                custom_base_url=req.webUrl,
            )
        except Exception as err:
            logger.exception(f"Background leave-request-submitted email failed: {err}")

    background_tasks.add_task(run_send)

    return {
        "status": "success",
        "message": f"Notifikasi pengajuan cuti {req.employeeName} sedang dikirim ke Admin.",
        "recipients": admin_targets,
    }


@router.post("/leave-request-status")
def notify_leave_request_status(req: LeaveRequestStatusRequest, background_tasks: BackgroundTasks):
    """
    Admin -> Karyawan: Notifikasi keputusan cuti (Disetujui / Ditolak).
    """
    clean_target = req.employeeEmail.strip().lower()
    if not clean_target or "@" not in clean_target:
        raise HTTPException(status_code=400, detail="employeeEmail tidak valid.")

    def run_send():
        try:
            send_leave_request_status_email(
                employee_email=clean_target,
                employee_name=req.employeeName,
                status=req.status,
                leave_type=req.leaveType,
                start_date=req.startDate,
                end_date=req.endDate,
                approver_notes=req.approverNotes,
                custom_base_url=req.webUrl,
            )
        except Exception as err:
            logger.exception(f"Background leave-request-status email failed: {err}")

    background_tasks.add_task(run_send)

    return {
        "status": "success",
        "message": f"Notifikasi status cuti ({req.status}) sedang dikirim ke {clean_target}.",
        "recipient": clean_target,
    }


# ------------------------------------------------------------------------------
# EXPAND / BUSINESS TRIP CLAIMS: KARYAWAN -> ADMIN & ADMIN -> KARYAWAN
# ------------------------------------------------------------------------------

@router.post("/expand-claim-submitted")
def notify_expand_claim_submitted(req: ExpandClaimSubmittedRequest, background_tasks: BackgroundTasks):
    """
    Karyawan -> Admin: Notifikasi pengajuan klaim biaya expand / perjalanan dinas baru.
    """
    admin_targets: List[str] = []
    if req.adminEmail:
        if isinstance(req.adminEmail, list):
            admin_targets.extend([e.strip().lower() for e in req.adminEmail if "@" in e])
        elif isinstance(req.adminEmail, str):
            for part in req.adminEmail.split(","):
                clean = part.strip().lower()
                if clean and "@" in clean and clean not in admin_targets:
                    admin_targets.append(clean)

    if not admin_targets:
        admin_targets = find_admin_emails()

    def run_send():
        try:
            send_expand_claim_submitted_email(
                admin_emails=admin_targets,
                employee_name=req.employeeName,
                employee_email=req.employeeEmail,
                claim_type=req.claimType,
                amount=req.amount,
                purpose=req.purpose,
                claim_date=req.claimDate,
                client_name=req.clientName or "",
                destination=req.destination or "",
                transport_type=req.transportType or "",
                trip_start_date=req.tripStartDate,
                trip_end_date=req.tripEndDate,
                custom_base_url=req.webUrl,
            )
        except Exception as err:
            logger.exception(f"Background expand-claim-submitted email failed: {err}")

    background_tasks.add_task(run_send)

    return {
        "status": "success",
        "message": f"Notifikasi klaim expand {req.employeeName} sedang dikirim ke Admin/Finance.",
        "recipients": admin_targets,
    }


@router.post("/expand-claim-status")
def notify_expand_claim_status(req: ExpandClaimStatusRequest, background_tasks: BackgroundTasks):
    """
    Admin -> Karyawan: Notifikasi keputusan klaim expand (Disetujui / Ditolak).
    """
    clean_target = req.employeeEmail.strip().lower()
    if not clean_target or "@" not in clean_target:
        raise HTTPException(status_code=400, detail="employeeEmail tidak valid.")

    def run_send():
        try:
            send_expand_claim_status_email(
                employee_email=clean_target,
                employee_name=req.employeeName,
                status=req.status,
                claim_type=req.claimType,
                amount=req.amount,
                approved_amount=req.approvedAmount,
                purpose=req.purpose or "",
                approver_notes=req.approverNotes,
                custom_base_url=req.webUrl,
            )
        except Exception as err:
            logger.exception(f"Background expand-claim-status email failed: {err}")

    background_tasks.add_task(run_send)

    return {
        "status": "success",
        "message": f"Notifikasi status expand ({req.status}) sedang dikirim ke {clean_target}.",
        "recipient": clean_target,
    }


# ------------------------------------------------------------------------------
# PERSETUJUAN AKUN (ACCOUNT APPROVALS): KARYAWAN -> ADMIN & ADMIN -> KARYAWAN
# ------------------------------------------------------------------------------

@router.post("/account-registration-submitted")
def notify_account_registration_submitted(req: AccountRegistrationSubmittedRequest, background_tasks: BackgroundTasks):
    """
    Karyawan -> Admin: Notifikasi pendaftaran akun baru yang telah lolos verifikasi OTP dan menunggu persetujuan HRD.
    """
    admin_targets: List[str] = []
    if req.adminEmail:
        if isinstance(req.adminEmail, list):
            admin_targets.extend([e.strip().lower() for e in req.adminEmail if "@" in e])
        elif isinstance(req.adminEmail, str):
            for part in req.adminEmail.split(","):
                clean = part.strip().lower()
                if clean and "@" in clean and clean not in admin_targets:
                    admin_targets.append(clean)

    if not admin_targets:
        admin_targets = find_admin_emails()

    def run_send():
        try:
            send_account_registration_submitted_email(
                admin_emails=admin_targets,
                employee_name=req.employeeName,
                employee_email=req.employeeEmail,
                phone=req.phone or "",
                department_id=req.departmentId or "",
                employee_id=req.employeeId or "",
                custom_base_url=req.webUrl,
            )
        except Exception as err:
            logger.exception(f"Background account-registration-submitted email failed: {err}")

    background_tasks.add_task(run_send)

    return {
        "status": "success",
        "message": f"Notifikasi pendaftaran akun {req.employeeName} sedang dikirim ke Tim HRD.",
        "recipients": admin_targets,
    }


@router.post("/account-approval-decision")
def notify_account_approval_decision(req: AccountApprovalDecisionRequest, background_tasks: BackgroundTasks):
    """
    Admin -> Karyawan: Notifikasi keputusan persetujuan akun (Disetujui / Ditolak) oleh HRD.
    """
    clean_target = req.employeeEmail.strip().lower()
    if not clean_target or "@" not in clean_target:
        raise HTTPException(status_code=400, detail="employeeEmail tidak valid.")

    def run_send():
        try:
            send_account_approval_decision_email(
                employee_email=clean_target,
                employee_name=req.employeeName,
                status=req.status,
                custom_base_url=req.webUrl,
            )
        except Exception as err:
            logger.exception(f"Background account-approval-decision email failed: {err}")

    background_tasks.add_task(run_send)

    return {
        "status": "success",
        "message": f"Notifikasi keputusan akun ({req.status}) sedang dikirim ke {clean_target}.",
        "recipient": clean_target,
    }


@router.post("/test-email")
def test_send_email(req: TestEmailRequest):
    """
    Endpoint uji coba pengiriman email langsung.
    """
    ok = send_general_notification_email(
        to_email=req.targetEmail,
        title="Uji Coba Sistem Notifikasi Email",
        message="Ini adalah email uji coba untuk memverifikasi bahwa integrasi notifikasi email PT Tri Cipta Integra telah aktif dan berjalan dengan baik.",
        category="Uji Coba",
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Pengiriman email uji coba gagal. Periksa log server dan kredensial SMTP.")

    return {
        "status": "success",
        "message": f"Email uji coba berhasil dikirimkan ke {req.targetEmail}!",
    }
