#!/usr/bin/env python3
"""
dis.py: Disassembler for the MISC v3 architecture.

Converts a hex string of machine code into human-readable assembly.

Usage:
  python3 dis.py <input_file.hex>
"""

import argparse
import ctypes
import sys

# Import the instruction set definition from the VM
from misc import vm_core

def disassemble(program_bytes: bytes) -> str:
    """
    Disassembles a byte string using the C core.
    """
    program_len = len(program_bytes)
    c_bytes = (ctypes.c_uint8 * program_len)(*program_bytes)
    output_str_ptr = ctypes.c_char_p()

    result = vm_core.disassemble(c_bytes, program_len, ctypes.byref(output_str_ptr))
    
    if result != 0:
        raise RuntimeError("Disassembly failed in C core.")
    
    assembly_code = output_str_ptr.value.decode('utf-8')
    vm_core.free_memory(output_str_ptr)
    return assembly_code

def main():
    parser = argparse.ArgumentParser(description="Disassembler for MISC v3 architecture.")
    parser.add_argument("input_file", help="Path to the hex file to disassemble.")
    args = parser.parse_args()

    try:
        with open(args.input_file, 'rb') as f: # Read bytes directly
            program_bytes = f.read()
        
        assembly_code = disassemble(program_bytes)
        print(assembly_code)

    except FileNotFoundError:
        print(f"Error: Input file not found at '{args.input_file}'", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Disassembly Error: Invalid byte string in file. {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()