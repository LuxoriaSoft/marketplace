import sys
import os
import json
import shutil
import tempfile
import subprocess
import shlex
from pathlib import Path

"""
Marketplace Controller
Upload Manager
v0.1.0

Requirements :
Python >= 3.11
Poetry Manager

Configuration : 
Needs Environment variable : GITHUB_TOKEN (Token has RW on the target repository)

Usage : 
> poetry install
> poetry run upload-base https://github.com/ORG_USER/REPO_SRC.git https://github.com/ORG_USER/REPO_TGT.git BRANCH_TBCREATED

Released under Apache 2.0
The Luxoria Project
"""

### GLOBAL VARS
LUXMOD_FILENAME = "luxmod.json"
DOTNET_EXECUTOR = "dotnet"

PLATFORM_TO_ARCH = {
    "win-x64": "x64",
    "win-x86": "x86",
    "win-arm64": "arm64"
}

### ERROR CODES
ERR_RET_CODE = "Args should be : [PATH TO LUXMOD.JSON]"
ERR_PLATFORM_NOT_SUPPORTED = "The specified platform is not currently supported"

### INTERNAL FUNCTIONS

class BuildSystem:
    def __init__(self, dir, arch, platform):
        """Reads the path as a json file"""
        self.dir = dir
        self.config_file_path = os.path.join(dir, LUXMOD_FILENAME)
        self.arch = arch
        self.platform = platform

        self.log("Retreiving configuration from " + self.config_file_path)
        file = open(self.config_file_path, 'r')
        self.file_data = json.load(file)

    def log(self, content: str):
        print("[\\]\t" + content)

    def build(self):
        """Build the solution using configuration, with rich error logs"""
        build = self.file_data['build']
        runtimes = build['runtimes']
        archs_list = list(runtimes.keys()) if isinstance(runtimes, dict) else runtimes
        self.log(f"Loading configuration... defined by archs {archs_list}")
        self.log(f"Checking compatibility with {self.arch}")
        if self.arch not in runtimes:
            self.log("err: Module not compatible with the specified architecture !")
            self.log("err: Build cancelled !")
            return 1

        DOTNET = DOTNET_EXECUTOR
        csproj = build['csproj']
        config = build['config']
        rid = runtimes[self.arch]
        workdir = Path(self.dir)

        cmd = [DOTNET, "publish", csproj, "-c", config, "-r", rid]

        self.log(f"Executing: {shlex.join(cmd)} in [{workdir.resolve()}]")

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(workdir),
                text=True,
                capture_output=True,
                shell=False
            )
        except FileNotFoundError as fnf:
            self.log(f"err: could not execute '{DOTNET}': {fnf}")
            return 1
        except Exception as ex:
            self.log(f"err: unexpected failure launching process: {ex}")
            return 1

        log_filename = f"{self.file_data['name']}.{self.arch}.log"
        try:
            with open(log_filename, "w", encoding="utf-8", newline="") as f:
                f.write("=== COMMAND ===\n")
                f.write(shlex.join(cmd) + "\n\n")
                f.write("=== CWD ===\n")
                f.write(str(workdir.resolve()) + "\n\n")
                f.write("=== EXIT CODE ===\n")
                f.write(str(proc.returncode) + "\n\n")
                f.write("=== STDOUT ===\n")
                f.write(proc.stdout or "")
                f.write("\n\n=== STDERR ===\n")
                f.write(proc.stderr or "")
                f.write("\n")
        except OSError as file_err:
            self.log(f"err: could not write log file '{log_filename}': {file_err}")

        if proc.returncode != 0:
            self.log("err: executing command failed.")
            self.log(f"exit code: {proc.returncode}")
            tail = "\n".join((proc.stderr or "").splitlines()[-20:])
            if tail:
                self.log(f"stderr (last 20 lines):\n{tail}")
            self.log(f"stdout:\n{proc.stdout}")
            self.log(f"stderr:\n{proc.stderr}")
            self.log(f"Full log saved as {log_filename}")
            return 1

        self.log(f"Success. Full log saved as {log_filename}")
        return 0
    
    def prepare_export(self, output: str):
        """Renames dll from Name.dll to Name.Lux.dll & Moves bin folder to target folder (output)"""
        framework = self.file_data["build"]["targetFramework"]
        config = self.file_data["build"]["config"]
        platform = self.platform
        root_path = os.path.join(self.dir, self.file_data["build"]["bin"], config, framework, platform)

        gdir = os.path.join(root_path, self.file_data["build"]["dll"].replace(".dll", ""))
        pdir = os.path.join(root_path, "publish")
        
        odll_name = self.file_data["build"]["dll"]
        ndll_name = self.file_data["build"]["dll"].replace(".dll", ".Lux.dll")
        self.log(f"Renaming DLL in {pdir} from: '{odll_name}' to '{ndll_name}'")
        os.rename(os.path.join(pdir, odll_name), os.path.join(pdir, ndll_name))

        out_dir = os.path.join(output, f"{self.file_data["name"]}.{self.arch}")

        self.log(f"Creating folder {out_dir}")
        os.mkdir(out_dir)
        print(os.listdir(pdir))

        pdir_tgt = os.path.join(out_dir, f"{self.file_data["name"]}.luxmod")
        self.log(f"Copying dir (1/2) {pdir} to {pdir_tgt}")
        shutil.copytree(pdir, pdir_tgt)
        gdir_tgt = os.path.join(out_dir, self.file_data["build"]["dll"].replace(".dll", ""))
        self.log(f"Copying dir (2/2) {gdir} to {gdir_tgt}")
        shutil.copytree(gdir, gdir_tgt)
    
    def copy_brochure(self, output: str):
        """Copies brochure and moves it to out directory"""
        brochure_path = os.path.join(self.dir, self.file_data["brochure"])
        out_dir = os.path.join(output, f"{self.file_data["name"]}.{self.arch}")
        final_dest = os.path.join(out_dir, f"{self.file_data["name"]}.readme.md")

        self.log(f"Copying brochure {brochure_path} to {final_dest}")
        shutil.copyfile(brochure_path, final_dest)

