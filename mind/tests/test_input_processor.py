# standard library imports
from unittest.mock import AsyncMock, patch, MagicMock

# 3rd-party imports
import pytest


# ------------------------------------------------------------------------------
# InputProcessor tests
# ------------------------------------------------------------------------------

class TestInputProcessor:
    """Tests for the InputProcessor class."""

    # --------------------------------------------------------------------------
    # stop word detection tests
    # --------------------------------------------------------------------------

    def test_detect_stop_word_exact_match(self, input_processor):
        """Test stop word detection with exact match."""
        assert input_processor.detect_stop_word("stop") is True
        assert input_processor.detect_stop_word("cancel") is True
        assert input_processor.detect_stop_word("abort") is True

    def test_detect_stop_word_end_of_sentence(self, input_processor):
        """Test stop word at end of sentence."""
        assert input_processor.detect_stop_word("please stop") is True
        assert input_processor.detect_stop_word("hey cici stop") is True

    def test_detect_stop_word_with_punctuation(self, input_processor):
        """Test stop word with punctuation."""
        assert input_processor.detect_stop_word("stop.") is True
        assert input_processor.detect_stop_word("please stop!") is True

    def test_detect_stop_word_case_insensitive(self, input_processor):
        """Test case insensitivity of stop word detection."""
        assert input_processor.detect_stop_word("STOP") is True
        assert input_processor.detect_stop_word("Stop") is True
        assert input_processor.detect_stop_word("CANCEL") is True

    def test_detect_stop_word_no_match(self, input_processor):
        """Test no false positives for non-stop words."""
        assert input_processor.detect_stop_word("hello") is False
        assert input_processor.detect_stop_word("ls -la") is False
        assert input_processor.detect_stop_word("stopping") is False  # partial match

    def test_detect_stop_word_empty_input(self, input_processor):
        """Test empty input handling."""
        assert input_processor.detect_stop_word("") is False
        assert input_processor.detect_stop_word(None) is False

    # --------------------------------------------------------------------------
    # text processing tests
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_process_text_basic(self, input_processor, session):
        """Test basic text processing."""
        result = await input_processor.process_text("ls minus la", session)

        assert result["type"] == "text"
        assert result["original"] == "ls minus la"
        assert result["translated"] == "ls -la"
        assert result["stop_detected"] is False

    @pytest.mark.asyncio
    async def test_process_text_stop_word(self, input_processor, session):
        """Test text processing with stop word."""
        result = await input_processor.process_text("stop", session)

        assert result["type"] == "stop"
        assert result["stop_detected"] is True
        assert result["translated"] is None

    @pytest.mark.asyncio
    async def test_process_text_complex_command(self, input_processor, session):
        """Test text processing with complex command."""
        result = await input_processor.process_text(
            "git commit dash m quote hello quote",
            session
        )

        assert result["type"] == "text"
        assert result["stop_detected"] is False
        assert result["translated"] is not None

    @pytest.mark.asyncio
    async def test_process_text_updates_activity(self, input_processor, session):
        """Test that processing text updates session activity."""
        import time

        initial_activity = session.last_activity
        time.sleep(0.01)

        await input_processor.process_text("test", session)

        assert session.last_activity > initial_activity

    @pytest.mark.asyncio
    async def test_process_text_ask_claude_skip_translation(self, input_processor, session):
        """Test that 'ask claude' commands skip translation."""
        result = await input_processor.process_text("ask claude what is python", session)

        assert result["type"] == "text"
        assert result["stop_detected"] is False
        # ask claude should pass through unchanged
        assert result["translated"] == "ask claude what is python"

    # --------------------------------------------------------------------------
    # stop word management tests
    # --------------------------------------------------------------------------

    def test_add_stop_word(self, input_processor):
        """Test adding a custom stop word."""
        input_processor.add_stop_word("quit")
        assert input_processor.detect_stop_word("quit") is True

    def test_add_duplicate_stop_word(self, input_processor):
        """Test adding a duplicate stop word (should not duplicate)."""
        initial_count = len(input_processor.stop_words)
        input_processor.add_stop_word("stop")
        assert len(input_processor.stop_words) == initial_count

    def test_remove_stop_word(self, input_processor):
        """Test removing a stop word."""
        input_processor.add_stop_word("quit")
        result = input_processor.remove_stop_word("quit")

        assert result is True
        assert input_processor.detect_stop_word("quit") is False

    def test_remove_nonexistent_stop_word(self, input_processor):
        """Test removing a stop word that doesn't exist."""
        result = input_processor.remove_stop_word("nonexistent")
        assert result is False


# ------------------------------------------------------------------------------
# Voice-to-CLI Translation tests
# ------------------------------------------------------------------------------

