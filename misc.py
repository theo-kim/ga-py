from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Generator, List, Dict, Callable, Literal, Optional, Tuple, Iterable, overload, MutableSequence, NamedTuple
import sys
from bitarray import bitarray
from bitarray.util import ba2int, int2ba
from enum import Enum
import struct

DBG = False
Endian = Literal["big", "little"]

def dbg(*args, **kwargs) :
    if not DBG :
        return
    print(*args, **kwargs)

@dataclass
class Runtime : 
    """The current runtime state of the VM"""
    pc: int
    reg: List[Register]
    mem: Memory
    sys: Dict[int, Callable[[List[int]], Optional[Tuple[str, int]]]]
    d: Optional[int]
    d_i: Optional[int]
    s: Optional[int]
    s_i: Optional[int]
    i: Optional[Immediate]

    def __repr__(self) :
        mem_bytes = [ m.tobytes().hex() for m in self.mem.container ]
        grid = [" ".join(mem_bytes[i: i + 8]) for i in range(0, len(mem_bytes), 8) ]
        return f"PC: {self.pc}\nRegisters: {self.reg}\nMemory: " + "\n\t".join(grid)
    
    def args(self) -> str :
        if self.d_i is None and self.i is None :
            return ""
        if self.d_i is None :
            return f"{self.i}"
        if self.s_i is None :
            return f"R{self.d_i} {self.i}"
        return f"R{self.d_i} R{self.s_i} {self.i.value.tobytes().hex()}" 

Systable = Dict[int, Callable[[Runtime], Optional[Runtime]]]

# =========================
# VM result container
# =========================
@dataclass
class VMResult:
    halted: bool                # True if the VM did not exit gracefully
    error: Optional[Exception]  # The error which halted termination (if applicable)
    exit_code: Optional[int]    # Exit code if EXIT was used; otherwise Non
    steps: int                  # Number of steps taken
    rt: Runtime                 # The runtime at program termination

class Register() :
    """A class to represent a register"""
    class Error(Exception) :
        def __init__(self, msg, name = None) :
            super().__init__(msg)
            self.name = name

    def __init__(self, name: str, size: int = 8, protected: bool = False) :
        self.name = name
        self.protected = protected
        self._v: bitarray = bitarray(size)
        self.size = size

    def __str__(self) :
        return f"{self.name}({self.unsigned})"
    
    def __repr__(self) :
        return str(self)

    @property
    def value(self) :
        return self._v

    @property
    def signed(self) :
        return ba2int(self._v, True)
    
    @property
    def unsigned(self) :
        return ba2int(self._v, False)
    
    @value.setter
    def value(self, value: bitarray) :
        if self.protected :
            raise self.Error("Register is protected", self.name)
        self._test_value(value)
        self._v = value

    def _test_value(self, value: bitarray) :
        if len(value) > self.size :
            raise self.Error("Value is too large", self.name)

    def set_safe_value(self, value: bitarray) :
        self._v = value

class Immediate() :
    def __init__(self, value: bitarray = None, integer: int = None, signed: bool = False, length = 2) :
        if value is None and integer is None :
            raise ValueError("Immediate must specify either a value or a integer")
        if value is None :
            self.value = int2ba(integer, MiscVM.WORD_LENGTH, signed = signed)
        else :
            self.value = value
        f = [ "<" if MiscVM.ENDIAN == "little" else ">",  "I" if length == 4 else "H" if length == 2 else "B" ]
        if signed :
            f[1] = f[1].lower()
        self.fmt = "".join(f)

    @property
    def signed(self) :
        return ba2int(self.value, True)

    @property
    def unsigned(self) :
        return struct.unpack(self.fmt, (bitarray(len(self.value) % 8) + self.value).tobytes())[0]
    
    def __repr__(self) :
        return f"{self.value.tobytes().hex()}"

