from __future__ import annotations

"""
Synchronous AF_UNIX socket compatibility layer.

Use this module when you want ordinary/blocking socket-style Unix-domain socket
APIs, not asyncio stream APIs.

Typical usage:

    import af_unix_socket_compat as socket

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind("./server.sock")
    srv.listen(5)
    conn, addr = srv.accept()

The module is intentionally shaped like the stdlib socket module for AF_UNIX
use-cases:

    socket(AF_UNIX, SOCK_STREAM)
    create_connection(path, timeout=None)
    create_server(path, backlog=100, cleanup_socket=False)
    install()

On POSIX platforms it delegates to the stdlib socket implementation.  On modern
Windows/Python where socket.AF_UNIX already works, it delegates to the stdlib
implementation too.  A ctypes/Winsock fallback is included for environments
where AF_UNIX is available in Winsock but not exposed by Python's socket module.

Windows limitations:
- Only SOCK_STREAM is supported by the fallback.
- Linux abstract namespace addresses are not supported on Windows.
- makefile() is available only when the native Python socket backend is used.
"""

import errno
import os
import select
import socket as _socket_module
import sys
import time
from typing import Any

_ORIGINAL_SOCKET_FACTORY = _socket_module.socket
_IS_WINDOWS = sys.platform == "win32"
_NATIVE_AF_UNIX = getattr(_socket_module, "AF_UNIX", 1)
AF_UNIX = _NATIVE_AF_UNIX
AF_LOCAL = AF_UNIX
SOCK_STREAM = _socket_module.SOCK_STREAM
SOL_SOCKET = _socket_module.SOL_SOCKET
SO_ERROR = _socket_module.SO_ERROR
SHUT_RD = _socket_module.SHUT_RD
SHUT_WR = _socket_module.SHUT_WR
SHUT_RDWR = _socket_module.SHUT_RDWR
error = _socket_module.error
timeout = _socket_module.timeout

__all__ = [
    "AF_UNIX",
    "AF_LOCAL",
    "SOCK_STREAM",
    "SOL_SOCKET",
    "SO_ERROR",
    "SHUT_RD",
    "SHUT_WR",
    "SHUT_RDWR",
    "error",
    "timeout",
    "socket",
    "UnixSocket",
    "create_connection",
    "create_server",
    "unlink_socket",
    "install",
]


def __getattr__(name: str) -> Any:
    """Expose the rest of stdlib socket's constants/functions lazily."""
    return getattr(_socket_module, name)


def _path_bytes(path: os.PathLike[str] | str | bytes) -> bytes:
    if isinstance(path, bytes):
        raw = path
    else:
        raw = os.fsencode(os.fspath(path))
    if b"\x00" in raw:
        raise ValueError("AF_UNIX path must not contain NUL bytes on Windows")
    if len(raw) >= 108:
        raise OSError(errno.ENAMETOOLONG, f"AF_UNIX path is too long: {len(raw)} bytes")
    return raw


