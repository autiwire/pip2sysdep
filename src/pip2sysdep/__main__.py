import sys
import subprocess
from . import Pip2SysDep

def main():
    args = sys.argv[1:]
    use_online = False
    separator = '\n'  # default
    do_install = False
    # Parse --online, --separator, --install flags
    new_args = []
    for arg in args:
        if arg == '--online':
            use_online = True
        elif arg == '--install':
            do_install = True
        elif arg.startswith('--separator='):
            val = arg.split('=', 1)[1].strip().lower()
            if val == 'space':
                separator = ' '
            elif val == 'newline':
                separator = '\n'
            else:
                print("Unknown separator: {} (use 'space' or 'newline')".format(val), file=sys.stderr)
                sys.exit(1)
        else:
            new_args.append(arg)
    if not new_args:
        print("Usage: python3 -m pip2sysdep [--online] [--separator=space|newline] [--install] <pip-package> [<pip-package> ...]", file=sys.stderr)
        sys.exit(1)
    source = Pip2SysDep.Source.REPO if use_online else Pip2SysDep.Source.LOCAL
    converter = Pip2SysDep(source=source)
    result = converter.convert_list(new_args)
    pkgs = result['all']
    if do_install:
        # Get the install command and run it
        cmd = converter.get_install_command({'all': pkgs})
        print(f"Running: {cmd}")
        try:
            proc = subprocess.run(cmd, shell=True)
            sys.exit(proc.returncode)
        except Exception as e:
            print(f"Error running install command: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(separator.join(pkgs))

if __name__ == "__main__":
    main()
