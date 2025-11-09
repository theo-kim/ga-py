import unittest
from misc import MiscVM, Systable
from asm import assemble

class TestVM(unittest.TestCase):

    def setUp(self):
        """Set up a clean VM and systable for each test."""
        self.systable: Systable = {}

    def _run_test(self, source: str, max_steps: int = 20) -> MiscVM:
        """Helper to assemble and run code, returning the final VM state."""
        program_bytes = assemble(source)
        vm = MiscVM(systable=self.systable)
        result = vm.run(program_bytes, max_steps=max_steps)
        
        self.assertIsNone(result.error, f"VM run failed with error: {result.error}")
        return vm

    def test_mov_reg_imm(self):
        """Tests loading immediate values into registers."""
        source = """
            MOV_REG_IMM r0, 42
            MOV_REG_IMM r1, 0xFE
            MOV_REG_IMM r2, -1  # Should wrap to 255
        """
        vm = self._run_test(source)
        self.assertEqual(vm.registers[0].value, 42)
        self.assertEqual(vm.registers[1].value, 0xFE)
        self.assertEqual(vm.registers[2].value, 255)

    def test_mov_reg_reg_add(self):
        """Tests moving and adding between registers."""
        source = """
            MOV_REG_IMM r0, 10
            MOV_REG_IMM r1, 20
            MOV_REG_REG_ADD r0, r1, 5  # r0 = r1 + 5 = 25
        """
        vm = self._run_test(source)
        self.assertEqual(vm.registers[0].value, 25)

    def test_add_sub(self):
        """Tests ADD and SUB instructions."""
        source = """
            MOV_REG_IMM r0, 100
            MOV_REG_IMM r1, 50
            ADD r0, r1, 10  # r0 = r0 + r1 + 10 = 160
            SUB r1, r0, 5   # r1 = r1 - r0 - 5 = 50 - 160 - 5 = -115 -> 141
        """
        vm = self._run_test(source)
        self.assertEqual(vm.registers[0].value, 160)
        self.assertEqual(vm.registers[1].value, 141) # 256 - 115 = 141

    def test_bitwise_ops(self):
        """Tests AND, OR, XOR, and NOT instructions."""
        source = """
            MOV_REG_IMM r0, 0b1100
            MOV_REG_IMM r1, 0b1010
            AND r2, r0, r1   # r2 = 0b1000 = 8
            OR  r3, r0, r1   # r3 = 0b1110 = 14
            XOR r4, r0, r1   # r4 = 0b0110 = 6
            NOT r5, r0       # r5 = ~0b1100 = 0b11110011 = 243
        """
        vm = self._run_test(source)
        self.assertEqual(vm.registers[2].value, 8)
        self.assertEqual(vm.registers[3].value, 14)
        self.assertEqual(vm.registers[4].value, 6)
        self.assertEqual(vm.registers[5].value, 243)

    def test_memory_load_store(self):
        """Tests storing to and loading from memory."""
        source = """
            MOV_REG_IMM r0, 123      # Value to store
            MOV_REG_IMM r1, 10       # Memory address
            ST_MEM_REG  r1, r0, 5    # mem[r1+5] = mem[15] = r0
            LD_REG_MEM  r2, r1, 5    # r2 = mem[r1+5] = mem[15]
        """
        vm = self._run_test(source)
        self.assertEqual(vm.memory[15], 123)
        self.assertEqual(vm.registers[2].value, 123)

    def test_jmp(self):
        """Tests unconditional jump."""
        source = """
            MOV_REG_IMM r0, 1
            MOV_REG_IMM r6, end  # Load address of 'end' label into r6
            JMP r6, 0            # Jump to address in r6
            MOV_REG_IMM r0, 99   # This should be skipped
        end:
            MOV_REG_IMM r1, 42
        """
        vm = self._run_test(source)
        self.assertEqual(vm.registers[0].value, 1, "Instruction after jump was not skipped")
        self.assertEqual(vm.registers[1].value, 42, "Did not jump to the correct label")

    def test_jz(self):
        """Tests conditional jump (jump if zero)."""
        source = """
            MOV_REG_IMM r0, 0      # Condition register (is zero)
            MOV_REG_IMM r1, 1      # Condition register (is not zero)
            MOV_REG_IMM r6, skip   # Jump target
            
            JZ r0, r6, 0           # Should jump, since r0 is 0
            MOV_REG_IMM r2, 99     # This should be skipped
        skip:
            MOV_REG_IMM r3, 100
            JZ r1, r6, 0           # Should NOT jump, since r1 is not 0
            MOV_REG_IMM r4, 101    # This should be executed
        """
        vm = self._run_test(source)
        self.assertEqual(vm.registers[2].value, 0, "JZ jumped incorrectly when it should have")
        self.assertEqual(vm.registers[3].value, 100)
        self.assertEqual(vm.registers[4].value, 101, "JZ failed to execute fall-through case")

    def test_rip_protection(self):
        """Tests that direct writes to the RIP register (r7) fail."""
        source = "MOV_REG_IMM r7, 42"
        program_bytes = assemble(source)
        vm = MiscVM(systable=self.systable)
        result = vm.run(program_bytes, max_steps=10)

        self.assertIsNotNone(result.error, "VM should have thrown an error for illegal RIP write")
        self.assertIn("Register is protected", str(result.error))


if __name__ == '__main__':
    unittest.main()
