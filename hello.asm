.data
    str 1, "hello world\n"

.text
    XOR R3, R3, 0
    MOV_REG_IMM R2, END
    MOV_REG_IMM R1, 1
    MOV_REG_REG_ADD R5, R15, 0
    LD_REG_MEM R0, R1, 0
    JZ R0, R2, 0
    SYSCALL 1 # PUTC
    ADD R1, R3, 1
    JMP R5, 0
END:
    SYSCALL 0 # EXIT