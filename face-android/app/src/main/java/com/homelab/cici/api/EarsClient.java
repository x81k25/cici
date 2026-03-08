package com.homelab.cici.api;

import com.google.gson.Gson;
import com.google.gson.JsonObject;

import java.util.concurrent.ConcurrentLinkedQueue;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;
import okio.ByteString;

public class EarsClient extends WebSocketListener {

    public interface TranscriptionListener {
        void onTranscription(String text, boolean isFinal);
        void onError(String error);
        void onConnected();
        void onDisconnected();
    }

    private final OkHttpClient client;
    private final Gson gson = new Gson();
    private WebSocket webSocket;
    private String host;
    private int port;
    private boolean debug;
    private TranscriptionListener listener;
    private volatile boolean connected = false;
    private volatile boolean shouldReconnect = false;

    public EarsClient(String host, int port, boolean debug) {
        this.host = host;
        this.port = port;
        this.debug = debug;
        this.client = new OkHttpClient.Builder()
                .connectTimeout(10, java.util.concurrent.TimeUnit.SECONDS)
                .readTimeout(0, java.util.concurrent.TimeUnit.SECONDS)
                .build();
    }

    public void updateEndpoint(String host, int port, boolean debug) {
        this.host = host;
        this.port = port;
        this.debug = debug;
    }

    public void setListener(TranscriptionListener listener) {
        this.listener = listener;
    }

    public void connect() {
        shouldReconnect = true;
        doConnect();
    }

    private void doConnect() {
        String url = "ws://" + host + ":" + port + "/";
        if (debug) {
            url += "?debug=true";
        }

        Request request = new Request.Builder().url(url).build();
        webSocket = client.newWebSocket(request, this);
    }

    public void disconnect() {
        shouldReconnect = false;
        if (webSocket != null) {
            webSocket.close(1000, "Client disconnect");
            webSocket = null;
        }
        connected = false;
    }

    public void sendAudio(byte[] pcmData) {
        if (webSocket != null && connected) {
            webSocket.send(ByteString.of(pcmData));
        }
    }

    public boolean isConnected() {
        return connected;
    }

    @Override
    public void onOpen(WebSocket webSocket, Response response) {
        connected = true;
        if (listener != null) listener.onConnected();
    }

    @Override
    public void onMessage(WebSocket webSocket, String text) {
        try {
            JsonObject json = gson.fromJson(text, JsonObject.class);
            String type = json.has("type") ? json.get("type").getAsString() : "";

            if ("transcription".equals(type)) {
                String transcriptionText = json.has("text") ? json.get("text").getAsString() : "";
                boolean isFinal = json.has("final") && json.get("final").getAsBoolean();
                if (listener != null) {
                    listener.onTranscription(transcriptionText, isFinal);
                }
            } else if ("error".equals(type)) {
                String errorMsg = json.has("message") ? json.get("message").getAsString() : "Unknown error";
                if (listener != null) listener.onError(errorMsg);
            }
        } catch (Exception e) {
            if (listener != null) listener.onError("Parse error: " + e.getMessage());
        }
    }

    @Override
    public void onFailure(WebSocket webSocket, Throwable t, Response response) {
        connected = false;
        if (shouldReconnect) {
            if (listener != null) listener.onError("WebSocket error: " + t.getMessage() + " (retrying...)");
            // Auto-reconnect after 2 seconds
            new Thread(() -> {
                try { Thread.sleep(2000); } catch (InterruptedException ignored) { return; }
                if (shouldReconnect) doConnect();
            }).start();
        } else {
            if (listener != null) listener.onError("WebSocket error: " + t.getMessage());
            if (listener != null) listener.onDisconnected();
        }
    }

    @Override
    public void onClosed(WebSocket webSocket, int code, String reason) {
        connected = false;
        if (listener != null) listener.onDisconnected();
    }
}
