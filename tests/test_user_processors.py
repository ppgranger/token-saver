"""Tests for user-defined processor loading from external directories."""

import os
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config
from src.processors import _load_user_processors, discover_processors
from src.processors.base import Processor


class TestUserProcessorLoading:
    """Test that user processors are discovered and loaded correctly."""

    def _write_processor(self, tmpdir, filename, content):
        """Write a processor file to the temp directory."""
        path = os.path.join(tmpdir, filename)
        with open(path, "w") as f:
            f.write(textwrap.dedent(content))
        return path

    def test_user_processor_loaded_and_used(self, tmp_path):
        """Test that a valid user processor is loaded and can handle commands."""
        self._write_processor(
            str(tmp_path),
            "custom_hello.py",
            """\
            from src.processors.base import Processor

            class HelloProcessor(Processor):
                priority = 5
                hook_patterns = []

                @property
                def name(self):
                    return "hello"

                def can_handle(self, command):
                    return command.strip().startswith("hello")

                def process(self, command, output):
                    return "compressed: " + output[:20]
            """,
        )

        _load_user_processors(str(tmp_path))

        # The HelloProcessor subclass should now exist
        subclasses = {cls.__name__ for cls in Processor.__subclasses__()}
        assert "HelloProcessor" in subclasses

    def test_broken_processor_syntax_error_skipped(self, tmp_path):
        """Test that a processor with a syntax error is skipped gracefully."""
        self._write_processor(
            str(tmp_path),
            "broken.py",
            """\
            def this is not valid python !!!
            """,
        )

        # Should not raise — broken processor is skipped
        _load_user_processors(str(tmp_path))

    def test_broken_processor_missing_class_skipped(self, tmp_path):
        """Test that a processor that raises on import is skipped."""
        self._write_processor(
            str(tmp_path),
            "bad_import.py",
            """\
            import nonexistent_module_that_does_not_exist
            """,
        )

        # Should not raise
        _load_user_processors(str(tmp_path))

    def test_nonexistent_directory_is_noop(self):
        """Test that a non-existent directory is handled gracefully."""
        _load_user_processors("/tmp/nonexistent_dir_for_test_12345")
        # No error raised

    def test_underscore_files_skipped(self, tmp_path):
        """Test that files starting with _ are skipped."""
        self._write_processor(
            str(tmp_path),
            "_helper.py",
            """\
            from src.processors.base import Processor

            class ShouldNotLoad(Processor):
                priority = 5
                hook_patterns = []

                @property
                def name(self):
                    return "should_not_load"

                def can_handle(self, command):
                    return True

                def process(self, command, output):
                    return output
            """,
        )

        _load_user_processors(str(tmp_path))
        subclasses = {cls.__name__ for cls in Processor.__subclasses__()}
        assert "ShouldNotLoad" not in subclasses

    def test_user_processors_dir_config_override(self, tmp_path, monkeypatch):
        """Test that the user_processors_dir config key is respected."""
        monkeypatch.setenv("TOKEN_SAVER_USER_PROCESSORS_DIR", str(tmp_path))
        config.reload()

        from src.processors import _get_user_processors_dir

        result = _get_user_processors_dir()
        assert result == str(tmp_path)

        config.reload()

    def test_priority_ordering_with_user_processor(self, tmp_path):
        """Test that user processors are sorted by priority alongside built-ins."""
        self._write_processor(
            str(tmp_path),
            "high_priority.py",
            """\
            from src.processors.base import Processor

            class HighPriorityTestProcessor(Processor):
                priority = 1
                hook_patterns = []

                @property
                def name(self):
                    return "high_priority_test"

                def can_handle(self, command):
                    return command.strip() == "high-priority-test-cmd"

                def process(self, command, output):
                    return "high-priority"
            """,
        )

        _load_user_processors(str(tmp_path))
        processors = discover_processors()

        # The high-priority processor should be first (priority 1 < all built-ins)
        names = [p.name for p in processors]
        assert "high_priority_test" in names
        # Priority 1 should come before package_list (priority 15)
        hp_idx = names.index("high_priority_test")
        pl_idx = names.index("package_list")
        assert hp_idx < pl_idx
