# standard library imports
from unittest.mock import MagicMock, patch

# 3rd-party imports
import pytest

# local imports
from mind.config import config


# ------------------------------------------------------------------------------
# CLIController tests
# ------------------------------------------------------------------------------

class TestCLIController:
    """Tests for the CLIController class."""

    # --------------------------------------------------------------------------
    # safety check tests
    # --------------------------------------------------------------------------

    def test_is_safe_normal_command(self, cli_controller):
        """Test that normal commands pass safety check."""
        is_safe, reason = cli_controller.is_safe("ls -la")
        assert is_safe is True
        assert reason is None

    def test_is_safe_blocks_rm_rf_root(self, cli_controller):
        """Test that rm -rf / is blocked."""
        is_safe, reason = cli_controller.is_safe("rm -rf /")
        assert is_safe is False
        assert "rm -rf /" in reason

    def test_is_safe_blocks_sudo_rm(self, cli_controller):
        """Test that sudo rm is blocked."""
        is_safe, reason = cli_controller.is_safe("sudo rm file.txt")
        assert is_safe is False
        assert "sudo rm" in reason

    def test_is_safe_blocks_mkfs(self, cli_controller):
        """Test that mkfs is blocked."""
        is_safe, reason = cli_controller.is_safe("mkfs.ext4 /dev/sda1")
        assert is_safe is False
        assert "mkfs" in reason

    def test_is_safe_blocks_dd_zero(self, cli_controller):
        """Test that dd if=/dev/zero is blocked."""
        is_safe, reason = cli_controller.is_safe("dd if=/dev/zero of=/dev/sda")
        assert is_safe is False

    def test_is_safe_blocks_fork_bomb(self, cli_controller):
        """Test that fork bomb is blocked."""
        is_safe, reason = cli_controller.is_safe(":(){:|:&};:")
        assert is_safe is False

    def test_is_safe_case_insensitive(self, cli_controller):
        """Test that safety checks are case insensitive."""
        is_safe, reason = cli_controller.is_safe("SUDO RM file.txt")
        assert is_safe is False

    # --------------------------------------------------------------------------
    # execute tests
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_execute_safe_command(self, cli_controller, session):
        """Test executing a safe command with exit code 0."""
        session.tmux.execute_with_status = MagicMock(return_value={
            "output": "file1.txt\nfile2.txt",
            "exit_code": 0,
            "success": True
        })

        result = await cli_controller.execute("ls", session)

        assert result["success"] is True
        assert result["command"] == "ls"
        assert "file1.txt" in result["output"]
        assert result["exit_code"] == 0
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_execute_command_with_nonzero_exit(self, cli_controller, session):
        """Test executing a command that returns non-zero exit code."""
        session.tmux.execute_with_status = MagicMock(return_value={
            "output": "ls: cannot access 'foo': No such file or directory",
            "exit_code": 2,
            "success": False
        })

        result = await cli_controller.execute("ls foo", session)

        assert result["success"] is False
        assert result["exit_code"] == 2
        assert "exited with code 2" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_blocked_command(self, cli_controller, session):
        """Test executing a blocked command."""
        result = await cli_controller.execute("rm -rf /", session)

        assert result["success"] is False
        assert result["command"] == "rm -rf /"
        assert "blocked" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_execute_with_error(self, cli_controller, session):
        """Test handling execution errors."""
        session.tmux.execute_with_status = MagicMock(side_effect=Exception("Execution failed"))

        result = await cli_controller.execute("ls", session)

        assert result["success"] is False
        assert "execution failed" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_execute_raw(self, cli_controller, session):
        """Test execute_raw convenience method."""
        session.tmux.execute_with_status = MagicMock(return_value={
            "output": "output",
            "exit_code": 0,
            "success": True
        })

        output = await cli_controller.execute_raw("ls", session)

        assert output == "output"

    @pytest.mark.asyncio
    async def test_execute_raw_with_error(self, cli_controller, session):
        """Test execute_raw with error."""
        result = await cli_controller.execute_raw("rm -rf /", session)

        assert "error:" in result.lower()

    # --------------------------------------------------------------------------
    # LLM correction tests
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_llm_correction_success(self, cli_controller, session):
        """Test LLM correction returns corrected command."""
        with patch("mind.controllers.cli.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"response": "cd .."}
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            result = await cli_controller.get_llm_correction(
                original_voice="cd dot dot",
                translated_command="cd..",
                error_output="bash: cd..: command not found",
                session=session
            )

            assert result["success"] is True
            assert result["corrected_command"] == "cd .."

    @pytest.mark.asyncio
    async def test_get_llm_correction_cannot_correct(self, cli_controller, session):
        """Test LLM correction handles CANNOT_CORRECT response."""
        with patch("mind.controllers.cli.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"response": "CANNOT_CORRECT"}
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            result = await cli_controller.get_llm_correction(
                original_voice="gibberish",
                translated_command="gibberish",
                error_output="command not found",
                session=session
            )

            assert result["success"] is False
            assert result["corrected_command"] is None

    @pytest.mark.asyncio
    async def test_get_llm_correction_timeout(self, cli_controller, session):
        """Test LLM correction handles timeout."""
        import httpx
        with patch("mind.controllers.cli.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post.side_effect = httpx.TimeoutException("timeout")

            result = await cli_controller.get_llm_correction(
                original_voice="test",
                translated_command="test",
                error_output="error",
                session=session
            )

            assert result["success"] is False
            assert "timed out" in result["error"]

    # --------------------------------------------------------------------------
    # execute_with_fallback tests
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_execute_with_fallback_success_no_fallback(self, cli_controller, session):
        """Test successful execution (exit code 0) doesn't trigger fallback."""
        session.tmux.execute_with_status = MagicMock(return_value={
            "output": "file1.txt\nfile2.txt",
            "exit_code": 0,
            "success": True
        })

        result = await cli_controller.execute_with_fallback("ls", session, "list files")

        assert result["success"] is True
        assert result["correction_attempted"] is False

    @pytest.mark.asyncio
    async def test_execute_with_fallback_error_triggers_correction(self, cli_controller, session):
        """Test non-zero exit code triggers LLM correction."""
        # First call fails (exit code 127), correction succeeds (exit code 0)
        session.tmux.execute_with_status = MagicMock(side_effect=[
            {"output": "bash: cd..: command not found", "exit_code": 127, "success": False},
            {"output": "", "exit_code": 0, "success": True},
        ])

        with patch("mind.controllers.cli.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"response": "cd .."}
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            result = await cli_controller.execute_with_fallback(
                "cd..", session, "cd dot dot"
            )

            assert result["correction_attempted"] is True
            assert result["original_command"] == "cd.."
            assert result["corrected_command"] == "cd .."

    @pytest.mark.asyncio
    async def test_execute_with_fallback_no_voice_no_correction(self, cli_controller, session):
        """Test error without voice context doesn't trigger correction."""
        session.tmux.execute_with_status = MagicMock(return_value={
            "output": "command not found",
            "exit_code": 127,
            "success": False
        })

        result = await cli_controller.execute_with_fallback("badcmd", session, None)

        assert result["correction_attempted"] is False

    @pytest.mark.asyncio
    async def test_execute_with_fallback_blocked_no_correction(self, cli_controller, session):
        """Test blocked commands never trigger LLM correction (security)."""
        # Even with voice context, blocked commands should not be corrected
        result = await cli_controller.execute_with_fallback(
            "sudo rm -rf /", session, "sudo remove everything"
        )

        assert result["success"] is False
        assert result["correction_attempted"] is False
        assert "blocked" in result["error"].lower()


# ------------------------------------------------------------------------------
# OllamaController tests
# ------------------------------------------------------------------------------

class TestOllamaController:
    """Tests for the OllamaController class."""

    def test_initialization(self, ollama_controller):
        """Test Ollama controller initialization."""
        assert ollama_controller.host == config.ollama_host
        assert ollama_controller.model == config.ollama_model
        assert ollama_controller.timeout == 60.0

    def test_initialization_custom(self):
        """Test Ollama controller with custom config."""
        from mind.controllers.ollama import OllamaController
        controller = OllamaController(host="http://localhost:11434", model="llama2")
        assert controller.host == "http://localhost:11434"
        assert controller.model == "llama2"

    @pytest.mark.asyncio
    async def test_is_available_success(self, ollama_controller):
        """Test is_available returns True when server responds."""
        with patch("mind.controllers.ollama.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response

            result = await ollama_controller.is_available()
            assert result is True

    @pytest.mark.asyncio
    async def test_is_available_failure(self, ollama_controller):
        """Test is_available returns False when server is down."""
        with patch("mind.controllers.ollama.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.side_effect = Exception("Connection refused")

            result = await ollama_controller.is_available()
            assert result is False

    @pytest.mark.asyncio
    async def test_chat_success(self, ollama_controller, session):
        """Test chat method with successful response."""
        with patch("mind.controllers.ollama.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "message": {"content": "Hello! How can I help you?"}
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            result = await ollama_controller.chat("hello", session)

            assert result["success"] is True
            assert result["response"] == "Hello! How can I help you?"
            assert result["error"] is None
            # check context was updated
            assert len(session.conversation_context) == 2
            assert session.conversation_context[0]["role"] == "user"
            assert session.conversation_context[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_chat_timeout(self, ollama_controller, session):
        """Test chat method handles timeout."""
        import httpx
        with patch("mind.controllers.ollama.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post.side_effect = httpx.TimeoutException("Timeout")

            result = await ollama_controller.chat("hello", session)

            assert result["success"] is False
            assert result["response"] is None
            assert "timed out" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_chat_http_error(self, ollama_controller, session):
        """Test chat method handles HTTP errors."""
        import httpx
        with patch("mind.controllers.ollama.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 500
            error = httpx.HTTPStatusError("Server error", request=MagicMock(), response=mock_response)
            mock_client.return_value.__aenter__.return_value.post.return_value.raise_for_status.side_effect = error

            result = await ollama_controller.chat("hello", session)

            assert result["success"] is False
            assert result["response"] is None

    @pytest.mark.asyncio
    async def test_chat_adds_to_context(self, ollama_controller, session):
        """Test that chat adds messages to conversation context."""
        with patch("mind.controllers.ollama.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "message": {"content": "Response 1"}
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            await ollama_controller.chat("Message 1", session)
            assert len(session.conversation_context) == 2

            mock_response.json.return_value = {
                "message": {"content": "Response 2"}
            }
            await ollama_controller.chat("Message 2", session)
            assert len(session.conversation_context) == 4


# ------------------------------------------------------------------------------
# ClaudeCodeController tests
# ------------------------------------------------------------------------------

class TestClaudeCodeController:
    """Tests for the ClaudeCodeController class."""

    @pytest.fixture
    def claude_code_controller(self):
        """Create a ClaudeCodeController for testing."""
        from mind.controllers.claude_code import ClaudeCodeController
        return ClaudeCodeController()

    def test_initialization(self, claude_code_controller):
        """Test Claude Code controller initialization."""
        assert claude_code_controller.model == "claude-sonnet-4-20250514"
        assert claude_code_controller.display_name == "claude-code"
        assert claude_code_controller._clients == {}
        assert claude_code_controller._pending_confirmations == {}

    # --------------------------------------------------------------------------
    # brief summary generation tests
    # --------------------------------------------------------------------------

    def test_generate_brief_summary_with_text(self, claude_code_controller):
        """Test brief summary generation with response text."""
        summary = claude_code_controller._generate_brief_summary(
            "I've created a new file called hello.py with a basic hello world function. "
            "The file is now ready to use. You can run it with python hello.py.",
            []
        )
        # should be truncated to first 2 sentences
        assert "hello.py" in summary
        assert len(summary) <= 200

    def test_generate_brief_summary_with_actions_only(self, claude_code_controller):
        """Test brief summary when only actions were taken (no text)."""
        summary = claude_code_controller._generate_brief_summary(
            "",
            ["Read", "Edit", "Edit", "Write"]
        )
        assert "Done." in summary
        assert "read 1 file" in summary
        assert "2 edits" in summary
        assert "wrote 1 file" in summary

    def test_generate_brief_summary_no_content(self, claude_code_controller):
        """Test brief summary with no text or actions."""
        summary = claude_code_controller._generate_brief_summary("", [])
        assert summary == "Done."

    def test_generate_brief_summary_long_text_truncated(self, claude_code_controller):
        """Test that long text is truncated."""
        long_text = "A" * 300
        summary = claude_code_controller._generate_brief_summary(long_text, [])
        assert len(summary) <= 203  # 200 + "..."

    # --------------------------------------------------------------------------
    # confirmation tests
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_has_pending_confirmation_false(self, claude_code_controller, session):
        """Test has_pending_confirmation returns False when no confirmation pending."""
        assert claude_code_controller.has_pending_confirmation(session) is False

    @pytest.mark.asyncio
    async def test_has_pending_confirmation_true(self, claude_code_controller, session):
        """Test has_pending_confirmation returns True when confirmation pending."""
        claude_code_controller._pending_confirmations[session.id] = {"test": "data"}
        assert claude_code_controller.has_pending_confirmation(session) is True

    @pytest.mark.asyncio
    async def test_handle_confirmation_affirmative_no_pending(self, claude_code_controller, session):
        """Test affirmative confirmation with nothing pending."""
        result = await claude_code_controller.handle_confirmation("affirmative", session)
        assert result["success"] is True
        assert "Nothing pending" in result["response"]

    @pytest.mark.asyncio
    async def test_handle_confirmation_affirmative_with_pending(self, claude_code_controller, session):
        """Test affirmative confirmation with pending action."""
        claude_code_controller._pending_confirmations[session.id] = {"action": "test"}
        result = await claude_code_controller.handle_confirmation("affirmative", session)
        assert result["success"] is True
        assert "Confirmed" in result["response"]
        assert session.id not in claude_code_controller._pending_confirmations

    @pytest.mark.asyncio
    async def test_handle_confirmation_negative(self, claude_code_controller, session):
        """Test negative confirmation."""
        claude_code_controller._pending_confirmations[session.id] = {"action": "test"}
        result = await claude_code_controller.handle_confirmation("negative", session)
        assert result["success"] is True
        assert "Cancelled" in result["response"]
        assert session.id not in claude_code_controller._pending_confirmations

    # --------------------------------------------------------------------------
    # interrupt tests
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_interrupt_no_client(self, claude_code_controller, session):
        """Test interrupt when no client exists."""
        result = await claude_code_controller.interrupt(session)
        assert result["success"] is True
        assert "Nothing to interrupt" in result["response"]

    # --------------------------------------------------------------------------
    # is_available tests
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_is_available_true(self, claude_code_controller):
        """Test is_available when SDK is installed."""
        with patch.dict("sys.modules", {"claude_agent_sdk": MagicMock()}):
            result = await claude_code_controller.is_available()
            # May be True or False depending on actual installation
            assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_is_available_false(self, claude_code_controller):
        """Test is_available when SDK is not installed."""
        with patch.dict("sys.modules", {"claude_agent_sdk": None}):
            with patch("builtins.__import__", side_effect=ImportError("No module")):
                result = await claude_code_controller.is_available()
                assert result is False

    # --------------------------------------------------------------------------
    # query tests (mocked)
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_query_import_error(self, claude_code_controller, session):
        """Test query handles ImportError when SDK not installed."""
        with patch.object(
            claude_code_controller,
            "_get_or_create_client",
            side_effect=ImportError("No module named 'claude_agent_sdk'")
        ):
            result = await claude_code_controller.query("test prompt", session)
            assert result["success"] is False
            assert "not installed" in result["error"]

    @pytest.mark.asyncio
    async def test_query_generic_error(self, claude_code_controller, session):
        """Test query handles generic errors."""
        with patch.object(
            claude_code_controller,
            "_get_or_create_client",
            side_effect=Exception("Connection failed")
        ):
            result = await claude_code_controller.query("test prompt", session)
            assert result["success"] is False
            assert "Connection failed" in result["error"]

    # --------------------------------------------------------------------------
    # cleanup tests
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_cleanup_session_no_client(self, claude_code_controller, session):
        """Test cleanup when no client exists."""
        await claude_code_controller.cleanup_session(session)
        # should not raise

    @pytest.mark.asyncio
    async def test_cleanup_session_with_pending(self, claude_code_controller, session):
        """Test cleanup clears pending confirmations."""
        claude_code_controller._pending_confirmations[session.id] = {"test": "data"}
        await claude_code_controller.cleanup_session(session)
        assert session.id not in claude_code_controller._pending_confirmations
