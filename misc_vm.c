#include "misc_vm.h"
#include <stdlib.h>
#include <stdio.h>

#define STACK_CAPACITY 256

// Helper to sign-extend a 12-bit immediate value
static inline int16_t sign_extend_12(uint16_t imm12) {
    return (imm12 & 0x800) ? (imm12 | 0xF000) : imm12;
}

VMResult misc_vm_run(const uint16_t* program_words, int program_len,
                       syscall_handler_t* systable, int systable_len,
                       int max_steps) {

    uint16_t stack[STACK_CAPACITY];
    int sp = 0; // Stack pointer

    int pc = 0;
    int steps = 0;
    int32_t exit_code = -1; // Use -1 to indicate no graceful exit

    VMResult result = {0};

    while (pc >= 0 && pc < program_len) {
        if (steps >= max_steps) {
            result.error = "Runtime limit exceeded";
            break;
        }

        uint16_t word = program_words[pc];
        uint8_t op = (word >> 12) & 0xF;
        uint16_t imm12 = word & 0xFFF;
        steps++;
        int next_pc = pc + 1;

        switch (op) {
            case OP_NOP:
                break;

            case OP_SYSC: {
                uint16_t sid = imm12;
                if (sid >= systable_len || systable[sid] == NULL) {
                    result.error = "Unknown syscall";
                    goto end_loop;
                }
                // This is a placeholder for the real syscall mechanism
                // which will be handled by Python's ctypes wrapper.
                // For now, this structure allows compilation.
                break;
            }

            case OP_LIT:
                if (sp >= STACK_CAPACITY) { result.error = "Stack overflow"; goto end_loop; }
                stack[sp++] = imm12;
                break;

            case OP_DUP:
                if (sp < 1) { result.error = "Stack underflow"; goto end_loop; }
                if (sp >= STACK_CAPACITY) { result.error = "Stack overflow"; goto end_loop; }
                stack[sp] = stack[sp - 1];
                sp++;
                break;

            case OP_DROP:
                if (sp < 1) { result.error = "Stack underflow"; goto end_loop; }
                sp--;
                break;

            case OP_SWAP: {
                if (sp < 2) { result.error = "Stack underflow"; goto end_loop; }
                uint16_t temp = stack[sp - 1];
                stack[sp - 1] = stack[sp - 2];
                stack[sp - 2] = temp;
                break;
            }

            case OP_ADD:
                if (sp < 2) { result.error = "Stack underflow"; goto end_loop; }
                stack[sp - 2] = (stack[sp - 2] + stack[sp - 1]) & WORD_MASK;
                sp--;
                break;

            case OP_SUB:
                if (sp < 2) { result.error = "Stack underflow"; goto end_loop; }
                stack[sp - 2] = (stack[sp - 2] - stack[sp - 1]) & WORD_MASK;
                sp--;
                break;

            case OP_AND:
                if (sp < 2) { result.error = "Stack underflow"; goto end_loop; }
                stack[sp - 2] = stack[sp - 2] & stack[sp - 1];
                sp--;
                break;

            case OP_OR:
                if (sp < 2) { result.error = "Stack underflow"; goto end_loop; }
                stack[sp - 2] = stack[sp - 2] | stack[sp - 1];
                sp--;
                break;

            case OP_XOR:
                if (sp < 2) { result.error = "Stack underflow"; goto end_loop; }
                stack[sp - 2] = stack[sp - 2] ^ stack[sp - 1];
                sp--;
                break;

            case OP_NOT:
                if (sp < 1) { result.error = "Stack underflow"; goto end_loop; }
                stack[sp - 1] = (~stack[sp - 1]) & WORD_MASK;
                break;

            case OP_SHL1:
                if (sp < 1) { result.error = "Stack underflow"; goto end_loop; }
                stack[sp - 1] = (stack[sp - 1] << 1) & WORD_MASK;
                break;

            case OP_SHR1:
                if (sp < 1) { result.error = "Stack underflow"; goto end_loop; }
                stack[sp - 1] = (stack[sp - 1] >> 1) & WORD_MASK;
                break;

            case OP_JMP: {
                int16_t rel = sign_extend_12(imm12);
                next_pc = (pc + 1) + rel;
                break;
            }

            case OP_JZ: {
                if (sp < 1) { result.error = "Stack underflow"; goto end_loop; }
                if (stack[--sp] == 0) {
                    int16_t rel = sign_extend_12(imm12);
                    next_pc = (pc + 1) + rel;
                }
                break;
            }

            default:
                result.error = "Unknown opcode";
                goto end_loop;
        }

        // Syscall handling is special. The Python wrapper will handle the actual call.
        // Here we just check for the exception signal from the wrapper.
        if (op == OP_SYSC) {
             // A special value in sp signals a graceful exit from Python.
            if (sp == -999) {
                exit_code = stack[0]; // The exit code is passed back in the stack.
                result.halted = true;
                goto end_loop;
            }
        }

        pc = next_pc;
    }

end_loop:
    if (result.error == NULL) {
        result.halted = true;
    }

    result.exit_code = exit_code;
    result.pc = pc;
    result.steps = steps;
    result.stack_size = sp;

    // Copy the final stack into a dynamically allocated array for Python
    if (sp > 0) {
        result.stack = (uint16_t*)malloc(sp * sizeof(uint16_t));
        if (result.stack != NULL) {
            for (int i = 0; i < sp; i++) {
                result.stack[i] = stack[i];
            }
        } else {
            // Failed to allocate memory for the stack to be returned
            result.error = "Failed to allocate memory for result stack";
            result.stack_size = 0;
        }
    } else {
        result.stack = NULL;
    }

    return result;
}

void free_vm_result(VMResult result) {
    if (result.stack != NULL) {
        free(result.stack);
    }
}