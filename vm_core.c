#include "vm_core.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

// This constant is used to determine protected registers
const unsigned char protected_registers[] = 
    {0, 0, 0, 0,
     0, 0, 0, 0,
     0, 0, 0, 0,
     0, 0, 0, 1};

void run_c(VMState* state, const uint8_t* program, int program_len, int max_steps, bool debug) {
    // Check if the state needs to be picked up after a signal
    uint8_t op, rd, rs;
    Instruction *instr;
    
    if (state->interrupt < -1) return; // There is an error
    if (state->interrupt == INTERRUPT_DEBUG) {// pick up after a debug interrupt
        state->interrupt = INTERRUPT_NONE;
        op = state->op;
        rd = state->rd;
        rs = state->rs;
        instr = (Instruction *)(program + state->pc);

        goto DEBUG_PICKUP;
    }
    else { // a syscall was just completed
        state->interrupt = INTERRUPT_NONE;
        instr = (Instruction *)(program + state->pc);
        goto SYSCALL_PICKUP;
    }
    // Reset the interupt
    state->interrupt = INTERRUPT_NONE;

    // While the interrupt is not set and the steps is below the max runtime
    while (state->steps < max_steps && state->interrupt == INTERRUPT_NONE) {
        if (state->pc + INSTRUCTION_LENGTH > program_len) {
            // Catch PC overrun
            state->interrupt = INTERRUPT_ILLEGAL_PC;
            return;
        }

        // --- Fast Instruction Fetch and Decode ---
        // Decode directly into local variables. This is much faster than writing
        // to the VMState struct in memory on every cycle. The compiler can
        // optimize these local variables into registers.
        instr = (Instruction *)(program + state->pc);
        op = instr->op_imm.op;
        rd = instr->op_reg_imm.rd;
        rs = instr->op_reg_reg_imm.rs;

        if (debug) {
            state->interrupt = INTERRUPT_DEBUG;
            state->op = instr->op_imm.op;
            state->rd = instr->op_reg_imm.rd;
            state->rs = instr->op_reg_reg_imm.rs;
            state->imm8 = instr->op_reg_imm.imm;
            state->imm4 = instr->op_reg_reg_imm.imm;
            state->imm12 = instr->op_imm.imm;
            return;
        }
DEBUG_PICKUP:
        state->pc += INSTRUCTION_LENGTH;
        state->registers[PC_REG] = state->pc;
        state->steps++;

        // Special handling for RAW_DUMP
        if (op == OP_NOP && instr->op_imm.imm == OP_RAW_DUMP) {
            while (state->pc + 2 < program_len) {
                uint8_t addr = program[state->pc];
                uint8_t val = program[state->pc + 1];
                state->pc += 2;
                state->registers[PC_REG] = state->pc;
                if (addr == 0 && val == 0) break;
                if (addr < MEMORY_SIZE) {
                    state->memory[addr] = val;
                } else {
                    state->interrupt = INTERRUPT_MEMORY_ACCESS;
                    return;
                }
            }
            continue;
        }

        // RIP is protected
        if (protected_registers[rd]) {
             state->interrupt = INTERRUPT_PROTECTED_REG;
             return;
        }
        
        switch (op) {
            case OP_SYSCALL:
                // Positive interrupt values are syscall IDs                
                state->interrupt = instr->op_imm.imm & 0xFF;
                if (state->interrupt == 0) {
                }
                return; // Return to Python to handle syscall

            case OP_MOV_REG_IMM:
                state->registers[rd] = instr->op_reg_imm.imm;
                break;

            case OP_MOV_REG_REG_SHR:
                state->registers[rd] = state->registers[rs] >> instr->op_reg_reg_imm.imm;
                break;

            case OP_MOV_REG_REG_SHL:
                state->registers[rd] = state->registers[rs] << instr->op_reg_reg_imm.imm;
                break;

            case OP_MOV_REG_REG_ADD:
                state->registers[rd] = state->registers[rs] + (instr->op_reg_reg_imm.imm * 2);
                break;

            case OP_LD_REG_MEM: {
                uint16_t addr = state->registers[rs] + instr->op_reg_reg_imm.imm;
                if (addr < MEMORY_SIZE) {
                    state->registers[rd] = state->memory[addr];
                } else {
                    state->interrupt = INTERRUPT_MEMORY_ACCESS;
                    return;
                }
                break;
            }

            case OP_ST_MEM_REG: {
                uint16_t addr = state->registers[rs] + instr->op_reg_reg_imm.imm;
                if (addr < MEMORY_SIZE) {
                    state->memory[addr] = state->registers[rd];
                } else {
                    state->interrupt = INTERRUPT_MEMORY_ACCESS;
                    return;
                }
                break;
            }

            case OP_ADD: {
                int16_t res = (int8_t)state->registers[rd] + (int8_t)state->registers[rs] + instr->op_reg_reg_imm.imm;
                // TODO: Set overflow and sign flags
                state->registers[rd] = (uint8_t)res;
                break;
            }

            case OP_SUB: {
                int16_t res = (int8_t)state->registers[rd] - (int8_t)state->registers[rs] - instr->op_reg_reg_imm.imm;
                // TODO: Set overflow and sign flags
                state->registers[rd] = (uint8_t)res;
                break;
            }

            case OP_AND:
                state->registers[rd] &= state->registers[rs];
                // TODO: Set sign flag
                break;

            case OP_OR:
                state->registers[rd] |= state->registers[rs];
                break;

            case OP_XOR:
                state->registers[rd] ^= state->registers[rs];
                break;

            case OP_NOT:
                state->registers[rd] = ~state->registers[rd];
                break;

            case OP_JMP:
                state->pc = state->registers[rd] + instr->op_reg_imm.imm;
                state->registers[PC_REG] = state->pc;
                break;

            case OP_JZ:
                if (state->registers[rd] == 0) {
                    state->pc = state->registers[rs] + instr->op_reg_reg_imm.imm;
                    state->registers[PC_REG] = state->pc;
                }
                break;

            case OP_NOP: // NOP
                break;

            default:
                state->interrupt = INTERRUPT_UNKNOWN_OPCODE;
                return;
        }
SYSCALL_PICKUP:
    }

    if (state->interrupt == INTERRUPT_NONE) {
        state->interrupt = INTERRUPT_MAX_STEPS;
    }
}

