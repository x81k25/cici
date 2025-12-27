# Sample Conversation Sequences

Test scenarios for validating Cici's mode behavior and transitions.

## API Overview

**Endpoints used:**
- `POST /text` - Send user input, returns `{"status": "ok"}` or `{"status": "error", "error": "..."}`
- `GET /messages` - Poll for responses, returns messages + current mode + working directory

**Message types in responses:**
- `system` - Mode changes, cancellations
- `llm_response` - From Ollama (hermes3) or Claude Code (claude-code)
- `cli_result` - Command execution results
- `error` - Error messages

---

## Ollama Mode Tests

### Basic Chat

```
# Request 1
POST /text {"text": "Hey, what's the weather usually like in December?"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "llm_response",
      "content": "<non-deterministic conversational response>",
      "model": "hermes3",
      "success": true
    }
  ],
  "mode": "ollama",
  "current_directory": "/infra/experiments/cici"
}

# Request 2 (context-aware follow-up)
POST /text {"text": "And what about in Australia?"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "llm_response",
      "content": "<non-deterministic response mentioning southern hemisphere>",
      "model": "hermes3",
      "success": true
    }
  ],
  "mode": "ollama",
  "current_directory": "/infra/experiments/cici"
}
```

### Context Retention

```
# Request 1
POST /text {"text": "My favorite color is blue"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "llm_response",
      "content": "<non-deterministic acknowledgment>",
      "model": "hermes3",
      "success": true
    }
  ],
  "mode": "ollama",
  "current_directory": "/infra/experiments/cici"
}

# Request 2
POST /text {"text": "What did I just tell you?"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "llm_response",
      "content": "<non-deterministic response referencing blue/favorite color>",
      "model": "hermes3",
      "success": true
    }
  ],
  "mode": "ollama",
  "current_directory": "/infra/experiments/cici"
}
```

---

## CLI Mode Tests

### Basic Commands

```
# Enter CLI mode
POST /text {"text": "cli mode"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "system",
      "content": "Switched to CLI mode",
      "mode_changed": true,
      "new_mode": "cli"
    }
  ],
  "mode": "cli",
  "current_directory": "/infra/experiments/cici"
}

# Execute command
POST /text {"text": "list files"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "cli_result",
      "command": "ls",
      "output": "<directory listing>",
      "exit_code": 0,
      "success": true,
      "correction_attempted": false
    }
  ],
  "mode": "cli",
  "current_directory": "/infra/experiments/cici"
}

# Another command
POST /text {"text": "show current directory"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "cli_result",
      "command": "pwd",
      "output": "/infra/experiments/cici",
      "exit_code": 0,
      "success": true,
      "correction_attempted": false
    }
  ],
  "mode": "cli",
  "current_directory": "/infra/experiments/cici"
}
```

### Natural Language Translation

```
# Enter terminal mode
POST /text {"text": "terminal mode"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "system",
      "content": "Switched to CLI mode",
      "mode_changed": true,
      "new_mode": "cli"
    }
  ],
  "mode": "cli",
  "current_directory": "/infra/experiments/cici"
}

# Natural language to command
POST /text {"text": "what processes are using the most memory"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "cli_result",
      "command": "ps aux --sort=-%mem | head",
      "output": "<process listing>",
      "exit_code": 0,
      "success": true,
      "correction_attempted": false
    }
  ],
  "mode": "cli",
  "current_directory": "/infra/experiments/cici"
}

# Create folder
POST /text {"text": "create a folder called test-folder"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "cli_result",
      "command": "mkdir test-folder",
      "output": "",
      "exit_code": 0,
      "success": true,
      "correction_attempted": false
    }
  ],
  "mode": "cli",
  "current_directory": "/infra/experiments/cici"
}
```

### Command Correction

```
# Enter commands mode
POST /text {"text": "commands mode"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "system",
      "content": "Switched to CLI mode",
      "mode_changed": true,
      "new_mode": "cli"
    }
  ],
  "mode": "cli",
  "current_directory": "/infra/experiments/cici"
}

# Typo command - LLM corrects it
POST /text {"text": "gti status"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "cli_result",
      "command": "git status",
      "output": "<git status output>",
      "exit_code": 0,
      "success": true,
      "correction_attempted": true,
      "original_command": "gti status",
      "corrected_command": "git status"
    }
  ],
  "mode": "cli",
  "current_directory": "/infra/experiments/cici"
}
```

---

## Claude Code Mode Tests

### Basic Coding Tasks

