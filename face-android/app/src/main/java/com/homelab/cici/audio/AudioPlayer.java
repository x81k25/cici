package com.homelab.cici.audio;

import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioTrack;

import com.homelab.cici.api.MouthClient;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Polls MOUTH for WAV audio chunks and plays them back.
 */
public class AudioPlayer {
    private final MouthClient mouthClient;
    private volatile boolean polling = false;
    private Thread pollThread;
    private final AtomicBoolean playing = new AtomicBoolean(false);

    public interface PlaybackListener {
        void onPlaybackStarted();
        void onPlaybackFinished();
        void onError(String error);
    }

    private PlaybackListener listener;

    public AudioPlayer(MouthClient mouthClient) {
        this.mouthClient = mouthClient;
    }

    public void setListener(PlaybackListener listener) {
        this.listener = listener;
    }

    public void startPolling() {
        if (polling) return;
        polling = true;

        pollThread = new Thread(() -> {
            int consecutiveErrors = 0;
            while (polling) {
                try {
                    MouthClient.AudioResult result = mouthClient.getNextAudio();
                    consecutiveErrors = 0;
                    if (result != null && result.audioData != null) {
                        playWav(result.audioData);
                    } else {
                        Thread.sleep(500);
                    }
                } catch (IOException e) {
                    consecutiveErrors++;
                    // Only report first error, then stay quiet until recovered
                    if (consecutiveErrors == 1 && listener != null) {
                        listener.onError("MOUTH poll error: " + e.getMessage());
                    }
                    // Back off: 2s, 4s, 8s, max 15s
                    long backoff = Math.min(2000L * (1L << (consecutiveErrors - 1)), 15000L);
                    try { Thread.sleep(backoff); } catch (InterruptedException ignored) { break; }
                } catch (InterruptedException ignored) {
                    break;
                }
            }
        }, "MouthPoller");
        pollThread.start();
    }

    public void stopPolling() {
        polling = false;
        if (pollThread != null) {
            pollThread.interrupt();
            try {
                pollThread.join(2000);
            } catch (InterruptedException ignored) {}
            pollThread = null;
        }
    }

    private void playWav(byte[] wavData) {
        if (playing.getAndSet(true)) return; // skip if already playing

        try {
            if (listener != null) listener.onPlaybackStarted();

            // Parse WAV header to get format info
            ByteArrayInputStream bis = new ByteArrayInputStream(wavData);
            // Skip RIFF header (12 bytes) + fmt chunk header (8 bytes)
            bis.skip(20);
            // Audio format (2 bytes) - skip
            int audioFormat = readShortLE(bis);
            int channels = readShortLE(bis);
            int sampleRate = readIntLE(bis);
            int byteRate = readIntLE(bis);
            int blockAlign = readShortLE(bis);
            int bitsPerSample = readShortLE(bis);

            // Find data chunk
            // Skip to "data" marker
            byte[] marker = new byte[4];
            int dataSize = 0;
            while (bis.available() > 4) {
                bis.read(marker);
                dataSize = readIntLE(bis);
                if (marker[0] == 'd' && marker[1] == 'a' && marker[2] == 't' && marker[3] == 'a') {
                    break;
                }
                bis.skip(dataSize);
            }

            byte[] pcmData = new byte[dataSize];
            bis.read(pcmData);

            int channelConfig = channels == 1
                    ? AudioFormat.CHANNEL_OUT_MONO
                    : AudioFormat.CHANNEL_OUT_STEREO;
            int encoding = bitsPerSample == 16
                    ? AudioFormat.ENCODING_PCM_16BIT
                    : AudioFormat.ENCODING_PCM_8BIT;

            AudioTrack track = new AudioTrack.Builder()
                    .setAudioAttributes(new AudioAttributes.Builder()
                            .setUsage(AudioAttributes.USAGE_ASSISTANT)
                            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                            .build())
                    .setAudioFormat(new AudioFormat.Builder()
                            .setSampleRate(sampleRate)
                            .setChannelMask(channelConfig)
                            .setEncoding(encoding)
                            .build())
                    .setBufferSizeInBytes(pcmData.length)
                    .setTransferMode(AudioTrack.MODE_STATIC)
                    .build();

            track.write(pcmData, 0, pcmData.length);
            track.play();

            // Wait for playback to finish
            int durationMs = (pcmData.length * 1000) / (sampleRate * channels * (bitsPerSample / 8));
            Thread.sleep(durationMs + 100);

            track.stop();
            track.release();
        } catch (Exception e) {
            if (listener != null) listener.onError("Playback error: " + e.getMessage());
        } finally {
            playing.set(false);
            if (listener != null) listener.onPlaybackFinished();
        }
    }

    private int readShortLE(ByteArrayInputStream bis) throws IOException {
        int lo = bis.read();
        int hi = bis.read();
        return (hi << 8) | lo;
    }

    private int readIntLE(ByteArrayInputStream bis) throws IOException {
        int b0 = bis.read();
        int b1 = bis.read();
        int b2 = bis.read();
        int b3 = bis.read();
        return (b3 << 24) | (b2 << 16) | (b1 << 8) | b0;
    }
}
