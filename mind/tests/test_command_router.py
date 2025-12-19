# standard library imports
from unittest.mock import AsyncMock, patch, MagicMock

# 3rd-party imports
import pytest


# ------------------------------------------------------------------------------
# CommandRouter tests
# ------------------------------------------------------------------------------

class TestCommandRouter:
    """Tests for the CommandRouter class."""

    # --------------------------------------------------------------------------
    # parse_command tests
    # --------------------------------------------------------------------------

    def test_parse_command_basic_cli(self, command_router):
        """Test parsing a basic CLI command."""
        cmd_type, cmd_text, params = command_router.parse_command("ls -la")

        assert cmd_type == "cli"
        assert cmd_text == "ls -la"

    def test_parse_command_with_hey_cici_prefix(self, command_router):
        """Test parsing with Hey Cici prefix."""
        cmd_type, cmd_text, params = command_router.parse_command(
            "Hey Cici, ls -la"
        )

        assert cmd_type == "cli"
        assert cmd_text == "ls -la"

    def test_parse_command_hey_cici_variations(self, command_router):
        """Test various Hey Cici prefix variations."""
        prefixes = ["hey cici", "hey sissy", "hey cc", "cici"]

        for prefix in prefixes:
            cmd_type, cmd_text, params = command_router.parse_command(
                f"{prefix}, ls -la"
            )
            assert cmd_type == "cli"
            assert cmd_text == "ls -la"

    def test_parse_command_commands_mode(self, command_router):
        """Test parsing 'commands mode' enters CLI mode."""
        cmd_type, cmd_text, params = command_router.parse_command(
            "Hey Cici, commands mode"
        )

        assert cmd_type == "cli_enter"

    def test_parse_command_cli_mode(self, command_router):
        """Test parsing 'cli mode' enters CLI mode."""
        cmd_type, cmd_text, params = command_router.parse_command(
            "cici cli mode"
        )

        assert cmd_type == "cli_enter"

    def test_parse_command_empty_input(self, command_router):
        """Test parsing empty input."""
        cmd_type, cmd_text, params = command_router.parse_command("")

        assert cmd_type is None
        assert cmd_text is None

    def test_parse_command_none_input(self, command_router):
        """Test parsing None input."""
        cmd_type, cmd_text, params = command_router.parse_command(None)

        assert cmd_type is None

    # --------------------------------------------------------------------------
    # route tests - Ollama mode (default)
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_route_default_is_ollama_mode(self, command_router, session):
        """Test that default interaction_mode is Ollama."""
        assert session.interaction_mode == "ollama"

    @pytest.mark.asyncio
    async def test_route_ollama_mode_routes_to_ollama(self, command_router, session):
        """Test that in Ollama mode (default), text routes to Ollama."""
        assert session.interaction_mode == "ollama"

        with patch("mind.controllers.ollama.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "message": {"content": "Hello! How can I help?"}
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            result = await command_router.route("what is python?", session)

            assert result["type"] == "ollama"
            assert result["result"]["success"] is True

    @pytest.mark.asyncio
    async def test_route_ollama_mode_enter_cli(self, command_router, session):
        """Test entering CLI mode from Ollama mode."""
        assert session.interaction_mode == "ollama"

        result = await command_router.route("commands mode", session)

        assert result["type"] == "cli_enter"
        assert session.interaction_mode == "cli"

    # --------------------------------------------------------------------------
    # route tests - CLI mode
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_route_cli_mode_executes_commands(self, command_router, session):
        """Test that CLI mode executes commands."""
        session.enter_cli_mode()
        session.tmux.execute_with_status = MagicMock(return_value={
            "output": "file1.txt\nfile2.txt",
            "exit_code": 0,
            "success": True
        })

        result = await command_router.route("ls", session)

        assert result["type"] == "cli"
        assert result["result"]["success"] is True

    @pytest.mark.asyncio
    async def test_route_cli_mode_exit_to_ollama(self, command_router, session):
        """Test exiting CLI mode back to Ollama."""
        session.enter_cli_mode()
        assert session.interaction_mode == "cli"

        result = await command_router.route("back to chat", session)

        assert result["type"] == "ollama_enter"
        assert session.interaction_mode == "ollama"

    @pytest.mark.asyncio
    async def test_route_cli_mode_big_brain_exits(self, command_router, session):
        """Test 'big brain time' exits CLI mode (returns to Ollama default)."""
        session.enter_cli_mode()
        assert session.interaction_mode == "cli"

        result = await command_router.route("big brain time", session)

        assert result["type"] == "ollama_enter"
        assert session.interaction_mode == "ollama"

    @pytest.mark.asyncio
    async def test_route_triggered_command(self, command_router, session):
        """Test routing a triggered command from config."""
        session.enter_cli_mode()
        with patch('mind.command_router.check_command_trigger') as mock_trigger:
            mock_trigger.return_value = ("cli", "echo 'triggered'", "test")
            session.tmux.execute_with_status = MagicMock(return_value={
                "output": "triggered",
                "exit_code": 0,
                "success": True
            })

            result = await command_router.route("trigger test", session)

            assert result["type"] == "trigger"

    # --------------------------------------------------------------------------
    # CLI mode trigger tests
    # --------------------------------------------------------------------------

    def test_parse_command_chat_mode_exits_cli(self, command_router):
        """Test 'chat mode' exits CLI mode."""
        cmd_type, cmd_text, params = command_router.parse_command(
            "Hey Cici, chat mode"
        )

        assert cmd_type == "cli_exit"

    def test_parse_command_exit_cli(self, command_router):
        """Test 'exit cli' exits CLI mode."""
        cmd_type, cmd_text, params = command_router.parse_command(
            "cici exit cli"
        )

        assert cmd_type == "cli_exit"

    def test_parse_command_back_to_chat(self, command_router):
        """Test 'back to chat' exits CLI mode."""
        cmd_type, cmd_text, params = command_router.parse_command(
            "back to chat"
        )

        assert cmd_type == "cli_exit"

    # --------------------------------------------------------------------------
    # integration tests
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_full_flow_ollama_to_cli_and_back(self, command_router, session):
        """Test full flow: Ollama mode -> CLI mode -> back to Ollama."""
        # start in Ollama mode (default)
        assert session.interaction_mode == "ollama"

        # enter CLI mode
        result = await command_router.route("commands mode", session)
        assert result["type"] == "cli_enter"
        assert session.interaction_mode == "cli"

        # execute a command
        session.tmux.execute_with_status = MagicMock(return_value={
            "output": "output",
            "exit_code": 0,
            "success": True
        })
        result = await command_router.route("ls", session)
        assert result["type"] == "cli"

        # exit CLI mode
        result = await command_router.route("back to chat", session)
        assert result["type"] == "ollama_enter"
        assert session.interaction_mode == "ollama"

    # --------------------------------------------------------------------------
    # Claude Code mode tests
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_route_enter_claude_code_from_ollama(self, command_router, session):
        """Test entering Claude Code mode from Ollama mode."""
        assert session.interaction_mode == "ollama"

        result = await command_router.route("let's code", session)

        assert result["type"] == "claude_code_enter"
        assert session.interaction_mode == "claude_code"
        assert "Entering code mode" in result["confirmation"]["message"]

    @pytest.mark.asyncio
    async def test_route_enter_claude_code_from_cli(self, command_router, session):
        """Test entering Claude Code mode from CLI mode."""
        session.enter_cli_mode()
        assert session.interaction_mode == "cli"

        result = await command_router.route("let's code", session)

        assert result["type"] == "claude_code_enter"
        assert session.interaction_mode == "claude_code"

    @pytest.mark.asyncio
    async def test_route_enter_claude_code_variations(self, command_router, session):
        """Test all Claude Code entrance triggers."""
        triggers = ["let's code", "lets code", "code mode", "coding mode"]

        for trigger in triggers:
            # reset to ollama mode
            session.interaction_mode = "ollama"

            result = await command_router.route(trigger, session)

            assert result["type"] == "claude_code_enter", f"Failed for trigger: {trigger}"
            assert session.interaction_mode == "claude_code", f"Failed for trigger: {trigger}"

    @pytest.mark.asyncio
    async def test_route_exit_claude_code_to_ollama(self, command_router, session):
        """Test exiting Claude Code mode to Ollama mode."""
        session.enter_claude_code_mode()
        assert session.interaction_mode == "claude_code"

        result = await command_router.route("back to chat", session)

        assert result["type"] == "ollama_enter"
        assert session.interaction_mode == "ollama"

    @pytest.mark.asyncio
    async def test_route_exit_claude_code_to_cli(self, command_router, session):
        """Test switching from Claude Code to CLI mode."""
        session.enter_claude_code_mode()
        assert session.interaction_mode == "claude_code"

        result = await command_router.route("commands mode", session)

        assert result["type"] == "cli_enter"
        assert session.interaction_mode == "cli"

    @pytest.mark.asyncio
    async def test_route_claude_code_mode_query(self, command_router, session):
        """Test that Claude Code mode routes to Claude Code controller."""
        session.enter_claude_code_mode()

        with patch.object(
            command_router.claude_code_controller,
            "query",
            new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = {
                "success": True,
                "content": "Done.",
                "model": "claude-code",
                "error": None,
                "awaiting_confirmation": False,
                "confirmation_prompt": None
            }

            result = await command_router.route("add a hello function", session)

            assert result["type"] == "claude_code"
            mock_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_route_claude_code_confirmation_affirmative(self, command_router, session):
        """Test affirmative confirmation in Claude Code mode."""
        session.enter_claude_code_mode()

        # set up pending confirmation
        command_router.claude_code_controller._pending_confirmations[session.id] = {"test": True}

        with patch.object(
            command_router.claude_code_controller,
            "handle_confirmation",
            new_callable=AsyncMock
        ) as mock_handle:
            mock_handle.return_value = {
                "success": True,
                "content": "Confirmed.",
                "model": "claude-code",
                "error": None,
                "awaiting_confirmation": False,
                "confirmation_prompt": None
            }

            result = await command_router.route("affirmative", session)

            assert result["type"] == "claude_code"
            mock_handle.assert_called_once_with("affirmative", session)

    @pytest.mark.asyncio
    async def test_route_claude_code_confirmation_negative(self, command_router, session):
        """Test negative confirmation in Claude Code mode."""
        session.enter_claude_code_mode()

        # set up pending confirmation
        command_router.claude_code_controller._pending_confirmations[session.id] = {"test": True}

        with patch.object(
            command_router.claude_code_controller,
            "handle_confirmation",
            new_callable=AsyncMock
        ) as mock_handle:
            mock_handle.return_value = {
                "success": True,
                "content": "Cancelled.",
                "model": "claude-code",
                "error": None,
                "awaiting_confirmation": False,
                "confirmation_prompt": None
            }

            result = await command_router.route("negative", session)

            assert result["type"] == "claude_code"
            mock_handle.assert_called_once_with("negative", session)

    @pytest.mark.asyncio
    async def test_full_flow_with_claude_code(self, command_router, session):
        """Test full flow including Claude Code mode."""
        # start in Ollama mode (default)
        assert session.interaction_mode == "ollama"

        # enter Claude Code mode
        result = await command_router.route("let's code", session)
        assert result["type"] == "claude_code_enter"
        assert session.interaction_mode == "claude_code"

        # switch to CLI mode
        result = await command_router.route("commands mode", session)
        assert result["type"] == "cli_enter"
        assert session.interaction_mode == "cli"

        # switch back to Claude Code mode
        result = await command_router.route("code mode", session)
        assert result["type"] == "claude_code_enter"
        assert session.interaction_mode == "claude_code"

        # return to Ollama mode
        result = await command_router.route("chat mode", session)
        assert result["type"] == "ollama_enter"
        assert session.interaction_mode == "ollama"
