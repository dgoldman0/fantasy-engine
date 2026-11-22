"""Record what this Python process reads, so tests can be selected by it.

Test selection (``fantasy_engine.testing``) puts this directory first on
PYTHONPATH and names a record directory in FE_TESTSEL_RECORD_DIR.  Every
Python process a run starts then imports this module at startup, opens a
record file of its own in that directory, and appends one JSON line for each
new thing Python's audit hooks show it doing: opening, writing, renaming or
removing files, listing directories, importing modules, starting programs
and reaching the network.  The runner merges the files after the run.

The audit hooks do not show which names the import system looks for in each
folder, and a folder's listing alone would make every file added there an
input.  The recorder therefore wraps the path finder's lookup in a folder
(``FileFinder.find_spec``) and notes each name looked up in each folder:
the folders before the one that resolved an import, where a new file would
shadow it, the resolving folder itself, and every folder an import that
failed searched.  This covers imports through ``importlib.import_module``,
which raise no audit event, as pytest's import of each test file does.
Imports made before this module loaded are noted as looked up in every
folder of the path at startup, the most they could have searched.  A path
entry that no lookup could use, such as a missing folder or a zip file, is
noted as a read, so that its appearance or change runs the unit again.

pytest's collection lists each folder on the way from its root to a test
file it was given, and builds and discards a collector for every other
entry there.  When every implementation of the hooks that build those
collectors is pytest's own, the result of the run depends only on the
names pytest checks by name in such a folder (``_PYTEST_CONSULTED``), so
the recorder notes that listing with those names only.  Any other listing,
such as a test's own glob, or pytest's collection of a folder it was given,
counts in full.

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

# The names pytest checks by name, through file tests no audit event shows,
# in a folder its collection lists on the way to a path it was given: the
# package marker that makes the folder a package and names the test module,
# the conftest it loads, and the configuration files and setup.py that
# decide its root folder and settings (_pytest/python.py, _pytest/config/
# __init__.py and findpaths.py in pytest 9).  Every other entry only gets a
# collector that pytest discards.
_PYTEST_CONSULTED = ("__init__.py", "conftest.py", "pytest.toml", ".pytest.toml",
                     "pytest.ini", ".pytest.ini", "pyproject.toml", "tox.ini",
                     "setup.cfg", "setup.py")
# The hooks pytest calls for each entry of such a folder.  A plugin or
# conftest that implements one may act on any entry, so the listing then
# counts in full.
_PYTEST_COLLECTION_HOOKS = ("pytest_ignore_collect", "pytest_collect_directory",
                            "pytest_collect_file", "pytest_pycollect_makemodule")

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


def _program_file(program, env, cwd):
    """The file a program name starts, as the system would find it, or None.

    A name with a folder in it is that path, taken from the folder the
    program starts in; a bare name is looked up along the PATH the program
    is given.  Symbolic links are followed, so the answer names the file
    whose content runs.
    """
    try:
        base = os.path.abspath(os.fsdecode(cwd)) if cwd else os.getcwd()
        if os.sep in program:
            candidates = [program]
        else:
            folders = env.get("PATH", os.defpath).split(os.pathsep)
            candidates = [os.path.join(folder or os.curdir, program)
                          for folder in folders]
        for candidate in candidates:
            path = os.path.join(base, candidate)
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return os.path.realpath(path)
    except (OSError, ValueError, TypeError):
        pass
    return None


def _named_files(arguments, cwd):
    """The existing files a program's arguments name.

    An argument names a file as a whole, or after an equals sign as in
    ``--config=FILE``; a relative name is taken from the folder the program
    starts in.  Folders, and files named inside a command string or a script,
    are not found here.
    """
    try:
        base = os.path.abspath(os.fsdecode(cwd)) if cwd else os.getcwd()
    except (OSError, ValueError, TypeError):
        return []
    found = []
    for argument in arguments:
        for text in dict.fromkeys((argument, argument.partition("=")[2])):
            if not text:
                continue
            try:
                path = os.path.abspath(os.path.join(base, text))
                if os.path.isfile(path):
                    found.append(path)
            except (OSError, ValueError):
                continue
    return found


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
        key = (kind, path) + tuple(
            (name, tuple(value) if isinstance(value, (list, tuple)) else value)
            for name, value in sorted(extra.items()))
        if key in self.seen:
            return
        self.seen.add(key)
        item = {"t": kind, "p": path}
        item.update(extra)
        self.line(item)

    def lookup(self, folder, fullname):
        """Note that the import system looked for FULLNAME in FOLDER."""
        try:
            if isinstance(folder, str) and isinstance(fullname, str):
                self.emit("l", folder, n=fullname.rpartition(".")[2])
        except Exception as exc:  # never break the import being made
            try:
                self.emit("err", "lookup: %r" % exc)
            except Exception:
                pass

    def startup_lookups(self):
        """Note the modules imported before the recorder as looked up in
        every folder they could have searched: the path at startup for a
        top-level module, its package's folders for a submodule."""
        startup = [self.path_of(entry) for entry in sys.path if isinstance(entry, str)]
        startup = [folder for folder in dict.fromkeys(startup) if os.path.isdir(folder)]
        for name in list(sys.modules):
            parent, _, tail = name.rpartition(".")
            if parent:
                folders = getattr(sys.modules.get(parent), "__path__", None) or []
                folders = [self.path_of(f) for f in folders if isinstance(f, str)]
                folders = [folder for folder in folders if os.path.isdir(folder)]
            else:
                folders = startup
            for folder in folders:
                self.emit("l", folder, n=tail)

    def unfound_entries(self):
        """Note each path entry the path finder consulted but could not
        search as a folder, such as a missing folder or a zip file: it is
        read as a whole, so its appearance or change counts."""
        from importlib.machinery import FileFinder

        for entry, finder in list(sys.path_importer_cache.items()):
            if isinstance(entry, str) and not isinstance(finder, FileFinder):
                self.emit("r", self.path_of(entry))

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
            kind = self.listing_kind()
            if kind == "p":
                self.emit(kind, path, n=list(_PYTEST_CONSULTED))
            else:
                self.emit(kind, path)
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

        The import system's finder ("i") looks only for the names its
        lookups note, and importlib.metadata ("e") only for package
        metadata folders.  pytest's collection of a folder on the way to a
        path it was given ("p") depends only on the names it checks there
        (see ``pytest_leads_through``).  Any other listing ("d") counts in
        full.
        """
        try:
            caller = frame = sys._getframe(3)
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
        if self.pytest_leads_through(caller):
            return "p"
        return "d"

    def pytest_leads_through(self, frame):
        """Whether FRAME is pytest listing a folder for its collection, the
        folder lies on the way to a path pytest was given without being
        one, and every implementation of the hooks pytest calls for the
        folder's entries is pytest's own.  The collector of each other entry
        is then built and discarded, and only the names in
        _PYTEST_CONSULTED decide the run.  A pytest whose collection works
        otherwise fails one of these tests, and its listings count in full.
        """
        code = frame.f_code
        if code.co_name != "scandir" or not code.co_filename.endswith(
                os.path.join("_pytest", "pathlib.py")):
            return False
        collect = frame.f_back
        if collect is None or collect.f_code.co_name != "collect":
            return False
        nodes = sys.modules.get("_pytest.nodes")
        directory = getattr(nodes, "Directory", None)
        node = collect.f_locals.get("self")
        if directory is None or not isinstance(node, directory):
            return False
        session = node.session
        leading = getattr(session, "_initialpaths_with_parents", None)
        given = getattr(session, "_initialpaths", None)
        if leading is None or given is None:
            return False
        if node.path not in leading or node.path in given:
            return False
        return self.pytest_hooks_are_its_own(session)

    @staticmethod
    def pytest_hooks_are_its_own(session):
        """Whether pytest's own modules implement every collection hook the
        session has registered so far; checked at each listing, since a
        plugin may register later."""
        hooks = session.config.pluginmanager.hook
        for name in _PYTEST_COLLECTION_HOOKS:
            caller = getattr(hooks, name, None)
            if caller is None:
                return False
            for implementation in caller.get_hookimpls():
                plugin = implementation.plugin
                module = (plugin.__name__ if isinstance(plugin, type(sys))
                          else type(plugin).__module__)
                if not (isinstance(module, str) and module.startswith("_pytest.")):
                    return False
        return True

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
        cwd = None
        if event == "subprocess.Popen":
            executable, argv, cwd, env = args[:4]
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
        self.classify(program, argv,
                      dict(env) if env is not None else dict(os.environ), cwd)

    def classify(self, program, argv, env, cwd=None):
        base = os.path.basename(program)
        if base in _WRAPPERS:
            inner = _unwrap(base, argv[1:], env)
            if inner is None:
                self.emit("x", program, why="wrapper with an unknown command")
                return
            inner_argv, inner_env = inner
            self.classify(inner_argv[0], inner_argv, inner_env, cwd)
            return
        if not _is_python(program, base):
            # What the program reads by itself goes unrecorded.  The file it
            # runs is noted, so that a run whose programs all come from
            # folders its repository vouches for can still be resumed.
            self.emit("x", program, why="not Python",
                      file=_program_file(program, env, cwd))
            # The files its arguments name are read on its behalf.
            for path in _named_files(argv[1:], cwd):
                self.emit("r", path)
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
            self.unfound_entries()
            self.line({"t": "end"})
        except Exception:
            pass


def _watch_lookups(recorder):
    """Wrap the path finder's lookup in a folder so that each one is noted,
    whichever import made it."""
    from importlib.machinery import FileFinder

    original = FileFinder.find_spec

    def find_spec(self, fullname, target=None):
        try:
            return original(self, fullname, target)
        finally:
            recorder.lookup(self.path, fullname)

    find_spec.__wrapped__ = original
    find_spec.__doc__ = original.__doc__
    FileFinder.find_spec = find_spec


def _install():
    record_dir = os.environ.get(RECORD_ENV)
    if not record_dir:
        return
    recorder = _Recorder(record_dir)
    sys.addaudithook(recorder.hook)
    os.register_at_fork(after_in_child=recorder.after_fork)
    _watch_lookups(recorder)
    # Modules imported before the hook existed still count as imports, and
    # as looked up wherever they could have been; the folders the import
    # system listed for them are listed again, now under the hook, the next
    # time an import looks there.
    for name in list(sys.modules):
        recorder.emit("m", name)
    recorder.startup_lookups()
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
