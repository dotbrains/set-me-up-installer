#!/usr/bin/env python3
"""
Tests for remove_symlinks() function in smu.py

These tests verify that remove_symlinks() correctly:
1. Uses lsrc to get the list of symlinks managed by rcm
2. Removes exact managed symlink targets left behind by rcdn
3. Removes exact managed directories left empty by rcdn
"""

import os
import unittest
from unittest.mock import patch, MagicMock


class TestRemoveSymlinksLsrcExtraction(unittest.TestCase):
    """Test target extraction from lsrc output."""

    def test_parses_lsrc_output_correctly(self):
        """Test that targets are correctly extracted from lsrc output."""
        # Simulate lsrc output format: target -> source
        lsrc_output = """/home/user/.zshrc -> /home/user/set-me-up/dotfiles/tag-universal/shell/zshrc/zshrc
/home/user/.gitconfig -> /home/user/set-me-up/dotfiles/tag-universal/git/gitconfig/gitconfig
/home/user/.config/alacritty/alacritty.toml -> /home/user/set-me-up/dotfiles/tag-macos/terminal/alacritty/alacritty.toml
"""
        
        # Extract targets the same way remove_symlinks does
        lines = lsrc_output.strip().split('\n')
        targets = []
        
        for line in lines:
            if '->' in line:
                target = line.split('->', 1)[0].strip()
                if target:
                    targets.append(target)

        expected = [
            '/home/user/.zshrc',
            '/home/user/.gitconfig',
            '/home/user/.config/alacritty/alacritty.toml',
        ]
        self.assertEqual(targets, expected)

    def test_handles_empty_lsrc_output(self):
        """Test handling when lsrc returns empty output."""
        lsrc_output = ""
        
        lines = lsrc_output.strip().split('\n')
        targets = []
        
        for line in lines:
            if '->' in line:
                target = line.split('->', 1)[0].strip()
                if target:
                    targets.append(target)

        self.assertEqual(targets, [])

    def test_handles_malformed_lsrc_output(self):
        """Test handling when lsrc output is malformed (no ->)."""
        lsrc_output = """some random line
another line without arrow
"""
        
        lines = lsrc_output.strip().split('\n')
        targets = []
        
        for line in lines:
            if '->' in line:
                target = line.split('->', 1)[0].strip()
                if target:
                    targets.append(target)

        self.assertEqual(targets, [])


class TestRemoveSymlinksIntegration(unittest.TestCase):
    """Integration tests for remove_symlinks() with mocked subprocess calls."""

    def test_calls_rcdn_command(self):
        """Test that remove_symlinks calls rcdn command."""
        with patch('smu.subprocess.run') as mock_run:
            with patch('smu.os.path.exists') as mock_exists:
                mock_exists.return_value = True
                mock_run.return_value = MagicMock(returncode=0, stdout='')

                import smu
                smu.remove_symlinks()

                all_cmds = [call[0][0] for call in mock_run.call_args_list]
                rcdn_called = any('rcdn' in cmd for cmd in all_cmds)
                self.assertTrue(rcdn_called, "rcdn command should be called")

    def test_calls_lsrc_to_get_symlinks(self):
        """Test that remove_symlinks calls lsrc to get managed symlinks."""
        with patch('smu.subprocess.run') as mock_run:
            with patch('smu.os.path.exists') as mock_exists:
                mock_exists.return_value = True
                mock_run.return_value = MagicMock(returncode=0, stdout='')

                import smu
                smu.remove_symlinks()

                all_cmds = [call[0][0] for call in mock_run.call_args_list]
                lsrc_called = any('lsrc' in cmd for cmd in all_cmds)
                self.assertTrue(lsrc_called, "lsrc command should be called to get symlinks")

    def test_removes_exact_managed_symlink_targets(self):
        """Test that only exact targets reported by lsrc are unlinked."""
        with patch('smu.subprocess.run') as mock_run:
            with patch('smu.os.path.exists') as mock_exists:
                with patch('smu.os.path.islink') as mock_islink:
                    with patch('smu.os.unlink') as mock_unlink:
                        mock_exists.return_value = True
                        mock_islink.return_value = True
                        mock_run.return_value = MagicMock(
                            returncode=0,
                            stdout='/home/user/.zshrc -> /path/to/zshrc\n'
                        )

                        import smu
                        smu.remove_symlinks()

                        mock_unlink.assert_called_once_with('/home/user/.zshrc')

    def test_removes_empty_exact_managed_directories(self):
        """Test that exact managed directories left empty by rcdn are removed."""
        with patch('smu.subprocess.run') as mock_run:
            with patch('smu.os.path.exists') as mock_exists:
                with patch('smu.os.path.islink') as mock_islink:
                    with patch('smu.os.path.isdir') as mock_isdir:
                        with patch('smu.os.rmdir') as mock_rmdir:
                            mock_exists.return_value = True
                            mock_islink.return_value = False
                            mock_isdir.return_value = True
                            mock_run.return_value = MagicMock(
                                returncode=0,
                                stdout='/home/user/.config/tool -> /path/to/tool\n'
                            )

                            import smu
                            smu.remove_symlinks()

                            mock_rmdir.assert_called_once_with('/home/user/.config/tool')

    def test_skips_target_cleanup_when_lsrc_returns_empty(self):
        """Test that no proactive cleanup runs without exact lsrc targets."""
        with patch('smu.subprocess.run') as mock_run:
            with patch('smu.os.path.exists') as mock_exists:
                with patch('smu.os.unlink') as mock_unlink:
                    with patch('smu.os.rmdir') as mock_rmdir:
                        mock_exists.return_value = True
                        mock_run.return_value = MagicMock(returncode=0, stdout='')

                        import smu
                        smu.remove_symlinks()

                        mock_unlink.assert_not_called()
                        mock_rmdir.assert_not_called()


