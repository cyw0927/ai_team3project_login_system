# Legacy views still import _recalculate_round_results from common via wildcard.
# Keep this single compatibility binding until those large legacy modules are split.
# Seed/team-assignment helpers are no longer monkey-patched: dedicated views import
# their services directly.
from . import common as _common_module
from ..services.result_service import recalculate_round_results
from ..services.seed_service import cumulative_seed_scores_before

_common_module._recalculate_round_results = recalculate_round_results

# Public helper alias retained for existing tests/tools during the refactor.
_recalculate_round_results = recalculate_round_results

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

# Tutor evaluates whole teams after evaluation start and owns the three-part
# scoring controls for newly created rounds.
from .admin_tutor import admin_result_weights_save, admin_round_create, admin_tutor_evaluations
