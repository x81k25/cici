# standard library imports
import re
import subprocess
import time

# 3rd-party imports
from loguru import logger


class TmuxSession:
    """
    Manages a tmux session for command execution.

    Each user session gets its own tmux session, named to match the session ID.
    Commands are sent to the tmux session and output is captured from it.
    """

    def __init__(self, session_name: str):
        """
        Initialize tmux session manager.

        Args:
            session_name: Name for the tmux session
        """
        self.session_name = session_name
        self.created = False

    def exists(self) -> bool:
        """Check if the tmux session already exists."""
        result = subprocess.run(
            ["tmux", "has-session", "-t", self.session_name],
            capture_output=True
        )
        return result.returncode == 0

    def create(self) -> bool:
        """
        Create the tmux session if it doesn't exist.

        Returns:
            True if session was created or already exists, False on error
        """
        if self.exists():
            logger.info(f"tmux session '{self.session_name}' already exists")
            self.created = True
            return True

        try:
            # create detached session
            result = subprocess.run(
                ["tmux", "new-session", "-d", "-s", self.session_name],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                logger.info(f"created tmux session '{self.session_name}'")
                self.created = True
                return True
            else:
                logger.error(f"failed to create tmux session: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"error creating tmux session: {e}")
            return False

    def send_command(self, command: str) -> bool:
        """
        Send a command to the tmux session.

        Args:
            command: The command to execute

        Returns:
            True if command was sent successfully
        """
        if not self.created and not self.create():
            return False

        try:
            # send keys to the tmux session
            result = subprocess.run(
                ["tmux", "send-keys", "-t", self.session_name, command, "Enter"],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                logger.debug(f"sent command to tmux: {command}")
                return True
            else:
                logger.error(f"failed to send command: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"error sending command to tmux: {e}")
            return False

    def capture_output(self, wait_seconds: float = 0.5, max_lines: int = 1000) -> str:
        """
        Capture the current pane output from the tmux session.

        Args:
            wait_seconds: Time to wait for command to complete before capturing
            max_lines: Maximum number of lines to capture from history

        Returns:
            The captured output as a string
        """
        if not self.exists():
            return "error: tmux session does not exist"

        # wait for command to produce output
        time.sleep(wait_seconds)

        try:
            # capture pane content
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", self.session_name, "-p", "-S", f"-{max_lines}"],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                return result.stdout.strip()
            else:
                logger.error(f"failed to capture output: {result.stderr}")
                return f"error capturing output: {result.stderr}"

        except Exception as e:
            logger.error(f"error capturing tmux output: {e}")
            return f"error: {str(e)}"

    def execute(self, command: str, wait_seconds: float = 0.5) -> str:
        """
        Execute a command and return its output.

        This is a convenience method that:
        1. Creates the session if needed
        2. Clears the pane
        3. Sends the command
        4. Waits and captures output

        Args:
            command: The command to execute
            wait_seconds: Time to wait for output

        Returns:
            The command output
        """
        result = self.execute_with_status(command, wait_seconds)
        return result["output"]

    def execute_with_status(self, command: str, wait_seconds: float = 0.5) -> dict:
        """
        Execute a command and return output with exit status.

        Args:
            command: The command to execute
            wait_seconds: Time to wait for output

        Returns:
            Dict with:
            {
                "output": str,
                "exit_code": int | None,
                "success": bool
            }
        """
        # ensure session exists
        if not self.created and not self.create():
            return {
                "output": "error: could not create tmux session",
                "exit_code": None,
                "success": False
            }

        # clear the pane first to get clean output
        subprocess.run(
            ["tmux", "send-keys", "-t", self.session_name, "clear", "Enter"],
            capture_output=True
        )
        time.sleep(0.1)

        # send the command
        if not self.send_command(command):
            return {
                "output": "error: failed to send command to tmux",
                "exit_code": None,
                "success": False
            }

        # wait for command to complete
        time.sleep(wait_seconds)

        # capture command output
        output = self.capture_output(wait_seconds=0)

        # now get exit status by echoing $?
        # use a unique marker to find the exit code in output
        marker = f"__EXIT_CODE_{time.time_ns()}__"
        exit_cmd = f"echo {marker}$?{marker}"

        if not self.send_command(exit_cmd):
            return {
                "output": output,
                "exit_code": None,
                "success": True  # command ran, just couldn't get status
            }

        time.sleep(0.1)
        status_output = self.capture_output(wait_seconds=0)

        # parse exit code from marker
        exit_code = None
        match = re.search(rf"{marker}(\d+){marker}", status_output)
        if match:
            exit_code = int(match.group(1))

        return {
            "output": output,
            "exit_code": exit_code,
            "success": exit_code == 0 if exit_code is not None else True
        }

    def kill(self) -> bool:
        """Kill the tmux session."""
        if not self.exists():
            return True

        try:
            result = subprocess.run(
                ["tmux", "kill-session", "-t", self.session_name],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                logger.info(f"killed tmux session '{self.session_name}'")
                self.created = False
                return True
            else:
                logger.error(f"failed to kill tmux session: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"error killing tmux session: {e}")
            return False


def cleanup_stale_tmux_sessions(
    pattern: str = r"^\d{8}-\d{6}_",
    exclude_session: str | None = None
) -> int:
    """
    Kill all tmux sessions matching the given pattern.

    Default pattern matches our session naming convention: YYYYMMDD-HHMMSS_*

    Args:
        pattern: Regex pattern to match session names
        exclude_session: Session name to exclude from cleanup

    Returns:
        Number of sessions killed
    """
    compiled_pattern = re.compile(pattern)

    try:
        # list all tmux sessions
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            # no sessions or tmux not running
            return 0

        sessions = result.stdout.strip().split("\n")
        killed = 0

        for session_name in sessions:
            if not session_name:
                continue

            # check if matches our pattern
            if compiled_pattern.match(session_name):
                # skip excluded session
                if exclude_session and session_name == exclude_session:
                    logger.debug(f"skipping excluded session: {session_name}")
                    continue

                # kill the session
                kill_result = subprocess.run(
                    ["tmux", "kill-session", "-t", session_name],
                    capture_output=True,
                    text=True
                )

                if kill_result.returncode == 0:
                    logger.info(f"killed stale tmux session: {session_name}")
                    killed += 1
                else:
                    logger.warning(f"failed to kill session {session_name}: {kill_result.stderr}")

        return killed

    except Exception as e:
        logger.error(f"error cleaning up tmux sessions: {e}")
        return 0
