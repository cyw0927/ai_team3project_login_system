from .auth import *
from .student import *
from .admin_dashboard import *
from .admin_students import *
from .admin_rounds import *
from .admin_teams import *
from .admin_evaluations import *
from .admin_system import *
from .errors import *

from .admin_hr_tasks import *

from .admin_hr_dashboard import *

# Compatibility bridge: keep existing view modules unchanged while routing
# all runtime result recalculation calls through the service layer.
from ..services.result_service import _recalculate_round_results as _result_recalculate_round_results
from ..services.seed_service import (
    cumulative_seed_scores_before as _service_cumulative_seed_scores_before,
    previous_round_for as _service_previous_round_for,
)
from ..services.team_assignment_service import (
    balanced_random_assignment as _service_balanced_random_assignment,
    pot_seed_assignment as _service_pot_seed_assignment,
    snake_seed_assignment as _service_snake_seed_assignment,
)
from . import admin_evaluations as _admin_evaluations_module
from . import admin_hr_tasks as _admin_hr_tasks_module
from . import admin_teams as _admin_teams_module
from . import student as _student_module

_recalculate_round_results = _result_recalculate_round_results
_cumulative_seed_scores_before = _service_cumulative_seed_scores_before
_previous_round_for = _service_previous_round_for
_snake_seed_assignment = _service_snake_seed_assignment
_pot_seed_assignment = _service_pot_seed_assignment
_balanced_random_assignment = _service_balanced_random_assignment

for _module in (
    _admin_evaluations_module,
    _admin_hr_tasks_module,
    _admin_teams_module,
    _student_module,
):
    _module._recalculate_round_results = _result_recalculate_round_results

_admin_evaluations_module._cumulative_seed_scores_before = _service_cumulative_seed_scores_before
_admin_teams_module._cumulative_seed_scores_before = _service_cumulative_seed_scores_before
_admin_teams_module._previous_round_for = _service_previous_round_for
_admin_teams_module._snake_seed_assignment = _service_snake_seed_assignment
_admin_teams_module._pot_seed_assignment = _service_pot_seed_assignment
_admin_teams_module._balanced_random_assignment = _service_balanced_random_assignment

# Prefer the thin dedicated view for result pages. The legacy function remains
# in student.py temporarily so existing imports outside the package do not break.
from .student_results import student_results
