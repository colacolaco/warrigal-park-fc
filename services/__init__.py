"""Business services for the Warrigal Park FC registration system.

Each module in this package owns one capability and is the only place its
business rules are implemented.  The web layer calls these functions and never
writes SQL itself, which is what makes the rules testable directly.
"""

from services.member_service import (  # noqa: F401
    create_member,
    deactivate_member,
    find_members,
    get_member,
    reactivate_member,
    update_member,
)
from services.guardian_service import (  # noqa: F401
    create_guardian,
    find_guardians,
    get_guardian,
    has_guardian,
    link_guardian,
    list_guardians_for_member,
    list_juniors_for_guardian,
    unlink_guardian,
    update_guardian,
)
from services.registration_service import (  # noqa: F401
    amend_registration,
    complete_registration,
    find_registrations,
    get_registration,
    registration_history,
    start_registration,
    summarise_season,
    withdraw_registration,
)
from services.team_service import (  # noqa: F401
    add_player,
    create_team,
    find_teams,
    get_team,
    move_player,
    remove_player,
    roster_contact_gaps,
    team_roster,
)
from services.validation import (  # noqa: F401
    AGE_OF_MAJORITY,
    BusinessRuleError,
    ValidationError,
    age_group_for,
    calculate_age,
    is_minor,
    parse_date,
)

__all__ = [
    "AGE_OF_MAJORITY",
    "BusinessRuleError",
    "ValidationError",
    "add_player",
    "age_group_for",
    "amend_registration",
    "calculate_age",
    "complete_registration",
    "create_guardian",
    "create_member",
    "create_team",
    "deactivate_member",
    "find_guardians",
    "find_members",
    "find_registrations",
    "find_teams",
    "get_guardian",
    "get_member",
    "get_registration",
    "get_team",
    "has_guardian",
    "is_minor",
    "link_guardian",
    "list_guardians_for_member",
    "list_juniors_for_guardian",
    "move_player",
    "parse_date",
    "reactivate_member",
    "registration_history",
    "remove_player",
    "roster_contact_gaps",
    "start_registration",
    "summarise_season",
    "team_roster",
    "unlink_guardian",
    "update_guardian",
    "update_member",
    "withdraw_registration",
]
