"""Broadcast Interrupt 相关的工具"""
from __future__ import annotations

import asyncio
import contextlib
from typing import (
    Any,
    Awaitable,
    Callable,
    Generic,
    List,
    Optional,
    Type,
    TypeVar,
    cast,
    overload,
)

from graia.broadcast.entities.decorator import Decorator
from graia.broadcast.entities.event import Dispatchable
from graia.broadcast.exceptions import ExecutionStop
from graia.broadcast.interfaces.dispatcher import DispatcherInterface
from graia.broadcast.interrupt import InterruptControl, Waiter
from graia.broadcast.typing import T_Dispatcher
from typing_extensions import Self, TypeVarTuple, Unpack

T = TypeVar("T")

T_E = TypeVar("T_E", bound=Dispatchable)


class _ExtendedWaiter(Waiter, Generic[T, T_E]):
    """集成 InterruptControl 的 waiter."""

    listening_events: List[Type[T_E]]

    def __init__(
        self,
        events: List[Type[T_E]],
        dispatchers: List[T_Dispatcher],
        decorators: List[Decorator],
        priority: int,
        block_propagation: bool,
    ) -> None:
        self.listening_events = self.events = events
        self.using_dispatchers = self.dispatchers = dispatchers
        self.using_decorators = self.decorators = decorators
        self.priority = priority
        self.block_propagation = block_propagation

    @overload
    async def wait(self, timeout: float, default: T) -> T:
        ...

    @overload
    async def wait(self, timeout: float, default: Optional[T] = None) -> Optional[T]:
        ...

    @overload
    async def wait(self, timeout: None = None) -> T:
        ...

    async def wait(self, timeout: Optional[float] = None, default: Optional[T] = None):
        """等待 Waiter, 如果超时则返回默认值

        Args:
            timeout (float, optional): 超时时间, 单位为秒
            default (T, optional): 默认值
        """
        from creart import it

        inc = it(InterruptControl)
        if timeout:
            try:
                return await inc.wait(self, timeout=timeout)
            except asyncio.TimeoutError:
                return default
        return await inc.wait(self)


class FunctionWaiter(_ExtendedWaiter[T, Dispatchable]):
    """将 Waiter.create_using_function 封装了一层"""

    def __init__(
        self,
        func: Callable[..., Awaitable[Optional[T]]],
        events: List[Type[Dispatchable]],
        dispatchers: Optional[List[T_Dispatcher]] = None,
        decorators: Optional[List[Decorator]] = None,
        priority: int = 15,
        block_propagation: bool = False,
    ) -> None:
        """
        Args:
            func (Callable): 调用函数
            events (List[Type[Dispatchable]]): 事件类型
            dispatchers (Optional[List[T_Dispatcher]]): 广播器
            decorators (Optional[List[Decorator]]): 装饰器
            priority (int): 优先级
            block_propagation (bool): 是否阻止事件往下传播
        """
        super().__init__(events, dispatchers or [], decorators or [], priority, block_propagation)
        self.detected_event = func  # type: ignore


class EventWaiter(_ExtendedWaiter[T_E, T_E]):
    """将 Waiter.create_using_event 封装了一层."""

    def __init__(
        self,
        events: List[Type[T_E]],
        dispatchers: Optional[List[T_Dispatcher]] = None,
        decorators: Optional[List[Decorator]] = None,
        extra_validator: Optional[Callable[[T_E], bool]] = None,
        priority: int = 15,
        block_propagation: bool = False,
    ) -> None:
        """
        Args:
            events (List[Type[T_E]]): 事件类型
            dispatchers (Optional[List[T_Dispatcher]], optional): Dispatcher 列表
            decorators (Optional[List[Decorator]], optional): Decorator 列表
            extra_validator (Optional[Callable[[T_E], bool]], optional): 额外的验证器
            priority (int, optional): 优先级, 越小越靠前
            block_propagation (bool): 是否阻止事件往下传播
        """
        super().__init__(events, dispatchers or [], decorators or [], priority, block_propagation)
        self.extra_validator = extra_validator

    async def detected_event(self, ev: Dispatchable) -> T_E:
        event = cast(T_E, ev)
        if self.extra_validator and not self.extra_validator(event):
            raise ExecutionStop
        return event


Ts = TypeVarTuple("Ts")
V = TypeVar("V")


class AnnotationWaiter(_ExtendedWaiter[T, T_E]):
    """用于直接获取对应标注的 Waiter."""

    def __init__(
        self,
        annotation: Type[T],
        events: List[Type[T_E]],
        dispatchers: Optional[List[T_Dispatcher]] = None,
        decorator: Optional[Decorator] = None,
        headless_decorators: Optional[List[Decorator]] = None,
        priority: int = 15,
        block_propagation: bool = False,
    ) -> None:
        """
        Args:
            annotation (Type[T]): 参数标注
            events (List[Type[T_E]]): 事件类型
            dispatchers (Optional[List[T_Dispatcher]], optional): Dispatcher 列表
            decorator (Decorator, optional): 可选的参数装饰器
            headless_decorators (Optional[List[Decorator]], optional): 无头 Decorator 列表
            priority (int, optional): 优先级, 越小越靠前
            block_propagation (bool): 是否阻止事件往下传播
        """
        super().__init__(events, dispatchers or [], headless_decorators or [], priority, block_propagation)
        self.annotation: Type[T] = annotation
        self.decorator = decorator
        self.anno_validators: list[tuple[type, Callable[[Any], bool]]] = []

    @overload
    def validator(self, func: Callable[[T_E], bool], /) -> Self:
        ...

    @overload
    def validator(self, annotation: Type[V], func: Callable[[V], bool], /) -> Self:
        ...

    def validator(self, *args: Any) -> Self:
        if len(args) == 1 and callable(args[0]):
            self.anno_validators.append((Dispatchable, args[0]))
        elif len(args) == 2:
            self.anno_validators.append(args)
        else:
            raise ValueError(f"Unrecognized arguments: {args}")
        return self

    async def detected_event(self, dii: DispatcherInterface) -> T:
        for anno, validator in self.anno_validators:
            res = False
            with contextlib.suppress(Exception):
                val: Any = await dii.lookup_param("__AnnotationWaiter_annotation__", anno, None)
                res = validator(val)
            if not res:
                raise ExecutionStop

        return await dii.lookup_param("__AnnotationWaiter_annotation__", self.annotation, self.decorator)
