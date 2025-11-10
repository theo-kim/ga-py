"""Minimal Instruction Set VM"""
from __future__ import annotations
import ctypes
import platform
import os
import sys

from string import printable

from dataclasses import dataclass
from typing import (
    Generator,
    List,
    Dict,
    Callable,
    Literal,
    Optional,
    Tuple,
)

DBG = False
Endian = Literal["big", "little"]

# --- C Core Integration & Interrupts ---

# Read constants from the C header file to keep them in sync
def _load_constants_from_header(header_path):
    constants = {}
    with open(header_path, 'r') as f:
        for line in f:
            if line.startswith("#define"):
                parts = line.split()
                if len(parts) >= 3:
                    name = parts[1]
                    try:
                        value = int(parts[2], 0) # Handles hex, dec
                        constants[name] = value
                    except ValueError:
                        pass # Not a simple numeric define
    return constants

class VMState(ctypes.Structure):
    """VMState structure to match the C implementation, represents the runtime"""
    _fields_ = [
        ("pc", ctypes.c_uint16),
        ("registers", ctypes.c_uint8 * 16),
        ("memory", ctypes.c_uint8 * 64),
        ("interrupt", ctypes.c_int16),
        ("flags", ctypes.c_uint8), # For arithmetic flags
        ("steps", ctypes.c_uint32),
        ("op", ctypes.c_uint16),
        ("rd", ctypes.c_uint16),
        ("rs", ctypes.c_uint16),
        ("imm4", ctypes.c_uint16),
        ("imm8", ctypes.c_uint16),
        ("imm12", ctypes.c_uint16),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Load constants only once
        if not hasattr(type(self), 'CONSTANTS'):
            type(self).CONSTANTS = _load_constants_from_header(os.path.join(os.path.dirname(__file__), "vm_core.h"))

    def _show_imm(self, imm) -> str :
        if chr(imm) in printable :
            return f"{imm} '{chr(imm)}'"
        else :
            return f"{imm}"

    def _format_instruction(self) -> str:
        """Pretty print instruction"""
        if self.op == self.CONSTANTS.get('OP_SYSCALL'):
            return f"SYSCALL {self.imm12}"
        elif self.op == self.CONSTANTS.get('OP_MOV_REG_IMM'):
            return f"MOV_REG_IMM r{self.rd}, {self._show_imm(self.imm8)}"
        elif self.op == self.CONSTANTS.get('OP_MOV_REG_REG_SHR'):
            return f"MOV_REG_REG_SHR r{self.rd}, r{self.rs}, {self.imm4}"
        elif self.op == self.CONSTANTS.get('OP_MOV_REG_REG_SHL'):
            return f"MOV_REG_REG_SHL r{self.rd}, r{self.rs}, {self.imm4}"
        elif self.op == self.CONSTANTS.get('OP_MOV_REG_REG_ADD'):
            return f"MOV_REG_REG_ADD r{self.rd}, r{self.rs}, r{self.imm4}"
        elif self.op == self.CONSTANTS.get('OP_LD_REG_MEM'):
            return f"LD_REG_MEM r{self.rd}, [r{self.rs}], {self.imm4}"
        elif self.op == self.CONSTANTS.get('OP_ST_MEM_REG'):
            return f"ST_MEM_REG [r{self.rd}], r{self.rs}, {self.imm4}"
        elif self.op == self.CONSTANTS.get('OP_ADD'):
            return f"ADD r{self.rd}, r{self.rs}, r{self.imm4}"
        elif self.op == self.CONSTANTS.get('OP_SUB'):
            return f"SUB r{self.rd}, r{self.rs}, r{self.imm4}"
        elif self.op == self.CONSTANTS.get('OP_AND'):
            return f"AND r{self.rd}, r{self.rs}, r{self.imm4}"
        elif self.op == self.CONSTANTS.get('OP_OR'):
            return f"OR r{self.rd}, r{self.rs}, r{self.imm4}"
        elif self.op == self.CONSTANTS.get('OP_XOR'):
            return f"XOR r{self.rd}, r{self.rs}, r{self.imm4}"
        elif self.op == self.CONSTANTS.get('OP_NOT'):
            return f"NOT r{self.rd}"
        elif self.op == self.CONSTANTS.get('OP_JMP'):
            return f"JMP {self.rd}, {self.imm8}"
        elif self.op == self.CONSTANTS.get('OP_JZ'):
            return f"JZ r{self.rd}, r{self.rs}, {self.imm4}"
        elif self.op == self.CONSTANTS.get('OP_NOP'):
            if self.imm12 == self.CONSTANTS.get('OP_RAW_DUMP'):
                return "MEMLOAD"
            else :
                return f"NOP {self.imm12}"
        else:
            return "UNKNOWN"

    def _format_memory(self) -> str:
        """Formats the memory as an 8x8 hexdump-style grid."""
        lines = ["Memory (8x8 Grid):"]
        for i in range(0, 64, 8):
            chunk = self.memory[i:i+8]
            
            # Hex part
            hex_part = " ".join(f"{byte:02x}" for byte in chunk)
            
            # ASCII part
            ascii_part = "".join(
                chr(byte) if 32 <= byte <= 126 else "." for byte in chunk
            )
            
            lines.append(f"  {i:02x}:  {hex_part:<23}  |{ascii_part}|")
        return "\n".join(lines)

    def __repr__(self) :
        registers = ", ".join([f"{i}({v})" for i, v in enumerate(self.registers)])
        instruction = self._format_instruction()
        return "\n".join([
            f"PC: {self.pc}",
            f"Int: {self.interrupt} ({hex(self.interrupt)})",
            f"Registers: {registers}",
            f"Instruction: {instruction}",
            self._format_memory()
        ])

# Load the compiled C library
LIB_EXT = ".dll" if platform.system() == "Windows" else ".so"
LIB_PATH = os.path.join(os.path.dirname(__file__), "vm_core" + LIB_EXT)

# Load constants from header
CONSTANTS = _load_constants_from_header(os.path.join(os.path.dirname(__file__), "vm_core.h"))

vm_core = ctypes.CDLL(LIB_PATH)

# --- Function Prototypes ---
vm_core.run_c.argtypes = [ctypes.POINTER(VMState), ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_bool]\

vm_core.assemble_instruction.argtypes = [ctypes.c_char_p, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint16,
                                         ctypes.POINTER(ctypes.c_uint16), ctypes.POINTER(ctypes.c_char_p)]
vm_core.assemble_instruction.restype = ctypes.c_int

vm_core.disassemble.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)]
vm_core.disassemble.restype = ctypes.c_int

