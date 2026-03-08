package com.homelab.cici.api;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

public class MouthClient {
    private final OkHttpClient client;
    private String baseUrl;

    public MouthClient(String host, int port) {
        this.baseUrl = "http://" + host + ":" + port;
        this.client = new OkHttpClient.Builder()
                .connectTimeout(5, TimeUnit.SECONDS)
                .readTimeout(5, TimeUnit.SECONDS)
                .build();
    }

    public void updateEndpoint(String host, int port) {
        this.baseUrl = "http://" + host + ":" + port;
    }

    public static class AudioResult {
        public final byte[] audioData;
        public final int pendingCount;
        public final int completedCount;

        public AudioResult(byte[] audioData, int pendingCount, int completedCount) {
            this.audioData = audioData;
            this.pendingCount = pendingCount;
            this.completedCount = completedCount;
        }
    }

    /**
     * Fetch next audio chunk from MOUTH. Returns null if no audio available (204).
     */
    public AudioResult getNextAudio() throws IOException {
        Request request = new Request.Builder()
                .url(baseUrl + "/audio/next")
                .build();

        try (Response response = client.newCall(request).execute()) {
            if (response.code() == 204) {
                return null;
            }
            if (!response.isSuccessful()) {
                throw new IOException("MOUTH returned " + response.code());
            }

            byte[] data = response.body().bytes();
            int pending = parseIntHeader(response, "X-Pending-Count", 0);
            int completed = parseIntHeader(response, "X-Completed-Count", 0);

            return new AudioResult(data, pending, completed);
        }
    }

    public boolean healthCheck() {
        Request request = new Request.Builder()
                .url(baseUrl + "/health")
                .build();
        try (Response response = client.newCall(request).execute()) {
            return response.isSuccessful();
        } catch (IOException e) {
            return false;
        }
    }

    private int parseIntHeader(Response response, String name, int defaultValue) {
        String val = response.header(name);
        if (val == null) return defaultValue;
        try {
            return Integer.parseInt(val);
        } catch (NumberFormatException e) {
            return defaultValue;
        }
    }
}
