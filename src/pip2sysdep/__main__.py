import sys
import subprocess
import re
import tomllib
from . import Pip2SysDep

def extract_pkg_name(line):
    # Skip VCS, URLs, editable installs, and local paths
    vcs_prefixes = ('git+', 'http://', 'https://', 'ssh://', '-e', './', '../', '/')
    if line.startswith(vcs_prefixes):
        return None
    # Remove comments and environment markers
    line = line.split('#', 1)[0].split(';', 1)[0].strip()
    if not line:
        return None
    # Remove extras and version specifiers (e.g. foo[bar]==1.2.3)
    pkg = re.split(r'[=<>!~\[ ]', line, 1)[0].strip()
    if pkg:
        return pkg
    return None

def parse_requirements_file(filename):
    pkgs = []
    with open(filename, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            pkg = extract_pkg_name(line)
            if pkg:
                pkgs.append(pkg)
    return pkgs

def parse_pyproject_toml(filename):
    pkgs = []
    with open(filename, 'rb') as f:
        data = tomllib.load(f)
    # PEP 621
    project = data.get('project', {})
    if 'dependencies' in project:
        for dep in project['dependencies']:
            pkg = extract_pkg_name(dep)
            if pkg:
                pkgs.append(pkg)
    # Poetry
    poetry_deps = data.get('tool', {}).get('poetry', {}).get('dependencies', {})
    for pkg in poetry_deps:
        if pkg.lower() == 'python':
            continue
        pkgs.append(pkg)
    # PDM
    pdm_deps = data.get('tool', {}).get('pdm', {}).get('dependencies', {})
    for pkg in pdm_deps:
        pkgs.append(pkg)
    return pkgs

HELP_MESSAGE = '''\
Usage: python3 -m pip2sysdep [OPTIONS] <pip-package> [<pip-package> ...]

Options:
  --help                Show this help message and exit
  --local[=file]        Use local mapping files (default: online lookup). If a file is given (with =), use it as the mapping TOML.
  --install             Run the system package install command
  --separator=space|newline
                        Output separator for system packages (default: newline)
  --txt <file>          Read Python package names from requirements.txt-style file
  --toml <file>         Read Python package names from pyproject.toml (PEP 621, Poetry, or PDM)
  --show-input          Print the list of Python package names parsed from input and exit

You can combine --txt/--toml with additional package names on the command line.
Only one of --txt or --toml can be used at a time.
'''

def main():
    args = sys.argv[1:]
    if '--help' in args:
        print(HELP_MESSAGE)
        sys.exit(0)
    use_local = False
    local_file = None
    separator = '\n'  # default
    do_install = False
    show_input = False
    txt_file = None
    toml_file = None
    # Parse --local, --separator, --install, --txt, --toml, --show-input flags
    new_args = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == '--local':
            use_local = True
        elif arg.startswith('--local='):
            use_local = True
            local_file = arg.split('=', 1)[1]
        elif arg == '--install':
            do_install = True
        elif arg == '--show-input':
            show_input = True
        elif arg.startswith('--separator='):
            val = arg.split('=', 1)[1].strip().lower()
            if val == 'space':
                separator = ' '
            elif val == 'newline':
                separator = '\n'
            else:
                print("Unknown separator: {} (use 'space' or 'newline')".format(val), file=sys.stderr)
                sys.exit(1)
        elif arg == '--txt' and i + 1 < len(args):
            txt_file = args[i + 1]
            i += 1
        elif arg == '--toml' and i + 1 < len(args):
            toml_file = args[i + 1]
            i += 1
        else:
            new_args.append(arg)
        i += 1
    if txt_file and toml_file:
        print("Cannot use both --txt and --toml at the same time.", file=sys.stderr)
        sys.exit(1)
    pkgs = []
    if txt_file:
        pkgs.extend(parse_requirements_file(txt_file))
    if toml_file:
        pkgs.extend(parse_pyproject_toml(toml_file))
    pkgs.extend(new_args)
    if not pkgs:
        print(HELP_MESSAGE, file=sys.stderr)
        sys.exit(1)
    # Deduplicate while preserving order
    seen = set()
    pkgs = [x for x in pkgs if not (x in seen or seen.add(x))]
    if show_input:
        for pkg in pkgs:
            print(pkg)
        sys.exit(0)
    if use_local and local_file:
        # Patch Pip2SysDep._get_local_content to load from the given file
        def _get_local_content(self):
            with open(local_file, 'rb') as f:
                return tomllib.load(f)
        Pip2SysDep._get_local_content = _get_local_content
    source = Pip2SysDep.Source.LOCAL if use_local else Pip2SysDep.Source.REPO
    converter = Pip2SysDep(source=source)
    result = converter.convert_list(pkgs)
    pkgs_out = result['all']
    if do_install:
        # Get the install command and run it
        cmd = converter.get_install_command({'all': pkgs_out})
        print(f"Running: {cmd}")
        try:
            proc = subprocess.run(cmd, shell=True)
            sys.exit(proc.returncode)
        except Exception as e:
            print(f"Error running install command: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(separator.join(pkgs_out))

if __name__ == "__main__":
    main()
