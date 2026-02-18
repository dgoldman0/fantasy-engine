/*
 * chimera_accel.c — C accelerator for the Chimera-1 MP64 emulator.
 *
 * Handles the hot-path instructions (ALU, branches, loads/stores,
 * immediates, INC/DEC, MOV) in C.  Falls back to the Python emulator
 * for complex/side-effectful instructions (SYS, I/O, CSR, MEX, MMIO).
 *
 * Build:
 *   gcc -O3 -march=native -shared -fPIC -o chimera_accel.so mp64_accel.c
 */

#include <stdint.h>
#include <stddef.h>
#include <string.h>

/* ------------------------------------------------------------------ */
/*  State structures — must match the ctypes layout in core.py        */
/* ------------------------------------------------------------------ */

typedef struct {
    uint64_t regs[16];
    uint8_t  psel, xsel, spsel;
    uint8_t  d_reg, t_reg, q_out;
    uint8_t  flag_z, flag_c, flag_n, flag_v, flag_p, flag_g, flag_i, flag_s;
    uint64_t ivt_base;
    uint8_t  priv_level;
    uint8_t  halted, idle;
    uint8_t  _pad0;
    int32_t  ext_modifier;
    uint64_t cycle_count;
    uint8_t  ivec_id;
    uint8_t  _pad1[7];
    uint64_t trap_addr;
    uint64_t mpu_base, mpu_limit;
    uint32_t core_id, n_cores;
} MP64State;

typedef struct {
    uint64_t total_cycles;
    int32_t  steps_executed;
    int32_t  stop_reason;   /* 0=max, 1=halt, 2=idle, 3=fallback, 4=trap */
} RunResult;

/* Stop reasons */
#define STOP_MAX      0
#define STOP_HALT     1
#define STOP_IDLE     2
#define STOP_FALLBACK 3
#define STOP_TRAP     4

/* IVT vectors */
#define IVEC_DIV_ZERO  4
#define IVEC_SW_TRAP   6

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

static inline uint8_t parity8(uint64_t v) {
    v &= 0xFF;
    v ^= v >> 4;
    v ^= v >> 2;
    v ^= v >> 1;
    return v & 1;
}

static inline int64_t sext8(uint8_t v) {
    return (int64_t)(int8_t)v;
}

static inline int64_t sext16(uint16_t v) {
    return (int64_t)(int16_t)v;
}

static inline int64_t sext64(uint64_t v) {
    return (int64_t)v;
}

static inline void flags_add(MP64State *s, uint64_t a, uint64_t b, uint64_t r64, int carry) {
    s->flag_z = (r64 == 0);
    s->flag_c = carry;
    s->flag_n = (r64 >> 63) & 1;
    uint8_t sa = (a >> 63) & 1, sb = (b >> 63) & 1, sr = (r64 >> 63) & 1;
    s->flag_v = (sa == sb) && (sr != sa);
    s->flag_p = parity8(r64);
}

static inline void flags_sub(MP64State *s, uint64_t a, uint64_t b, uint64_t r64) {
    s->flag_z = (r64 == 0);
    s->flag_c = (a >= b);   /* no borrow */
    s->flag_n = (r64 >> 63) & 1;
    uint8_t sa = (a >> 63) & 1, sb = (b >> 63) & 1, sr = (r64 >> 63) & 1;
    s->flag_v = (sa != sb) && (sr != sa);
    s->flag_p = parity8(r64);
}

static inline void flags_logic(MP64State *s, uint64_t r64) {
    s->flag_z = (r64 == 0);
    s->flag_p = parity8(r64);
}

static inline void flags_shift(MP64State *s, uint64_t r64, uint8_t c) {
    s->flag_z = (r64 == 0);
    s->flag_c = c;
    s->flag_n = (r64 >> 63) & 1;
    s->flag_p = parity8(r64);
}

/* Inline memory helpers (non-MMIO fast path) */
static inline uint8_t rd8(const uint8_t *mem, size_t sz, uint64_t a) {
    return mem[a % sz];
}

static inline uint64_t rd64(const uint8_t *mem, size_t sz, uint64_t a) {
    size_t o = a % sz;
    uint64_t v;
    memcpy(&v, mem + o, 8);  /* assumes LE host */
    return v;
}

static inline void wr64(uint8_t *mem, size_t sz, uint64_t a, uint64_t v) {
    size_t o = a % sz;
    memcpy(mem + o, &v, 8);
}

static inline uint16_t rd16(const uint8_t *mem, size_t sz, uint64_t a) {
    size_t o = a % sz;
    uint16_t v;
    memcpy(&v, mem + o, 2);
    return v;
}