```
# Enter code mode
POST /text {"text": "code mode"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "system",
      "content": "Switched to Claude Code mode",
      "mode_changed": true,
      "new_mode": "claude_code"
    }
  ],
  "mode": "claude_code",
  "current_directory": "/infra/experiments/cici"
}

# Read file request
POST /text {"text": "read the main.py file in the mind directory"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "llm_response",
      "content": "<non-deterministic summary of main.py contents>",
      "model": "claude-code",
      "success": true
    }
  ],
  "mode": "claude_code",
  "current_directory": "/infra/experiments/cici"
}

# Follow-up question
POST /text {"text": "what functions are defined there"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "llm_response",
      "content": "<non-deterministic list of functions>",
      "model": "claude-code",
      "success": true
    }
  ],
  "mode": "claude_code",
  "current_directory": "/infra/experiments/cici"
}
```

### File Operations

```
# Enter coding mode
POST /text {"text": "let's code"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "system",
      "content": "Switched to Claude Code mode",
      "mode_changed": true,
      "new_mode": "claude_code"
    }
  ],
  "mode": "claude_code",
  "current_directory": "/infra/experiments/cici"
}

# Create file
POST /text {"text": "create a simple hello world python script in the tests folder"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "llm_response",
      "content": "<non-deterministic confirmation of file creation>",
      "model": "claude-code",
      "success": true
    }
  ],
  "mode": "claude_code",
  "current_directory": "/infra/experiments/cici"
}

# Run script
POST /text {"text": "now run it"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "llm_response",
      "content": "<non-deterministic output showing Hello World>",
      "model": "claude-code",
      "success": true
    }
  ],
  "mode": "claude_code",
  "current_directory": "/infra/experiments/cici"
}
```

### Confirmations

```
# Enter coding mode
POST /text {"text": "coding mode"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "system",
      "content": "Switched to Claude Code mode",
      "mode_changed": true,
      "new_mode": "claude_code"
    }
  ],
  "mode": "claude_code",
  "current_directory": "/infra/experiments/cici"
}

# Destructive operation (Claude asks for confirmation)
POST /text {"text": "delete all .pyc files in the project"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "llm_response",
      "content": "<non-deterministic confirmation request>",
      "model": "claude-code",
      "success": true
    }
  ],
  "mode": "claude_code",
  "current_directory": "/infra/experiments/cici"
}

# User confirms
POST /text {"text": "affirmative"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "llm_response",
      "content": "<non-deterministic confirmation of deletion>",
      "model": "claude-code",
      "success": true
    }
  ],
  "mode": "claude_code",
  "current_directory": "/infra/experiments/cici"
}

# -- OR user declines --

POST /text {"text": "negative"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "llm_response",
      "content": "<non-deterministic cancellation acknowledgment>",
      "model": "claude-code",
      "success": true
    }
  ],
  "mode": "claude_code",
  "current_directory": "/infra/experiments/cici"
}
```

---

## Mode Switching Tests

### Ollama to CLI and Back

```
# Start in Ollama mode (default)
POST /text {"text": "What is Python used for?"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "llm_response",
      "content": "<non-deterministic response about Python>",
      "model": "hermes3",
      "success": true
    }
  ],
  "mode": "ollama",
  "current_directory": "/infra/experiments/cici"
}

# Switch to CLI
POST /text {"text": "cli mode"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "system",
      "content": "Switched to CLI mode",
      "mode_changed": true,
      "new_mode": "cli"
    }
  ],
  "mode": "cli",
  "current_directory": "/infra/experiments/cici"
}

# Run command
POST /text {"text": "python --version"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "cli_result",
      "command": "python --version",
      "output": "Python 3.x.x",
      "exit_code": 0,
      "success": true,
      "correction_attempted": false
    }
  ],
  "mode": "cli",
  "current_directory": "/infra/experiments/cici"
}

# Switch back to Ollama
POST /text {"text": "back to chat"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "system",
      "content": "Switched to Ollama mode",
      "mode_changed": true,
      "new_mode": "ollama"
    }
  ],
  "mode": "ollama",
  "current_directory": "/infra/experiments/cici"
}

# Continue conversation (context preserved)
POST /text {"text": "Tell me more about Python's history"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "llm_response",
      "content": "<non-deterministic response about Python history>",
      "model": "hermes3",
      "success": true
    }
  ],
  "mode": "ollama",
  "current_directory": "/infra/experiments/cici"
}
```

### CLI to Code Mode

