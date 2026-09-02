"""规则包：导入即注册全部内置规则到注册表（rules.base._REGISTRY）。"""

from . import syntax_rules  # noqa: F401  (注册 assign-in-condition / unbalanced-bracket / syntax-error)
from . import variable_rules  # noqa: F401
from . import import_rules  # noqa: F401
from . import exception_rules  # noqa: F401
from . import scenario_rules  # noqa: F401
