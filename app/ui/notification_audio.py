"""Decode alert audio completely before sending every sample to the device."""
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat, QAudioSink, QMediaDevices, QtAudio


STARTUP_SILENCE_MS = 150


def playback_bytes(pcm, audio_format):
    """Let a sleeping output device wake before the first original sample."""
    frames = audio_format.sampleRate() * STARTUP_SILENCE_MS // 1000
    value = b"\x80" if audio_format.sampleFormat() == QAudioFormat.SampleFormat.UInt8 else b"\0"
    silence = value * (frames * audio_format.bytesPerFrame())
    return silence + pcm + silence


class NotificationAudio(QObject):
    finished = Signal()
    errorOccurred = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.decoder = None
        self.sink = None
        self.buffer = QBuffer(self)
        self.source = QUrl()
        self.pcm = b""
        self.format = QAudioFormat()
        self._cache_key = None
        self._chunks = []
        self._pending = False
        self._allowed = lambda: True
        self._closed = False
        self._output_timer = QTimer(self)
        self._output_timer.setInterval(25)
        self._output_timer.timeout.connect(self._check_output)

    def setSource(self, source):  # noqa: N802 - media player interface
        self.stop()
        path = Path(source.toLocalFile()) if not source.isEmpty() else None
        try:
            stat = path.stat() if path is not None else None
            key = (str(path), stat.st_mtime_ns, stat.st_size) if stat is not None else None
        except OSError:
            key = None
        if key != self._cache_key or source != self.source:
            self.pcm = b""
            self._cache_key = key
        self.source = source

    def play(self, allowed=None):
        if self._closed or self.source.isEmpty():
            return
        self.stop()
        self._allowed = allowed or (lambda: True)
        self._pending = True
        if self.pcm:
            self._start_output()
            return
        self._chunks = []
        decoder = QAudioDecoder(self)
        self.decoder = decoder
        device = QMediaDevices.defaultAudioOutput()
        if device.isNull():
            self._failed()
            return
        decoder.setAudioFormat(device.preferredFormat())
        decoder.setSource(self.source)
        decoder.bufferReady.connect(lambda: self._read_buffer(decoder))
        decoder.finished.connect(lambda: self._decoded(decoder))
        decoder.error.connect(lambda *_: self._failed() if self.decoder is decoder else None)
        decoder.start()

    def _read_buffer(self, decoder):
        if self.decoder is not decoder:
            return
        buffer = decoder.read()
        if buffer.isValid():
            self.format = buffer.format()
            self._chunks.append(bytes(buffer.data()))

    def _decoded(self, decoder):
        if self.decoder is not decoder:
            return
        self.pcm = b"".join(self._chunks)
        self._chunks = []
        self.decoder = None
        decoder.deleteLater()
        if self.pcm and self.format.isValid():
            self._start_output()
        else:
            self._failed()

    def _start_output(self):
        if not self._pending or not self._allowed():
            self._pending = False
            return
        self.buffer.close()
        self.buffer.setData(QByteArray(playback_bytes(self.pcm, self.format)))
        self.buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        device = QMediaDevices.defaultAudioOutput()
        sink = QAudioSink(device, self.format, self)
        self.sink = sink
        sink.setVolume(0.8)
        sink.setBufferSize(self.format.bytesForDuration(100_000))
        sink.start(self.buffer)
        # This portable PySide build still names the signal enum QAudio::State,
        # although its bound enum is QtAudio.State. Read the typed getter instead.
        self._output_timer.start()

    def _check_output(self):
        if self.sink is not None:
            self._state_changed(self.sink, self.sink.state())

    def _state_changed(self, sink, state):
        if self.sink is not sink:
            return
        if state == QtAudio.State.IdleState:
            # Idle means the finite PCM stream has drained, including its tail.
            self.stop()
            self.finished.emit()
        elif state == QtAudio.State.StoppedState and sink.error() != QtAudio.Error.NoError:
            self._failed()

    def _failed(self):
        self.stop()
        self.errorOccurred.emit()

    def stop(self):
        self._pending = False
        self._output_timer.stop()
        if self.decoder is not None:
            decoder, self.decoder = self.decoder, None
            decoder.stop()
            decoder.deleteLater()
        self._chunks = []
        if self.sink is not None:
            sink, self.sink = self.sink, None
            sink.reset()
            sink.deleteLater()
        self.buffer.close()

    def shutdown(self):
        self._closed = True
        self.stop()
        self.pcm = b""
        self.source = QUrl()
