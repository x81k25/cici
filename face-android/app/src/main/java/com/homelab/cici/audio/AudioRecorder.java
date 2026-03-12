package com.homelab.cici.audio;

import android.Manifest;
import android.content.pm.PackageManager;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.util.Log;

import androidx.core.app.ActivityCompat;

import com.homelab.cici.api.EarsClient;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;

/**
 * Captures microphone audio as PCM Int16 @ 16kHz mono and streams to EARS via WebSocket.
 * Also supports file-based injection for e2e testing.
 */
public class AudioRecorder {
    private static final String TAG = "AudioRecorder";
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

    /**
     * Stream a raw PCM file (16kHz, mono, int16) to EARS instead of using the mic.
     * Used for e2e testing — triggered via broadcast intent.
     *
     * @param filePath absolute path to a raw PCM file on the device
     * @return true if streaming started successfully
     */
    public boolean startFromFile(String filePath) {
        File file = new File(filePath);
        if (!file.exists() || !file.canRead()) {
            Log.e(TAG, "Cannot read audio file: " + filePath);
            return false;
        }

        recording = true;

        // 100ms chunks, same as mic path
        final int chunkSize = SAMPLE_RATE * 2 / 10;
        recordThread = new Thread(() -> {
            try (FileInputStream fis = new FileInputStream(file)) {
                // Skip WAV header if present (44 bytes starting with "RIFF")
                byte[] header = new byte[4];
                int headerRead = fis.read(header);
                if (headerRead == 4 && header[0] == 'R' && header[1] == 'I'
                        && header[2] == 'F' && header[3] == 'F') {
                    // WAV file — skip remaining 40 bytes of header
                    fis.skip(40);
                } else {
                    // Raw PCM — reopen to start from beginning
                    fis.close();
                    FileInputStream fis2 = new FileInputStream(file);
                    streamChunks(fis2, chunkSize);
                    fis2.close();
                    return;
                }
                streamChunks(fis, chunkSize);
            } catch (IOException e) {
                Log.e(TAG, "Error streaming audio file", e);
            } finally {
                recording = false;
            }
        }, "AudioRecorder-File");
        recordThread.start();
        return true;
    }

    private void streamChunks(FileInputStream fis, int chunkSize) throws IOException {
        byte[] buffer = new byte[chunkSize];
        int read;
        while (recording && (read = fis.read(buffer)) > 0) {
            byte[] chunk = new byte[read];
            System.arraycopy(buffer, 0, chunk, 0, read);
            earsClient.sendAudio(chunk);
            // Pace at ~real-time to avoid overwhelming EARS
            try { Thread.sleep(90); } catch (InterruptedException ignored) { break; }
        }
        // Send 1.5s of silence so EARS VAD detects speech-end and triggers transcription.
        // Without this, the stream ends abruptly and VAD never sees the trailing silence
        // it needs to finalize the speech segment.
        if (recording) {
            byte[] silence = new byte[chunkSize]; // zero-filled = silence
            int silenceChunks = 15; // 15 * 100ms = 1.5s
            for (int i = 0; i < silenceChunks && recording; i++) {
                earsClient.sendAudio(silence);
                try { Thread.sleep(90); } catch (InterruptedException ignored) { break; }
            }
        }
    }

    public void stop() {
        recording = false;
        if (recordThread != null) {
            try {
                recordThread.join(2000);
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