void free_memory(void* ptr) {
    if (ptr) {
        free(ptr);
    }
}

// --- Disassembler ---

int disassemble(const uint8_t* program_bytes, int program_len, char** output_string) {
    // Estimate buffer size: avg 40 chars per instruction + some overhead
    size_t buffer_size = (program_len / 2) * 40 + 256;
    char* buffer = (char*)malloc(buffer_size);
    if (!buffer) return -1;
    buffer[0] = '\0';

    char line_buffer[128];
    int pc = 0;

    while (pc < program_len) {
        if (pc + INSTRUCTION_LENGTH > program_len) break;

        // Handle raw dump section
        if (program_bytes[pc] == 0x0F && program_bytes[pc+1] == 0xFF) {
            snprintf(line_buffer, sizeof(line_buffer), "%04X:  .data\n", pc);
            strcat(buffer, line_buffer);
            pc += 2;
            while (pc + 1 < program_len) {
                uint8_t addr = program_bytes[pc];
                uint8_t val = program_bytes[pc+1];
                if (addr == 0 && val == 0) {
                    pc += 2; // Consume terminator
                    break;
                }
                snprintf(line_buffer, sizeof(line_buffer), "         byte %d, %d\n", addr, val);
                strcat(buffer, line_buffer);
                pc += 2;
            }
            continue;
        }

        Instruction* instr = (Instruction*)(program_bytes + pc);
        uint8_t op = instr->op_imm.op;
        uint8_t rd = instr->op_reg_imm.rd;
        uint8_t rs = instr->op_reg_reg_imm.rs;
        int8_t imm4 = instr->op_reg_reg_imm.imm;
        int8_t imm8 = instr->op_reg_imm.imm;
        int16_t imm12 = instr->op_imm.imm;

        char mnemonic[64];
        switch(op) {
            case OP_NOP: 
                if (imm12 == OP_RAW_DUMP) strcpy(mnemonic, "MEMLOAD");
                else snprintf(mnemonic, sizeof(mnemonic), "NOP %d", imm12);
                break;
            case OP_SYSCALL: snprintf(mnemonic, sizeof(mnemonic), "SYSCALL %d", imm12); break;
            case OP_MOV_REG_IMM: snprintf(mnemonic, sizeof(mnemonic), "MOV_REG_IMM r%d, %d", rd, imm8); break;
            case OP_MOV_REG_REG_SHR: snprintf(mnemonic, sizeof(mnemonic), "MOV_REG_REG_SHR r%d, r%d, %d", rd, rs, imm4); break;
            case OP_MOV_REG_REG_SHL: snprintf(mnemonic, sizeof(mnemonic), "MOV_REG_REG_SHL r%d, r%d, %d", rd, rs, imm4); break;
            case OP_MOV_REG_REG_ADD: snprintf(mnemonic, sizeof(mnemonic), "MOV_REG_REG_ADD r%d, r%d, %d", rd, rs, imm4); break;
            case OP_LD_REG_MEM: snprintf(mnemonic, sizeof(mnemonic), "LD_REG_MEM r%d, [r%d], %d", rd, rs, imm4); break;
            case OP_ST_MEM_REG: snprintf(mnemonic, sizeof(mnemonic), "ST_MEM_REG [r%d], r%d, %d", rd, rs, imm4); break;
            case OP_ADD: snprintf(mnemonic, sizeof(mnemonic), "ADD r%d, r%d, %d", rd, rs, imm4); break;
            case OP_SUB: snprintf(mnemonic, sizeof(mnemonic), "SUB r%d, r%d, %d", rd, rs, imm4); break;
            case OP_AND: snprintf(mnemonic, sizeof(mnemonic), "AND r%d, r%d", rd, rs); break;
            case OP_OR: snprintf(mnemonic, sizeof(mnemonic), "OR r%d, r%d", rd, rs); break;
            case OP_XOR: snprintf(mnemonic, sizeof(mnemonic), "XOR r%d, r%d", rd, rs); break;
            case OP_NOT: snprintf(mnemonic, sizeof(mnemonic), "NOT r%d", rd); break;
            case OP_JMP: snprintf(mnemonic, sizeof(mnemonic), "JMP r%d, %d", rd, imm8); break;
            case OP_JZ: snprintf(mnemonic, sizeof(mnemonic), "JZ r%d, r%d, %d", rd, rs, imm4); break;
            default: snprintf(mnemonic, sizeof(mnemonic), "DB 0x%02X%02X", program_bytes[pc], program_bytes[pc+1]); break;
        }
        snprintf(line_buffer, sizeof(line_buffer), "%04X:  %s\n", pc, mnemonic);
        strcat(buffer, line_buffer);
        pc += INSTRUCTION_LENGTH;
    }

    *output_string = buffer;
    return 0;
}

