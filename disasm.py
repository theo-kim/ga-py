#!/usr/bin/env python3
"""
dis.py: Disassembler for the MISC v3 architecture.

Converts a hex string of machine code into human-readable assembly.

Usage:
  python3 dis.py <input_file.hex>
"""

import argparse
import sys
from bitarray import bitarray
from bitarray.util import ba2int

# Import the instruction set definition from the VM
from misc import MiscVM

def disassemble(program_bytes: bytes) -> str:
    """
    Disassembles a byte string into a human-readable assembly listing.
    """
    output_lines = []
    pc = 0
    
    while pc < len(program_bytes):
        if pc + MiscVM.INSTRUCTION_LENGTH > len(program_bytes):
            break  # Incomplete instruction

        # Handle raw dump section
        if program_bytes[pc:pc+2] == b'\xff\x00':
            output_lines.append(f"{pc:04X}:  .data")
            pc += 2
            while pc + 1 < len(program_bytes):
                addr = program_bytes[pc]
                val = program_bytes[pc+1]
                if addr == 0 and val == 0:
                    pc += 2 # Consume terminator
                    break
                output_lines.append(f"         byte {addr}, {val}")
                pc += 2
            continue

        instruction_bytes = program_bytes[pc : pc + MiscVM.INSTRUCTION_LENGTH]
        instruction_bits = bitarray(endian="big")
        instruction_bits.frombytes(instruction_bytes)

        op_code_val = ba2int(instruction_bits[:MiscVM.OP_LEN])
        op_code_bytes = op_code_val.to_bytes(1, 'big')

        found_op = False
        for name, op_bytes, arg_type, _, _ in MiscVM.OPS:
            if op_code_bytes == op_bytes:
                mnemonic = name.split('_', 1)[1]
                line = f"{pc:04X}:  {mnemonic:<18}"

                if arg_type == MiscVM.OpArg.I:
                    i = ba2int(instruction_bits[MiscVM.OP_LEN:], signed=True)
                    line += f"{i}"
                
                elif arg_type == MiscVM.OpArg.RI:
                    r_d = ba2int(instruction_bits[MiscVM.OP_LEN : MiscVM.OP_LEN + MiscVM.REG_LEN])
                    i = ba2int(instruction_bits[MiscVM.OP_LEN + MiscVM.REG_LEN:], signed=True)
                    line += f"r{r_d}, {i}"

                elif arg_type == MiscVM.OpArg.RRI:
                    r_d = ba2int(instruction_bits[MiscVM.OP_LEN : MiscVM.OP_LEN + MiscVM.REG_LEN])
                    r_s = ba2int(instruction_bits[MiscVM.OP_LEN + MiscVM.REG_LEN : MiscVM.OP_LEN + MiscVM.REG_LEN * 2])
                    i = ba2int(instruction_bits[MiscVM.OP_LEN + MiscVM.REG_LEN * 2:], signed=True)
                    line += f"r{r_d}, r{r_s}, {i}"

                output_lines.append(line)
                found_op = True
                break
        
        if not found_op:
            hex_val = instruction_bytes.hex()
            output_lines.append(f"{pc:04X}:  DB 0x{hex_val}")

        pc += MiscVM.INSTRUCTION_LENGTH

    return "\n".join(output_lines)

def main():
    parser = argparse.ArgumentParser(description="Disassembler for MISC v3 architecture.")
    parser.add_argument("input_file", help="Path to the hex file to disassemble.")
    args = parser.parse_args()

    try:
        with open(args.input_file, 'r') as f:
            hex_string = f.read().strip()
        
        program_bytes = bytes.fromhex(hex_string)
        assembly_code = disassemble(program_bytes)
        print(assembly_code)

    except FileNotFoundError:
        print(f"Error: Input file not found at '{args.input_file}'", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Disassembly Error: Invalid hex string in file. {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()