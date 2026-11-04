"""Record what this Python process reads, so tests can be selected by it.

Test selection (``fantasy_engine.testing``) puts this directory first on
PYTHONPATH and names a record directory in FE_TESTSEL_RECORD_DIR.  Every
Python process a run starts then imports this module at startup, opens a
record file of its own in that directory, and appends one JSON line for each
new thing Python's audit hooks show it doing: opening, writing, renaming or
removing files, listing directories, importing modules, starting programs
and reaching the network.  The runner merges the files after the run.

Without FE_TESTSEL_RECORD_DIR the module only hands over to the next
``sitecustomize`` on the path, which this one would otherwise hide.
"""

import os
import sys

RECORD_ENV = "FE_TESTSEL_RECORD_DIR"
HERE = os.path.dirname(os.path.abspath(__file__))

_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
_PROGRAM_EVENTS = frozenset(
    ("subprocess.Popen", "os.exec", "os.posix_spawn", "os.spawn", "os.system")
)
# Events that change files, with the positions of the paths they change.
_WRITE_EVENTS = {
    "os.rename": (0, 1),
    "os.remove": (0,),
    "os.rmdir": (0,),
    "os.mkdir": (0,),
    "os.truncate": (0,),
    "os.link": (1,),
    "os.symlink": (1,),
}
_NETWORK_EVENTS = frozenset(("socket.connect", "socket.sendto", "socket.getaddrinfo"))
_EVENTS = (
    frozenset(("open", "os.listdir", "os.scandir", "import", "ctypes.dlopen",
               "sqlite3.connect"))
    | _PROGRAM_EVENTS | frozenset(_WRITE_EVENTS) | _NETWORK_EVENTS
)
_LOCAL_HOSTS = frozenset(("127.0.0.1", "::1", "localhost", "", "0.0.0.0", "::"))

# Programs that only start another program; the one they start decides.
# Each maps to the options that take a separate argument, and to how many
# positional arguments come before the program (timeout's duration, for one).
_WRAPPERS = {
    "env": (frozenset(("-u", "--unset", "-C", "--chdir")), 0),
    "nice": (frozenset(("-n", "--adjustment")), 0),
    "ionice": (frozenset(("-c", "--class", "-n", "--classdata")), 0),
    "nohup": (frozenset(), 0),
    "setsid": (frozenset(), 0),
    "stdbuf": (frozenset(("-i", "-o", "-e")), 0),
    "timeout": (frozenset(("-s", "--signal", "-k", "--kill-after")), 1),
    "taskset": (frozenset(), 1),
    "chrt": (frozenset(), 1),
}


def _is_python(program, base):
    if base.startswith("python") and base[6:].replace(".", "").isdigit():
        return True
    if base == "python":
        return True
    try:
        return os.path.realpath(program) == os.path.realpath(sys.executable)
    except (OSError, ValueError):
        return False


def _isolating(argv):
    """Whether a Python command line skips site or ignores the environment."""
    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg in ("-m", "-c") or not arg.startswith("-") or arg == "-":
            return False
        if arg in ("-W", "-X"):
            i += 2
            continue
        if not (arg.startswith("--") or arg[1:2] in ("W", "X")):
            if any(flag in arg for flag in "ISE"):
                return True
        i += 1
    return False


def _unwrap(base, rest, env):
    """The command a wrapper starts and its environment, or None if unknown."""
    with_argument, positionals = _WRAPPERS[base]
    env = dict(env)
    i = 0
    while i < len(rest) and rest[i].startswith("-") and rest[i] != "-":
        arg = rest[i]
        if base == "env" and arg in ("-i", "--ignore-environment", "-S",
                                     "--split-string"):
            return None
        if arg in with_argument:
            i += 2
        else:
            i += 1
    if base == "env":
        while i < len(rest) and "=" in rest[i]:
            name, _, value = rest[i].partition("=")
            env[name] = value
            i += 1
    i += positionals
    if i >= len(rest):
        return None
    return rest[i:], env


