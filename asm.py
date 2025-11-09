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
import sys
from bitarray import bitarray
from bitarray.util import int2ba
import struct

# Import the instruction set definition from the VM
from misc import MiscVM


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
    if op.lower().startswith('r'):
        return int(op[1:])
    if op.lower().startswith('0x'):
        return int(op[2:], 16)
    if op.lower().startswith('0b'):
        return int(op[2:], 2)
    
    # Default to decimal integer
    return int(op) 


def assemble(source_code: str) -> bytes:
    """
    Assembles the given source code into a byte string.
    """
    lines = source_code.splitlines()
    code_lines = []
    data_pairs = []
    
    # --- First Pass: Separate code and data, find labels ---
    labels = {}
    program_counter = 0
    in_data_section = False

    for line in lines:
        line = line.split('#', 1)[0].strip()
        if not line:
            continue

        if line.lower() == '.data':
            in_data_section = True
            continue
        elif line.lower() == '.text': # Or any other section start
            in_data_section = False
            continue

        if in_data_section:
            try:
                parts = line.split(maxsplit=2)
                data_type, addr_str, val_str = parts
                addr = parse_operand(addr_str, {}) # No labels in data addresses yet
                
                if data_type.lower() == 'byte':
                    val = parse_operand(val_str, {})
                    data_pairs.append((addr, val))
                elif data_type.lower() == 'str':
                    # Use regex to find all literals (chars or numbers)
                    vals = re.findall(r"'.*?'|\S+", val_str)
                    for i, v_str in enumerate(vals):
                        val = parse_operand(v_str, {})
                        data_pairs.append((addr + i, val))
                continue # Move to the next line after processing data
            except (ValueError, IndexError):
                # If parsing as data fails, assume it's the start of the code section
                in_data_section = False

        # This part now runs for all code lines
        if not in_data_section:
            match = re.match(r'^([a-zA-Z0-9_]+):$', line)
            if match:
                label_name = match.group(1).lower()
                if label_name in labels:
                    raise ValueError(f"Duplicate label found: {label_name}")
                # The PC for labels needs to account for the data section
                labels[label_name] = program_counter
            else:
                code_lines.append(line)
                program_counter += MiscVM.INSTRUCTION_LENGTH
    
    # --- Second Pass: Assemble instructions and data ---
    output_bytes = bytearray()

    # Assemble .data section if it exists
    if data_pairs:
        # OP_RAW_DUMP instruction (0xFF00)
        output_bytes.extend(b'\x0f\xff')
        for addr, val in data_pairs:
            output_bytes.extend([addr & 0xFF, val & 0xFF])
        # Terminator for raw dump mode
        output_bytes.extend(b'\x00\x00')
    
    # Adjust labels to account for the data section length
    data_section_len = len(output_bytes)
    for label in labels:
        labels[label] += data_section_len
    
    # Assemble code section
    for line_num, line in enumerate(code_lines, 1):
        parts = re.split(r'[,\s]+', line, 1)
        parts = line.split(maxsplit=1)
        mnemonic = parts[0].upper()
        args_str = parts[1] if len(parts) > 1 else ""
        
        instruction_bits = bitarray(endian="big")
        found_op = False
        for name, op_code_bytes, arg_type, _, imm_type, _ in MiscVM.OPS:
            op_name = name.split('_', 1)[1] # e.g., OP_MOV_REG_IMM -> MOV_REG_IMM
            if mnemonic != op_name.rsplit('_', 2)[0] and mnemonic != op_name.rsplit('_',1)[0] and mnemonic != op_name:
                 if not (mnemonic == "MOV" and op_name.startswith("MOV")):
                    continue
            op_bits = bitarray(endian="big")
            op_bits.frombytes(op_code_bytes)
            instruction_bits += op_bits[-MiscVM.OP_LEN:]
            
            try:
                operands = [op.strip() for op in args_str.split(',') if op.strip()]
                
                if arg_type == MiscVM.OpArg.I:
                    i = parse_operand(operands[0], labels) if operands else 0
                    i_bytes = struct.pack("".join([ "<" if MiscVM.ENDIAN == "little" else ">", "h" if i < 0 else "H" ]), i)
                    instruction_bits += bitarray(i_bytes)[MiscVM.OP_LEN:]
                
                elif arg_type == MiscVM.OpArg.RI:
                    d_i = parse_operand(operands[0], labels)
                    i = parse_operand(operands[1], labels)
                    i_bytes = struct.pack("".join([ "<" if MiscVM.ENDIAN == "little" else ">", "b" if i < 0 else "B" ]), i)
                    instruction_bits += int2ba(d_i, MiscVM.REG_LEN) + bitarray(i_bytes)

                elif arg_type == MiscVM.OpArg.RRI:
                    d_i = parse_operand(operands[0], labels)
                    s_i = parse_operand(operands[1], labels)
                    i = parse_operand(operands[2], labels) if len(operands) > 2 else 0
                    instruction_bits += int2ba(d_i, MiscVM.REG_LEN) + int2ba(s_i, MiscVM.REG_LEN) + int2ba(i, MiscVM.REG_LEN, signed=i < 0)
                
                output_bytes.extend(instruction_bits.tobytes())
                found_op = True
                break
            except (ValueError, IndexError) as e:
                # This was not the correct operator overload, try the next one
                continue

        if not found_op:
            raise ValueError(f"L{line_num}: Invalid instruction or operands: '{line}'")
    return bytes(output_bytes)


def main():
    parser = argparse.ArgumentParser(description="Assembler for MISC v3 architecture.")
    parser.add_argument("input_file", help="Path to the assembly source file (.asm).")
    parser.add_argument("-o", "--output", help="Path to the output hex file. Defaults to stdout.")
    args = parser.parse_args()

    try:
        with open(args.input_file, 'r') as f:
            source = f.read()
        
        machine_code = assemble(source)
        # print(machine_code)
        hex_output = machine_code.hex()
        # print(bytes.fromhex(hex_output))

        if args.output:
            with open(args.output, 'w') as f:
                f.write(machine_code)
            print(f"Successfully assembled {args.input_file} to {args.output}")
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