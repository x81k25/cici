package com.homelab.cici.audio;

import android.Manifest;
import android.content.pm.PackageManager;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;

import androidx.core.app.ActivityCompat;

import com.homelab.cici.api.EarsClient;

/**
 * Captures microphone audio as PCM Int16 @ 16kHz mono and streams to EARS via WebSocket.
 */
public class AudioRecorder {
    private static final int SAMPLE_RATE = 16000;
    private static final int CHANNEL = AudioFormat.CHANNEL_IN_MONO;
    private static final int ENCODING = AudioFormat.ENCODING_PCM_16BIT;

    private AudioRecord audioRecord;
    private volatile boolean recording = false;
    private Thread recordThread;
    private final EarsClient earsClient;

    public AudioRecorder(EarsClient earsClient) {
        this.earsClient = earsClient;
    }

    public boolean start(android.content.Context context) {
        if (ActivityCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO)
                != PackageManager.PERMISSION_GRANTED) {
            return false;
        }

        int bufferSize = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL, ENCODING);
        if (bufferSize == AudioRecord.ERROR || bufferSize == AudioRecord.ERROR_BAD_VALUE) {
            bufferSize = SAMPLE_RATE * 2; // 1 second fallback
        }

        audioRecord = new AudioRecord(
                MediaRecorder.AudioSource.VOICE_COMMUNICATION,
                SAMPLE_RATE, CHANNEL, ENCODING, bufferSize);

        if (audioRecord.getState() != AudioRecord.STATE_INITIALIZED) {
            return false;
        }

        recording = true;
        audioRecord.startRecording();

        // 100ms chunks to match FACE Streamlit behavior
        final int chunkSize = SAMPLE_RATE * 2 / 10; // 16000 samples/s * 2 bytes * 0.1s
        recordThread = new Thread(() -> {
            byte[] buffer = new byte[chunkSize];
            while (recording) {
                int read = audioRecord.read(buffer, 0, chunkSize);
                if (read > 0) {
                    byte[] chunk = new byte[read];
                    System.arraycopy(buffer, 0, chunk, 0, read);
                    earsClient.sendAudio(chunk);
                }
            }
        }, "AudioRecorder");
        recordThread.start();
        return true;
    }

    public void stop() {
        recording = false;
        if (recordThread != null) {
            try {
                recordThread.join(1000);
            } catch (InterruptedException ignored) {}
            recordThread = null;
        }
        if (audioRecord != null) {
            try {
                audioRecord.stop();
                audioRecord.release();
            } catch (IllegalStateException ignored) {}
            audioRecord = null;
        }
    }

    public boolean isRecording() {
        return recording;
    }
}
