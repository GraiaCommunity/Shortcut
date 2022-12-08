import contextlib
import sys
import types
from typing import Tuple, Type, TypeVar, Union

from typing_extensions import Annotated, Any, TypeGuard, get_args, get_origin

_T = TypeVar("_T")


def is_subclass(obj: Any, cls: Type[_T]) -> TypeGuard[Type[_T]]:
    return isinstance(obj, type) and issubclass(obj, cls)


AnnotatedType = type(Annotated[int, lambda x: x > 0])
Unions = (Union, types.UnionType) if sys.version_info >= (3, 10) else (Union,)


def generic_issubclass(cls: Any, par: Union[type, Any, Tuple[type, ...]]) -> bool:
    """检查 cls 是否是 args 中的一个子类, 支持泛型, Any, Union

    Args:
        cls (type): 要检查的类
        par (Union[type, Any, Tuple[type, ...]]): 要检查的类的父类

    Returns:
        bool: 是否是父类
    """
    if par is Any:
        return True
    with contextlib.suppress(TypeError):
        if isinstance(par, AnnotatedType):
            return generic_issubclass(cls, get_args(par)[0])
        if isinstance(par, type):
            return issubclass(cls, par)
        if get_origin(par) in Unions:
            return any(generic_issubclass(cls, p) for p in get_args(par))
        if isinstance(par, TypeVar):
            if par.__constraints__:
                return any(generic_issubclass(cls, p) for p in par.__constraints__)
            if par.__bound__:
                return generic_issubclass(cls, par.__bound__)
        if isinstance(par, tuple):
            return any(generic_issubclass(cls, p) for p in par)
        if isinstance(origin := get_origin(par), type):
            return issubclass(cls, origin)
    return False


def is_union(obj: Any) -> bool:
    return get_origin(obj) in Unions