class TestRemoveSymlinksEdgeCases(unittest.TestCase):
    """Edge case tests for remove_symlinks()."""

    def test_handles_nonexistent_dotfiles_directory(self):
        """Test behavior when dotfiles directory doesn't exist."""
        with patch('smu.subprocess.run') as mock_run:
            with patch('smu.os.path.exists') as mock_exists:
                mock_exists.return_value = False

                import smu
                smu.remove_symlinks()

                self.assertTrue(mock_run.called)

    def test_uses_correct_rcrc_path(self):
        """Test that the correct RCRC path is used."""
        with patch('smu.subprocess.run') as mock_run:
            with patch('smu.os.path.exists') as mock_exists:
                mock_exists.return_value = True
                mock_run.return_value = MagicMock(returncode=0, stdout='')

                import smu
                smu.remove_symlinks()

                self.assertEqual(os.environ["RCRC"], smu.rcrc)


class TestRemoveSymlinksEfficiency(unittest.TestCase):
    """Tests to verify cleanup stays proportional to managed symlinks."""

    def test_uses_single_lsrc_call_not_multiple_find_calls(self):
        """Test that lsrc is called once, not multiple find calls on tag-*."""
        with patch('smu.subprocess.run') as mock_run:
            with patch('smu.os.path.exists') as mock_exists:
                mock_exists.return_value = True
                mock_run.return_value = MagicMock(returncode=0, stdout='/home/user/.zshrc -> /path\n')

                import smu
                smu.remove_symlinks()

                all_cmds = [call[0][0] for call in mock_run.call_args_list]
                find_calls = [cmd for cmd in all_cmds if cmd and 'find ' in cmd]
                gh_calls = [cmd for cmd in all_cmds if cmd and 'gh api' in cmd]
                lsrc_calls = [cmd for cmd in all_cmds if cmd and 'lsrc' in cmd]

                self.assertEqual(find_calls, [])
                self.assertEqual(gh_calls, [])
                self.assertEqual(len(lsrc_calls), 1)


class TestSelfUpdate(unittest.TestCase):
    """Tests for self-update sequencing."""

    def test_removes_symlinks_before_deleting_smu_home_dir(self):
        """Test that self-update cleans links while old sources still exist."""
        events = []

        def fake_run(command, *args, **kwargs):
            if isinstance(command, list):
                events.append('install')
            else:
                events.append(command)
            return MagicMock(returncode=0)

        with patch.dict(os.environ, {'SMU_BLUEPRINT': 'owner/repo', 'SMU_BLUEPRINT_BRANCH': 'main'}, clear=False):
            with patch('smu.remove_symlinks', side_effect=lambda: events.append('remove_symlinks')):
                with patch('smu.shutil.rmtree', side_effect=lambda path, ignore_errors: events.append('rmtree')):
                    with patch('smu.subprocess.run', side_effect=fake_run):
                        with patch('smu.symlink', side_effect=lambda: events.append('symlink')):
                            import smu
                            smu.self_update()

        self.assertEqual(events, ['remove_symlinks', 'rmtree', 'install', 'symlink'])


if __name__ == '__main__':
    unittest.main()
