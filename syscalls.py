from __future__ import annotations
import sys
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Dict, Type, Callable, TextIO
from misc import MiscVM

if TYPE_CHECKING :
    from misc import VMState as Runtime

class OutputStream:
    """A file-like object that captures written characters and can optionally echo to stdout."""
    def __init__(self, echo: bool = False):
        self.buffer: List[str] = []
        self.echo = echo

    def write(self, s: int) -> int:
        self.buffer.append(s)
        if self.echo:
            sys.stdout.write(chr(s))
            sys.stdout.flush()
        return 1

    def clear(self) -> None:
        self.buffer.clear()

    def get_output(self) -> str:
        return "".join(self.buffer)

# --- Syscall Framework ---

# Global registry for all syscall subclasses, mapping ID -> class
_syscall_classes: Dict[int, Type[Syscall]] = {}

class Syscall(ABC):
    """Abstract base class for a system call."""
    SYSCALL_ID: int

    def __init_subclass__(cls, **kwargs):
        """Registers any subclass with a SYSCALL_ID into the global registry."""
        super().__init_subclass__(**kwargs)
        if hasattr(cls, 'SYSCALL_ID'):
            if cls.SYSCALL_ID in _syscall_classes:
                raise TypeError(f"Duplicate syscall ID {cls.SYSCALL_ID} for {cls.__name__}")
            _syscall_classes[cls.SYSCALL_ID] = cls

    @abstractmethod
    def execute(self, rt: Runtime) -> None:
        """The main logic of the syscall, operating on the VM's stack."""
        pass


def get_syscall_classes() -> List[Type[Syscall]]:
    """Returns a list of all registered syscall classes."""
    return list(_syscall_classes.values())


def build_systable(**kwargs) -> Dict[int, Callable[[List[int]], None]]:
    """Builds the VM-compatible systable from a list of configured syscall instances."""
    syscall_instances = [ cls(**kwargs) for cls in get_syscall_classes() ]
    return {instance.SYSCALL_ID: instance.execute for instance in syscall_instances}


# --- Concrete Syscall Implementations ---

class ExitSyscall(Syscall):
    """
    SYSCALL 0 (EXIT): Pops a value from the stack and terminates the VM with that code.
    """
    SYSCALL_ID = 0x00

    def __init__(self, **_kwargs):
        pass

    def execute(self, rt: Runtime) -> Runtime:
        # Import locally to avoid circular dependency with runner.py
        code = rt.registers[0]
        raise MiscVM.Stop(code)


class PutcSyscall(Syscall):
    """
    SYSCALL 1 (PUTC): Pops a value and writes it as a character to the configured stream.
    """
    SYSCALL_ID = 0x01

    def __init__(self, stream: TextIO, **_kwargs):
        self.stream = stream

    def execute(self, rt: Runtime) -> Runtime:
        char_code = rt.registers[0]
        self.stream.write(char_code)
        return rt