class Memory() :
    class Error(Exception) :
        def __init__(self, addr) :
            super().__init__(f"Illegal memory access: {addr}")
            self.addr = addr

    def __init__(self, container: MutableSequence[bitarray], wordmask: int = 0xFF) :
        self.container = container
        self.wordmask = wordmask
        self.clear()

    def __getitem__(self, addr) -> bitarray :
        try :
            return self.container[addr][-self.wordmask:]
        except IndexError :
            raise self.Error(addr)

    def __setitem__(self, addr, value: bitarray) :
        try : 
            self.container[addr] = value[-self.wordmask:]
            return
        except IndexError :
            raise self.Error(addr)
    
    def clear(self) :
        for c in range(len(self.container)) :
            self.container[c].setall(0)

# =========================
# MISC v3 VM (Register-based)
# =========================
class MiscVM:
    """
    An 8-bit, register-based VM with 8 general-purpose registers and 256 bytes of RAM.
    """

    class OpArg(Enum) :
        I = 1
        RI = 2
        RRI = 3
    
    class OpRes(Enum) :
        NUL = 1
        SYS = 2
        MUT = 3
        SMUT = 4
        UMUT = 5
        MEM = 6
        PC = 7
    
    class OpImm(Enum) :
        S = 1
        U = 2
        NA = 3

    # Opcodes
    OPS : List[Tuple[str, bytes, OpArg, OpRes, Callable[[Runtime], Any]]] = [
        ("OP_NOP", b'\x00', OpArg.I, OpRes.NUL, OpImm.NA, lambda _: None),
        ("OP_SYSCALL", b'\x01', OpArg.I, OpRes.SYS, OpImm.U, None),
        ("OP_MOV_REG_IMM", b'\x02', OpArg.RI, OpRes.MUT, OpImm.U, lambda rt : rt.i.value ),
        ("OP_MOV_REG_REG_SHR", b'\x03', OpArg.RRI, OpRes.MUT, OpImm.U, (lambda rt : rt.s.value >> rt.i.unsigned)),
        ("OP_MOV_REG_REG_SHL", b'\x04', OpArg.RRI, OpRes.MUT, OpImm.U, (lambda rt : rt.s.value << rt.i.unsigned)),
        ("OP_MOV_REG_REG_ADD", b'\x05', OpArg.RRI, OpRes.UMUT, OpImm.U, (lambda rt: rt.s.unsigned + rt.i.unsigned)), # this can be replaced
        ("OP_LD_REG_MEM", b'\x06', OpArg.RRI, OpRes.MEM, OpImm.S, (lambda rt: (rt.d.unsigned + rt.i.signed, rt.s.value))),
        ("OP_ST_MEM_REG", b'\x07', OpArg.RRI, OpRes.MUT, OpImm.S, (lambda rt: rt.mem[rt.s.unsigned + rt.i.signed])),
        ("OP_ADD", b'\x08', OpArg.RRI, OpRes.SMUT, OpImm.S, (lambda rt: rt.d.signed + rt.s.signed + rt.i.signed)),
        ("OP_SUB", b'\x09', OpArg.RRI, OpRes.SMUT, OpImm.S, (lambda rt: rt.d.signed - rt.s.signed + rt.i.signed)),
        ("OP_AND", b'\x0A', OpArg.RRI, OpRes.MUT, OpImm.U, (lambda rt: rt.d.value & rt.s.value)),
        ("OP_OR", b'\x0B', OpArg.RRI, OpRes.MUT, OpImm.U, (lambda rt: rt.d.value | rt.s.value)),
        ("OP_XOR", b'\x0C', OpArg.RRI, OpRes.MUT, OpImm.U, (lambda rt: rt.d.value ^ rt.s.value)),
        ("OP_NOT", b'\x0D', OpArg.RI, OpRes.MUT, OpImm.U, (lambda rt: ~rt.d.value)),
        ("OP_JMP", b'\x0E', OpArg.RI, OpRes.PC, OpImm.U, (lambda rt: rt.d.signed + rt.i.unsigned)),
        ("OP_JZ", b'\x0F', OpArg.RRI, OpRes.PC, OpImm.U, (lambda rt: (rt.s.unsigned + rt.i.unsigned) if not rt.d.value.any() else rt.pc)),
        ("OP_RAW_DUMP", b'\xFF', OpArg.I, OpRes.NUL, lambda _: None), # Special opcode for raw dump mode
    ]

    OP_LEN = 4
    REG_LEN = 4
    IMM_LEN = 8

    MIN_S = -(2^7) + 1
    MAX_S = 2^7 - 1
    MAX_U = 2^8 - 1

    NUM_REGISTERS = 16
    RIP_REG = 15 # R15 is the instruction pointer

    WORD_LENGTH = 8
    INSTRUCTION_LENGTH = 2

    WORD_MASK = 0xFF

    ENDIAN = "little"

    class Stop(Exception) :
        def __init__(self, code: int) :
            self.code = code & 0xFF
    
    class Error(Exception) :
        def __init__(self, error: str, rt: Runtime = None) :
            super().__init__(error)
            self.rt = rt

    def __init__(self, systable: Systable, memory: Optional[MutableSequence[int]] = None):
        self.systable = systable
        self.registers: List[Register] = [Register(str(i), size=self.WORD_LENGTH) for i in range(self.NUM_REGISTERS)]  # R0-R7
        self.registers[self.RIP_REG] = Register('pc', size=self.WORD_LENGTH, protected=True) # set up special protected PC register
        if memory is None:
            self.memory: MutableSequence[int] = Memory([bitarray(self.WORD_LENGTH)] * (self.WORD_LENGTH * 8))
        else:
            if len(memory) != (self.WORD_LENGTH * 8):
                raise ValueError(f"Memory must be a sequence of {self.WORD_LENGTH * 8} bytes.")
            if not all([ type[m] == bitarray for m in memory ]) :
                raise TypeError(f"Memory must be a sequence of bitarrays")
            self.memory = Memory(memory)

    @property
    def pc(self) -> int :
        return self.registers[self.RIP_REG].unsigned
    
    @pc.setter
    def pc(self, value) -> int :
        self.registers[self.RIP_REG].set_safe_value(int2ba(value, self.WORD_LENGTH, signed = False))
    
    def _get_imm(self, instruction: bitarray) -> Immediate :
        return Immediate(instruction[self.OP_LEN:])

    def _get_reg_imm(self, instruction: bitarray) -> Tuple[int, Immediate] :
        return (
            ba2int(instruction[self.OP_LEN:self.OP_LEN + self.REG_LEN]),
            Immediate(instruction[self.OP_LEN + self.REG_LEN:], length=1)
        )
    
    def _get_reg_reg_imm(self, instruction: bitarray) -> Tuple[int, int, Immediate] :
        return (
            ba2int(instruction[self.OP_LEN:self.OP_LEN + self.REG_LEN]),
            ba2int(instruction[self.OP_LEN + self.REG_LEN:self.OP_LEN + self.REG_LEN * 2]),
            Immediate(instruction[self.OP_LEN + self.REG_LEN * 2:], length=1),
        )
    
    def _update_rt(self, rt: Runtime, instruction: bitarray, arg: OpArg) -> None:
        """Updates the runtime object with the current instruction's operands."""
        rt.pc = self.pc
        rt.d, rt.d_i, rt.s, rt.s_i, rt.i = None, None, None, None, None

        if arg == self.OpArg.I :
            rt.i = self._get_imm(instruction)
        elif arg == self.OpArg.RI :
            rt.d_i, rt.i = self._get_reg_imm(instruction)
            rt.d = rt.reg[rt.d_i]
        elif arg == self.OpArg.RRI :
            rt.d_i, rt.s_i, rt.i = self._get_reg_reg_imm(instruction)
            rt.d = rt.reg[rt.d_i]
            rt.s = rt.reg[rt.s_i]

    def _read_instruction(self, program: bytes, rt: Runtime) -> Tuple[str, bytes, OpArg, OpRes, OpImm, Callable[[Runtime], Any], bitarray] :
        try :
            instruction_bytes = program[self.pc:self.pc + self.INSTRUCTION_LENGTH]
            instruction = bitarray(instruction_bytes)
            if len(instruction) != self.INSTRUCTION_LENGTH * 8:
                raise self.Error("Illegal PC access", rt)
        except IndexError : 
            raise self.Error("Illegal PC access", rt)
        op = bytes(bitarray(4) + instruction[:self.OP_LEN])
        for OPERATION in self.OPS :
            if op != OPERATION[1] :
                continue
            return (*OPERATION, instruction)
        raise self.Error(f"Unknown opcode 0x{hex(int(op))}", rt)

    # ---------- Execution ----------
    def _execute_instruction(self, ret: OpRes, opfunc: Callable[[Runtime], Any], rt: Runtime) -> Runtime :
        if ret == self.OpRes.SYS :
            try :
                syscall = self.systable[rt.i.unsigned]
            except IndexError :
                raise self.Error("Unknown syscall", rt)
            except KeyError :
                raise self.Error("Unknown syscall", rt)

            rt = syscall(rt)
        if ret == self.OpRes.NUL :
            opfunc(rt)
        elif ret == self.OpRes.MUT :
            self.registers[rt.d_i].value = opfunc(rt)
        elif ret == self.OpRes.SMUT :
            self.registers[rt.d_i].value = int2ba(min(self.MAX_S, max(self.MIN_S, opfunc(rt))), self.WORD_LENGTH, signed = True)
        elif ret == self.OpRes.UMUT :
            self.registers[rt.d_i].value = int2ba(min(self.MAX_U, max(0, opfunc(rt))), self.WORD_LENGTH, signed = False)
        elif ret == self.OpRes.MEM :
            dst_addr, val = opfunc(rt)
            self.memory[dst_addr] = val
        elif ret == self.OpRes.PC :
            self.pc = min(self.MAX_U, max(0, opfunc(rt)))
        return rt

    def reset(self) :
        self.memory.clear()
        for r in self.registers :
            r.value.setall(0)


    def run(
        self,
        program: bytes,
        max_steps: Optional[int] = None,
    ) -> VMResult :
        """
        Execute until:
          - The state machine runs more than max_steps length (if specified)
          - The program raises an error
          - The program raises a Stop signal
        """
        self.reset()
        steps = 0

        if max_steps is None :
            check_runon = lambda _ : False
        else :
            check_runon = lambda x : x >= max_steps

        rt = Runtime(self.pc, self.registers, self.memory, self.systable, None, None, None, None, None)
        try :
            while True :
                if check_runon(steps):
                    raise self.Error("Runtime limit exceeded", rt)

                steps += 1

                mneumonic, op, arg, ret, imm_type, opfunc, instruction = self._read_instruction(program, rt)
                self.pc += self.INSTRUCTION_LENGTH
                
                # Check for Raw Dump Mode trigger (00FF)
                # The instruction is 0xFF, and the immediate value is 0x00
                if mneumonic == "OP_RAW_DUMP" and instruction[-8:].all(0):
                # Enter raw dump mode
                    while True:
                        if self.pc + 1 >= len(program):
                            raise self.Error("Unexpected end of program in raw dump mode", rt)
                        
                        addr = program[self.pc]
                        val = program[self.pc + 1]
                        self.pc += 2

                        if addr == 0 and val == 0:
                            # Exit raw dump mode
                            break
                        
                        self.memory[addr] = int2ba(val, self.WORD_LENGTH, signed = False)
                    continue # Continue to the next normal instruction

                self._update_rt(rt, instruction, arg)
                self._execute_instruction(ret, opfunc, rt)
                    
        except Memory.Error as e :
            return VMResult(True, e, None, steps, rt)
        except self.Error as e :
            return VMResult(True, e, None, steps, rt)
        except self.Stop as e :
            return VMResult(False, None, e.code, steps, rt)
        except Register.Error as e:
            return VMResult(True, e, None, steps, rt)

    def run_debug(
        self,
        program: bytes,
        max_steps: Optional[int] = None,
    ) -> Generator[Tuple[Runtime, str], None, None] : 
        """
        Same as above, but yield before every instruction
        """
        self.reset()
        steps = 0

        if max_steps is None :
            check_runon = lambda _ : False
        else :
            check_runon = lambda x : x >= max_steps

        rt = Runtime(self.pc, self.registers, self.memory, self.systable, None, None, None, None, None)
        
        try :
            while True :
                if check_runon(steps):
                    raise self.Error("Runtime limit exceeded", rt)

                steps += 1

                mneumonic, op, arg, ret, imm_type, opfunc, instruction = self._read_instruction(program, rt)
                self.pc += self.INSTRUCTION_LENGTH
                self._update_rt(rt, instruction, arg)

                # Check for Raw Dump Mode trigger (00FF)
                if mneumonic == "OP_RAW_DUMP" and instruction[-8:].all(0):
                    yield (rt, "Entering Raw Dump Mode...")
                    while True:
                        if self.pc + 1 >= len(program):
                            raise self.Error("Unexpected end of program in raw dump mode", rt)
                        
                        addr = program[self.pc]
                        val = program[self.pc + 1]
                        self.pc += 2

                        if addr == 0 and val == 0:
                            yield (rt, "Exiting Raw Dump Mode...")
                            break
                        
                        self.memory[addr] = int2ba(val, self.WORD_LENGTH, signed = False)
                    continue

                yield (rt, f"{mneumonic} {rt.args()} ({instruction})")
                self._execute_instruction(ret, opfunc, rt)

        except Memory.Error as e :
            yield rt, "Memory Error"
        except self.Error as e :
            yield rt, str(e)
        except self.Stop as e :
            yield rt, f"Exitted with code: {e.code}"
        
