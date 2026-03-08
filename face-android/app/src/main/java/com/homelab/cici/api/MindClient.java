package com.homelab.cici.api;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

public class MindClient {
    private static final MediaType JSON = MediaType.get("application/json; charset=utf-8");
    private final OkHttpClient client;
    private final Gson gson = new Gson();
    private String baseUrl;
    private String mode = "unknown";
    private String currentDirectory = "";

    public MindClient(String host, int port) {
        this.baseUrl = "http://" + host + ":" + port;
        this.client = new OkHttpClient.Builder()
                .connectTimeout(5, TimeUnit.SECONDS)
                .readTimeout(120, TimeUnit.SECONDS)
                .writeTimeout(10, TimeUnit.SECONDS)
                .build();
    }

    public void updateEndpoint(String host, int port) {
        this.baseUrl = "http://" + host + ":" + port;
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

    public static class ProcessResult {
        public final List<MessageEntry> messages;
        public final String mode;
        public final String currentDirectory;

        public ProcessResult(List<MessageEntry> messages, String mode, String currentDirectory) {
            this.messages = messages;
            this.mode = mode;
            this.currentDirectory = currentDirectory;
        }
    }

    public static class MessageEntry {
        public final String type;
        public final String content;
        public final String model;
        public final String command;
        public final Integer exitCode;

        public MessageEntry(String type, String content, String model, String command, Integer exitCode) {
            this.type = type;
            this.content = content;
            this.model = model;
            this.command = command;
            this.exitCode = exitCode;
        }
    }

    public ProcessResult processText(String text, String originalVoice) throws IOException {
        JsonObject body = new JsonObject();
        body.addProperty("text", text);
        if (originalVoice != null) {
            body.addProperty("original_voice", originalVoice);
        }

        RequestBody requestBody = RequestBody.create(body.toString(), JSON);
        Request request = new Request.Builder()
                .url(baseUrl + "/text")
                .post(requestBody)
                .build();

        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new IOException("MIND returned " + response.code());
            }
        }

        return pollMessages();
    }

    public ProcessResult pollMessages() throws IOException {
        Request request = new Request.Builder()
                .url(baseUrl + "/messages")
                .build();

        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new IOException("MIND returned " + response.code());
            }

            String responseBody = response.body().string();
            JsonObject json = gson.fromJson(responseBody, JsonObject.class);

            this.mode = json.has("mode") ? json.get("mode").getAsString() : "unknown";
            this.currentDirectory = json.has("current_directory") ? json.get("current_directory").getAsString() : "";

            List<MessageEntry> messages = new ArrayList<>();
            if (json.has("messages")) {
                JsonArray arr = json.getAsJsonArray("messages");
                for (JsonElement el : arr) {
                    JsonObject msg = el.getAsJsonObject();
                    String type = msg.has("type") ? msg.get("type").getAsString() : "";
                    String content = msg.has("content") ? msg.get("content").getAsString() : "";
                    String model = msg.has("model") ? msg.get("model").getAsString() : null;
                    String command = msg.has("command") ? msg.get("command").getAsString() : null;
                    Integer exitCode = msg.has("exit_code") && !msg.get("exit_code").isJsonNull()
                            ? msg.get("exit_code").getAsInt() : null;
                    messages.add(new MessageEntry(type, content, model, command, exitCode));
                }
            }

            return new ProcessResult(messages, this.mode, this.currentDirectory);
        }
    }

    public String getMode() { return mode; }
    public String getCurrentDirectory() { return currentDirectory; }
    public String getBaseUrl() { return baseUrl; }
}
