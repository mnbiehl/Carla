#!/usr/bin/make -f
# Makefile for Carla MCP Server
# ----------------------------------

include ../../Makefile.mk

# ------------------------------------------------------------------------------
# Build config

OBJS = $(OBJDIR)/mcp-server.cpp.o $(OBJDIR)/mcp-host.cpp.o $(OBJDIR)/mcp-discovery.cpp.o

TARGETS = $(BINDIR)/carla-mcp-server

# ------------------------------------------------------------------------------
# Build flags

BUILD_CXX_FLAGS += -I../backend -I../includes -I../utils

# ------------------------------------------------------------------------------
# Link flags

LINK_FLAGS += $(CARLA_BACKEND_LIBS)

# Add FastMCP dependencies (Python integration)
BUILD_CXX_FLAGS += $(shell python3-config --includes)
LINK_FLAGS += $(shell python3-config --ldflags --embed)

# ------------------------------------------------------------------------------
# Targets

all: $(TARGETS)

install: $(TARGETS)
	install -d $(DESTDIR)$(BINDIR)
	install -m 755 $(TARGETS) $(DESTDIR)$(BINDIR)

clean:
	rm -f $(OBJS) $(TARGETS)

# ------------------------------------------------------------------------------
# Build rules

$(BINDIR)/carla-mcp-server: $(OBJS)
	@echo "Linking carla-mcp-server"
	@$(CXX) $(OBJS) $(LINK_FLAGS) -o $@

$(OBJDIR)/%.cpp.o: %.cpp
	@echo "Compiling $<"
	@$(CXX) $< $(BUILD_CXX_FLAGS) -c -o $@

-include $(OBJS:%.o=%.d)

# ------------------------------------------------------------------------------