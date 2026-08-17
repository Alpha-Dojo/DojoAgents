"""
asyncio AF_UNIX compatibility helpers.

This module exposes a small API compatible with the high-level Unix-domain
socket helpers from asyncio:

    await open_unix_connection(path, ...)
    await start_unix_server(callback, path, ...)
    await create_unix_connection(protocol_factory, path, ...)
    await create_unix_server(protocol_factory, path, ...)

On POSIX platforms the functions delegate directly to asyncio's native
AF_UNIX implementation.  On Windows they use Winsock AF_UNIX plus
WSAEventSelect/IOCP handle waits so the API can be used with the default
ProactorEventLoop.

Notes / intentional limits of the Windows fallback:
- SSL over AF_UNIX is not implemented here.
- Windows AF_UNIX does not support Linux abstract namespace addresses.
- The returned server is asyncio.Server-like, not an actual asyncio.Server.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import socket
import sys
from typing import Any, Callable, Iterable

_DEFAULT_LIMIT = 2**16
_IS_WINDOWS = sys.platform == "win32"

__all__ = [
    "open_unix_connection",
    "start_unix_server",
    "create_unix_connection",
    "create_unix_server",
    "install",
]


# ---------------------------------------------------------------------------
# POSIX implementation: defer to the stdlib implementation.
# ---------------------------------------------------------------------------

if not _IS_WINDOWS:  # noqa: C901 - platform implementations are grouped here intentionally

    async def open_unix_connection(
        path: os.PathLike[str] | str | bytes | None = None,
        *,
        limit: int = _DEFAULT_LIMIT,
        **kwds: Any,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        return await asyncio.open_unix_connection(path=path, limit=limit, **kwds)

    async def start_unix_server(
        client_connected_cb: Callable[[asyncio.StreamReader, asyncio.StreamWriter], Any],
        path: os.PathLike[str] | str | bytes | None = None,
        *,
        limit: int = _DEFAULT_LIMIT,
        **kwds: Any,
    ) -> asyncio.AbstractServer:
        return await asyncio.start_unix_server(client_connected_cb, path=path, limit=limit, **kwds)

    async def create_unix_connection(
        protocol_factory: Callable[[], asyncio.BaseProtocol],
        path: os.PathLike[str] | str | bytes | None = None,
        **kwds: Any,
    ) -> tuple[asyncio.Transport, asyncio.BaseProtocol]:
        loop = asyncio.get_running_loop()
        return await loop.create_unix_connection(protocol_factory, path=path, **kwds)

    async def create_unix_server(
        protocol_factory: Callable[[], asyncio.BaseProtocol],
        path: os.PathLike[str] | str | bytes | None = None,
        **kwds: Any,
    ) -> asyncio.AbstractServer:
        loop = asyncio.get_running_loop()
        return await loop.create_unix_server(protocol_factory, path=path, **kwds)

    def install() -> None:
        """No-op on POSIX. asyncio already has native AF_UNIX helpers."""
        return None

else:
    import ctypes
    import ctypes.wintypes as wintypes

    if not hasattr(socket, "AF_UNIX"):
        # Winsock uses 1 for AF_UNIX.  Python normally exposes this on modern
        # Windows builds, but keep this for older/minimal builds.
        socket.AF_UNIX = 1  # type: ignore[attr-defined]

    UNIX_PATH_MAX = 108

    FD_READ_BIT = 0
    FD_WRITE_BIT = 1
    FD_OOB_BIT = 2
    FD_ACCEPT_BIT = 3
    FD_CONNECT_BIT = 4
    FD_CLOSE_BIT = 5

    FD_READ = 1 << FD_READ_BIT
    FD_WRITE = 1 << FD_WRITE_BIT
    FD_OOB = 1 << FD_OOB_BIT
    FD_ACCEPT = 1 << FD_ACCEPT_BIT
    FD_CONNECT = 1 << FD_CONNECT_BIT
    FD_CLOSE = 1 << FD_CLOSE_BIT

    WSAEINTR = 10004
    WSAEWOULDBLOCK = 10035
    WSAEINPROGRESS = 10036
    WSAEALREADY = 10037
    WSAEINVAL = 10022
    WSAECONNRESET = 10054
    WSAENOTCONN = 10057

    WSA_INFINITE = 0xFFFFFFFF
    WSA_WAIT_EVENT_0 = 0
    WSA_WAIT_FAILED = 0xFFFFFFFF

    SOCKET_T = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32
    INVALID_SOCKET = (1 << (ctypes.sizeof(SOCKET_T) * 8)) - 1

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

    class WSANetworkEvents(ctypes.Structure):
        _fields_ = [
            ("lNetworkEvents", ctypes.c_long),
            ("iErrorCode", ctypes.c_int * 10),
        ]

    ws2_32 = ctypes.WinDLL("ws2_32", use_last_error=True)

    ws2_32.WSAStartup.restype = ctypes.c_int
    ws2_32.WSAStartup.argtypes = (wintypes.WORD, ctypes.POINTER(WSAData))

    ws2_32.WSAGetLastError.restype = ctypes.c_int
    ws2_32.WSAGetLastError.argtypes = ()

    ws2_32.WSACreateEvent.restype = wintypes.HANDLE
    ws2_32.WSACreateEvent.argtypes = ()

    ws2_32.WSASetEvent.restype = wintypes.BOOL
    ws2_32.WSASetEvent.argtypes = (wintypes.HANDLE,)

    ws2_32.WSACloseEvent.restype = wintypes.BOOL
    ws2_32.WSACloseEvent.argtypes = (wintypes.HANDLE,)

    ws2_32.WSAEventSelect.restype = ctypes.c_int
    ws2_32.WSAEventSelect.argtypes = (SOCKET_T, wintypes.HANDLE, ctypes.c_long)

    ws2_32.WSAEnumNetworkEvents.restype = ctypes.c_int
    ws2_32.WSAEnumNetworkEvents.argtypes = (
        SOCKET_T,
        wintypes.HANDLE,
        ctypes.POINTER(WSANetworkEvents),
    )

    ws2_32.WSAWaitForMultipleEvents.restype = wintypes.DWORD
    ws2_32.WSAWaitForMultipleEvents.argtypes = (
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.BOOL,
        wintypes.DWORD,
        wintypes.BOOL,
    )

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

    _wsa_started = False

    def _ensure_winsock() -> None:
        global _wsa_started
        if _wsa_started:
            return
        data = WSAData()
        ret = ws2_32.WSAStartup(0x0202, ctypes.byref(data))
        if ret:
            raise ctypes.WinError(ret)
        _wsa_started = True

    def _last_wsa_error() -> int:
        return int(ws2_32.WSAGetLastError())

    def _raise_last_wsa_error() -> None:
        raise ctypes.WinError(_last_wsa_error())

    def _socket_handle(sock: socket.socket | int) -> int:
        if isinstance(sock, socket.socket):
            return int(sock.fileno())
        return int(sock)

    def _is_invalid_socket(value: int) -> bool:
        return value in (-1, INVALID_SOCKET)

    def _path_bytes(path: os.PathLike[str] | str | bytes) -> bytes:
        if isinstance(path, bytes):
            raw = path
        else:
            raw = os.fsencode(os.fspath(path))
        if b"\x00" in raw:
            raise ValueError("AF_UNIX path must not contain NUL bytes on Windows")
        if len(raw) >= UNIX_PATH_MAX:
            raise OSError(206, f"AF_UNIX path is too long: {len(raw)} bytes")
        return raw

    def _sockaddr(path: os.PathLike[str] | str | bytes) -> SockaddrUn:
        raw = _path_bytes(path)
        addr = SockaddrUn()
        addr.sun_family = socket.AF_UNIX  # type: ignore[attr-defined]
        addr.sun_path = raw
        return addr

    def _check_no_ssl(ssl: Any, server_hostname: Any = None) -> None:
        if ssl is not None:
            raise NotImplementedError("SSL over Windows AF_UNIX is not implemented")
        if server_hostname is not None:
            raise ValueError("server_hostname is only meaningful with ssl")

    async def _wait_for_handle(loop: asyncio.AbstractEventLoop, handle: int) -> None:
        proactor = getattr(loop, "_proactor", None)
        if proactor is not None and hasattr(proactor, "wait_for_handle"):
            await proactor.wait_for_handle(handle)
            return

        # Fallback for non-Proactor event loops.  This costs one executor thread
        # while waiting, but keeps the public API usable.
        def blocking_wait() -> None:
            handles = (wintypes.HANDLE * 1)(handle)
            rc = ws2_32.WSAWaitForMultipleEvents(1, handles, True, WSA_INFINITE, False)
            if rc == WSA_WAIT_FAILED:
                _raise_last_wsa_error()

        await loop.run_in_executor(None, blocking_wait)

    class _AsyncWSASocket:
        """One WSAEventSelect event handle plus an asyncio waiter multiplexer."""

        def __init__(
            self,
            sock: socket.socket,
            mask: int,
            *,
            loop: asyncio.AbstractEventLoop,
        ) -> None:
            _ensure_winsock()
            self.sock = sock
            self.loop = loop
            self.handle = _socket_handle(sock)
            self.event = int(ws2_32.WSACreateEvent())
            if not self.event:
                _raise_last_wsa_error()
            self._closed = False
            self._waiters: list[tuple[int, asyncio.Future[WSANetworkEvents]]] = []
            self._pump_task: asyncio.Task[None] | None = None

            if ws2_32.WSAEventSelect(self.handle, self.event, mask) != 0:
                err = _last_wsa_error()
                ws2_32.WSACloseEvent(self.event)
                raise ctypes.WinError(err)

        def start(self) -> None:
            if self._pump_task is None:
                self._pump_task = self.loop.create_task(self._pump())

        async def wait_for(self, mask: int) -> WSANetworkEvents:
            if self._closed:
                raise OSError("socket watcher is closed")
            self.start()
            fut: asyncio.Future[WSANetworkEvents] = self.loop.create_future()
            self._waiters.append((mask, fut))
            try:
                return await fut
            finally:
                if fut.cancelled():
                    self._waiters = [(m, f) for (m, f) in self._waiters if f is not fut]

        async def _pump(self) -> None:
            try:
                while not self._closed:
                    await _wait_for_handle(self.loop, self.event)
                    if self._closed:
                        break
                    ne = WSANetworkEvents()
                    rc = ws2_32.WSAEnumNetworkEvents(self.handle, self.event, ctypes.byref(ne))
                    if rc != 0:
                        exc = ctypes.WinError(_last_wsa_error())
                        self._finish_waiters(exc=exc)
                        break
                    self._finish_waiters(events=ne)
            except asyncio.CancelledError:
                raise
            except BaseException as exc:
                self._finish_waiters(exc=exc)

        def _finish_waiters(
            self,
            *,
            events: WSANetworkEvents | None = None,
            exc: BaseException | None = None,
        ) -> None:
            if exc is not None:
                waiters, self._waiters = self._waiters, []
                for _, fut in waiters:
                    if not fut.done():
                        fut.set_exception(exc)
                return

            if events is None:
                return
            mask_seen = int(events.lNetworkEvents)
            if not mask_seen:
                return

            remaining: list[tuple[int, asyncio.Future[WSANetworkEvents]]] = []
            ready: list[asyncio.Future[WSANetworkEvents]] = []
            for mask, fut in self._waiters:
                if fut.done():
                    continue
                if mask_seen & mask:
                    ready.append(fut)
                else:
                    remaining.append((mask, fut))
            self._waiters = remaining
            for fut in ready:
                if not fut.done():
                    fut.set_result(events)

        def close(self) -> None:
            if self._closed:
                return
            self._closed = True
            self._finish_waiters(exc=ConnectionAbortedError("socket watcher closed"))
            try:
                ws2_32.WSAEventSelect(self.handle, 0, 0)
            except Exception:
                pass
            try:
                ws2_32.WSASetEvent(self.event)
            except Exception:
                pass
            if self._pump_task is not None:
                self._pump_task.cancel()
            try:
                ws2_32.WSACloseEvent(self.event)
            except Exception:
                pass

    def _event_error(events: WSANetworkEvents, bit: int) -> int:
        return int(events.iErrorCode[bit])

    def _recv_nowait(handle: int, max_bytes: int) -> bytes | None:
        buf = ctypes.create_string_buffer(max_bytes)
        n = ws2_32.recv(handle, buf, max_bytes, 0)
        if n > 0:
            return bytes(buf.raw[:n])
        if n == 0:
            return b""
        err = _last_wsa_error()
        if err == WSAEWOULDBLOCK:
            return None
        if err in (WSAECONNRESET, WSAENOTCONN):
            return b""
        raise ctypes.WinError(err)

    def _send_nowait(handle: int, data: memoryview) -> int | None:
        if not data:
            return 0
        # Winsock send() needs a stable C buffer for the duration of the call.
        chunk = data[: min(len(data), 256 * 1024)]
        buf = (ctypes.c_char * len(chunk)).from_buffer_copy(chunk)
        n = ws2_32.send(handle, buf, len(chunk), 0)
        if n >= 0:
            return int(n)
        err = _last_wsa_error()
        if err == WSAEWOULDBLOCK:
            return None
        if err in (WSAECONNRESET, WSAENOTCONN):
            raise ConnectionResetError(err, "connection reset")
        raise ctypes.WinError(err)

    async def _connect_socket(
        path: os.PathLike[str] | str | bytes,
        *,
        loop: asyncio.AbstractEventLoop,
        sock: socket.socket | None = None,
    ) -> _AsyncWSASocket:
        _ensure_winsock()
        if sock is None:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # type: ignore[attr-defined]
        watcher = _AsyncWSASocket(sock, FD_READ | FD_WRITE | FD_CONNECT | FD_CLOSE, loop=loop)

        addr = _sockaddr(path)
        rc = ws2_32.connect(_socket_handle(sock), ctypes.byref(addr), ctypes.sizeof(addr))
        if rc == 0:
            watcher.start()
            return watcher

        err = _last_wsa_error()
        if err not in (WSAEWOULDBLOCK, WSAEINPROGRESS, WSAEALREADY, WSAEINVAL):
            watcher.close()
            sock.close()
            raise ctypes.WinError(err)

        events = await watcher.wait_for(FD_CONNECT | FD_CLOSE)
        if int(events.lNetworkEvents) & FD_CONNECT:
            err = _event_error(events, FD_CONNECT_BIT)
            if err:
                watcher.close()
                sock.close()
                raise ctypes.WinError(err)
            return watcher

        watcher.close()
        sock.close()
        raise ConnectionRefusedError("AF_UNIX connection closed before connect completed")

    class _UnixSocketTransport(asyncio.Transport):
        def __init__(
            self,
            loop: asyncio.AbstractEventLoop,
            watcher: _AsyncWSASocket,
            protocol: asyncio.BaseProtocol,
            *,
            peername: Any = None,
            sockname: Any = None,
        ) -> None:
            super().__init__()
            self._loop = loop
            self._watcher = watcher
            self._sock = watcher.sock
            self._protocol = protocol
            self._peername = peername
            self._sockname = sockname
            self._closing = False
            self._conn_lost = False
            self._reading_paused = False
            self._write_buffer = bytearray()
            self._write_task: asyncio.Task[None] | None = None
            self._read_task: asyncio.Task[None] | None = None
            self._high_water = 64 * 1024
            self._low_water = 16 * 1024
            self._protocol_paused = False
            self._resume_reading_waiter: asyncio.Future[None] | None = None

            self._watcher.start()
            self._protocol.connection_made(self)
            self._read_task = self._loop.create_task(self._read_loop())

        def is_closing(self) -> bool:
            return self._closing or self._conn_lost

        def get_extra_info(self, name: str, default: Any = None) -> Any:
            if name == "socket":
                return self._sock
            if name == "peername":
                return self._peername
            if name == "sockname":
                return self._sockname
            return default

        def set_write_buffer_limits(
            self,
            high: int | None = None,
            low: int | None = None,
        ) -> None:
            if high is None:
                high = 64 * 1024
            if low is None:
                low = high // 4
            if high < low or low < 0:
                raise ValueError("high must be >= low >= 0")
            self._high_water = high
            self._low_water = low
            self._maybe_pause_protocol()

        def get_write_buffer_size(self) -> int:
            return len(self._write_buffer)

        def write(self, data: bytes | bytearray | memoryview) -> None:
            if self._conn_lost:
                return
            if self._closing:
                raise RuntimeError("cannot write to closing transport")
            if not isinstance(data, (bytes, bytearray, memoryview)):
                raise TypeError("data must be bytes-like")
            if not data:
                return
            self._write_buffer.extend(data)
            self._maybe_pause_protocol()
            if self._write_task is None or self._write_task.done():
                self._write_task = self._loop.create_task(self._write_loop())

        def writelines(self, list_of_data: Iterable[bytes]) -> None:
            for data in list_of_data:
                self.write(data)

        def can_write_eof(self) -> bool:
            return True

        def write_eof(self) -> None:
            try:
                self._sock.shutdown(socket.SHUT_WR)
            except OSError:
                pass

        def pause_reading(self) -> bool:
            if self._reading_paused:
                return False
            self._reading_paused = True
            return True

        def resume_reading(self) -> bool:
            if not self._reading_paused:
                return False
            self._reading_paused = False
            waiter = self._resume_reading_waiter
            if waiter is not None and not waiter.done():
                waiter.set_result(None)
            return True

        def close(self) -> None:
            if self._conn_lost or self._closing:
                return
            self._closing = True
            if not self._write_buffer:
                self._force_close(None)

        def abort(self) -> None:
            self._force_close(ConnectionAbortedError("transport aborted"))

        def _maybe_pause_protocol(self) -> None:
            if not self._protocol_paused and len(self._write_buffer) > self._high_water and hasattr(self._protocol, "pause_writing"):
                self._protocol_paused = True
                self._protocol.pause_writing()  # type: ignore[attr-defined]

        def _maybe_resume_protocol(self) -> None:
            if self._protocol_paused and len(self._write_buffer) <= self._low_water and hasattr(self._protocol, "resume_writing"):
                self._protocol_paused = False
                self._protocol.resume_writing()  # type: ignore[attr-defined]

        async def _read_loop(self) -> None:
            try:
                while not self._closing and not self._conn_lost:
                    if self._reading_paused:
                        self._resume_reading_waiter = self._loop.create_future()
                        try:
                            await self._resume_reading_waiter
                        finally:
                            self._resume_reading_waiter = None
                        continue

                    data = _recv_nowait(self._watcher.handle, _DEFAULT_LIMIT)
                    if data is None:
                        events = await self._watcher.wait_for(FD_READ | FD_CLOSE)
                        if int(events.lNetworkEvents) & FD_READ:
                            err = _event_error(events, FD_READ_BIT)
                            if err:
                                raise ctypes.WinError(err)
                        if int(events.lNetworkEvents) & FD_CLOSE:
                            err = _event_error(events, FD_CLOSE_BIT)
                            if err and err not in (WSAECONNRESET, WSAENOTCONN):
                                raise ctypes.WinError(err)
                        continue
                    if data == b"":
                        eof_accepted = False
                        if hasattr(self._protocol, "eof_received"):
                            eof_accepted = bool(self._protocol.eof_received())  # type: ignore[attr-defined]
                        if not eof_accepted:
                            self._force_close(None)
                        return
                    if hasattr(self._protocol, "data_received"):
                        self._protocol.data_received(data)  # type: ignore[attr-defined]
            except asyncio.CancelledError:
                raise
            except BaseException as exc:
                self._force_close(exc)

        async def _write_loop(self) -> None:
            try:
                while self._write_buffer and not self._conn_lost:
                    view = memoryview(self._write_buffer)
                    try:
                        n = _send_nowait(self._watcher.handle, view)
                    finally:
                        view.release()
                    if n is None:
                        events = await self._watcher.wait_for(FD_WRITE | FD_CLOSE)
                        if int(events.lNetworkEvents) & FD_WRITE:
                            err = _event_error(events, FD_WRITE_BIT)
                            if err:
                                raise ctypes.WinError(err)
                        if int(events.lNetworkEvents) & FD_CLOSE:
                            err = _event_error(events, FD_CLOSE_BIT)
                            if err and err not in (WSAECONNRESET, WSAENOTCONN):
                                raise ctypes.WinError(err)
                        continue
                    if n == 0:
                        await self._watcher.wait_for(FD_WRITE | FD_CLOSE)
                        continue
                    del self._write_buffer[:n]
                    self._maybe_resume_protocol()
            except asyncio.CancelledError:
                raise
            except BaseException as exc:
                self._force_close(exc)
                return

            if self._closing:
                self._force_close(None)

        def _force_close(self, exc: BaseException | None) -> None:
            if self._conn_lost:
                return
            self._conn_lost = True
            self._closing = True
            self._watcher.close()
            try:
                self._sock.close()
            except OSError:
                pass

            read_task = self._read_task
            if read_task is not None and read_task is not asyncio.current_task(self._loop):
                read_task.cancel()
            write_task = self._write_task
            if write_task is not None and write_task is not asyncio.current_task(self._loop):
                write_task.cancel()

            if hasattr(self._protocol, "connection_lost"):
                self._loop.call_soon(self._protocol.connection_lost, exc)

    class _WindowsUnixServer:
        def __init__(
            self,
            loop: asyncio.AbstractEventLoop,
            sock: socket.socket,
            watcher: _AsyncWSASocket,
            protocol_factory: Callable[[], asyncio.BaseProtocol],
            *,
            cleanup_path: os.PathLike[str] | str | bytes | None = None,
        ) -> None:
            self._loop = loop
            self._sock = sock
            self._watcher = watcher
            self._protocol_factory = protocol_factory
            self._cleanup_path = cleanup_path
            self._serving = False
            self._closed = False
            self._accept_task: asyncio.Task[None] | None = None
            self._closed_fut: asyncio.Future[None] = loop.create_future()

        @property
        def sockets(self) -> tuple[socket.socket, ...]:
            return (self._sock,)

        def get_loop(self) -> asyncio.AbstractEventLoop:
            return self._loop

        def is_serving(self) -> bool:
            return self._serving and not self._closed

        async def start_serving(self) -> None:
            if self._closed:
                raise RuntimeError("server is closed")
            if self._serving:
                return
            self._serving = True
            self._watcher.start()
            self._accept_task = self._loop.create_task(self._accept_loop())

        async def serve_forever(self) -> None:
            await self.start_serving()
            fut = self._loop.create_future()
            try:
                await fut
            except asyncio.CancelledError:
                self.close()
                await self.wait_closed()
                raise

        def close(self) -> None:
            if self._closed:
                return
            self._closed = True
            self._serving = False
            if self._accept_task is not None:
                self._accept_task.cancel()
            self._watcher.close()
            try:
                self._sock.close()
            except OSError:
                pass
            if self._cleanup_path is not None:
                try:
                    os.unlink(self._cleanup_path)
                except FileNotFoundError:
                    pass
                except OSError:
                    # Match asyncio's best-effort cleanup behaviour.
                    pass
            if not self._closed_fut.done():
                self._closed_fut.set_result(None)

        async def wait_closed(self) -> None:
            await self._closed_fut

        async def _accept_loop(self) -> None:
            try:
                while self._serving and not self._closed:
                    client_handle = self._accept_nowait()
                    if client_handle is None:
                        events = await self._watcher.wait_for(FD_ACCEPT | FD_CLOSE)
                        if int(events.lNetworkEvents) & FD_ACCEPT:
                            err = _event_error(events, FD_ACCEPT_BIT)
                            if err:
                                raise ctypes.WinError(err)
                        if int(events.lNetworkEvents) & FD_CLOSE:
                            return
                        continue
                    self._start_client(client_handle)
            except asyncio.CancelledError:
                raise
            except BaseException as exc:
                self._loop.call_exception_handler(
                    {
                        "message": "AF_UNIX server accept loop failed",
                        "exception": exc,
                        "server": self,
                    }
                )
                self.close()

        def _accept_nowait(self) -> int | None:
            addr = SockaddrUn()
            addr_len = ctypes.c_int(ctypes.sizeof(addr))
            client = int(ws2_32.accept(_socket_handle(self._sock), ctypes.byref(addr), ctypes.byref(addr_len)))
            if not _is_invalid_socket(client):
                return client
            err = _last_wsa_error()
            if err == WSAEWOULDBLOCK:
                return None
            raise ctypes.WinError(err)

        def _start_client(self, client_handle: int) -> None:
            try:
                client_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM, fileno=client_handle)  # type: ignore[attr-defined]
                watcher = _AsyncWSASocket(client_sock, FD_READ | FD_WRITE | FD_CLOSE, loop=self._loop)
                protocol = self._protocol_factory()
                _UnixSocketTransport(
                    self._loop,
                    watcher,
                    protocol,
                    peername="",
                    sockname=self._cleanup_path,
                )
            except BaseException as exc:
                self._loop.call_exception_handler(
                    {
                        "message": "failed to initialize AF_UNIX client transport",
                        "exception": exc,
                        "server": self,
                    }
                )
                try:
                    socket.socket(socket.AF_UNIX, socket.SOCK_STREAM, fileno=client_handle).close()  # type: ignore[attr-defined]
                except Exception:
                    pass

    async def create_unix_connection(
        protocol_factory: Callable[[], asyncio.BaseProtocol],
        path: os.PathLike[str] | str | bytes | None = None,
        *,
        ssl: Any = None,
        sock: socket.socket | None = None,
        server_hostname: str | None = None,
        ssl_handshake_timeout: float | None = None,
        ssl_shutdown_timeout: float | None = None,
    ) -> tuple[asyncio.Transport, asyncio.BaseProtocol]:
        _check_no_ssl(ssl, server_hostname)
        if path is None and sock is None:
            raise TypeError("path was not specified, and no sock specified")
        if path is not None and sock is not None:
            raise ValueError("path and sock can not be specified at the same time")

        loop = asyncio.get_running_loop()
        if sock is not None:
            watcher = _AsyncWSASocket(sock, FD_READ | FD_WRITE | FD_CLOSE, loop=loop)
        else:
            watcher = await _connect_socket(path, loop=loop)  # type: ignore[arg-type]

        protocol = protocol_factory()
        transport = _UnixSocketTransport(
            loop,
            watcher,
            protocol,
            peername=path,
            sockname=None,
        )
        return transport, protocol

    async def open_unix_connection(
        path: os.PathLike[str] | str | bytes | None = None,
        *,
        limit: int = _DEFAULT_LIMIT,
        ssl: Any = None,
        sock: socket.socket | None = None,
        server_hostname: str | None = None,
        ssl_handshake_timeout: float | None = None,
        ssl_shutdown_timeout: float | None = None,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        _check_no_ssl(ssl, server_hostname)
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader(limit=limit)
        protocol = asyncio.StreamReaderProtocol(reader)

        transport, _ = await create_unix_connection(
            lambda: protocol,
            path=path,
            ssl=ssl,
            sock=sock,
            server_hostname=server_hostname,
            ssl_handshake_timeout=ssl_handshake_timeout,
            ssl_shutdown_timeout=ssl_shutdown_timeout,
        )
        writer = asyncio.StreamWriter(transport, protocol, reader, loop)
        return reader, writer

    async def create_unix_server(
        protocol_factory: Callable[[], asyncio.BaseProtocol],
        path: os.PathLike[str] | str | bytes | None = None,
        *,
        sock: socket.socket | None = None,
        backlog: int = 100,
        ssl: Any = None,
        ssl_handshake_timeout: float | None = None,
        ssl_shutdown_timeout: float | None = None,
        start_serving: bool = True,
        cleanup_socket: bool = True,
    ) -> _WindowsUnixServer:
        _check_no_ssl(ssl)
        if path is None and sock is None:
            raise TypeError("path was not specified, and no sock specified")
        if path is not None and sock is not None:
            raise ValueError("path and sock can not be specified at the same time")

        _ensure_winsock()
        loop = asyncio.get_running_loop()
        cleanup_path: os.PathLike[str] | str | bytes | None = None

        if sock is None:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # type: ignore[attr-defined]
            addr = _sockaddr(path)  # type: ignore[arg-type]
            if ws2_32.bind(_socket_handle(sock), ctypes.byref(addr), ctypes.sizeof(addr)) != 0:
                err = _last_wsa_error()
                sock.close()
                raise ctypes.WinError(err)
            if ws2_32.listen(_socket_handle(sock), int(backlog)) != 0:
                err = _last_wsa_error()
                sock.close()
                raise ctypes.WinError(err)
            if cleanup_socket:
                cleanup_path = path
        else:
            if ws2_32.listen(_socket_handle(sock), int(backlog)) != 0:
                err = _last_wsa_error()
                raise ctypes.WinError(err)

        watcher = _AsyncWSASocket(sock, FD_ACCEPT | FD_CLOSE, loop=loop)
        server = _WindowsUnixServer(
            loop,
            sock,
            watcher,
            protocol_factory,
            cleanup_path=cleanup_path,
        )
        if start_serving:
            await server.start_serving()
        return server

    async def start_unix_server(
        client_connected_cb: Callable[[asyncio.StreamReader, asyncio.StreamWriter], Any],
        path: os.PathLike[str] | str | bytes | None = None,
        *,
        limit: int = _DEFAULT_LIMIT,
        sock: socket.socket | None = None,
        backlog: int = 100,
        ssl: Any = None,
        ssl_handshake_timeout: float | None = None,
        ssl_shutdown_timeout: float | None = None,
        start_serving: bool = True,
        cleanup_socket: bool = True,
    ) -> _WindowsUnixServer:
        _check_no_ssl(ssl)

        def factory() -> asyncio.StreamReaderProtocol:
            reader = asyncio.StreamReader(limit=limit)
            protocol: asyncio.StreamReaderProtocol

            def connected_cb(
                reader: asyncio.StreamReader,
                writer: asyncio.StreamWriter,
            ) -> None:
                result = client_connected_cb(reader, writer)
                if inspect.isawaitable(result):
                    asyncio.ensure_future(result)

            protocol = asyncio.StreamReaderProtocol(reader, connected_cb)
            return protocol

        return await create_unix_server(
            factory,
            path=path,
            sock=sock,
            backlog=backlog,
            ssl=ssl,
            ssl_handshake_timeout=ssl_handshake_timeout,
            ssl_shutdown_timeout=ssl_shutdown_timeout,
            start_serving=start_serving,
            cleanup_socket=cleanup_socket,
        )

    def install() -> None:
        """
        Monkey-patch asyncio's module-level stream helpers on Windows.

        This intentionally patches only asyncio.open_unix_connection and
        asyncio.start_unix_server.  Event-loop instance methods are not patched
        because their implementation classes differ between Python versions.
        Use this module's create_unix_connection/create_unix_server directly
        when protocol-level APIs are needed.
        """
        asyncio.open_unix_connection = open_unix_connection  # type: ignore[assignment]
        asyncio.start_unix_server = start_unix_server  # type: ignore[assignment]
