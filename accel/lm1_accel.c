/*
 * lm1_accel.c — C accelerator for LM-1 scalar operations.
 *
 * Handles: ARITH_RAW, BITWISE, LDR, STR, BR, BR_COND, LI, LUI, LI32,
 *          PUSH_POP, HALT_NOP.
 * Falls back to Python for tagged ops, allocation, GC, field access,
 * call/return, traps, and system.
 *
 * Build: gcc -O3 -march=native -shared -fPIC -o lm1_accel.so lm1_accel.c
 */

#include <stdint.h>
#include <stddef.h>
#include <string.h>

/* ── LM-1 opcode constants ─────────────────────────────────────────── */
#define OP_ARITH_RAW   48
#define OP_BITWISE     49
#define OP_LDR         50
#define OP_STR         51
#define OP_BR          52
#define OP_BR_COND     53
#define OP_PUSH_POP    54
#define OP_LI          55
#define OP_LUI         56
#define OP_PUSH_MULTI  57
#define OP_POP_MULTI   58
#define OP_LI32        59
#define OP_HALT_NOP    63

/* Prefetch no-ops (32-35) */
#define OP_PREFETCH_LO  32
#define OP_PREFETCH_HI  35

/* ── Tagged value helpers ──────────────────────────────────────────── */
#define NIL       0x05ULL
#define T_VALUE   0x0DULL
#define MASK64    0xFFFFFFFFFFFFFFFFULL

static inline int is_fixnum(uint64_t w)  { return (w & 1) == 0; }
static inline int is_truthy(uint64_t w)  { return w != NIL && w != 0; }

static inline int64_t untag_fixnum(uint64_t w) {
    return (int64_t)w >> 1;
}

/* ── State structures ──────────────────────────────────────────────── */

typedef struct {
    uint64_t regs[32];
    uint64_t pc;
    uint64_t sp;
    uint64_t fp;
    uint64_t lr;
    uint8_t  halted;
    uint8_t  _pad[7];
    uint64_t cycle_count;
} LM1State;

typedef struct {
    int32_t steps_executed;
    int32_t stop_reason;   /* 0=max_steps, 1=halt, 3=fallback */
} LM1Result;

/* ── Memory helpers ────────────────────────────────────────────────── */

static inline uint32_t mem_r32(const uint8_t *mem, size_t memsz, uint64_t addr) {
    size_t o = (size_t)(addr % memsz);
    uint32_t v;
    memcpy(&v, mem + o, 4);
    return v;
}

static inline uint64_t mem_r64(const uint8_t *mem, size_t memsz, uint64_t addr) {
    size_t o = (size_t)(addr % memsz);
    uint64_t v;
    memcpy(&v, mem + o, 8);
    return v;
}

static inline void mem_w64(uint8_t *mem, size_t memsz, uint64_t addr, uint64_t val) {
    size_t o = (size_t)(addr % memsz);
    memcpy(mem + o, &val, 8);
}

/* ── Main run loop ─────────────────────────────────────────────────── */