static inline void wr16(uint8_t *mem, size_t sz, uint64_t a, uint16_t v) {
    size_t o = a % sz;
    memcpy(mem + o, &v, 2);
}

static inline uint32_t rd32(const uint8_t *mem, size_t sz, uint64_t a) {
    size_t o = a % sz;
    uint32_t v;
    memcpy(&v, mem + o, 4);
    return v;
}

static inline void wr32(uint8_t *mem, size_t sz, uint64_t a, uint32_t v) {
    size_t o = a % sz;
    memcpy(mem + o, &v, 4);
}

/* Check if address is in MMIO range */
static inline int is_mmio(uint64_t a, uint64_t mmio_start, uint64_t mmio_end) {
    return a >= mmio_start && a < mmio_end;
}

/* ------------------------------------------------------------------ */
/*  Condition test                                                    */
/* ------------------------------------------------------------------ */

static inline int cond_test(const MP64State *s, uint8_t cc) {
    switch (cc) {
        case  0: return 1;              /* AL */
        case  1: return s->flag_z;      /* EQ */
        case  2: return !s->flag_z;     /* NE */
        case  3: return s->flag_c;      /* CS */
        case  4: return !s->flag_c;     /* CC */
        case  5: return s->flag_n;      /* MI */
        case  6: return !s->flag_n;     /* PL */
        case  7: return s->flag_v;      /* VS */
        case  8: return !s->flag_v;     /* VC */
        case  9: return s->flag_g;      /* GT */
        case 10: return !s->flag_g;     /* LE */
        case 11: return s->q_out;       /* BQ */
        case 12: return !s->q_out;      /* BNQ */
        case 13: return s->flag_s;      /* SAT */
        case 15: return 0;             /* NV */
        default: return 0;
    }
}

/* ------------------------------------------------------------------ */
/*  Main run loop                                                     */
/* ------------------------------------------------------------------ */

