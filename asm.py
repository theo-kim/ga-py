#!/usr/bin/env python3
"""
asm.py: Assembler for the MISC v3 architecture.

Converts human-readable assembly code into a hex string of machine code.

Usage:
  python3 asm.py <input_file.asm>
  python3 asm.py <input_file.asm> -o <output_file.hex>
"""

import argparse
import re
import ctypes
import sys
import struct

# --- Debug Logging ---
DBG = False
def d_print(*args, **kwargs):
    if not DBG:
        return
    print("[ASM DBG]", *args, **kwargs, file=sys.stderr)

# Import the instruction set definition from the VM
from misc import vm_core

def parse_operand(op: str, labels: dict[str, int]) -> int:
    """Parses an operand string into an integer value."""
    op = op.strip()

    # Character literal e.g. 'a' or '\n'
    if op.startswith("'") and op.endswith("'") and len(op) >= 2:
        char_str = op[1:-1]
        if len(char_str) == 1:
            return ord(char_str)
        elif len(char_str) == 2 and char_str.startswith('\\'):
            # Handle simple escape sequences
            escape_map = {'n': '\n', 't': '\t', 'r': '\r', '\\': '\\', "'": "'"}
            if char_str[1] in escape_map:
                return ord(escape_map[char_str[1]])
        raise ValueError(f"Invalid character literal: {op}")

    if op.lower() in labels:
        return labels[op.lower()]
    
    # Handle registers (r5 -> 5)
    if op.lower().startswith('r'):
        return int(op[1:])
    
    # Handle hex (0x10), binary (0b10), and decimal (10)
    return int(op, 0)

def assemble(source_code: str) -> bytes:
    """
    Assembles the given source code into a byte string.
    Python handles the two-pass assembly (labels), and calls the C core
    to assemble each individual instruction.
    """
    d_print("--- Starting Assembly ---")
    lines = source_code.splitlines()
    code_lines = []
    data_pairs = []
    
    # --- First Pass: Separate code and data, find labels ---
    labels = {}
    program_counter = 0
    in_data_section = False

    d_print("\n--- Pass 1: Parsing labels and data ---")
    for i, line in enumerate(lines):
        line = line.split('#', 1)[0].strip()
        if not line:
            continue

        if line.lower() == '.data':
            d_print(f"L{i+1}: Entering .data section")
            in_data_section = True
            continue
        elif line.lower() == '.text':
            d_print(f"L{i+1}: Entering .text section")
            in_data_section = False
            continue

        if in_data_section:
            # Try to match 'byte ADDR, VAL'
            byte_match = re.match(r'byte\s+([^,]+),\s*(.+)', line, re.IGNORECASE)
            # Try to match 'str ADDR, "string"'
            str_match = re.match(r'str\s+([^,]+),\s*"([^"]*)"', line, re.IGNORECASE)
            if byte_match:
                addr_str, val_str = byte_match.groups()
                addr = parse_operand(addr_str, {})
                val = parse_operand(val_str, {})
                d_print(f"L{i+1}: Found data: byte @{addr}, {val}")
                data_pairs.append((addr, val))
            elif str_match:
                addr_str, raw_string_literal = str_match.groups()
                start_addr = parse_operand(addr_str, {})
                
                # Process escape sequences in the string literal
                try:
                    # The 'unicode_escape' codec is perfect for this
                    processed_string = raw_string_literal.encode('latin1').decode('unicode_escape')
                except UnicodeDecodeError as e:
                    raise ValueError(f"Invalid escape sequence in string on line {i+1}: {e}")

                d_print(f"L{i+1}: Found data: str @{start_addr}, \"{raw_string_literal}\" -> (len: {len(processed_string)})")
                for j, char in enumerate(processed_string):
                    addr = start_addr + j
                    val = ord(char)
                    d_print(f"  -> generating: byte @{addr}, {val} ('{char}')")
                    data_pairs.append((addr, val))

            continue

        match = re.match(r'^([a-zA-Z0-9_]+):$', line)
        if match:
            label_name = match.group(1).lower()
            if label_name in labels:
                raise ValueError(f"Duplicate label found: {label_name}")
            d_print(f"L{i+1}: Found label '{label_name}' at address {program_counter}")
            labels[label_name] = program_counter
        else:
            code_lines.append(line)
            program_counter += 2 # Each instruction is 2 bytes
    
    # --- Second Pass: Assemble instructions and data ---
    output_bytes = bytearray()

    d_print("\n--- Pass 2: Generating machine code ---")
    # Assemble .data section if it exists
    if data_pairs:
        output_bytes.extend(b'\xf0\xff') # MEMLOAD instruction
        for addr, val in data_pairs:
            output_bytes.extend([addr & 0xFF, val & 0xFF])
        output_bytes.extend(b'\x00\x00') # Terminator
    
    # Adjust labels to account for the data section length
    data_section_len = len(output_bytes)
    d_print(f"Data section is {data_section_len} bytes long.")
    for label in labels:
        labels[label] += data_section_len
        d_print(f"Adjusted label '{label}' to address {labels[label]}")
    
    d_print("\nAssembling code section:")
    for line_num, line in enumerate(code_lines, 1):
        parts = re.split(r'[,\s]+', line.strip(), maxsplit=1)
        mnemonic = parts[0].upper()
        args_str = parts[1] if len(parts) > 1 else ""
        operands = [op.strip() for op in args_str.split(',') if op.strip()]
        
        # Resolve labels to integer strings
        resolved_ops = [parse_operand(op, labels) for op in operands]
        d_print(f"L{line_num}: '{line.strip()}' -> {mnemonic} {', '.join(str(op) for op in resolved_ops if op)}")
        
        # Pad with None for C function signature
        while len(resolved_ops) < 3:
            resolved_ops.append(0) # Pass 0 for unused operands

        c_ops = [ctypes.c_uint16(op) for op in resolved_ops]
        c_mnemonic = ctypes.c_char_p(mnemonic.encode('ascii'))
        output_instruction = ctypes.c_uint16()
        error_ptr = ctypes.c_char_p()

        result = vm_core.assemble_instruction(c_mnemonic, *c_ops, ctypes.byref(output_instruction), ctypes.byref(error_ptr))

        if result != 0:
            error_msg = error_ptr.value.decode('utf-8') if error_ptr.value else f"Unknown assembly error on line {line_num}"
            if error_ptr: vm_core.free_memory(error_ptr)
            raise ValueError(f"L{line_num}: {error_msg} in '{line}'")

        # Pack as big-endian
        instruction_bytes = struct.pack('<H', output_instruction.value)
        output_bytes.extend(instruction_bytes)
        d_print(f"  -> Encoded as: 0x{instruction_bytes.hex()}")

    d_print("\n--- Assembly Finished ---")
    return bytes(output_bytes)


def main():
    parser = argparse.ArgumentParser(description="Assembler for MISC v3 architecture.")
    parser.add_argument("input_file", help="Path to the assembly source file (.asm).")
    parser.add_argument("-o", "--output", help="Path to the output hex file. Defaults to stdout.")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    args = parser.parse_args()

    try:
        if args.debug:
            global DBG
            DBG = True

        with open(args.input_file, 'r') as f:
            source = f.read()
        
        machine_code = assemble(source)
        hex_output = machine_code.hex()

        if args.output:
            with open(args.output, 'wb') as f: # Write bytes
                f.write(machine_code)
            print(f"Successfully assembled {args.input_file} to {args.output} ({len(machine_code)} bytes)", file=sys.stderr)
        else:
            print(hex_output)

    except FileNotFoundError:
        print(f"Error: Input file not found at '{args.input_file}'", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Assembly Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()