# ======= DEMO SYSCALLS ============

# =========================
# EXIT syscall
# =========================
def exit_handler(rt: Runtime) -> Runtime:
    """
    EXIT (sid=0): pop one value and terminate the VM with that code.
    Stack contract: code -> —
    """
    code = rt.reg[0].unsigned
    raise MiscVM.Stop(code)

# =========================
# PUTC syscall
# =========================
def put_handler(rt: Runtime) -> Runtime:
    """
    PUTC (sid=1): pop one value and print to the active terminal.
    Stack contract: code -> —
    """
    code = rt.reg[0].unsigned
    print(chr(code), end='', flush=True)
    rt.reg[0].value = Immediate(integer=1).value
    return rt

# Keep the systable in a dictionary named exactly 'systable'
systable: Dict[int, Callable[[List[int]], Optional[Tuple[str, int]]]] = {
    0: exit_handler,   # EXIT
    1: put_handler,   # PUTC
    # You can add more: 1: puti_handler, 2: putch_handler, ...
}


# =========================
# Demo program
# =========================
DEMO = """
0FFF  # DUMP
0168
0265
0000  # EXIT DUMP
2068  # MOV R0 'h'
1100  # SYSCALL 1 (PUTC)
2065  # MOV R0 'e'
1100  # SYSCALL 1 (PUTC)
206c  # MOV R0 'l'
1100  # SYSCALL 1 (PUTC)
206c  # MOV R0 'l'
1100  # SYSCALL 1 (PUTC)
206f  # MOV R0 'o'
1100  # SYSCALL 1 (PUTC)
200a  # MOV R0 'NL'
1100  # SYSCALL 1 (PUTC)

1000  # SYSCALL 0 (EXIT) -> pops 0 as exit code
"""

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run a MISC v2 program.")
    parser.add_argument('program', nargs='?', default=None,
                        help="Program to run as a hex string (e.g., '2042/1001'). If not provided, reads from stdin.")
    parser.add_argument('--demo', action='store_true',
                        help="Run the built-in demo program.")
    parser.add_argument('--debug', action='store_true',
                        help="Enable debugging mode")
    args = parser.parse_args()

    program_source = ""
    if args.debug :
        DBG = True

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
    vm = MiscVM(
        systable=systable
    )
    program_bytes = bytes.fromhex("".join(program_source.split()))
    if not args.debug :
        result = vm.run(program_bytes)
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
        for rt, instr in g :
            print(instr)
            print(rt)
            input()
