from ..services.seed_service import cumulative_seed_scores_before

from .auth import *
from .student import *
from .student_assignment_compat import assignment_attachment_download
from .admin_dashboard import *
from .admin_students import *
from .admin_rounds import *
from .admin_teams import *
from .admin_evaluations import *
from .admin_system import *
from .errors import *
from .admin_hr_tasks import *
from .admin_hr_dashboard import *

# Dedicated thin views override legacy implementations imported above.
from .student_results import student_results
from .student_evaluations import (
    student_evaluation_status,
    student_personal_evaluation,
    student_team_evaluation,
)
from .admin_home import admin_dashboard
from .admin_seed import admin_seed_management
from .admin_results import admin_evaluation_results
from .admin_missing import admin_missing_evaluations
from .admin_result_settings import admin_result_settings
from .admin_result_adjustments import admin_student_result_adjust
from .admin_result_export import admin_evaluation_results_excel_export
from .admin_scores import admin_personal_scores, admin_rankings, admin_team_scores
from .admin_students_filtered import admin_students
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