vm_core.free_memory.argtypes = [ctypes.c_void_p]
vm_core.free_memory.restype = None

Systable = Dict[int, Callable[[VMState], Optional[VMState]]]

# =========================
# VM result container
# =========================
@dataclass
class VMResult:
    """Capture how the VM terminated"""
    halted: bool                # True if the VM did not exit gracefully
    error: Optional[Exception]  # The error which halted termination (if applicable)
    exit_code: Optional[int]    # Exit code if EXIT was used; otherwise Non
    steps: int                  # Number of steps taken
    rt: VMState                 # The runtime at program termination

# =========================
# MISC v3 VM (Register-based)
# =========================
class MiscVM:
    """
    An 8-bit, register-based VM with 8 general-purpose registers and 256 bytes of RAM.
    """

    class Stop(Exception) :
        """Gracefully stop the VM"""
        def __init__(self, code: int) :
            self.code = code & 0xFF

    class Error(Exception) :
        """An error type for the VM"""
        def __init__(self, error: str, state: VMState = None) :
            super().__init__(error)
            self.rt = state

    def __init__(self, systable: Systable):
        self.systable = systable

    def run(
        self,
        program: bytes,
        max_steps: Optional[int] = None,
    ) -> VMResult:
        """
        Execute using the high-performance C core.
        """
        max_steps = max_steps or (2**32 - 1)

        state = VMState()
        state.pc = 0
        state.steps = 0
        state.interrupt = CONSTANTS.get('INTERRUPT_NONE', -1)

        try:
            while True:
                vm_core.run_c(ctypes.byref(state), program, len(program), max_steps, False)

                if state.interrupt >= 0: # Positive interrupt is a syscall
                    syscall_id = state.interrupt
                    try:
                        syscall_handler = self.systable[syscall_id]
                        syscall_handler(state) # Pass the C state object
                    except KeyError as exc:
                        raise self.Error(f"Unknown syscall: {syscall_id}", state) from exc
                    except self.Stop as e: # Exit syscall raises this
                        return VMResult(False, None, e.code, state.steps, state)
                elif state.interrupt < -1: # Negative interrupt is an error/halt
                    error_map = {
                        CONSTANTS.get('INTERRUPT_MAX_STEPS'): "Runtime limit exceeded",
                        CONSTANTS.get('INTERRUPT_ILLEGAL_PC'): "Illegal PC access",
                        CONSTANTS.get('INTERRUPT_PROTECTED_REG'): "Protected register write attempt",
                        CONSTANTS.get('INTERRUPT_UNKNOWN_OPCODE'): "Unknown opcode",
                        CONSTANTS.get('INTERRUPT_MEMORY_ACCESS'): "Illegal memory access",
                    }
                    error_msg = error_map.get(state.interrupt, f"Unknown error from C core: {state.interrupt}")
                    raise self.Error(error_msg, state)

        except self.Error as e:
            return VMResult(True, e, None, state.steps, state)


    def run_debug(
        self,
        program: bytes,
        max_steps: Optional[int] = None,
    ) -> Generator[Tuple[VMState, str, Optional[str]], None, None] : 
        """
        Same as above, but yield before every instruction
        """
        max_steps = max_steps or (2**32 - 1)

        state = VMState()
        state.pc = 0
        state.steps = 0
        state.interrupt = CONSTANTS.get('INTERRUPT_NONE', -1)

        while True:
            vm_core.run_c(ctypes.byref(state), program, len(program), max_steps, True)
            print(f"INTERRUPT RECEIVED: {state.interrupt}")
            instr = program[state.pc:state.pc + 2].hex()
            if state.interrupt >= 0: # Positive interrupt is a syscall
                if state.interrupt == CONSTANTS.get('INTERRUPT_DEBUG'):
                    yield state, instr, None
                    continue
                syscall_id = state.interrupt
                try:
                    syscall_handler = self.systable[syscall_id]
                    syscall_handler(state) # Pass the C state object
                except KeyError:
                    yield state, instr, f"Unknown syscall: {syscall_id}"
                    break
                except self.Stop as e: # Exit syscall raises this
                    yield state, instr, f"Graceful shutdown: {e.code}"
                    break
            elif state.interrupt < -1: # Negative interrupt is an error/halt
                error_map = {
                    CONSTANTS.get('INTERRUPT_MAX_STEPS'): "Runtime limit exceeded",
                    CONSTANTS.get('INTERRUPT_ILLEGAL_PC'): "Illegal PC access",
                    CONSTANTS.get('INTERRUPT_PROTECTED_REG'): "Protected register write attempt",
                    CONSTANTS.get('INTERRUPT_UNKNOWN_OPCODE'): "Unknown opcode",
                    CONSTANTS.get('INTERRUPT_MEMORY_ACCESS'): "Illegal memory access",
                }
                error_msg = error_map.get(state.interrupt, "Unknown error from C core")
                yield state, instr, error_msg
                break
       