def unlink_socket(path: os.PathLike[str] | str | bytes) -> None:
    """Best-effort unlink helper matching common Unix-domain socket setup code."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        return


def _native_af_unix_works() -> bool:
    if not hasattr(_socket_module, "AF_UNIX"):
        return False
    try:
        s = _ORIGINAL_SOCKET_FACTORY(_socket_module.AF_UNIX, _socket_module.SOCK_STREAM)
    except OSError:
        return False
    else:
        s.close()
        return True


_USE_NATIVE = (not _IS_WINDOWS) or _native_af_unix_works()


class _NativeUnixSocket:
    """Thin delegating wrapper around a real Python socket.socket object."""

    def __init__(self, sock: _socket_module.socket):
        self._sock = sock

    def __getattr__(self, name: str) -> Any:
        return getattr(self._sock, name)

    def __enter__(self) -> "_NativeUnixSocket":
        self._sock.__enter__()
        return self

    def __exit__(self, *args: Any) -> Any:
        return self._sock.__exit__(*args)

    def fileno(self) -> int:
        return self._sock.fileno()

    def bind(self, address: os.PathLike[str] | str | bytes) -> None:
        self._sock.bind(os.fspath(address) if not isinstance(address, bytes) else address)

    def connect(self, address: os.PathLike[str] | str | bytes) -> None:
        self._sock.connect(os.fspath(address) if not isinstance(address, bytes) else address)

    def accept(self) -> tuple["_NativeUnixSocket", Any]:
        conn, addr = self._sock.accept()
        return _NativeUnixSocket(conn), addr

    def close(self) -> None:
        self._sock.close()

    def detach(self) -> int:
        return self._sock.detach()

    @property
    def family(self) -> int:
        return self._sock.family

    @property
    def type(self) -> int:
        return self._sock.type

    @property
    def proto(self) -> int:
        return self._sock.proto


UnixSocket = _NativeUnixSocket


# ---------------------------------------------------------------------------
# Windows ctypes fallback.
# ---------------------------------------------------------------------------

if _IS_WINDOWS and not _USE_NATIVE:
    import ctypes
    import ctypes.wintypes as wintypes

    AF_UNIX = 1
    AF_LOCAL = AF_UNIX
    UNIX_PATH_MAX = 108

    WSAEWOULDBLOCK = 10035
    WSAEINPROGRESS = 10036
    WSAEALREADY = 10037
    WSAEINVAL = 10022
    WSAECONNRESET = 10054
    WSAENOTCONN = 10057

    FIONBIO = 0x8004667E
    INVALID_SOCKET = -1
    SOCKET_ERROR = -1

    SOCKET_T = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32
    INVALID_SOCKET_VALUE = (1 << (ctypes.sizeof(SOCKET_T) * 8)) - 1

    class SockaddrUn(ctypes.Structure):
        _fields_ = [
            ("sun_family", wintypes.USHORT),
            ("sun_path", ctypes.c_char * UNIX_PATH_MAX),
        ]

    class WSAData(ctypes.Structure):
        _fields_ = [
            ("wVersion", wintypes.WORD),
            ("wHighVersion", wintypes.WORD),
            ("szDescription", ctypes.c_char * 257),
            ("szSystemStatus", ctypes.c_char * 129),
            ("iMaxSockets", wintypes.USHORT),
            ("iMaxUdpDg", wintypes.USHORT),
            ("lpVendorInfo", ctypes.c_char_p),
        ]

    ws2_32 = ctypes.WinDLL("ws2_32", use_last_error=True)

    ws2_32.WSAStartup.restype = ctypes.c_int
    ws2_32.WSAStartup.argtypes = (wintypes.WORD, ctypes.POINTER(WSAData))

    ws2_32.WSAGetLastError.restype = ctypes.c_int
    ws2_32.WSAGetLastError.argtypes = ()

    ws2_32.socket.restype = SOCKET_T
    ws2_32.socket.argtypes = (ctypes.c_int, ctypes.c_int, ctypes.c_int)

    ws2_32.closesocket.restype = ctypes.c_int
    ws2_32.closesocket.argtypes = (SOCKET_T,)

    ws2_32.bind.restype = ctypes.c_int
    ws2_32.bind.argtypes = (SOCKET_T, ctypes.POINTER(SockaddrUn), ctypes.c_int)

    ws2_32.connect.restype = ctypes.c_int
    ws2_32.connect.argtypes = (SOCKET_T, ctypes.POINTER(SockaddrUn), ctypes.c_int)

    ws2_32.listen.restype = ctypes.c_int
    ws2_32.listen.argtypes = (SOCKET_T, ctypes.c_int)

    ws2_32.accept.restype = SOCKET_T
    ws2_32.accept.argtypes = (SOCKET_T, ctypes.POINTER(SockaddrUn), ctypes.POINTER(ctypes.c_int))

    ws2_32.recv.restype = ctypes.c_int
    ws2_32.recv.argtypes = (SOCKET_T, ctypes.c_void_p, ctypes.c_int, ctypes.c_int)

    ws2_32.send.restype = ctypes.c_int
    ws2_32.send.argtypes = (SOCKET_T, ctypes.c_void_p, ctypes.c_int, ctypes.c_int)

    ws2_32.shutdown.restype = ctypes.c_int
    ws2_32.shutdown.argtypes = (SOCKET_T, ctypes.c_int)

    ws2_32.ioctlsocket.restype = ctypes.c_int
    ws2_32.ioctlsocket.argtypes = (SOCKET_T, ctypes.c_long, ctypes.POINTER(ctypes.c_ulong))

    ws2_32.getsockopt.restype = ctypes.c_int
    ws2_32.getsockopt.argtypes = (
        SOCKET_T,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int),
    )

    ws2_32.setsockopt.restype = ctypes.c_int
    ws2_32.setsockopt.argtypes = (
        SOCKET_T,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_int,
    )

    _wsa_started = False

    def _ensure_winsock() -> None:
        global _wsa_started
        if _wsa_started:
            return
        data = WSAData()
        rc = ws2_32.WSAStartup(0x0202, ctypes.byref(data))
        if rc:
            raise OSError(rc, "WSAStartup failed")
        _wsa_started = True

    def _last_error() -> int:
        return int(ws2_32.WSAGetLastError())

    def _raise_socket_error(err: int | None = None) -> None:
        if err is None:
            err = _last_error()
        # socket.error/OSError on Windows conventionally stores the WSA error.
        raise OSError(err, os.strerror(err) if err < 10000 else f"Winsock error {err}")

    def _invalid_socket(value: int) -> bool:
        return value in (-1, INVALID_SOCKET_VALUE)

    def _sockaddr(path: os.PathLike[str] | str | bytes) -> SockaddrUn:
        raw = _path_bytes(path)
        addr = SockaddrUn()
        addr.sun_family = AF_UNIX
        addr.sun_path = raw
        return addr

    def _deadline(timeout_value: float | None) -> float | None:
        if timeout_value is None:
            return None
        if timeout_value < 0:
            raise ValueError("Timeout value out of range")
        return time.monotonic() + timeout_value

    def _remaining(deadline: float | None) -> float | None:
        if deadline is None:
            return None
        rem = deadline - time.monotonic()
        if rem <= 0:
            raise timeout("timed out")
        return rem

    class _CtypesUnixSocket:
        def __init__(
            self,
            family: int = AF_UNIX,
            type: int = SOCK_STREAM,
            proto: int = 0,
            fileno: int | None = None,
        ) -> None:
            if family not in (AF_UNIX, AF_LOCAL):
                raise OSError(errno.EAFNOSUPPORT, "only AF_UNIX is supported by this fallback")
            if type != SOCK_STREAM:
                raise OSError(errno.EPROTONOSUPPORT, "only SOCK_STREAM is supported by this fallback")
            _ensure_winsock()
            if fileno is None:
                handle = int(ws2_32.socket(AF_UNIX, type, proto))
                if _invalid_socket(handle):
                    _raise_socket_error()
            else:
                handle = int(fileno)
            self._handle = handle
            self._family = family
            self._type = type
            self._proto = proto
            self._timeout: float | None = _socket_module.getdefaulttimeout()
            self._blocking = self._timeout != 0.0
            self._closed = False
            self._sockname: os.PathLike[str] | str | bytes | None = None
            self._peername: os.PathLike[str] | str | bytes | None = None
            if self._timeout == 0.0:
                self.setblocking(False)

        def __enter__(self) -> "_CtypesUnixSocket":
            return self

        def __exit__(self, *args: Any) -> None:
            self.close()

        @property
        def family(self) -> int:
            return self._family

        @property
        def type(self) -> int:
            return self._type

        @property
        def proto(self) -> int:
            return self._proto

        def fileno(self) -> int:
            return -1 if self._closed else self._handle

        def detach(self) -> int:
            if self._closed:
                raise OSError(errno.EBADF, "socket is closed")
            handle = self._handle
            self._closed = True
            self._handle = -1
            return handle

        def _check_open(self) -> None:
            if self._closed:
                raise OSError(errno.EBADF, "socket is closed")

        def setblocking(self, flag: bool) -> None:
            self._check_open()
            mode = ctypes.c_ulong(0 if flag else 1)
            if ws2_32.ioctlsocket(self._handle, FIONBIO, ctypes.byref(mode)) != 0:
                _raise_socket_error()
            self._blocking = bool(flag)
            self._timeout = None if flag else 0.0

        def getblocking(self) -> bool:
            return self._blocking

        def settimeout(self, value: float | None) -> None:
            if value is not None:
                value = float(value)
                if value < 0:
                    raise ValueError("Timeout value out of range")
            self._timeout = value
            # Python sockets use non-blocking mode internally for finite timeouts.
            mode = ctypes.c_ulong(1 if value is not None else 0)
            if ws2_32.ioctlsocket(self._handle, FIONBIO, ctypes.byref(mode)) != 0:
                _raise_socket_error()
            self._blocking = value is None

        def gettimeout(self) -> float | None:
            return self._timeout

        def bind(self, address: os.PathLike[str] | str | bytes) -> None:
            self._check_open()
            addr = _sockaddr(address)
            if ws2_32.bind(self._handle, ctypes.byref(addr), ctypes.sizeof(addr)) != 0:
                _raise_socket_error()
            self._sockname = address

        def listen(self, backlog: int = 128) -> None:
            self._check_open()
            if ws2_32.listen(self._handle, int(backlog)) != 0:
                _raise_socket_error()

        def connect(self, address: os.PathLike[str] | str | bytes) -> None:
            self._check_open()
            addr = _sockaddr(address)
            rc = ws2_32.connect(self._handle, ctypes.byref(addr), ctypes.sizeof(addr))
            if rc == 0:
                self._peername = address
                return
            err = _last_error()
            if self._timeout == 0.0:
                if err in (WSAEWOULDBLOCK, WSAEINPROGRESS, WSAEALREADY, WSAEINVAL):
                    raise BlockingIOError(err, "operation would block")
                _raise_socket_error(err)
            if err not in (WSAEWOULDBLOCK, WSAEINPROGRESS, WSAEALREADY, WSAEINVAL):
                _raise_socket_error(err)

            deadline = _deadline(self._timeout)
            self._wait_writable(deadline)
            so_error = self.getsockopt(SOL_SOCKET, SO_ERROR)
            if so_error:
                _raise_socket_error(int(so_error))
            self._peername = address

        def connect_ex(self, address: os.PathLike[str] | str | bytes) -> int:
            try:
                self.connect(address)
                return 0
            except BlockingIOError as exc:
                return int(exc.errno or WSAEWOULDBLOCK)
            except OSError as exc:
                return int(exc.errno or SOCKET_ERROR)

        def accept(self) -> tuple["_CtypesUnixSocket", Any]:
            self._check_open()
            deadline = _deadline(self._timeout)
            while True:
                addr = SockaddrUn()
                addr_len = ctypes.c_int(ctypes.sizeof(addr))
                client = int(ws2_32.accept(self._handle, ctypes.byref(addr), ctypes.byref(addr_len)))
                if not _invalid_socket(client):
                    sock = _CtypesUnixSocket(AF_UNIX, SOCK_STREAM, 0, fileno=client)
                    sock.settimeout(self._timeout)
                    return sock, b""
                err = _last_error()
                if err != WSAEWOULDBLOCK:
                    _raise_socket_error(err)
                if self._timeout == 0.0:
                    raise BlockingIOError(err, "operation would block")
                self._wait_readable(deadline)

        def recv(self, bufsize: int, flags: int = 0) -> bytes:
            self._check_open()
            if bufsize < 0:
                raise ValueError("negative buffersize in recv")
            deadline = _deadline(self._timeout)
            while True:
                buf = ctypes.create_string_buffer(bufsize)
                n = ws2_32.recv(self._handle, buf, int(bufsize), int(flags))
                if n >= 0:
                    return bytes(buf.raw[:n])
                err = _last_error()
                if err == WSAEWOULDBLOCK:
                    if self._timeout == 0.0:
                        raise BlockingIOError(err, "operation would block")
                    self._wait_readable(deadline)
                    continue
                if err in (WSAECONNRESET, WSAENOTCONN):
                    return b""
                _raise_socket_error(err)

        def recv_into(self, buffer: Any, nbytes: int | None = None, flags: int = 0) -> int:
            data = self.recv(len(buffer) if nbytes is None else nbytes, flags)
            buffer[: len(data)] = data
            return len(data)

        def send(self, data: bytes | bytearray | memoryview, flags: int = 0) -> int:
            self._check_open()
            view = memoryview(data)
            deadline = _deadline(self._timeout)
            while True:
                # Copy to a stable ctypes buffer for the duration of send().
                chunk = view[: min(len(view), 1024 * 1024)]
                cbuf = (ctypes.c_char * len(chunk)).from_buffer_copy(chunk)
                n = ws2_32.send(self._handle, cbuf, len(chunk), int(flags))
                if n >= 0:
                    return int(n)
                err = _last_error()
                if err == WSAEWOULDBLOCK:
                    if self._timeout == 0.0:
                        raise BlockingIOError(err, "operation would block")
                    self._wait_writable(deadline)
                    continue
                if err in (WSAECONNRESET, WSAENOTCONN):
                    raise ConnectionResetError(err, "connection reset")
                _raise_socket_error(err)

        def sendall(self, data: bytes | bytearray | memoryview, flags: int = 0) -> None:
            view = memoryview(data)
            total = 0
            while total < len(view):
                sent = self.send(view[total:], flags)
                if sent == 0:
                    raise RuntimeError("socket connection broken")
                total += sent

        def sendmsg(self, *args: Any, **kwargs: Any) -> None:
            raise NotImplementedError("sendmsg is not implemented by the Windows fallback")

        def recvmsg(self, *args: Any, **kwargs: Any) -> None:
            raise NotImplementedError("recvmsg is not implemented by the Windows fallback")

        def shutdown(self, how: int) -> None:
            self._check_open()
            if ws2_32.shutdown(self._handle, int(how)) != 0:
                err = _last_error()
                if err not in (WSAENOTCONN,):
                    _raise_socket_error(err)

        def close(self) -> None:
            if self._closed:
                return
            self._closed = True
            if self._handle != -1:
                ws2_32.closesocket(self._handle)
            self._handle = -1

        def getsockname(self) -> Any:
            return self._sockname if self._sockname is not None else b""

        def getpeername(self) -> Any:
            if self._peername is None:
                raise OSError(errno.ENOTCONN, "socket is not connected")
            return self._peername

        def getsockopt(self, level: int, optname: int, buflen: int | None = None) -> Any:
            self._check_open()
            if buflen is None:
                value = ctypes.c_int()
                value_len = ctypes.c_int(ctypes.sizeof(value))
                rc = ws2_32.getsockopt(
                    self._handle,
                    int(level),
                    int(optname),
                    ctypes.byref(value),
                    ctypes.byref(value_len),
                )
                if rc != 0:
                    _raise_socket_error()
                return int(value.value)
            buf = ctypes.create_string_buffer(int(buflen))
            value_len = ctypes.c_int(int(buflen))
            rc = ws2_32.getsockopt(
                self._handle,
                int(level),
                int(optname),
                buf,
                ctypes.byref(value_len),
            )
            if rc != 0:
                _raise_socket_error()
            return bytes(buf.raw[: value_len.value])

        def setsockopt(self, level: int, optname: int, value: int | bytes | bytearray) -> None:
            self._check_open()
            if isinstance(value, int):
                cval = ctypes.c_int(value)
                ptr = ctypes.byref(cval)
                size = ctypes.sizeof(cval)
            else:
                cbuf = (ctypes.c_char * len(value)).from_buffer_copy(value)
                ptr = cbuf
                size = len(value)
            if ws2_32.setsockopt(self._handle, int(level), int(optname), ptr, size) != 0:
                _raise_socket_error()

        def makefile(self, *args: Any, **kwargs: Any) -> Any:
            raise NotImplementedError("makefile() is not implemented by the ctypes fallback; " "use recv/send or run on a Python build with native socket.AF_UNIX")

        def _wait_readable(self, deadline: float | None) -> None:
            rem = _remaining(deadline)
            readable, _, _ = select.select([self], [], [], rem)
            if not readable:
                raise timeout("timed out")

        def _wait_writable(self, deadline: float | None) -> None:
            rem = _remaining(deadline)
            _, writable, _ = select.select([], [self], [], rem)
            if not writable:
                raise timeout("timed out")

    UnixSocket = _CtypesUnixSocket


# ---------------------------------------------------------------------------
# Public factory/convenience APIs.
# ---------------------------------------------------------------------------


def socket(
    family: int = AF_UNIX,
    type: int = SOCK_STREAM,
    proto: int = 0,
    fileno: int | None = None,
) -> Any:
    """
    socket.socket-compatible factory.

    For AF_UNIX sockets this returns a compatibility object.  For all other
    families it returns the stdlib socket.socket object unchanged.
    """
    if family not in (AF_UNIX, AF_LOCAL):
        if fileno is None:
            return _ORIGINAL_SOCKET_FACTORY(family, type, proto)
        return _ORIGINAL_SOCKET_FACTORY(family, type, proto, fileno=fileno)

    if _USE_NATIVE:
        native_family = getattr(_socket_module, "AF_UNIX", AF_UNIX)
        if fileno is None:
            sock = _ORIGINAL_SOCKET_FACTORY(native_family, type, proto)
        else:
            try:
                sock = _ORIGINAL_SOCKET_FACTORY(native_family, type, proto, fileno=fileno)
            except TypeError:
                sock = _ORIGINAL_SOCKET_FACTORY(fileno=fileno)
        return _NativeUnixSocket(sock)

    return UnixSocket(family, type, proto, fileno=fileno)


def create_connection(
    address: os.PathLike[str] | str | bytes,
    timeout: float | None | object = _socket_module._GLOBAL_DEFAULT_TIMEOUT,
    source_address: Any = None,
) -> Any:
    """AF_UNIX equivalent of socket.create_connection(address, timeout=...)."""
    if source_address is not None:
        raise ValueError("source_address is not meaningful for AF_UNIX sockets")
    sock = socket(AF_UNIX, SOCK_STREAM)
    try:
        if timeout is not _socket_module._GLOBAL_DEFAULT_TIMEOUT:
            sock.settimeout(timeout)  # type: ignore[arg-type]
        sock.connect(address)
        return sock
    except BaseException:
        sock.close()
        raise


def create_server(
    address: os.PathLike[str] | str | bytes,
    *,
    backlog: int = 100,
    cleanup_socket: bool = False,
) -> Any:
    """
    Create, bind, and listen on an AF_UNIX SOCK_STREAM server socket.

    cleanup_socket=True unlinks an existing path before bind, matching the
    common Unix-domain server pattern.  It does not unlink on close; call
    unlink_socket(path) explicitly when you want post-close cleanup.
    """
    if cleanup_socket:
        unlink_socket(address)
    srv = socket(AF_UNIX, SOCK_STREAM)
    try:
        srv.bind(address)
        srv.listen(backlog)
        return srv
    except BaseException:
        srv.close()
        raise


def install() -> None:
    """
    Install this compatibility factory into the stdlib socket module.

    This is optional and intentionally narrow: existing code can instead do
    `import af_unix_socket_compat as socket`.
    """
    if not hasattr(_socket_module, "AF_UNIX"):
        setattr(_socket_module, "AF_UNIX", AF_UNIX)
    if not hasattr(_socket_module, "AF_LOCAL"):
        setattr(_socket_module, "AF_LOCAL", AF_LOCAL)
    _socket_module.socket = socket  # type: ignore[assignment]