class _Recorder:
    def __init__(self, record_dir):
        import _thread
        import json
        import time

        self._json = json
        self._time = time
        self._get_ident = _thread.get_ident
        self.record_dir = record_dir
        self.seen = set()
        self.pending = []
        self.busy = set()
        self.fd = -1
        self.open_record()

    def open_record(self):
        os.makedirs(self.record_dir, exist_ok=True)
        name = "%d-%d.jsonl" % (os.getpid(), self._time.monotonic_ns())
        self.fd = os.open(
            os.path.join(self.record_dir, name),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND | os.O_CLOEXEC,
            0o600,
        )
        self.seen = set()
        self.line({
            "t": "proc",
            "pid": os.getpid(),
            "ppid": os.getppid(),
            "argv": list(getattr(sys, "orig_argv", sys.argv)),
            "exe": sys.executable,
            "version": sys.version,
            "cwd": os.getcwd(),
            "env": dict(os.environ),
        })

    def after_fork(self):
        self.busy = set()
        self.open_record()

    def line(self, item):
        data = self._json.dumps(item, separators=(",", ":"), default=str) + "\n"
        os.write(self.fd, data.encode("utf-8", "surrogateescape"))

    def emit(self, kind, path, **extra):
        key = (kind, path, extra.get("why"))
        if key in self.seen:
            return
        self.seen.add(key)
        item = {"t": kind, "p": path}
        item.update(extra)
        self.line(item)

    def hook(self, event, args):
        if event not in _EVENTS:
            return
        ident = self._get_ident()
        if ident in self.busy:
            return
        self.busy.add(ident)
        try:
            self.handle(event, args)
        except Exception as exc:  # never break the program being recorded
            try:
                self.emit("err", "%s: %r" % (event, exc))
            except Exception:
                pass
        finally:
            self.busy.discard(ident)

    @staticmethod
    def path_of(value):
        if value is None or isinstance(value, int):
            return None
        value = os.fsdecode(os.fspath(value))
        return os.path.abspath(value or os.curdir)

    def handle(self, event, args):
        if self.pending:
            self.resolve_pending()
        if event == "open":
            self.on_open(*args[:3])
        elif event in ("os.listdir", "os.scandir"):
            path = args[0] if args else None
            if isinstance(path, int):
                return
            path = self.path_of(path if path is not None else os.curdir)
            self.emit(self.listing_kind(), path)
        elif event == "import":
            name = args[0]
            self.emit("m", name)
            self.pending.append(name)
        elif event in _WRITE_EVENTS:
            for index in _WRITE_EVENTS[event]:
                value = args[index] if index < len(args) else None
                if isinstance(value, (str, bytes, os.PathLike)):
                    self.emit("w", self.path_of(value))
        elif event == "ctypes.dlopen":
            name = args[0]
            if isinstance(name, (str, bytes)) and os.path.isabs(os.fsdecode(name)):
                self.emit("r", os.fsdecode(name))
        elif event == "sqlite3.connect":
            database = args[0]
            if isinstance(database, (str, bytes, os.PathLike)):
                text = os.fsdecode(os.fspath(database))
                if text and text != ":memory:" and not text.startswith("file:"):
                    self.emit("r", self.path_of(text))
        elif event in _PROGRAM_EVENTS:
            self.on_program(event, args)
        elif event in _NETWORK_EVENTS:
            self.on_network(event, args)

    def on_open(self, path, mode, flags):
        path = self.path_of(path)
        if path is None:
            return
        writing = bool(isinstance(flags, int) and flags & _WRITE_FLAGS)
        if isinstance(mode, str) and any(c in mode for c in "wax+"):
            writing = True
        if path.endswith(".pyc"):
            folder, base = os.path.split(path)
            if os.path.basename(folder) == "__pycache__":
                if writing:
                    return
                source = os.path.join(
                    os.path.dirname(folder), base.split(".", 1)[0] + ".py"
                )
                if os.path.exists(source):
                    path = source
        if path == "/dev/net/tun":
            self.emit("x", path, why="network device")
        self.emit("w" if writing else "r", path)

    def listing_kind(self):
        """Who listed a directory decides which of its entries matter.

        The import system's finder ("i") looks only for entries named like a
        module being imported, and importlib.metadata ("e") only for package
        metadata folders; any other listing ("d") counts in full.
        """
        try:
            frame = sys._getframe(3)
        except ValueError:
            return "d"
        for _ in range(3):
            if frame is None:
                break
            code = frame.f_code
            if code.co_name == "_fill_cache":
                return "i"
            if code.co_name == "children" and "metadata" in code.co_filename:
                return "e"
            frame = frame.f_back
        return "d"

    def resolve_pending(self):
        pending, self.pending = self.pending, []
        for name in pending:
            module = sys.modules.get(name)
            if module is None:
                continue
            origin = getattr(module, "__file__", None)
            if isinstance(origin, str) and origin:
                self.emit("r", os.path.abspath(origin))

    def on_program(self, event, args):
        if event == "os.system":
            self.emit("x", "os.system", why=str(args[0])[:200])
            return
        if event == "subprocess.Popen":
            executable, argv, _cwd, env = args[:4]
        elif event == "os.spawn":
            _mode, executable, argv, env = args[:4]
        else:
            executable, argv, env = args[:3]
        if isinstance(argv, (str, bytes)):
            self.emit("x", os.fsdecode(argv)[:200], why="shell command")
            return
        argv = [os.fsdecode(a) if isinstance(a, bytes) else str(a) for a in argv]
        program = executable if executable is not None else (argv[0] if argv else "")
        program = os.fsdecode(program) if isinstance(program, bytes) else str(program)
        self.classify(program, argv, dict(env) if env is not None else dict(os.environ))

    def classify(self, program, argv, env):
        base = os.path.basename(program)
        if base in _WRAPPERS:
            inner = _unwrap(base, argv[1:], env)
            if inner is None:
                self.emit("x", program, why="wrapper with an unknown command")
                return
            inner_argv, inner_env = inner
            self.classify(inner_argv[0], inner_argv, inner_env)
            return
        if not _is_python(program, base):
            self.emit("x", program, why="not Python")
            return
        paths = env.get("PYTHONPATH", "").split(os.pathsep)
        if env.get(RECORD_ENV) != self.record_dir or HERE not in paths:
            self.emit("x", program, why="Python without the recorder")
        elif _isolating(argv):
            self.emit("x", program, why="Python that skips site or the environment")
        else:
            self.emit("c", program)

    def on_network(self, event, args):
        if event == "socket.getaddrinfo":
            host = args[0]
        else:
            address = args[1]
            if not isinstance(address, tuple):
                return  # a Unix socket path or a raw address
            host = address[0]
        if isinstance(host, bytes):
            host = host.decode("ascii", "replace")
        if not isinstance(host, str) or host in _LOCAL_HOSTS or host.startswith("127."):
            return
        self.emit("x", "network:%s" % host, why="reaches the network")

    def finish(self):
        self.busy.add(self._get_ident())
        try:
            self.resolve_pending()
            for module in list(sys.modules.values()):
                origin = getattr(module, "__file__", None)
                if isinstance(origin, str) and origin:
                    self.emit("r", os.path.abspath(origin))
            self.line({"t": "end"})
        except Exception:
            pass


def _install():
    record_dir = os.environ.get(RECORD_ENV)
    if not record_dir:
        return
    recorder = _Recorder(record_dir)
    sys.addaudithook(recorder.hook)
    os.register_at_fork(after_in_child=recorder.after_fork)
    # Modules imported before the hook existed still count as imports, and
    # the folders the import system listed for them are listed again, now
    # under the hook, the next time an import looks there.
    for name in list(sys.modules):
        recorder.emit("m", name)
    import importlib

    importlib.invalidate_caches()
    import atexit

    atexit.register(recorder.finish)


def _chain():
    """Run the next sitecustomize on the path, which this module hides."""
    import importlib.machinery
    import importlib.util

    paths = [p for p in sys.path if os.path.abspath(p or os.curdir) != HERE]
    spec = importlib.machinery.PathFinder.find_spec("sitecustomize", paths)
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


_install()
_chain()
