"""One desktop owner per application directory; repeated launches only activate it."""
from hashlib import sha256
import os
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class DesktopInstance(QObject):
    activation_requested = Signal()

    def __init__(self, root, parent=None):
        super().__init__(parent)
        root = Path(root).resolve()
        self.state = root / "state"
        self.name = "orsi-desktop-" + sha256(os.path.normcase(str(root)).encode()).hexdigest()
        self.lock = QLockFile(str(self.state / "desktop_instance_v1.lock"))
        # A long-running app is not stale merely because its lock is old. Qt
        # still checks process liveness when recovering a crashed owner.
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._activate)
        self.owned = False

    def claim(self):
        from app.vault.files import ordinary
        ordinary(self.state / "desktop_instance_v1.lock")
        self.state.mkdir(parents=True, exist_ok=True)
        if not self.lock.tryLock(0):
            if self.lock.error() != QLockFile.LockError.LockFailedError:
                raise RuntimeError("Cannot acquire desktop startup access.")
            # The first owner may still be between acquiring the lock and
            # listening. A secondary never constructs another profile/window.
            socket = QLocalSocket()
            for _ in range(5):
                socket.connectToServer(self.name)
                if socket.waitForConnected(200):
                    socket.disconnectFromServer()
                    return False
                socket.abort()
            return False
        self.owned = True
        if os.name != "nt":
            QLocalServer.removeServer(self.name)  # Only after owning the lock.
        if not self.server.listen(self.name):
            self.close()
            raise RuntimeError("Cannot establish desktop activation access.")
        return True

    def _activate(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.abort()
            socket.deleteLater()
            # No payload, profile path, password, credential or tool command.
            self.activation_requested.emit()

    def close(self):
        if self.owned:
            self.server.close()
            self.lock.unlock()
            self.owned = False
