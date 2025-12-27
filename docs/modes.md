# Cici Modes

## Ollama Mode (Default)

```mermaid
stateDiagram-v2
    state "Any Mode" as Any {
        [*] --> [*]
    }
    state "Ollama Mode" as Ollama

    Any --> Ollama : "back to chat"
    Any --> Ollama : "chat mode"
    Any --> Ollama : "ollama mode"
    Any --> Ollama : "exit cli"
```

Conversational mode. Input routes to local Ollama (hermes3) for chat responses.
- Maintains conversation context (50 message limit)
- Context preserved when switching modes

## CLI Mode

```mermaid
stateDiagram-v2
    state "Any Mode" as Any {
        [*] --> [*]
    }
    state "CLI Mode" as CLI

    Any --> CLI : "commands mode"
    Any --> CLI : "cli mode"
    Any --> CLI : "terminal mode"
```

Command execution mode. Input executes as shell commands via tmux.
- Voice-to-CLI translation for natural commands
- LLM fallback for failed command correction

## Claude Code Mode

```mermaid
stateDiagram-v2
    state "Any Mode" as Any {
        [*] --> [*]
    }
    state "Claude Code Mode" as ClaudeCode

    Any --> ClaudeCode : "let's code"
    Any --> ClaudeCode : "code mode"
    Any --> ClaudeCode : "coding mode"
```

Coding assistant mode using Claude Agent SDK. Input routes to Claude Code for:
- Reading/writing/editing files
- Running shell commands
- Searching codebases
- Multi-step coding tasks

### Features
- **Session continuity**: Claude remembers context across exchanges
- **Working directory**: Uses tmux pwd, defaults to cici project dir
- **Brief output**: Responses optimized for voice (1-2 sentences)
- **Confirmations**: Use "affirmative" or "negative" for yes/no prompts

## Claude Queries

```mermaid
stateDiagram-v2
    state "Any Mode" as Any {
        [*] --> [*]
    }

    state "Claude API" as Claude

    Any --> Claude : "ask claude {question}"
    Claude --> Any : response
```

Stateless API calls to Claude (claude-sonnet). Works from any mode without changing mode state. Returns response in `llm_response` with `model: "claude-sonnet"`.