class ModuleBuilder:
    def __init__(self, dir, arch, platform, output_dir):
        """Fetches every folder in the specified directory"""

        self.arch = arch
        self.platform = platform
        self.dir = dir
        self.output_dir = output_dir

        # Fetch every folder in dir
        self.dirs = os.listdir(dir)

    def build_all(self):
        for module_dir in self.dirs:
            path = os.path.join(self.dir, module_dir)
            luxmodjson_path = os.path.join(path, LUXMOD_FILENAME)
            if os.path.exists(luxmodjson_path):
                print("[*]Building [{}] \t => \t ...".format(module_dir))
                module_builder = BuildSystem(path, self.arch, self.platform)
                if module_builder.build() == 0:
                    module_builder.prepare_export(self.output_dir)
                    module_builder.copy_brochure(self.output_dir)
            else:
                print("[ ]Skipping [{}] \t => \t err: {} is missing.".format(module_dir, LUXMOD_FILENAME))

def main(args=sys.argv):
    print(f"Building architecture : [{args[1]}] ...")

    # Check arguments
    if len(args[1:]) != 2:
        exit(ERR_RET_CODE)
    
    platform = args[1]
    try:
        arch = PLATFORM_TO_ARCH[platform]
    except:
        exit(ERR_PLATFORM_NOT_SUPPORTED)

    dir = args[2]
    output_dir = "out"

    if os.path.exists(output_dir) == False:
        print(f"Creating directory : {output_dir}...")
        os.mkdir(output_dir)

    print(f"Saving builds in {output_dir}...")
    
    mbuilder = ModuleBuilder(dir, arch, platform, output_dir)
    mbuilder.build_all()

    os.system(f"ls {output_dir}")

if __name__ == '__main__':
    main()
