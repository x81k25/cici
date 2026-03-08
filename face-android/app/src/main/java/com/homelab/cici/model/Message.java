package com.homelab.cici.model;

public class Message {
    public enum Type {
        USER,
        ASSISTANT,
        SYSTEM,
        CLI_COMMAND,
        CLI_OUTPUT,
        ERROR,
        TRANSCRIPTION
    }

    private final Type type;
    private final String content;
    private final long timestamp;

    public Message(Type type, String content) {
        this.type = type;
        this.content = content;
        this.timestamp = System.currentTimeMillis();
    }

    public Type getType() { return type; }
    public String getContent() { return content; }
    public long getTimestamp() { return timestamp; }
}
