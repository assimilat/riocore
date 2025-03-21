import importlib
import sys
import os
import shutil


class Toolchain:
    def __init__(self, config):
        self.config = config
        self.gateware_path = os.path.join(self.config["output_path"], "Gateware")
        self.riocore_path = config["riocore_path"]
        self.toolchain_path = self.config.get("toolchains_json", {}).get("diamond", "")
        if self.toolchain_path and not self.toolchain_path.endswith("bin"):
            self.toolchain_path = os.path.join(self.toolchain_path, "bin")

    def info(cls):
        info = {
            "url": "https://www.latticesemi.com/latticediamond",
            "info": "lattice diamond",
            "description": "",
        }
        return info

    def generate(self, path):
        pins_generator = importlib.import_module(".pins", "riocore.generator.pins.lpf")
        pins_generator.Pins(self.config).generate(path)

        if sys.platform == "linux":
            diamondc = shutil.which("diamondc")
            if diamondc is None:
                print("WARNING: can not found toolchain installation in PATH: diamondc")

        verilogs = " ".join(self.config["verilog_files"])

        makefile_data = []
        makefile_data.append("")
        makefile_data.append("# Toolchain: Diamond")
        makefile_data.append("")
        if self.toolchain_path:
            makefile_data.append(f"PATH     := {self.toolchain_path}:$(PATH)")
            makefile_data.append("")
        makefile_data.append("PROJECT  := rio")
        makefile_data.append("TOP      := rio")
        makefile_data.append(f"PART     := {self.config['type']}")
        makefile_data.append(f"VERILOGS := {verilogs}")
        makefile_data.append(f"CLK_SPEED := {float(self.config['speed']) / 1000000}")
        makefile_data.append("")
        makefile_data.append("all: build/$(PROJECT)_build.bit")
        makefile_data.append("")
        makefile_data.append("")
        makefile_data.append("$(PROJECT).tcl: $(VERILOGS)")
        makefile_data.append('	@echo "prj_project new -name $(PROJECT) -impl build -dev $(PART) -lpf pins.lpf" > $(PROJECT).tcl')
        makefile_data.append('	@for VAR in $?; do echo $$VAR | grep -s -q "\.v$$" && echo "prj_src add $$VAR" >> $(PROJECT).tcl; done')
        makefile_data.append('	@echo "prj_impl option top $(TOP)" >> $(PROJECT).tcl')
        makefile_data.append('	@echo "prj_project save" >> $(PROJECT).tcl')
        makefile_data.append('	@echo "prj_project close" >> $(PROJECT).tcl')
        makefile_data.append("")
        makefile_data.append("syn.tcl: $(PROJECT).tcl")
        makefile_data.append('	@echo "prj_project open $(PROJECT).ldf" >> syn.tcl')
        makefile_data.append('	@echo "prj_run Synthesis -impl build" >> syn.tcl')
        makefile_data.append('	@echo "prj_run Translate -impl build" >> syn.tcl')
        makefile_data.append('	@echo "prj_run Map -impl build" >> syn.tcl')
        makefile_data.append('	@echo "prj_run PAR -impl build" >> syn.tcl')
        makefile_data.append('	@echo "prj_run PAR -impl build -task PARTrace" >> syn.tcl')
        makefile_data.append('	@echo "prj_run Export -impl build -task Bitgen" >> syn.tcl')
        makefile_data.append('	@echo "prj_run Export -impl build -task Jedecgen" >> syn.tcl')
        makefile_data.append('	@echo "prj_project close" >> syn.tcl')
        makefile_data.append("")
        makefile_data.append("$(PROJECT).ldf: syn.tcl")
        makefile_data.append("	diamondc $(PROJECT).tcl")
        makefile_data.append("")
        makefile_data.append("build/$(PROJECT)_build.bit: $(PROJECT).ldf")
        makefile_data.append("	diamondc syn.tcl")
        makefile_data.append("	cp -v hash_new.txt hash_compiled.txt")
        makefile_data.append("")
        makefile_data.append("load:")
        makefile_data.append("	openFPGALoader -c usb-blaster build/$(PROJECT)_build.bit")
        makefile_data.append("	cp -v hash_new.txt hash_flashed.txt")
        makefile_data.append("")
        makefile_data.append("clean:")
        makefile_data.append("	rm -rf build $(PROJECT).ldf $(PROJECT).tcl syn.tcl")
        makefile_data.append("")
        makefile_data.append("")
        open(os.path.join(path, "Makefile"), "w").write("\n".join(makefile_data))