// --- Assembler ---

int assemble_instruction(const char* mnemonic, uint16_t op1, uint16_t op2, uint16_t op3,
                         Instruction* instr, char** error_message) {
    

    if (strcasecmp(mnemonic, "SYSCALL") == 0) {
        instr->op_imm.op = OP_SYSCALL;
        instr->op_imm.imm = op1 & 0xFFF;
    } else if (strcasecmp(mnemonic, "MOV_REG_IMM") == 0) {
        instr->op_reg_imm.op = OP_MOV_REG_IMM;
        instr->op_reg_imm.rd = op1 & 0xF;
        instr->op_reg_imm.imm = op2 & 0xFF;
    } else if (strcasecmp(mnemonic, "MOV_REG_REG_SHR") == 0) {
        instr->op_reg_reg_imm.op = OP_MOV_REG_REG_SHR;
        instr->op_reg_reg_imm.rd = op1 & 0xF;
        instr->op_reg_reg_imm.rs = op2 & 0xF;
        instr->op_reg_reg_imm.imm = op3 & 0xF;
    } else if (strcasecmp(mnemonic, "MOV_REG_REG_SHL") == 0) {
        instr->op_reg_reg_imm.op = OP_MOV_REG_REG_SHL;
        instr->op_reg_reg_imm.rd = op1 & 0xF;
        instr->op_reg_reg_imm.rs = op2 & 0xF;
        instr->op_reg_reg_imm.imm = op3 & 0xF;
    } else if (strcasecmp(mnemonic, "MOV_REG_REG_ADD") == 0) {
        instr->op_reg_reg_imm.op = OP_MOV_REG_REG_ADD;
        instr->op_reg_reg_imm.rd = op1 & 0xF;
        instr->op_reg_reg_imm.rs = op2 & 0xF;
        instr->op_reg_reg_imm.imm = op3 & 0xF;
    } else if (strcasecmp(mnemonic, "LD_REG_MEM") == 0) {
        instr->op_reg_reg_imm.op = OP_LD_REG_MEM;
        instr->op_reg_reg_imm.rd = op1 & 0xF;
        instr->op_reg_reg_imm.rs = op2 & 0xF;
        instr->op_reg_reg_imm.imm = op3 & 0xF;
    } else if (strcasecmp(mnemonic, "ST_MEM_REG") == 0) {
        instr->op_reg_reg_imm.op = OP_ST_MEM_REG;
        instr->op_reg_reg_imm.rd = op1 & 0xF;
        instr->op_reg_reg_imm.rs = op2 & 0xF;
        instr->op_reg_reg_imm.imm = op3 & 0xF;
    } else if (strcasecmp(mnemonic, "ADD") == 0) {
        instr->op_reg_reg_imm.op = OP_ADD;
        instr->op_reg_reg_imm.rd = op1 & 0xF;
        instr->op_reg_reg_imm.rs = op2 & 0xF;
        instr->op_reg_reg_imm.imm = op3 & 0xF;
    } else if (strcasecmp(mnemonic, "SUB") == 0) {
        instr->op_reg_reg_imm.op = OP_SUB;
        instr->op_reg_reg_imm.rd = op1 & 0xF;
        instr->op_reg_reg_imm.rs = op2 & 0xF;
        instr->op_reg_reg_imm.imm = op3 & 0xF;
    } else if (strcasecmp(mnemonic, "AND") == 0) {
        instr->op_reg_reg_imm.op = OP_AND;
        instr->op_reg_reg_imm.rd = op1 & 0xF;
        instr->op_reg_reg_imm.rs = op2 & 0xF;
        instr->op_reg_reg_imm.imm = 0; // Not used
    } else if (strcasecmp(mnemonic, "OR") == 0) {
        instr->op_reg_reg_imm.op = OP_OR;
        instr->op_reg_reg_imm.rd = op1 & 0xF;
        instr->op_reg_reg_imm.rs = op2 & 0xF;
        instr->op_reg_reg_imm.imm = 0; // Not used
    } else if (strcasecmp(mnemonic, "XOR") == 0) {
        instr->op_reg_reg_imm.op = OP_XOR;
        instr->op_reg_reg_imm.rd = op1 & 0xF;
        instr->op_reg_reg_imm.rs = op2 & 0xF;
        instr->op_reg_reg_imm.imm = 0; // Not used
    } else if (strcasecmp(mnemonic, "NOT") == 0) {
        instr->op_reg_imm.op = OP_NOT;
        instr->op_reg_imm.rd = op1 & 0xF;
        instr->op_reg_imm.imm = 0; // Not used
    } else if (strcasecmp(mnemonic, "JMP") == 0) {
        instr->op_reg_imm.op = OP_JMP;
        instr->op_reg_imm.rd = op1 & 0xF;
        instr->op_reg_imm.imm = op2 & 0xFF;
    } else if (strcasecmp(mnemonic, "JZ") == 0) {
        instr->op_reg_reg_imm.op = OP_JZ;
        instr->op_reg_reg_imm.rd = op1 & 0xF;
        instr->op_reg_reg_imm.rs = op2 & 0xF;
        instr->op_reg_reg_imm.imm = op3 & 0xF;
    } else if (strcasecmp(mnemonic, "NOP") == 0) {
        instr->op_imm.op = OP_NOP;
        instr->op_imm.imm = 0;
    } else {
        // Invalid mnemonic
        *error_message = (char*)malloc(128);
        snprintf(*error_message, 128, "Invalid mnemonic: %s", mnemonic);
        return -1;
    }

    // Since the union and uint16_t are the same size, we can cast the address
    // of the union to a uint16_t pointer and dereference it.
    return 0;
}