"""Saya 相关的工具"""
from __future__ import annotations

import inspect
from datetime import datetime
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    List,
    Literal,
    Optional,
    Protocol,
    Type,
    TypeVar,
    Union,
    overload,
)

from graia.broadcast.entities.decorator import Decorator
from graia.broadcast.entities.event import Dispatchable
from graia.broadcast.typing import T_Dispatcher
from graia.saya.builtins.broadcast.schema import ListenerSchema
from graia.saya.factory import BufferModifier, SchemaWrapper, buffer_modifier, factory
from graia.scheduler import Timer
from graia.scheduler.saya import SchedulerSchema
from graia.scheduler.timers import (
    crontabify,
    every_custom_hours,
    every_custom_minutes,
    every_custom_seconds,
)
from graia.scheduler.utilles import TimeObject

T_Callable = TypeVar("T_Callable", bound=Callable)
Wrapper = Callable[[T_Callable], T_Callable]

T = TypeVar("T")


def gen_subclass(cls: type[T]) -> Generator[type[T], Any, Any]:
    yield cls
    for sub in cls.__subclasses__():
        yield from gen_subclass(sub)


@buffer_modifier
def dispatch(*dispatcher: T_Dispatcher) -> BufferModifier:
    """附加参数解析器，最后必须接 `listen` 才能起效

    Args:
        *dispatcher (T_Dispatcher): 参数解析器

    Returns:
        Callable[[T_Callable], T_Callable]: 装饰器
    """

    return lambda buffer: buffer.setdefault("dispatchers", []).extend(dispatcher)


@overload
def decorate(*decorator: Decorator) -> Wrapper:
    """附加多个无头装饰器

    Args:
        *decorator (Decorator): 无头装饰器

    Returns:
        Callable[[T_Callable], T_Callable]: 装饰器
    """
    ...


@overload
def decorate(name: str, decorator: Decorator, /) -> Wrapper:
    """给指定参数名称附加装饰器

    Args:
        name (str): 参数名称
        decorator (Decorator): 装饰器

    Returns:
        Callable[[T_Callable], T_Callable]: 装饰器
    """
    ...


@overload
def decorate(map: Dict[str, Decorator], /) -> Wrapper:
    """给指定参数名称附加装饰器

    Args:
        map (Dict[str, Decorator]): 参数名称与装饰器的映射

    Returns:
        Callable[[T_Callable], T_Callable]: 装饰器
    """
    ...


@buffer_modifier
def decorate(*args) -> BufferModifier:
    """给指定参数名称附加装饰器

    Args:
        name (str | Dict[str, Decorator]): 参数名称或与装饰器的映射
        decorator (Decorator): 装饰器

    Returns:
        Callable[[T_Callable], T_Callable]: 装饰器
    """
    arg: Union[Dict[str, Decorator], List[Decorator]]
    if isinstance(args[0], str):
        name: str = args[0]
        decorator: Decorator = args[1]
        arg = {name: decorator}
    elif isinstance(args[0], dict):
        arg = args[0]
    else:
        arg = list(args)

    def wrapper(buffer: Dict[str, Any]) -> None:
        if isinstance(arg, list):
            buffer.setdefault("decorators", []).extend(arg)
        elif isinstance(arg, dict):
            buffer.setdefault("decorator_map", {}).update(arg)

    return wrapper


@buffer_modifier
def priority(priority: int, *events: Type[Dispatchable]) -> BufferModifier:
    """设置事件优先级

    Args:
        priority (int): 事件优先级
        *events (Type[Dispatchable]): 提供时则会设置这些事件的优先级, 否则设置全局优先级

    Returns:
        Callable[[T_Callable], T_Callable]: 装饰器
    """

    def wrapper(buffer: Dict[str, Any]) -> None:
        if events:
            buffer.setdefault("extra_priorities", {}).update((e, priority) for e in events)
        else:
            buffer["priority"] = priority

    return wrapper


@factory
def listen(*event: Union[Type[Dispatchable], str]) -> SchemaWrapper:
    """在当前 Saya Channel 中监听指定事件

    Args:
        *event (Union[Type[Dispatchable], str]): 事件类型或事件名称

    Returns:
        Callable[[T_Callable], T_Callable]: 装饰器
    """
    EVENTS: Dict[str, Type[Dispatchable]] = {e.__name__: e for e in gen_subclass(Dispatchable)}
    events: List[Type[Dispatchable]] = [e if isinstance(e, type) else EVENTS[e] for e in event]

    def wrapper(func: Callable, buffer: Dict[str, Any]) -> ListenerSchema:
        decorator_map: Dict[str, Decorator] = buffer.pop("decorator_map", {})
        buffer["inline_dispatchers"] = buffer.pop("dispatchers", [])
        if decorator_map:
            sig = inspect.signature(func)
            for param in sig.parameters.values():
                if decorator := decorator_map.get(param.name):
                    setattr(param, "_default", decorator)
            func.__signature__ = sig
        return ListenerSchema(listening_events=events, **buffer)

    return wrapper


@factory
def schedule(timer: Union[Timer, str], cancelable: bool = True) -> SchemaWrapper:
    """在当前 Saya Channel 中设置定时任务

    Args:
        timer (Union[Timer, str]): 定时器或者类似 crontab 的定时模板
        cancelable (bool): 是否能够取消定时任务, 默认为 True
    Returns:
        Callable[[T_Callable], T_Callable]: 装饰器
    """

    return lambda _, buffer: SchedulerSchema(
        timer=crontabify(timer) if isinstance(timer, str) else timer, cancelable=cancelable, **buffer
    )


class _TimerProtocol(Protocol):
    def __call__(self, value: int, /, *, base: Optional[TimeObject] = None) -> Generator[datetime, None, None]:
        ...


_TIMER_MAPPING: Dict[str, _TimerProtocol] = {
    "second": every_custom_seconds,
    "minute": every_custom_minutes,
    "hour": every_custom_hours,
}


@factory
def every(
    value: int = 1,
    mode: Literal["second", "minute", "hour"] = "second",
    start: Optional[TimeObject] = None,
    cancelable: bool = True,
) -> SchemaWrapper:
    """在当前 Saya Channel 中设置基本的定时任务

    Args:
        value (int): 时间间隔, 默认为 1
        mode (Literal["second", "minute", "hour"]): 定时模式, 默认为 ’second‘
        start (Optional[Union[datetime, time, str, float]]): 定时起始时间, 默认为 datetime.now()
        cancelable (bool): 是否能够取消定时任务, 默认为 True
    Returns:
        Callable[[T_Callable], T_Callable]: 装饰器
    """

    return lambda _, buffer: SchedulerSchema(
        timer=_TIMER_MAPPING[mode](value, base=start), cancelable=cancelable, **buffer
    )


@factory
def crontab(pattern: str, start: Optional[TimeObject] = None, cancelable: bool = True) -> SchemaWrapper:
    """在当前 Saya Channel 中设置类似于 crontab 模板的定时任务

    Args:
        pattern (str): 类似 crontab 的定时模板
        start (Optional[Union[datetime, time, str, float]]): 定时起始时间, 默认为 datetime.now()
        cancelable (bool): 是否能够取消定时任务, 默认为 True
    Returns:
        Callable[[T_Callable], T_Callable]: 装饰器
    """

    return lambda _, buffer: SchedulerSchema(timer=crontabify(pattern, start), cancelable=cancelable, **buffer)


on_timer = schedule
