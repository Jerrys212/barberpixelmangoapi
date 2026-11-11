from src.models import Base


def load_models() -> type[Base]:
    from src.audit import models as audit_models  # noqa: F401
    from src.auth import models as auth_models  # noqa: F401
    from src.business import models as business_models  # noqa: F401
    from src.catalog import models as catalog_models  # noqa: F401
    from src.schedule import models as schedule_models  # noqa: F401
    from src.users import models as users_models  # noqa: F401

    return Base
