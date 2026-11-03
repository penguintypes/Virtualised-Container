CC ?= gcc
CFLAGS ?= -O2 -g
CFLAGS += -std=c17 -Wall -Wextra -Werror
CPPFLAGS += -iquote include

.PHONY: all clean

SOURCES := src/vcontainer.c src/cgroup.c src/namespace.c src/seccomp.c src/remember.c src/log.c src/state.c src/overlay.c src/network.c
HEADERS := include/cgroup.h include/namespace.h include/seccomp.h include/remember.h include/log.h include/state.h include/overlay.h include/network.h
BINARY := build/vcontainer

all: $(BINARY)

$(BINARY): $(SOURCES) $(HEADERS) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(SOURCES) -lseccomp -o $@

build:
	mkdir -p $@

clean:
	rm -f $(BINARY)