class TestVoiceToCliTranslation:
    """Tests for voice-to-CLI translation accuracy."""

    # --------------------------------------------------------------------------
    # basic command tests
    # --------------------------------------------------------------------------

    def test_translation_ls_minus_la(self):
        """Test 'ls minus la' -> 'ls -la'."""
        from mind.core.translation import parse_voice_to_cli
        assert parse_voice_to_cli("ls minus la") == "ls -la"

    def test_translation_cd_dot_dot(self):
        """Test 'cd dot dot' -> 'cd ..'."""
        from mind.core.translation import parse_voice_to_cli
        assert parse_voice_to_cli("cd dot dot") == "cd .."

    def test_translation_cd_dot(self):
        """Test 'cd dot' -> 'cd .'."""
        from mind.core.translation import parse_voice_to_cli
        assert parse_voice_to_cli("cd dot") == "cd ."

    def test_translation_git_status(self):
        """Test 'git status' passes through unchanged."""
        from mind.core.translation import parse_voice_to_cli
        assert parse_voice_to_cli("git status") == "git status"

    def test_translation_pwd(self):
        """Test 'pwd' passes through unchanged."""
        from mind.core.translation import parse_voice_to_cli
        assert parse_voice_to_cli("pwd") == "pwd"

    # --------------------------------------------------------------------------
    # dotfile and path tests
    # --------------------------------------------------------------------------

    def test_translation_ls_dot_hidden(self):
        """Test 'ls dot hidden' -> 'ls .hidden'."""
        from mind.core.translation import parse_voice_to_cli
        assert parse_voice_to_cli("ls dot hidden") == "ls .hidden"

    def test_translation_cat_dot_bashrc(self):
        """Test 'cat dot bashrc' -> 'cat .bashrc'."""
        from mind.core.translation import parse_voice_to_cli
        assert parse_voice_to_cli("cat dot bashrc") == "cat .bashrc"

    def test_translation_dot_slash_script(self):
        """Test 'dot slash script' -> './script'."""
        from mind.core.translation import parse_voice_to_cli
        assert parse_voice_to_cli("dot slash script") == "./script"

    def test_translation_dot_dot_slash_foo(self):
        """Test 'dot dot slash foo' -> '../foo'."""
        from mind.core.translation import parse_voice_to_cli
        assert parse_voice_to_cli("dot dot slash foo") == "../foo"

    # --------------------------------------------------------------------------
    # file extension tests
    # --------------------------------------------------------------------------

    def test_translation_cat_file_dot_txt(self):
        """Test 'cat file dot txt' -> 'cat file.txt'."""
        from mind.core.translation import parse_voice_to_cli
        assert parse_voice_to_cli("cat file dot txt") == "cat file.txt"

    def test_translation_vim_test_dot_py(self):
        """Test 'vim test dot py' -> 'vim test.py'."""
        from mind.core.translation import parse_voice_to_cli
        assert parse_voice_to_cli("vim test dot py") == "vim test.py"

    def test_translation_nano_config_dot_yaml(self):
        """Test 'nano config dot yaml' -> 'nano config.yaml'."""
        from mind.core.translation import parse_voice_to_cli
        assert parse_voice_to_cli("nano config dot yaml") == "nano config.yaml"

    # --------------------------------------------------------------------------
    # flag and option tests
    # --------------------------------------------------------------------------

    def test_translation_double_dash_help(self):
        """Test 'git double dash help' -> 'git --help'."""
        from mind.core.translation import parse_voice_to_cli
        assert parse_voice_to_cli("git double dash help") == "git --help"

    def test_translation_grep_minus_r(self):
        """Test 'grep minus r pattern' -> 'grep -r pattern'."""
        from mind.core.translation import parse_voice_to_cli
        assert parse_voice_to_cli("grep minus r pattern") == "grep -r pattern"

    def test_translation_rm_minus_rf(self):
        """Test 'rm minus rf folder' -> 'rm -rf folder'."""
        from mind.core.translation import parse_voice_to_cli
        assert parse_voice_to_cli("rm minus rf folder") == "rm -rf folder"

    # --------------------------------------------------------------------------
    # NATO alphabet tests
    # --------------------------------------------------------------------------

    def test_translation_nato_ls(self):
        """Test NATO 'lima sierra' -> 'ls'."""
        from mind.core.translation import parse_voice_to_cli
        assert parse_voice_to_cli("lima sierra") == "ls"

    def test_translation_nato_cd(self):
        """Test NATO 'charlie dixie' -> 'cd'."""
        from mind.core.translation import parse_voice_to_cli
        assert parse_voice_to_cli("charlie dixie") == "cd"

    # --------------------------------------------------------------------------
    # symbol tests
    # --------------------------------------------------------------------------

    def test_translation_pipe(self):
        """Test 'ls pipe grep foo' -> 'ls | grep foo'."""
        from mind.core.translation import parse_voice_to_cli
        # pipe should remain with spaces around it for readability
        result = parse_voice_to_cli("ls pipe grep foo")
        assert "|" in result
        assert "grep" in result

    def test_translation_redirect(self):
        """Test 'echo hello greater than file' -> 'echo hello > file'."""
        from mind.core.translation import parse_voice_to_cli
        result = parse_voice_to_cli("echo hello greater than file")
        assert ">" in result

    def test_translation_tilde_home(self):
        """Test 'cd tilde' -> 'cd ~'."""
        from mind.core.translation import parse_voice_to_cli
        assert parse_voice_to_cli("cd tilde") == "cd ~"

    # --------------------------------------------------------------------------
    # integration tests with input processor
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_input_processor_cd_dot_dot(self, input_processor, session):
        """Test input processor correctly translates 'cd dot dot'."""
        result = await input_processor.process_text("cd dot dot", session)
        assert result["translated"] == "cd .."

    @pytest.mark.asyncio
    async def test_input_processor_ls_minus_la(self, input_processor, session):
        """Test input processor correctly translates 'ls minus la'."""
        result = await input_processor.process_text("ls minus la", session)
        assert result["translated"] == "ls -la"

    @pytest.mark.asyncio
    async def test_input_processor_cat_dot_bashrc(self, input_processor, session):
        """Test input processor correctly translates 'cat dot bashrc'."""
        result = await input_processor.process_text("cat dot bashrc", session)
        assert result["translated"] == "cat .bashrc"
