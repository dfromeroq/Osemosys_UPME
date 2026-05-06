"""Registro central de modelos ORM del backend."""

from .change_request import ChangeRequest
from .change_request_value import ChangeRequestValue
from .catalog_change_log import CatalogChangeLog
from .categorie import Categorie
from .deletion_log import DeletionLog
from .dailytimebracket import Dailytimebracket
from .daytype import Daytype
from .emission import Emission
from .fuel import Fuel
from .mode_of_operation import ModeOfOperation
from .osemosys_param_value import OsemosysParamValue
from .osemosys_param_value_audit import OsemosysParamValueAudit
from .osemosys_output_param_value import OsemosysOutputParamValue
from .parameter import Parameter
from .parameter_storage import ParameterStorage
from .parameter_value_audit import ParameterValueAudit
from .parameter_value import ParameterValue
from .region import Region
from .relation_categorie import RelationCategorie
from .report_template import ReportTemplate
from .report_template_favorite import ReportTemplateFavorite
from .saved_chart_template import SavedChartTemplate
from .saved_chart_template_favorite import SavedChartTemplateFavorite
from .scenario import Scenario
from .scenario_tag import ScenarioTag
from .scenario_tag_category import ScenarioTagCategory
from .scenario_tag_link import ScenarioTagLink
from .scenario_operation_job import ScenarioOperationJob
from .scenario_operation_job_event import ScenarioOperationJobEvent
from .scenario_permission import ScenarioPermission
from .season import Season
from .simulation_benchmark import SimulationBenchmark
from .simulation_job import SimulationJob
from .simulation_job_event import SimulationJobEvent
from .simulation_job_favorite import SimulationJobFavorite
from .solver import Solver
from .storage_set import StorageSet
from .timeslice import Timeslice
from .technology import Technology
from .udc_set import UdcSet
from .core.document_type import DocumentType
from .core.system_setting import SystemSetting
from .core.user import User

__all__ = [
    "Scenario",
    "ScenarioTag",
    "ScenarioTagCategory",
    "ScenarioTagLink",
    "ScenarioOperationJob",
    "ScenarioOperationJobEvent",
    "Parameter",
    "Region",
    "Technology",
    "Fuel",
    "Emission",
    "Solver",
    "Timeslice",
    "ModeOfOperation",
    "Season",
    "Daytype",
    "Dailytimebracket",
    "StorageSet",
    "UdcSet",
    "OsemosysParamValue",
    "OsemosysParamValueAudit",
    "ParameterValue",
    "ParameterValueAudit",
    "ParameterStorage",
    "OsemosysOutputParamValue",
    "ScenarioPermission",
    "ChangeRequest",
    "ChangeRequestValue",
    "CatalogChangeLog",
    "Categorie",
    "DeletionLog",
    "SimulationJob",
    "SimulationJobEvent",
    "SimulationJobFavorite",
    "SimulationBenchmark",
    "RelationCategorie",
    "DocumentType",
    "SystemSetting",
    "User",
    "SavedChartTemplate",
    "SavedChartTemplateFavorite",
    "ReportTemplate",
    "ReportTemplateFavorite",
]


# ============================================================================
# Arquitectura y Consideraciones Técnicas
# ============================================================================
#
# Responsabilidad del módulo:
# - Centralizar imports para autodescubrimiento de metadata SQLAlchemy/Alembic.
#
# Posibles mejoras:
# - Separar `__all__` por dominios para mejorar mantenibilidad.
#
# Riesgos en producción:
# - Omisión de imports puede provocar migraciones incompletas.
#
# Escalabilidad:
# - No aplica.