LM1Result lm1_run(LM1State *s, uint8_t *mem, size_t memsz, int max_steps) {
    LM1Result result = {0, 0};
    uint64_t *R = s->regs;

    for (int step = 0; step < max_steps; step++) {
        if (s->halted) {
            result.stop_reason = 1;
            break;
        }

        uint32_t raw = mem_r32(mem, memsz, s->pc);
        int op   = (raw >> 26) & 0x3F;
        int rd   = (raw >> 21) & 0x1F;
        int rs1  = (raw >> 16) & 0x1F;
        int rs2  = (raw >> 11) & 0x1F;
        int func = (raw >> 6)  & 0x1F;
        uint16_t imm16 = raw & 0xFFFF;
        int16_t  simm16 = (int16_t)imm16;

        uint64_t npc = s->pc + 4;

        switch (op) {

        /* ── HALT / NOP ──────────────────────────────────────────── */
        case OP_HALT_NOP: {
            uint32_t sub = raw & 0x03FFFFFF;
            if (sub == 0) {
                s->halted = 1;
                result.stop_reason = 1;
                result.steps_executed = step + 1;
                s->pc = npc;
                s->cycle_count++;
                return result;
            }
            /* NOP */
            break;
        }

        /* ── LI ──────────────────────────────────────────────────── */
        case OP_LI:
            R[rd] = (uint64_t)(int64_t)simm16;
            break;

        /* ── LUI ─────────────────────────────────────────────────── */
        case OP_LUI:
            R[rd] = (R[rd] & ~0xFFFF0000ULL) | (((uint64_t)imm16) << 16);
            break;

        /* ── LI32 ────────────────────────────────────────────────── */
        case OP_LI32: {
            uint32_t imm32 = mem_r32(mem, memsz, npc);
            npc += 4;
            if (imm32 >= 0x80000000U) {
                R[rd] = (uint64_t)imm32 | 0xFFFFFFFF00000000ULL;
            } else {
                R[rd] = (uint64_t)imm32;
            }
            break;
        }

        /* ── ARITH_RAW ───────────────────────────────────────────── */
        case OP_ARITH_RAW: {
            uint64_t a = R[rs1], b = R[rs2];
            switch (func) {
            case 0: R[rd] = a + b; break;
            case 1: R[rd] = a - b; break;
            case 2: R[rd] = a * b; break;
            case 3:
                if (b == 0) { result.stop_reason = 3; result.steps_executed = step; return result; }
                R[rd] = (uint64_t)((int64_t)a / (int64_t)b); break;
            case 4:
                if (b == 0) { result.stop_reason = 3; result.steps_executed = step; return result; }
                R[rd] = a % b; break;
            default: result.stop_reason = 3; result.steps_executed = step; return result;
            }
            break;
        }

        /* ── BITWISE ─────────────────────────────────────────────── */
        case OP_BITWISE: {
            uint64_t a = R[rs1], b = R[rs2];
            int sh = (int)(b & 63);
            switch (func) {
            case 0: R[rd] = a & b; break;
            case 1: R[rd] = a | b; break;
            case 2: R[rd] = a ^ b; break;
            case 3: R[rd] = a << sh; break;
            case 4: R[rd] = a >> sh; break;
            case 5: R[rd] = (uint64_t)((int64_t)a >> sh); break;
            case 6: R[rd] = ~a; break;
            default: result.stop_reason = 3; result.steps_executed = step; return result;
            }
            break;
        }

        /* ── LDR ─────────────────────────────────────────────────── */
        case OP_LDR: {
            uint64_t addr = R[rs1] + (int64_t)simm16 * 8;
            R[rd] = mem_r64(mem, memsz, addr);
            break;
        }

        /* ── STR ─────────────────────────────────────────────────── */
        case OP_STR: {
            uint64_t addr = R[rd] + (int64_t)simm16 * 8;
            mem_w64(mem, memsz, addr, R[rs1]);
            break;
        }

        /* ── BR (unconditional) ──────────────────────────────────── */
        case OP_BR:
            npc = s->pc + (int64_t)simm16 * 4;
            break;

        /* ── BR_COND ─────────────────────────────────────────────── */
        case OP_BR_COND: {
            int cond = rs1;   /* condition code in bits 20:16 */
            uint64_t w = R[rd];
            int taken = 0;
            switch (cond) {
            case 0: taken = is_truthy(w);  break;                /* BR.T */
            case 1: taken = (w == NIL);    break;                /* BR.NIL */
            case 2: taken = is_fixnum(w) && untag_fixnum(w) < 0; break;  /* FIX.LT */
            case 3: taken = (w == 0);      break;                /* FIX.EQ */
            case 4: taken = is_fixnum(w) && untag_fixnum(w) > 0; break;  /* FIX.GT */
            case 5: taken = (w == 0);      break;                /* EQ */
            default: break;
            }
            if (taken) {
                npc = s->pc + (int64_t)simm16 * 4;
            }
            break;
        }

        /* ── PUSH / POP ──────────────────────────────────────────── */
        case OP_PUSH_POP:
            if (func == 0) { /* PUSH */
                s->sp -= 8;
                mem_w64(mem, memsz, s->sp, R[rs1]);
            } else if (func == 1) { /* POP */
                R[rd] = mem_r64(mem, memsz, s->sp);
                s->sp += 8;
            }
            break;

        /* ── PUSH_MULTI ──────────────────────────────────────────── */
        case OP_PUSH_MULTI: {
            uint16_t mask = imm16;
            for (int i = 31; i >= 0; i--) {
                if (mask & (1u << i)) {
                    s->sp -= 8;
                    mem_w64(mem, memsz, s->sp, R[i]);
                }
            }
            break;
        }

        /* ── POP_MULTI ───────────────────────────────────────────── */
        case OP_POP_MULTI: {
            uint16_t mask = imm16;
            for (int i = 0; i < 32; i++) {
                if (mask & (1u << i)) {
                    R[i] = mem_r64(mem, memsz, s->sp);
                    s->sp += 8;
                }
            }
            break;
        }

        /* ── Prefetch (no-ops) ───────────────────────────────────── */
        case 32: case 33: case 34: case 35:
            break;

        /* ── Everything else → fallback to Python ────────────────── */
        default:
            result.stop_reason = 3;
            result.steps_executed = step;
            return result;
        }

        s->pc = npc;
        s->cycle_count++;
        result.steps_executed = step + 1;
    }

    return result;
}
