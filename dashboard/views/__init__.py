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
from . import admin_evaluations as _admin_evaluations_module
from . import admin_hr_tasks as _admin_hr_tasks_module
from . import admin_teams as _admin_teams_module
from . import student as _student_module

_recalculate_round_results = _result_recalculate_round_results
for _module in (
    _admin_evaluations_module,
    _admin_hr_tasks_module,
    _admin_teams_module,
    _student_module,
):
    _module._recalculate_round_results = _result_recalculate_round_results
