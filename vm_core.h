#ifndef VM_CORE_H
#define VM_CORE_H

#include <stdint.h>
#include <stdbool.h>

// Define constants that match the Python VM
#define NUM_REGISTERS 16
#define WORD_LENGTH 8
#define MEMORY_SIZE (WORD_LENGTH * 8)
#define INSTRUCTION_LENGTH 2
#define OP_LEN 4
#define REG_LEN 4
#define PC_REG 15

// Interrupt codes for communication with Python
#define INTERRUPT_NONE -1
#define INTERRUPT_MAX_STEPS -2
#define INTERRUPT_ILLEGAL_PC -3
#define INTERRUPT_PROTECTED_REG -4
#define INTERRUPT_UNKNOWN_OPCODE -5
#define INTERRUPT_MEMORY_ACCESS -6
#define INTERRUPT_DEBUG 0x7FFF

// Opcodes
#define OP_NOP 0x00
#define OP_SYSCALL 0x01
#define OP_MOV_REG_IMM 0x02
#define OP_MOV_REG_REG_SHR 0x03
#define OP_MOV_REG_REG_SHL 0x04
#define OP_MOV_REG_REG_ADD 0x05
#define OP_LD_REG_MEM 0x06
#define OP_ST_MEM_REG 0x07
#define OP_ADD 0x08
#define OP_SUB 0x09
#define OP_AND 0x0A
#define OP_OR 0x0B
#define OP_XOR 0x0C
#define OP_NOT 0x0D
#define OP_JMP 0x0E
#define OP_JZ 0x0F

#define OP_RAW_DUMP 0xFFF

// Represents the entire VM state passed between Python and C
typedef struct {
    uint16_t pc;
    uint8_t registers[NUM_REGISTERS];
    uint8_t memory[MEMORY_SIZE];
    int16_t interrupt;
    uint8_t flags; // For arithmetic flags (overflow, sign)
    uint32_t steps;
    uint16_t op;
    uint16_t rd;
    uint16_t rs;
    uint16_t imm4;
    uint16_t imm8;
    uint16_t imm12;
} VMState;


typedef union {
    struct
    {
        uint16_t op  : 4;
        uint16_t imm : 12;
    } op_imm;
    
    struct
    {
        uint16_t op  : 4;
        uint16_t rd  : 4;
        uint16_t imm : 8; 
    } op_reg_imm;

    struct
    {
        uint16_t op  : 4;
        uint16_t rd  : 4;
        uint16_t rs  : 4;
        uint16_t imm : 4; 
    } op_reg_reg_imm;

    char bytes[2];
} Instruction;

/**
 * @brief Executes instructions until a syscall, halt, or error occurs.
 */
void run_c(VMState* state, const uint8_t* program, int program_len, int max_steps, bool debug);

/**
 * @brief Assembles a single line of human-readable assembly into a 16-bit instruction.
 * Operands must be pre-resolved to integer strings.
 * @return 0 on success, negative on error.
 */
int assemble_instruction(const char* mnemonic, uint16_t op1, uint16_t op2, uint16_t op3,
                         Instruction* output_instruction, char** error_message);

/**
 * @brief Disassembles machine code into human-readable assembly.
 * @return 0 on success, negative on error. output_string must be freed by the caller.
 */
int disassemble(const uint8_t* program_bytes, int program_len, char** output_string);

/**
 * @brief Frees memory allocated by the C library (e.g., for assembly output).
 */
void free_memory(void* ptr);


#endif // VM_CORE_H