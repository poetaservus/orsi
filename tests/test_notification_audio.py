"""Every decoded frame, including the first one, reaches the padded PCM stream."""
import os
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QByteArray, QUrl
from PySide6.QtMultimedia import QAudioBuffer, QAudioFormat
from PySide6.QtWidgets import QApplication

from app.ui.notification_audio import NotificationAudio, STARTUP_SILENCE_MS, playback_bytes
from app.ui.notifications import SOUNDS
from tests.test_message_images import wait_for


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("sample_format", [QAudioFormat.SampleFormat.Int16,
    QAudioFormat.SampleFormat.Float, QAudioFormat.SampleFormat.UInt8])
def test_padding_preserves_the_entire_sample_stream(sample_format):
    fmt = QAudioFormat()
    fmt.setSampleRate(44100)
    fmt.setChannelCount(2)
    fmt.setSampleFormat(sample_format)
    pcm = bytes(range(256)) * 4
    padding_size = (fmt.sampleRate() * STARTUP_SILENCE_MS // 1000) * fmt.bytesPerFrame()
    silence = (b"\x80" if sample_format == QAudioFormat.SampleFormat.UInt8 else b"\0") * padding_size
    queued = playback_bytes(pcm, fmt)
    assert queued == silence + pcm + silence
    assert queued[padding_size:padding_size + fmt.bytesPerFrame()] == pcm[:fmt.bytesPerFrame()]


def test_decode_collects_first_and_last_buffer_without_trimming(app):
    audio = NotificationAudio()
    fmt = QAudioFormat()
    fmt.setSampleRate(44100)
    fmt.setChannelCount(2)
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    decoder = Mock()
    audio.decoder = decoder
    first = b"\xff\x7f\x00\x80" * 8
    last = b"\x01\x00\x02\x00" * 8
    decoder.read.side_effect = [QAudioBuffer(QByteArray(first), fmt), QAudioBuffer(QByteArray(last), fmt)]
    try:
        audio._read_buffer(decoder)
        audio._read_buffer(decoder)
        audio._decoded(decoder)
        assert audio.pcm == first + last
        assert audio.sink is None  # Decode alone never starts output.
    finally:
        audio.shutdown()


@pytest.mark.parametrize("name", ["noti_1.ogg", "noti_2.ogg"])
def test_real_ogg_decode_and_cache_can_be_cancelled_before_output(app, monkeypatch, name):
    audio = NotificationAudio()
    errors = []
    audio.errorOccurred.connect(lambda: errors.append(True))
    try:
        audio.setSource(QUrl.fromLocalFile(str((SOUNDS / name).resolve())))
        audio.play(allowed=lambda: False)
        wait_for(lambda: bool(audio.pcm) or errors)
        assert not errors
        assert audio.decoder is None and audio.sink is None
        assert 3_000_000 < audio.format.durationForBytes(len(audio.pcm)) < 3_400_000
        original = audio.pcm
        monkeypatch.setattr("app.ui.notification_audio.QAudioDecoder", Mock(side_effect=AssertionError("Unexpected decode")))
        audio.setSource(QUrl.fromLocalFile(str((SOUNDS / name).resolve())))
        audio.play(allowed=lambda: False)
        assert audio.pcm == original and audio.sink is None
        audio.shutdown()
        assert not audio.pcm and audio.source.isEmpty()
    finally:
        audio.shutdown()