# ======= DEMO SYSCALLS ============

# =========================
# EXIT syscall
# =========================
def exit_handler(state: VMState) -> None:
    """
    EXIT (sid=0): pop one value and terminate the VM with that code.
    Stack contract: code -> —
    """
    print("EXIT")
    code = state.registers[0]
    raise MiscVM.Stop(code)

# =========================
# PUTC syscall
# =========================
def put_handler(state: VMState) -> None:
    """
    PUTC (sid=1): pop one value and print to the active terminal.
    Stack contract: code -> —
    """
    code = state.registers[0]
    print(chr(code), end='', flush=True)

# Keep the systable in a dictionary named exactly 'systable'
demo_systable: Dict[int, Callable[[List[int]], Optional[Tuple[str, int]]]] = {
    0: exit_handler,   # EXIT
    1: put_handler,   # PUTC
    # You can add more: 1: puti_handler, 2: putch_handler, ...
}


# =========================
# Demo program
# =========================
DEMO = """
F0FF  # DUMP
0168
0265
0000  # EXIT DUMP
0268  # MOV R0 'h'
1100  # SYSCALL 1 (PUTC)
0265  # MOV R0 'e'
1100  # SYSCALL 1 (PUTC)
026c  # MOV R0 'l'
1100  # SYSCALL 1 (PUTC)
026c  # MOV R0 'l'
1100  # SYSCALL 1 (PUTC)
026f  # MOV R0 'o'
1100  # SYSCALL 1 (PUTC)
020a  # MOV R0 'NL'
1100  # SYSCALL 1 (PUTC)

0100  # SYSCALL 0 (EXIT) -> pops 0 as exit code
"""

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run a MISC v2 program.")
    parser.add_argument('--program', action="store",
                        help="Program to run as a hex string (e.g., '2042/1001'). If not provided, "
                        "reads from stdin.")
    parser.add_argument('--demo', action='store_true',
                        help="Run the built-in demo program.")
    parser.add_argument('--debug', action='store_true',
                        help="Enable debugging mode")
    parser.add_argument('binary', nargs='?',
                        help="The binary file to execute")
    args = parser.parse_args()

    program_source = ""
    if args.debug :
        DBG = True
    program_bytes = b''
    if args.binary :
        with open(args.binary, 'rb') as f:
            program_bytes = f.read()
    else :
        if args.demo:
            raw_source = DEMO
        elif args.program:
            raw_source = args.program
        else:
            # Read from standard input
            print("Reading program from stdin (Ctrl+D to end)...", file=sys.stderr)
            raw_source = sys.stdin.read()

        # Clean up the raw source and split it into 4-character lines
        program_source = "".join([ a.split("#")[0].strip() for a in raw_source.split("\n") ])
        program_bytes = bytes.fromhex("".join(program_source.split()))
    
    vm = MiscVM(
        systable=demo_systable
    )
    if not args.debug :
        result = vm.run(program_bytes, max_steps=100)
        print("\n--- VM Result ---")
        print(f"Halted: {result.halted}")
        print(f"Error: {result.error}")
        print(f"Exit code: {result.exit_code}")
        print(f"PC at end: {result.rt.pc}")
        print(f"Steps: {result.steps}")
        if result.exit_code :
            exit(result.exit_code)
        else :
            exit(1)
    else :
        g = vm.run_debug(program_bytes)
        for rt, inst, err in g :
            print(rt)
            print(inst)
            if err is not None :
                print("ERROR:", err)
            input()
