from ..services.seed_service import cumulative_seed_scores_before

from .auth import *
from .admin_dashboard import *
from .admin_rounds import *
from .admin_evaluations import *
from .admin_system import *
from .errors import *
from .admin_hr_tasks import *
from .admin_hr_dashboard import *

# Dedicated student views.
from .student_core import student_home, student_team_info
from .student_results import student_results
from .student_evaluations import (
    student_evaluation_status,
    student_personal_evaluation,
    student_team_evaluation,
)
from .student_assignments import (
    assignment_attachment_download,
    student_assignment_info,
    student_submission_attachment_download,
    submission_attachment_download,
)
from .student_account import (
    student_announcement_read,
    student_feedback,
    student_feedback_read,
    student_message_read,
    student_messages,
    student_notifications,
    student_profile,
    student_self_review,
)
from .student_hr import (
    hr_task_attachment_download,
    student_hr_task_step_toggle,
    student_hr_task_submit,
    student_hr_tasks,
)

# Dedicated admin views.
from .admin_home import admin_dashboard
from .admin_seed import admin_seed_management
from .admin_results import admin_evaluation_results
from .admin_missing import admin_missing_evaluations
from .admin_result_settings import admin_result_settings
from .admin_result_adjustments import admin_student_result_adjust
from .admin_result_export import admin_evaluation_results_excel_export
from .admin_scores import admin_personal_scores, admin_rankings, admin_team_scores
from .admin_student_list import admin_students
from .admin_student_excel import admin_students_excel_export, admin_students_excel_upload
from .admin_student_crud import (
    admin_student_create,
    admin_student_delete,
    admin_student_reset_password,
    admin_student_toggle_active,
    admin_student_update,
)
from .admin_student_detail import (
    admin_student_comment_delete,
    admin_student_comment_save,
    admin_student_detail,
    admin_student_skill_delete,
    admin_student_skill_save,
)
from .admin_student_messages import (
    admin_student_message_send,
    admin_students_bulk_message_send,
)
from .admin_skills import (
    admin_skill_create,
    admin_skill_delete,
    admin_skill_sync_all,
    admin_skill_update,
    admin_skills,
    admin_students_bulk_skill_save,
)
from .admin_team_management import (
    admin_team_create,
    admin_team_delete,
    admin_team_update,
    admin_teams,
    admin_teams_excel_export,
)
from .admin_team_assignment import (
    admin_auto_confirm,
    admin_manual_assign,
    admin_manual_unassign,
    admin_team_assignment,
    admin_team_dissolve_all,
    admin_team_member_role_update,
)
from .admin_team_assignment_configurable import admin_auto_preview
from .admin_round_lifecycle import admin_round_action, admin_round_delete, admin_round_update
from .admin_assignments import (
    admin_assignment_create,
    admin_assignment_delete,
    admin_assignment_update,
    admin_assignments,
)

# Tutor evaluates whole teams after evaluation start and owns the three-part
# scoring controls for newly created rounds.
from .admin_tutor import admin_result_weights_save, admin_round_create, admin_tutor_evaluations