RunResult mp64_run(MP64State *s, uint8_t *mem, size_t mem_sz,
                   uint64_t mmio_start, uint64_t mmio_end,
                   int max_steps)
{
    RunResult res = {0, 0, 0};
    uint64_t *R = s->regs;

    for (int step = 0; step < max_steps; step++) {
        if (s->halted) { res.stop_reason = STOP_HALT; break; }
        if (s->idle)   { res.stop_reason = STOP_IDLE; break; }

        uint64_t pc = R[s->psel];

        /* Check for MMIO in instruction stream */
        if (is_mmio(pc, mmio_start, mmio_end)) {
            res.stop_reason = STOP_FALLBACK;
            break;
        }

        uint8_t b0 = rd8(mem, mem_sz, pc);
        pc++;

        uint8_t f = (b0 >> 4) & 0xF;
        uint8_t n = b0 & 0xF;

        /* Handle EXT prefix */
        int ext = -1;
        if (f == 0xF) {
            ext = n;
            b0 = rd8(mem, mem_sz, pc);
            pc++;
            f = (b0 >> 4) & 0xF;
            n = b0 & 0xF;
        }

        int cycles = 1;

        switch (f) {

        case 0x0: /* SYS — fallback to Python */
            R[s->psel] = pc - 1 - (ext >= 0 ? 1 : 0);
            res.stop_reason = STOP_FALLBACK;
            goto done;

        case 0x1: /* INC */
            R[n]++;
            break;

        case 0x2: /* DEC */
            R[n]--;
            break;

        case 0x3: { /* BR (short branch) */
            int8_t off = (int8_t)rd8(mem, mem_sz, pc);
            pc++;
            if (ext == 6) { /* EXT.SKIP — fallback for complexity */
                R[s->psel] = pc - 3;
                res.stop_reason = STOP_FALLBACK;
                goto done;
            }
            if (cond_test(s, n))
                pc = (uint64_t)((int64_t)pc + off);
            cycles = 2;
            break;
        }

        case 0x4: { /* LBR (long branch) */
            uint8_t hi = rd8(mem, mem_sz, pc);
            uint8_t lo = rd8(mem, mem_sz, pc + 1);
            pc += 2;
            int16_t off = (int16_t)((hi << 8) | lo);
            if (cond_test(s, n))
                pc = (uint64_t)((int64_t)pc + off);
            cycles = 3;
            break;
        }

        case 0x5: { /* MEM */
            uint8_t b1 = rd8(mem, mem_sz, pc);
            pc++;
            uint8_t rd = (b1 >> 4) & 0xF;
            uint8_t rs = b1 & 0xF;

            /* Check for MMIO memory access */
            uint64_t addr;
            switch (n) {
                case 0x4: case 0x5: case 0x7: case 0x9: case 0xB:
                    addr = R[rd]; break;
                default:
                    addr = (n == 0x2 || n == 0x3) ? R[s->xsel] : R[rs]; break;
            }
            if (n == 0xF) {
                int8_t doff = (int8_t)rd8(mem, mem_sz, pc);
                addr = R[rs] + (int64_t)doff * 8;
            }
            if (is_mmio(addr, mmio_start, mmio_end)) {
                R[s->psel] = pc - 2;
                res.stop_reason = STOP_FALLBACK;
                goto done;
            }

            switch (n) {
                case 0x0: R[rd] = rd64(mem, mem_sz, R[rs]); break;
                case 0x1: R[rd] = rd64(mem, mem_sz, R[rs]); R[rs] += 8; break;
                case 0x2: R[rd] = rd64(mem, mem_sz, R[s->xsel]); break;
                case 0x3: R[rd] = rd64(mem, mem_sz, R[s->xsel]); R[s->xsel] += 8; break;
                case 0x4: wr64(mem, mem_sz, R[rd], R[rs]); break;
                case 0x5: wr64(mem, mem_sz, R[rd], R[rs]); R[rd] -= 8; break;
                case 0x6: R[rd] = rd8(mem, mem_sz, R[rs]); break;
                case 0x7: mem[R[rd] % mem_sz] = (uint8_t)(R[rs]); break;
                case 0x8: R[rd] = rd16(mem, mem_sz, R[rs]); break;
                case 0x9: wr16(mem, mem_sz, R[rd], (uint16_t)R[rs]); break;
                case 0xA: R[rd] = rd32(mem, mem_sz, R[rs]); break;
                case 0xB: wr32(mem, mem_sz, R[rd], (uint32_t)R[rs]); break;
                case 0xC: R[rd] = (uint64_t)(int64_t)(int8_t)rd8(mem, mem_sz, R[rs]); break;
                case 0xD: R[rd] = (uint64_t)(int64_t)(int16_t)rd16(mem, mem_sz, R[rs]); break;
                case 0xE: R[rd] = (uint64_t)(int64_t)(int32_t)rd32(mem, mem_sz, R[rs]); break;
                case 0xF: {
                    int8_t doff = (int8_t)rd8(mem, mem_sz, pc);
                    pc++;
                    R[rd] = rd64(mem, mem_sz, R[rs] + (int64_t)doff * 8);
                    cycles = 3;
                    break;
                }
            }
            cycles = (n == 0xF) ? 3 : 2;
            break;
        }

        case 0x6: { /* IMM */
            if (n == 0x0) { /* LDI */
                uint8_t rn = rd8(mem, mem_sz, pc) & 0xF;
                pc++;
                if (ext == 0) { /* EXT.IMM64 */
                    uint64_t v = 0;
                    for (int i = 0; i < 8; i++)
                        v |= (uint64_t)rd8(mem, mem_sz, pc + i) << (8 * i);
                    pc += 8;
                    R[rn] = v;
                    cycles = 4;
                } else {
                    R[rn] = rd8(mem, mem_sz, pc);
                    pc++;
                    cycles = 2;
                }
            } else if (n == 0x1) { /* LHI */
                uint8_t rn = rd8(mem, mem_sz, pc) & 0xF;
                uint8_t hi = rd8(mem, mem_sz, pc + 1);
                uint8_t lo = rd8(mem, mem_sz, pc + 2);
                pc += 3;
                uint16_t imm16 = (hi << 8) | lo;
                R[rn] = (R[rn] & 0x0000FFFFFFFFFFFFULL) | ((uint64_t)imm16 << 48);
                cycles = 3;
            } else if (n >= 0x2 && n <= 0x7) {
                uint8_t rn = rd8(mem, mem_sz, pc) & 0xF;
                uint8_t imm = rd8(mem, mem_sz, pc + 1);
                pc += 2;
                int64_t simm = sext8(imm);
                uint64_t uimm = (uint64_t)simm;
                uint64_t a = R[rn];
                switch (n) {
                    case 0x2: { /* ADDI */
                        __uint128_t r = (__uint128_t)a + uimm;
                        R[rn] = (uint64_t)r;
                        flags_add(s, a, uimm, R[rn], r > UINT64_MAX);
                        break;
                    }
                    case 0x3: /* ANDI */
                        R[rn] = a & (uint64_t)(uint8_t)imm;
                        flags_logic(s, R[rn]);
                        break;
                    case 0x4: /* ORI */
                        R[rn] = a | (uint64_t)(uint8_t)imm;
                        flags_logic(s, R[rn]);
                        break;
                    case 0x5: /* XORI */
                        R[rn] = a ^ (uint64_t)(uint8_t)imm;
                        flags_logic(s, R[rn]);
                        break;
                    case 0x6: { /* CMPI */
                        uint64_t r64 = a - uimm;
                        flags_sub(s, a, uimm, r64);
                        s->flag_g = (sext64(a) > simm) ? 1 : 0;
                        break;
                    }
                    case 0x7: { /* SUBI */
                        uint64_t r64 = a - uimm;
                        R[rn] = r64;
                        flags_sub(s, a, uimm, r64);
                        break;
                    }
                }
                cycles = 2;
            } else if (n >= 0x8 && n <= 0xB) {
                uint8_t b1 = rd8(mem, mem_sz, pc);
                pc++;
                uint8_t rn = (b1 >> 4) & 0xF;
                uint8_t imm4 = b1 & 0xF;
                uint64_t v = R[rn];
                switch (n) {
                    case 0x8: { /* LSLI */
                        uint8_t c = imm4 ? (v >> (64 - imm4)) & 1 : 0;
                        R[rn] = v << imm4;
                        flags_shift(s, R[rn], c);
                        break;
                    }
                    case 0x9: { /* LSRI */
                        uint8_t c = imm4 ? (v >> (imm4 - 1)) & 1 : 0;
                        R[rn] = v >> imm4;
                        flags_shift(s, R[rn], c);
                        break;
                    }
                    case 0xA: { /* ASRI */
                        uint8_t c = imm4 ? (v >> (imm4 - 1)) & 1 : 0;
                        R[rn] = (uint64_t)((int64_t)v >> imm4);
                        flags_shift(s, R[rn], c);
                        break;
                    }
                    case 0xB: { /* ROLI */
                        uint8_t amt = imm4 & 0x3F;
                        if (amt)
                            R[rn] = (v << amt) | (v >> (64 - amt));
                        s->flag_z = (R[rn] == 0);
                        s->flag_n = (R[rn] >> 63) & 1;
                        s->flag_p = parity8(R[rn]);
                        break;
                    }
                }
                cycles = 1;
            } else { /* C-F: GLO/GHI/PLO/PHI — fallback for simplicity */
                R[s->psel] = pc - 1 - (ext >= 0 ? 1 : 0);
                res.stop_reason = STOP_FALLBACK;
                goto done;
            }
            break;
        }

        case 0x7: { /* ALU */
            uint8_t b1 = rd8(mem, mem_sz, pc);
            pc++;
            uint8_t rd = (b1 >> 4) & 0xF;
            uint8_t rs = b1 & 0xF;
            uint64_t a = R[rd], b = R[rs];

            switch (n) {
                case 0x0: { /* ADD */
                    __uint128_t r = (__uint128_t)a + b;
                    R[rd] = (uint64_t)r;
                    flags_add(s, a, b, R[rd], r > UINT64_MAX);
                    break;
                }
                case 0x1: { /* ADC */
                    __uint128_t r = (__uint128_t)a + b + s->flag_c;
                    R[rd] = (uint64_t)r;
                    flags_add(s, a, b + s->flag_c, R[rd], r > UINT64_MAX);
                    break;
                }
                case 0x2: { /* SUB */
                    uint64_t r = a - b;
                    R[rd] = r;
                    flags_sub(s, a, b, r);
                    break;
                }
                case 0x3: { /* SBB */
                    uint64_t borrow = 1 - s->flag_c;
                    uint64_t r = a - b - borrow;
                    R[rd] = r;
                    flags_sub(s, a, b + borrow, r);
                    break;
                }
                case 0x4: R[rd] = a & b; flags_logic(s, R[rd]); break;
                case 0x5: R[rd] = a | b; flags_logic(s, R[rd]); break;
                case 0x6: R[rd] = a ^ b; flags_logic(s, R[rd]); break;
                case 0x7: { /* CMP */
                    uint64_t r = a - b;
                    flags_sub(s, a, b, r);
                    s->flag_g = (sext64(a) > sext64(b)) ? 1 : 0;
                    break;
                }
                case 0x8: R[rd] = b; break; /* MOV */
                case 0x9: R[rd] = ~b; flags_logic(s, R[rd]); break; /* NOT */
                case 0xA: { /* NEG */
                    R[rd] = (uint64_t)(-(int64_t)b);
                    flags_sub(s, 0, b, R[rd]);
                    break;
                }
                case 0xB: { /* SHL */
                    uint8_t amt = b & 0x3F;
                    uint8_t c = amt ? (a >> (64 - amt)) & 1 : 0;
                    R[rd] = a << amt;
                    flags_shift(s, R[rd], c);
                    break;
                }
                case 0xC: { /* SHR */
                    uint8_t amt = b & 0x3F;
                    uint8_t c = amt ? (a >> (amt - 1)) & 1 : 0;
                    R[rd] = a >> amt;
                    flags_shift(s, R[rd], c);
                    break;
                }
                case 0xD: { /* SAR */
                    uint8_t amt = b & 0x3F;
                    uint8_t c = amt ? (a >> (amt - 1)) & 1 : 0;
                    R[rd] = (uint64_t)((int64_t)a >> amt);
                    flags_shift(s, R[rd], c);
                    break;
                }
                case 0xE: { /* ROL */
                    uint8_t amt = b & 0x3F;
                    if (amt) R[rd] = (a << amt) | (a >> (64 - amt));
                    s->flag_z = (R[rd] == 0);
                    s->flag_n = (R[rd] >> 63) & 1;
                    s->flag_p = parity8(R[rd]);
                    break;
                }
                case 0xF: { /* ROR */
                    uint8_t amt = b & 0x3F;
                    if (amt) R[rd] = (a >> amt) | (a << (64 - amt));
                    s->flag_z = (R[rd] == 0);
                    s->flag_n = (R[rd] >> 63) & 1;
                    s->flag_p = parity8(R[rd]);
                    break;
                }
            }
            break;
        }

        case 0x8: /* MEMALU — fallback (accesses D register + M(R(X))) */
            R[s->psel] = pc - 1;
            res.stop_reason = STOP_FALLBACK;
            goto done;

        case 0x9: /* I/O — fallback */
            R[s->psel] = pc - 1;
            res.stop_reason = STOP_FALLBACK;
            goto done;

        case 0xA: { /* SEP */
            uint8_t old = s->psel;
            R[old] = pc;
            s->psel = n;
            pc = R[n];
            break;
        }

        case 0xB: /* SEX */
            s->xsel = n;
            break;

        case 0xC: { /* MULDIV */
            uint8_t b1 = rd8(mem, mem_sz, pc);
            pc++;
            uint8_t rd = (b1 >> 4) & 0xF;
            uint8_t rs = b1 & 0xF;
            uint64_t a = R[rd], b = R[rs];

            switch (n) {
                case 0: R[rd] = (uint64_t)((int64_t)a * (int64_t)b); break;
                case 1: R[rd] = (uint64_t)(((__int128)(int64_t)a * (int64_t)b) >> 64); break;
                case 2: R[rd] = a * b; break;
                case 3: R[rd] = (uint64_t)(((__uint128_t)a * b) >> 64); break;
                case 4:
                    if (b == 0) { s->ivec_id = IVEC_DIV_ZERO; R[s->psel] = pc; res.stop_reason = STOP_TRAP; goto done; }
                    R[rd] = (uint64_t)((int64_t)a / (int64_t)b); break;
                case 5:
                    if (b == 0) { s->ivec_id = IVEC_DIV_ZERO; R[s->psel] = pc; res.stop_reason = STOP_TRAP; goto done; }
                    R[rd] = a / b; break;
                case 6:
                    if (b == 0) { s->ivec_id = IVEC_DIV_ZERO; R[s->psel] = pc; res.stop_reason = STOP_TRAP; goto done; }
                    R[rd] = (uint64_t)((int64_t)a % (int64_t)b); break;
                case 7:
                    if (b == 0) { s->ivec_id = IVEC_DIV_ZERO; R[s->psel] = pc; res.stop_reason = STOP_TRAP; goto done; }
                    R[rd] = a % b; break;
            }
            cycles = 4;
            break;
        }

        case 0xD: /* CSR — fallback (side effects) */
            R[s->psel] = pc - 1 - (ext >= 0 ? 1 : 0);
            res.stop_reason = STOP_FALLBACK;
            goto done;

        case 0xE: /* MEX — fallback */
            R[s->psel] = pc - 1 - (ext >= 0 ? 1 : 0);
            res.stop_reason = STOP_FALLBACK;
            goto done;

        default:
            break;
        }

        R[s->psel] = pc;
        s->cycle_count += cycles;
        res.total_cycles += cycles;
        res.steps_executed = step + 1;
    }

    if (res.stop_reason == 0)
        res.stop_reason = STOP_MAX;

done:
    return res;
}
