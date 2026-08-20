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

# Prefer the thin dedicated view for result pages. The legacy function remains
# in student.py temporarily so existing imports outside the package do not break.
from .student_results import student_results

# Prefer the thin dedicated admin dashboard view. The legacy implementation
# remains in admin_dashboard.py during the staged refactor.
from .admin_home import admin_dashboard

# Prefer the thin dedicated Seed-management view while retaining the legacy
# implementation in admin_evaluations.py for staged compatibility.
from .admin_seed import admin_seed_management

# Prefer the thin dedicated evaluation-results view. The legacy implementation
# remains in admin_evaluations.py during the staged refactor.
from .admin_results import admin_evaluation_results

# Prefer the thin dedicated missing-evaluations view. The legacy implementation
# remains in admin_evaluations.py for staged compatibility.
from .admin_missing import admin_missing_evaluations

# Student management now supports whole-result filtering by evaluation status,
# rather than hiding only rows on the current pagination page.
from .admin_students_filtered import admin_students

# FIFA-style team assignment uses administrator-adjustable A/B/C/D boundaries.
from .admin_team_assignment_configurable import admin_auto_preview

# Tutor evaluates whole teams after evaluation start. This import is intentionally
# last because it replaces old handlers with the three-part scoring policy.
from .admin_tutor import admin_result_weights_save, admin_round_create, admin_tutor_evaluations
