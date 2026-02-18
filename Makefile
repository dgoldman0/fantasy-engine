.PHONY: accel test clean

CC ?= gcc
CFLAGS = -O3 -march=native -shared -fPIC -Wall -Wextra

accel: accel/chimera_accel.so

accel/chimera_accel.so: accel/mp64_accel.c
	$(CC) $(CFLAGS) -o $@ $<

test: accel
	python -m pytest tests/ -v

test-py:
	python -m pytest tests/ -v

clean:
	rm -f accel/*.so accel/*.o
