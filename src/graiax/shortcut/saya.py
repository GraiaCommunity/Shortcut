"""Saya 相关的工具"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    List,
    Literal,
    Optional,
    Type,
    TypeVar,
    Union,
    overload,
)

from graia.broadcast.entities.decorator import Decorator
from graia.broadcast.entities.event import Dispatchable
from graia.broadcast.typing import T_Dispatcher
from graia.saya import BaseSchema, Channel
from graia.saya.builtins.broadcast.schema import ListenerSchema
from graia.saya.cube import Cube
from graia.scheduler import Timer
from graia.scheduler.saya import SchedulerSchema
from graia.scheduler.timers import (
    crontabify,
    every_custom_hours,
    every_custom_minutes,
    every_custom_seconds,
    every_second,
)
from graia.scheduler.utilles import TimeObject

T_Callable = TypeVar("T_Callable", bound=Callable)
Wrapper = Callable[[T_Callable], T_Callable]

T = TypeVar("T")


@dataclass
class TempSchema(BaseSchema):
    # public
    dispatchers: List[T_Dispatcher] = field(default_factory=list)
    decorators: List[Decorator] = field(default_factory=list)
    # listener
    listening_events: List[Type[Dispatchable]] = field(default_factory=list)
    priority: int = 16
    extra_priorities: Dict[Type[Dispatchable], int] = field(default_factory=dict)
    # scheduler
    timer: Timer = every_second()
    cancelable: bool = field(default=False)


def gen_subclass(cls: type[T]) -> Generator[type[T], Any, Any]:
    yield cls
    for sub in cls.__subclasses__():
        yield from gen_subclass(sub)


def ensure_cube_mounted(func: Callable) -> Cube[TempSchema]:
    if hasattr(func, "__cube__"):
        if not isinstance(func.__cube__.metaclass, TempSchema):
            raise TypeError(f"Cannot use {func.__cube__.metaclass.__name__} unless ensure the top behavior")
        return func.__cube__
    channel = Channel.current()
    for cube in channel.content:
        if cube.content is func and isinstance(cube.metaclass, TempSchema):
            func.__cube__ = cube
            break
    else:
        cube = Cube(func, TempSchema())
        channel.content.append(cube)
        func.__cube__ = cube
    return func.__cube__


def convert_to_listener(func: Callable) -> Cube[ListenerSchema]:
    channel = Channel.current()
    if not hasattr(func, "__cube__"):
        new: Cube[ListenerSchema] = Cube(func, ListenerSchema([], None, [], [], 16))
        channel.content.append(new)
        return new
    prev = getattr(func, "__cube__")
    if not isinstance(prev.metaclass, TempSchema):
        raise TypeError(f"Cannot use {prev.metaclass.__name__} unless ensure the top behavior")
    temp: TempSchema = prev.metaclass
    new: Cube[ListenerSchema] = Cube(
        func, ListenerSchema(
            temp.listening_events, 
            None, 
            temp.dispatchers, 
            temp.decorators, 
            temp.priority,
            temp.extra_priorities
        )
    )
    for cube in channel.content:
        if cube.content is func and isinstance(cube.metaclass, TempSchema):
            channel.content.remove(cube)
            channel.content.append(new)
            break
    delattr(func, "__cube__")
    return new


def convert_to_scheduler(func: Callable) -> Cube[SchedulerSchema]:
    channel = Channel.current()
    if not hasattr(func, "__cube__"):
        new: Cube[SchedulerSchema] = Cube(func, SchedulerSchema(every_second(), True))
        channel.content.append(new)
        return new
    prev = getattr(func, "__cube__")
    if not isinstance(prev.metaclass, TempSchema):
        raise TypeError(f"Cannot use {prev.metaclass.__name__} unless ensure the top behavior")
    temp: TempSchema = prev.metaclass
    new = Cube(func, SchedulerSchema(temp.timer, temp.cancelable, temp.decorators, temp.dispatchers))
    for cube in channel.content:
        if cube.content is func and isinstance(cube.metaclass, TempSchema):
            channel.content.remove(cube)
            channel.content.append(new)
            break
    delattr(func, "__cube__")
    return new


def dispatch(*dispatcher: T_Dispatcher) -> Wrapper:
    """附加参数解析器，最后必须接 `listen` 才能起效

    Args:
        *dispatcher (T_Dispatcher): 参数解析器

    Returns:
        Callable[[T_Callable], T_Callable]: 装饰器
    """

    def wrapper(func: T_Callable) -> T_Callable:
        cube: Cube[TempSchema] = ensure_cube_mounted(func)
        cube.metaclass.dispatchers.extend(dispatcher)
        return func

    return wrapper


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


def decorate(*args) -> Wrapper:
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

    def wrapper(func: T_Callable) -> T_Callable:
        cube = ensure_cube_mounted(func)
        if isinstance(arg, list):
            cube.metaclass.decorators.extend(arg)
        elif isinstance(arg, dict):
            sig = inspect.signature(func)
            _ = sig.parameters
            for param in sig.parameters.values():
                if param.name in arg:
                    setattr(param, "_default", arg[param.name])
            func.__signature__ = sig
        return func

    return wrapper


def listen(*event: Union[Type[Dispatchable], str]) -> Wrapper:
    """在当前 Saya Channel 中监听指定事件

    Args:
        *event (Union[Type[Dispatchable], str]): 事件类型或事件名称

    Returns:
        Callable[[T_Callable], T_Callable]: 装饰器
    """
    event_map: Dict[str, Type[Dispatchable]] = {e.__name__: e for e in gen_subclass(Dispatchable)}
    events: List[Type[Dispatchable]] = [e if isinstance(e, type) else event_map[e] for e in event]

    def wrapper(func: T_Callable) -> T_Callable:
        cube = convert_to_listener(func)
        cube.metaclass.listening_events.extend(events)
        return func

    return wrapper


def priority(priority: int, *events: Type[Dispatchable]) -> Wrapper:
    """设置事件优先级

    Args:
        priority (int): 事件优先级
        *events (Type[Dispatchable]): 提供时则会设置这些事件的优先级, 否则设置全局优先级

    Returns:
        Callable[[T_Callable], T_Callable]: 装饰器
    """

    def wrapper(func: T_Callable) -> T_Callable:
        cube = ensure_cube_mounted(func)
        cube.metaclass.priority = priority
        if events:
            extra: Dict[Optional[Type[Dispatchable]], int] = getattr(cube.metaclass, "extra_priorities", {})
            extra.update((e, priority) for e in events)
        return func

    return wrapper


def schedule(timer: Union[Timer, str], cancelable: bool = True) -> Wrapper:
    """在当前 Saya Channel 中设置定时任务

    Args:
        timer (Union[Timer, str]): 定时器或者类似 crontab 的时间模式
        cancelable (bool): 是否能够取消定时任务, 默认为 True
    Returns:
        Callable[[T_Callable], T_Callable]: 装饰器
    """

    def wrapper(func: T_Callable):
        cube = convert_to_scheduler(func)
        cube.metaclass.timer = crontabify(timer) if isinstance(timer, str) else timer
        cube.metaclass.cancelable = cancelable
        return func

    return wrapper


_timer = {"second": every_custom_seconds, "minute": every_custom_minutes, "hour": every_custom_hours}


def every(
    value: int = 1,
    mode: Literal["second", "minute", "hour"] = "second",
    start: Optional[TimeObject] = None,
) -> Wrapper:
    """在当前 Saya Channel 中设置基本的定时任务

    Args:
        value (int): 时间间隔, 默认为 1
        mode (Literal["second", "minute", "hour"]): 定时模式, 默认为 ’second‘
        start (Optional[Type[Union[datetime, time, str, float]]]): 定时起始时间, 默认为 datetime.now()
    Returns:
        Callable[[T_Callable], T_Callable]: 装饰器

    """

    def wrapper(func: T_Callable):
        cube = convert_to_scheduler(func)
        cube.metaclass.timer = _timer[mode](value, base=start)
        return func

    return wrapper


def crontab(pattern: str, base: Optional[TimeObject] = None, cancelable: bool = True) -> Wrapper:
    def wrapper(func: T_Callable):
        cube = convert_to_scheduler(func)
        cube.metaclass.timer = crontabify(pattern, base)
        cube.metaclass.cancelable = cancelable
        return func

    return wrapper


on_timer = schedule
