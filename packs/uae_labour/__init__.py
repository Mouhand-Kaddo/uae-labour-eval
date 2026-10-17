"""UAE labour-law pack: the calculation tools the agent may call."""

from .annual_leave import ANNUAL_LEAVE_TOOL
from .gratuity import GRATUITY_TOOL
from .notice_period import NOTICE_PERIOD_TOOL
from .probation import PROBATION_TOOL

TOOLS = [GRATUITY_TOOL, ANNUAL_LEAVE_TOOL, NOTICE_PERIOD_TOOL, PROBATION_TOOL]
