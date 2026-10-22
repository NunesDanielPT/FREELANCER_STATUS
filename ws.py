"""WebSocket minimo (RFC 6455) so com a biblioteca standard + Hub de ligacoes por utilizador."""
import base64, hashlib, json, struct, threading

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def accept_key(key):
    return base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()


def handshake(key):
    return ("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept_key(key)}\r\n\r\n").encode()


def frame(data, op=1):
    b = data.encode() if isinstance(data, str) else data
    n = len(b); h = bytes([0x80 | op])
    if n < 126: h += bytes([n])
    elif n < 65536: h += bytes([126]) + struct.pack(">H", n)
    else: h += bytes([127]) + struct.pack(">Q", n)
    return h + b


class Reader:
    """Le mensagens de um socket; tolera timeouts sem perder bytes (so consome frames completos)."""
    def __init__(self, sock):
        self.s = sock; self.buf = b""; self.frag = b""; self.fop = 1

    def _parse(self):
        b = self.buf
        if len(b) < 2: return None
        fin, op, masked, n, i = b[0] & 0x80, b[0] & 0x0f, b[1] & 0x80, b[1] & 0x7f, 2
        if n == 126:
            if len(b) < 4: return None
            n = struct.unpack(">H", b[2:4])[0]; i = 4
        elif n == 127:
            if len(b) < 10: return None
            n = struct.unpack(">Q", b[2:10])[0]; i = 10
        if n > 65536 or not masked: raise ValueError("frame")
        if len(b) < i + 4 + n: return None
        mk = b[i:i + 4]; d = bytearray(b[i + 4:i + 4 + n])
        for k in range(n): d[k] ^= mk[k % 4]
        self.buf = b[i + 4 + n:]
        return fin, op, bytes(d)

    def message(self):
        while True:
            f = self._parse()
            if f is None:
                d = self.s.recv(4096)            # pode levantar socket.timeout (o buffer fica intacto)
                if not d: raise EOFError
                self.buf += d; continue
            fin, op, data = f
            if op >= 8: return op, data
            if op == 0: self.frag += data
            else: self.frag, self.fop = data, op
            if len(self.frag) > 65536: raise ValueError("grande")
            if fin:
                m, self.frag = self.frag, b""
                return self.fop, m


class Conn:
    def __init__(self, sock, uid):
        self.sock, self.uid, self.lock = sock, uid, threading.Lock()

    def send(self, data):
        with self.lock: self.sock.sendall(data)


class Hub:
    def __init__(self):
        self.lock = threading.Lock(); self.conns = {}

    def add(self, uid, c):
        with self.lock:
            s = self.conns.setdefault(uid, set()); first = not s; s.add(c); return first

    def remove(self, uid, c):
        with self.lock:
            s = self.conns.get(uid, set()); s.discard(c)
            if not s: self.conns.pop(uid, None); return True
            return False

    def online(self, uid): return bool(self.conns.get(uid))
    def online_ids(self): return list(self.conns.keys())

    def push(self, uids, obj):
        data = frame(json.dumps(obj, ensure_ascii=False))
        for uid in set(uids):
            for c in list(self.conns.get(uid, ())):
                try: c.send(data)
                except OSError:
                    try: c.sock.close()
                    except OSError: pass


hub = Hub()
