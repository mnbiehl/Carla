# Carla MCP Project Overview

## Project Purpose
Carla is a fully-featured audio plugin host with support for many audio drivers and plugin formats. It's an open-source project licensed under GPL v2 or later. The project includes:
- Support for LADSPA, DSSI, LV2, VST2, VST3, and AU plugin formats
- SF2/3 and SFZ sound banks support
- Internal audio and MIDI file player
- Automation of plugin parameters via MIDI CC
- Remote control over OSC
- Rack and Patchbay processing modes
- Native audio drivers (ALSA, DirectSound, CoreAudio) and JACK support
- Available as LV2 and VST2 plugin itself

This fork adds MCP (Model Context Protocol) server functionality for AI control over Carla via direct backend API integration.

## Tech Stack
- **Core Backend**: C++ (main audio engine and plugin handling)
- **Frontend**: Python 3.10+ with PyQt5 for GUI
- **MCP Server**: Python with FastMCP framework
- **Build System**: GNU Make with CMake support
- **Dependencies**: 
  - Required: PyQt5 (for frontend)
  - Recommended: libmagic/file, liblo (OSC support)
  - Optional: ALSA, PulseAudio, X11, Qt4/Qt5, FluidSynth
- **Python Dependencies**: fastmcp, python-osc, pyqt5
- **Development Tools**: pytest, black, flake8, pylint

## Architecture
- Modular design with separate backend engine and frontend
- Plugin bridges for loading different plugin types
- MCP server integrated as frontend module
- Parallel processing support for audio plugins
- Real-time safe audio processing