```
# Enter terminal mode
POST /text {"text": "terminal mode"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "system",
      "content": "Switched to CLI mode",
      "mode_changed": true,
      "new_mode": "cli"
    }
  ],
  "mode": "cli",
  "current_directory": "/infra/experiments/cici"
}

# List directory
POST /text {"text": "ls mind/"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "cli_result",
      "command": "ls mind/",
      "output": "<directory listing>",
      "exit_code": 0,
      "success": true,
      "correction_attempted": false
    }
  ],
  "mode": "cli",
  "current_directory": "/infra/experiments/cici"
}

# Switch to Claude Code
POST /text {"text": "let's code"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "system",
      "content": "Switched to Claude Code mode",
      "mode_changed": true,
      "new_mode": "claude_code"
    }
  ],
  "mode": "claude_code",
  "current_directory": "/infra/experiments/cici"
}

# Ask about code
POST /text {"text": "explain what the session.py file does"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "llm_response",
      "content": "<non-deterministic explanation of session.py>",
      "model": "claude-code",
      "success": true
    }
  ],
  "mode": "claude_code",
  "current_directory": "/infra/experiments/cici"
}
```

### Rapid Mode Switching

```
# CLI mode
POST /text {"text": "cli mode"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [{"type": "system", "mode_changed": true, "new_mode": "cli"}],
  "mode": "cli",
  "current_directory": "/infra/experiments/cici"
}

# Chat mode
POST /text {"text": "chat mode"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [{"type": "system", "mode_changed": true, "new_mode": "ollama"}],
  "mode": "ollama",
  "current_directory": "/infra/experiments/cici"
}

# Code mode
POST /text {"text": "code mode"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [{"type": "system", "mode_changed": true, "new_mode": "claude_code"}],
  "mode": "claude_code",
  "current_directory": "/infra/experiments/cici"
}

# Ollama mode
POST /text {"text": "ollama mode"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [{"type": "system", "mode_changed": true, "new_mode": "ollama"}],
  "mode": "ollama",
  "current_directory": "/infra/experiments/cici"
}
```

### Context Preservation Across Modes

```
# Start in Ollama (default)
POST /text {"text": "Remember the number 42"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "llm_response",
      "content": "<non-deterministic acknowledgment>",
      "model": "hermes3",
      "success": true
    }
  ],
  "mode": "ollama",
  "current_directory": "/infra/experiments/cici"
}

# Switch to CLI
POST /text {"text": "commands mode"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [{"type": "system", "mode_changed": true, "new_mode": "cli"}],
  "mode": "cli",
  "current_directory": "/infra/experiments/cici"
}

# Run command
POST /text {"text": "echo hello"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "cli_result",
      "command": "echo hello",
      "output": "hello",
      "exit_code": 0,
      "success": true,
      "correction_attempted": false
    }
  ],
  "mode": "cli",
  "current_directory": "/infra/experiments/cici"
}

# Return to Ollama
POST /text {"text": "exit cli"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [{"type": "system", "mode_changed": true, "new_mode": "ollama"}],
  "mode": "ollama",
  "current_directory": "/infra/experiments/cici"
}

# Test context retention
POST /text {"text": "What number did I ask you to remember?"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "llm_response",
      "content": "<non-deterministic response mentioning 42>",
      "model": "hermes3",
      "success": true
    }
  ],
  "mode": "ollama",
  "current_directory": "/infra/experiments/cici"
}
```

---

## Edge Cases

### Ambiguous Input

```
# Enter CLI mode
POST /text {"text": "cli mode"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [{"type": "system", "mode_changed": true, "new_mode": "cli"}],
  "mode": "cli",
  "current_directory": "/infra/experiments/cici"
}

# Ambiguous "help"
POST /text {"text": "help"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "cli_result",
      "command": "help",
      "output": "<shell help output or error>",
      "exit_code": 0,
      "success": true,
      "correction_attempted": false
    }
  ],
  "mode": "cli",
  "current_directory": "/infra/experiments/cici"
}
```

### Mode Keyword in Regular Speech

```
# In Ollama mode (default)
POST /text {"text": "I was thinking about switching to code mode for my project"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "llm_response",
      "content": "<non-deterministic conversational response, NOT a mode switch>",
      "model": "hermes3",
      "success": true
    }
  ],
  "mode": "ollama",
  "current_directory": "/infra/experiments/cici"
}
```

### Empty or Unclear Commands

```
# Enter terminal mode
POST /text {"text": "terminal mode"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [{"type": "system", "mode_changed": true, "new_mode": "cli"}],
  "mode": "cli",
  "current_directory": "/infra/experiments/cici"
}

# Unclear command
POST /text {"text": "do the thing"}
Response: {"status": "ok"}

GET /messages
Response:
{
  "messages": [
    {
      "type": "cli_result",
      "success": false,
      "error": "<non-deterministic error or clarification request>"
    }
  ],
  "mode": "cli",
  "current_directory": "/infra/experiments/cici"
}
```
