# Bind service implementations to the legacy common helper names before view modules
# import them via ``from .common import *``. This keeps old imports working without
# mutating each already-imported view module at runtime.
from . import common as _common_module
from ..services.result_service import _recalculate_round_results as _service_recalculate_round_results
from ..services.seed_service import (
    cumulative_seed_scores_before as _service_cumulative_seed_scores_before,
    previous_round_for as _service_previous_round_for,
)
from ..services.team_assignment_service import (
    balanced_random_assignment as _service_balanced_random_assignment,
    pot_seed_assignment as _service_pot_seed_assignment,
    snake_seed_assignment as _service_snake_seed_assignment,
)

_common_module._recalculate_round_results = _service_recalculate_round_results
_common_module._cumulative_seed_scores_before = _service_cumulative_seed_scores_before
_common_module._previous_round_for = _service_previous_round_for
_common_module._snake_seed_assignment = _service_snake_seed_assignment
_common_module._pot_seed_assignment = _service_pot_seed_assignment
_common_module._balanced_random_assignment = _service_balanced_random_assignment

# Public helper aliases retained for existing tests/tools.
_recalculate_round_results = _service_recalculate_round_results
_cumulative_seed_scores_before = _service_cumulative_seed_scores_before

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
# remains in admin_evaluations.py during the staged refactor.
from .admin_missing import admin_missing_evaluations

# Student management now supports whole-result filtering by evaluation status,
# rather than hiding only rows on the current pagination page.
from .admin_students_filtered import admin_students

# FIFA-style team assignment uses administrator-adjustable A/B/C/D boundaries.
from .admin_team_assignment_configurable import admin_auto_preview
