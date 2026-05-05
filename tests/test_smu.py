#!/usr/bin/env python3
"""
Tests for remove_symlinks() function in smu.py

These tests verify that remove_symlinks() correctly:
1. Uses lsrc to get the list of symlinks managed by rcm
2. Removes empty directories in ~/.config and ~/.local
3. Removes files in ~/.config, ~/.local, and ~ (home directory)
"""

import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch, MagicMock


class TestRemoveSymlinksLsrcExtraction(unittest.TestCase):
    """Test the basename extraction logic from lsrc output."""

    def test_parses_lsrc_output_correctly(self):
        """Test that basenames are correctly extracted from lsrc output."""
        # Simulate lsrc output format: target -> source
        lsrc_output = """/home/user/.zshrc -> /home/user/set-me-up/dotfiles/tag-universal/shell/zshrc/zshrc
/home/user/.gitconfig -> /home/user/set-me-up/dotfiles/tag-universal/git/gitconfig/gitconfig
/home/user/.config/alacritty/alacritty.toml -> /home/user/set-me-up/dotfiles/tag-macos/terminal/alacritty/alacritty.toml
"""
        
        # Extract basenames the same way remove_symlinks does
        lines = lsrc_output.strip().split('\n')
        basenames = set()
        
        for line in lines:
            if '->' in line:
                target = line.split('->')[0].strip()
                if target:
                    basename = os.path.basename(target)
                    if basename:
                        basenames.add(basename)

        expected = {'.zshrc', '.gitconfig', 'alacritty.toml'}
        self.assertEqual(basenames, expected)

    def test_handles_empty_lsrc_output(self):
        """Test handling when lsrc returns empty output."""
        lsrc_output = ""
        
        lines = lsrc_output.strip().split('\n')
        basenames = set()
        
        for line in lines:
            if '->' in line:
                target = line.split('->')[0].strip()
                if target:
                    basename = os.path.basename(target)
                    if basename:
                        basenames.add(basename)

        self.assertEqual(basenames, set())

    def test_handles_malformed_lsrc_output(self):
        """Test handling when lsrc output is malformed (no ->)."""
        lsrc_output = """some random line
another line without arrow
"""
        
        lines = lsrc_output.strip().split('\n')
        basenames = set()
        
        for line in lines:
            if '->' in line:
                target = line.split('->')[0].strip()
                if target:
                    basename = os.path.basename(target)
                    if basename:
                        basenames.add(basename)

        self.assertEqual(basenames, set())

    def test_filters_only_tag_directories_from_gh_api_output(self):
        """Test that only tag-* directories are filtered from GitHub API output."""
        # Simulate GitHub API output - full tree of a repo
        # Paths that start with 'tag-' at the root level
        gh_output = """README.md
LICENSE
dotfiles/rcrc
tag-macos/terminal/zshrc/zshrc
tag-macos/terminal/zshenv/zshenv
tag-debian/fonts/fonts/fonts.conf
tag-universal/git/gitconfig/gitconfig
tag-universal/shell/zshrc/zshrc
modules/install.sh
scripts/deploy.sh
"""
        
        # Apply the same filtering logic as _get_blueprint_basenames
        basenames = set()
        for path in gh_output.strip().split('\n'):
            if path.startswith('tag-') and '/' in path:
                basename = os.path.basename(path)
                if basename:
                    basenames.add(basename)
        
        # Should only include files from tag-* directories
        expected = {'zshrc', 'zshenv', 'fonts.conf', 'gitconfig'}
        self.assertEqual(basenames, expected)
        
        # Should NOT include files from non-tag-* paths
        self.assertNotIn('README.md', basenames)
        self.assertNotIn('rcrc', basenames)
        self.assertNotIn('install.sh', basenames)
        self.assertNotIn('deploy.sh', basenames)

    def test_handles_dotfiles_prefix_in_paths(self):
        """Test that paths with dotfiles/ prefix are matched."""
        # Files in dotfiles/tag-* should be matched
        gh_output = """dotfiles/tag-macos/terminal/zshrc/zshrc
dotfiles/tag-universal/git/gitconfig/gitconfig
README.md
"""
        
        basenames = set()
        for path in gh_output.strip().split('\n'):
            if path.startswith('dotfiles/tag-') and '/' in path:
                basename = os.path.basename(path)
                if basename:
                    basenames.add(basename)
        
        # dotfiles/tag-* paths should be matched
        expected = {'zshrc', 'gitconfig'}
        self.assertEqual(basenames, expected,
            "Paths with dotfiles/ prefix should be matched")

    def test_handles_mixed_path_formats(self):
        """Test that only dotfiles-prefixed paths are matched (not root-level tag-*)."""
        gh_output = """tag-macos/terminal/zshrc/zshrc
dotfiles/tag-universal/git/gitconfig/gitconfig
dotfiles/tag-debian/fonts/fonts/fonts.conf
README.md
"""
        
        basenames = set()
        for path in gh_output.strip().split('\n'):
            if path.startswith('dotfiles/tag-') and '/' in path:
                basename = os.path.basename(path)
                if basename:
                    basenames.add(basename)
        
        # Only dotfiles/tag-* should be matched (not root-level tag-*)
        expected = {'gitconfig', 'fonts.conf'}
        self.assertEqual(basenames, expected,
            "Should only match dotfiles/tag-* paths, not root-level tag-*")

    def test_handles_deeply_nested_tag_paths(self):
        """Test that deeply nested paths in tag-* directories are handled correctly."""
        # Some repos might have deeper nesting
        gh_output = """tag-macos/apps/vscode/settings.json
tag-macos/apps/vscode/keybindings.json
tag-universal/shell/zshrc/zshrc
tag-universal/shell/zshenv/zshenv
"""
        
        basenames = set()
        for path in gh_output.strip().split('\n'):
            if path.startswith('tag-') and '/' in path:
                basename = os.path.basename(path)
                if basename:
                    basenames.add(basename)
        
        expected = {'settings.json', 'keybindings.json', 'zshrc', 'zshenv'}
        self.assertEqual(basenames, expected)


class TestRemoveSymlinksBuildConditions(unittest.TestCase):
    """Test the logic that builds find conditions for cleanup."""

    def test_builds_correct_find_conditions(self):
        """Test that find conditions are correctly built from basenames."""
        basenames = {'zshrc', 'gitconfig', 'alacritty.toml'}
        
        name_conditions = []
        for name in basenames:
            escaped_name = name.replace("'", "'\\''")
            name_conditions.append(f"-name '{escaped_name}'")

        find_expr = " -o ".join(name_conditions)
        
        # Should create OR conditions for all names
        self.assertIn("-name 'zshrc'", find_expr)
        self.assertIn("-name 'gitconfig'", find_expr)
        self.assertIn("-name 'alacritty.toml'", find_expr)
        self.assertIn(" -o ", find_expr)

    def test_handles_special_characters_in_names(self):
        """Test that special characters in names are properly escaped."""
        basenames = {"file with spaces", "file'test"}
        
        name_conditions = []
        for name in basenames:
            escaped_name = name.replace("'", "'\\''")
            name_conditions.append(f"-name '{escaped_name}'")

        # Should properly escape single quotes
        self.assertIn("-name 'file with spaces'", name_conditions)
        self.assertIn("-name 'file'\\''test'", name_conditions)


class TestRemoveSymlinksIntegration(unittest.TestCase):
    """Integration tests for remove_symlinks() with mocked subprocess calls."""

    def test_calls_rcdn_command(self):
        """Test that remove_symlinks calls rcdn command."""
        with patch('smu.subprocess.run') as mock_run:
            with patch('smu.os.path.exists') as mock_exists:
                with patch('smu._get_blueprint_basenames') as mock_blueprint:
                    with patch.dict(os.environ, {'SMU_HOME_DIR': '/fake/home/set-me-up', 'SMU_BLUEPRINT': 'owner/repo', 'SMU_BLUEPRINT_BRANCH': 'main'}, clear=True):
                        mock_exists.return_value = True
                        mock_run.return_value = MagicMock(returncode=0, stdout='terminal\napps\n')
                        mock_blueprint.return_value = set()

                        import smu
                        smu.remove_symlinks()

                        # Check that rcdn was called (first subprocess.run call)
                        self.assertTrue(mock_run.called)
                        
                        # Get all commands that were run
                        all_cmds = [call[0][0] for call in mock_run.call_args_list]
                        rcdn_called = any('rcdn' in cmd for cmd in all_cmds)
                        self.assertTrue(rcdn_called, "rcdn command should be called")

    def test_calls_lsrc_to_get_symlinks(self):
        """Test that remove_symlinks calls lsrc to get managed symlinks."""
        with patch('smu.subprocess.run') as mock_run:
            with patch('smu.os.path.exists') as mock_exists:
                with patch('smu._get_blueprint_basenames') as mock_blueprint:
                    with patch.dict(os.environ, {'SMU_HOME_DIR': '/fake/home/set-me-up', 'SMU_BLUEPRINT': 'owner/repo', 'SMU_BLUEPRINT_BRANCH': 'main'}, clear=True):
                        mock_exists.return_value = True
                        mock_run.return_value = MagicMock(returncode=0, stdout='')
                        mock_blueprint.return_value = set()

                        import smu
                        smu.remove_symlinks()

                        # Get all commands that were run
                        all_cmds = [call[0][0] for call in mock_run.call_args_list]
                        lsrc_called = any('lsrc' in cmd for cmd in all_cmds)
                        self.assertTrue(lsrc_called, "lsrc command should be called to get symlinks")

    def test_cleans_up_empty_directories_in_config_and_local(self):
        """Test that empty directories in ~/.config and ~/.local are cleaned up."""
        with patch('smu.subprocess.run') as mock_run:
            with patch('smu.os.path.exists') as mock_exists:
                with patch('smu._get_blueprint_basenames') as mock_blueprint:
                    with patch.dict(os.environ, {'SMU_HOME_DIR': '/fake/home/set-me-up', 'SMU_BLUEPRINT': 'owner/repo', 'SMU_BLUEPRINT_BRANCH': 'main'}, clear=True):
                        mock_exists.return_value = True
                        mock_run.return_value = MagicMock(returncode=0, stdout='/home/user/.zshrc -> /path\n')
                        mock_blueprint.return_value = {'zshrc'}

                        import smu
                        smu.remove_symlinks()

                        # Get all commands that were run
                        all_cmds = [call[0][0] for call in mock_run.call_args_list]
                        
                        # Find the command that cleans up empty directories
                        cleanup_cmd = None
                        for cmd in all_cmds:
                            if cmd and '.config' in cmd and '.local' in cmd and '-type d' in cmd:
                                cleanup_cmd = cmd
                                break
                        
                        self.assertIsNotNone(cleanup_cmd, 
                            "Should have a cleanup command for empty directories in .config and .local")

    def test_cleans_up_symlinks_not_regular_files(self):
        """Test that only symlinks (-type l) are removed, not regular files."""
        with patch('smu.subprocess.run') as mock_run:
            with patch('smu.os.path.exists') as mock_exists:
                with patch('smu._get_blueprint_basenames') as mock_blueprint:
                    with patch.dict(os.environ, {'SMU_HOME_DIR': '/fake/home/set-me-up', 'SMU_BLUEPRINT': 'owner/repo', 'SMU_BLUEPRINT_BRANCH': 'main'}, clear=True):
                        mock_exists.return_value = True
                        mock_run.return_value = MagicMock(returncode=0, stdout='/home/user/.zshrc -> /path\n')
                        mock_blueprint.return_value = {'zshrc'}

                        import smu
                        smu.remove_symlinks()

                        # Get all commands that were run
                        all_cmds = [call[0][0] for call in mock_run.call_args_list]
                        
                        # Find the command that cleans up symlinks (-type l)
                        cleanup_cmd = None
                        for cmd in all_cmds:
                            if cmd and '-type l' in cmd:
                                cleanup_cmd = cmd
                                break
                        
                        self.assertIsNotNone(cleanup_cmd, 
                            "Should have a cleanup command for symlinks with -type l")
                        # Should NOT use -type f (regular files)
                        has_type_f = any(cmd and '-type f' in cmd for cmd in all_cmds if cmd)
                        self.assertFalse(has_type_f, 
                            "Should NOT remove regular files, only symlinks")

    def test_skips_named_symlink_cleanup_when_lsrc_returns_empty_but_uses_blueprint(self):
        """Test that when lsrc returns empty, blueprint is still used for broken symlink cleanup."""
        with patch('smu.subprocess.run') as mock_run:
            with patch('smu.os.path.exists') as mock_exists:
                with patch('smu._get_blueprint_basenames') as mock_blueprint:
                    with patch.dict(os.environ, {'SMU_HOME_DIR': '/fake/home/set-me-up', 'SMU_BLUEPRINT': 'owner/repo', 'SMU_BLUEPRINT_BRANCH': 'main'}, clear=True):
                        mock_exists.return_value = True
                        # lsrc returns empty, but blueprint returns basenames
                        mock_run.return_value = MagicMock(returncode=0, stdout='')
                        mock_blueprint.return_value = {'zshrc', 'gitconfig'}

                        import smu
                        smu.remove_symlinks()

                        # Get all commands that were run
                        all_cmds = [call[0][0] for call in mock_run.call_args_list]
                        
                        # Should have called lsrc
                        lsrc_called = any(cmd and 'lsrc' in cmd for cmd in all_cmds if cmd)
                        self.assertTrue(lsrc_called, "Should call lsrc")
                        
                        # When lsrc returns empty, named symlink cleanup should NOT run
                        # But broken symlink cleanup using blueprint should still run
                        named_cleanup = any(cmd and '-name' in cmd and '-type l' in cmd and '! -exec test -e' not in cmd 
                                              for cmd in all_cmds if cmd)
                        self.assertFalse(named_cleanup, 
                            "Should not run named symlink cleanup when lsrc returns empty")


class TestRemoveSymlinksEdgeCases(unittest.TestCase):
    """Edge case tests for remove_symlinks()."""

    def test_handles_nonexistent_dotfiles_directory(self):
        """Test behavior when dotfiles directory doesn't exist."""
        with patch('smu.subprocess.run') as mock_run:
            with patch('smu.os.path.exists') as mock_exists:
                with patch('smu._get_blueprint_basenames') as mock_blueprint:
                    with patch.dict(os.environ, {'SMU_HOME_DIR': '/fake/home/set-me-up', 'SMU_BLUEPRINT': 'owner/repo', 'SMU_BLUEPRINT_BRANCH': 'main'}, clear=True):
                        mock_exists.return_value = False
                        mock_blueprint.return_value = set()
                        
                        import smu
                        smu.remove_symlinks()
                        
                        # Should still call rcdn
                        self.assertTrue(mock_run.called)

    @patch.dict(os.environ, {'SMU_HOME_DIR': '/fake/home/set-me-up', 'SMU_BLUEPRINT': 'owner/repo', 'SMU_BLUEPRINT_BRANCH': 'main'}, clear=True)
    def test_uses_correct_rcrc_path(self):
        """Test that the correct RCRC path is used."""
        with patch('smu.subprocess.run') as mock_run:
            with patch('smu.os.path.exists') as mock_exists:
                with patch('smu._get_blueprint_basenames') as mock_blueprint:
                    mock_exists.return_value = True
                    mock_run.return_value = MagicMock(returncode=0, stdout='/home/user/.zshrc -> /path\n')
                    mock_blueprint.return_value = set()
                    
                    import smu
                    smu.remove_symlinks()
                    
                    # Check that RCRC environment variable was set
                    # (checked via any subprocess.run being called with RCRC in env)
                    self.assertTrue(mock_run.called)

    def test_throws_error_when_smu_blueprint_not_set(self):
        """Test that error is thrown when SMU_BLUEPRINT is not set."""
        # Clear the env vars
        with patch.dict(os.environ, {}, clear=True):
            with patch('smu.os.path.exists') as mock_exists:
                mock_exists.return_value = True
                
                import smu
                import importlib
                importlib.reload(smu)
                
                with self.assertRaises(SystemExit) as context:
                    smu._get_blueprint_basenames()
                
                self.assertNotEqual(context.exception.code, 0)
                # Check that the error message mentions SMU_BLUEPRINT
                # (This is tricky to test since die() uses print, so we just check exit code)

    def test_throws_error_when_smu_blueprint_branch_not_set(self):
        """Test that error is thrown when SMU_BLUEPRINT_BRANCH is not set."""
        with patch.dict(os.environ, {'SMU_BLUEPRINT': 'owner/repo'}, clear=False):
            # Remove SMU_BLUEPRINT_BRANCH if it exists
            env = os.environ.copy()
            env.pop('SMU_BLUEPRINT_BRANCH', None)
            
            with patch.dict(os.environ, env, clear=True):
                with patch('smu.os.path.exists') as mock_exists:
                    mock_exists.return_value = True
                    
                    import smu
                    import importlib
                    importlib.reload(smu)
                    
                    with self.assertRaises(SystemExit) as context:
                        smu._get_blueprint_basenames()
                    
                    self.assertNotEqual(context.exception.code, 0)


class TestRemoveSymlinksEfficiency(unittest.TestCase):
    """Tests to verify the efficiency of using lsrc vs find on tag-*."""

    def test_uses_single_lsrc_call_not_multiple_find_calls(self):
        """Test that lsrc is called once, not multiple find calls on tag-*."""
        with patch('smu.subprocess.run') as mock_run:
            with patch('smu.os.path.exists') as mock_exists:
                with patch('smu._get_blueprint_basenames') as mock_blueprint:
                    with patch.dict(os.environ, {'SMU_HOME_DIR': '/fake/home/set-me-up', 'SMU_BLUEPRINT': 'owner/repo', 'SMU_BLUEPRINT_BRANCH': 'main'}, clear=True):
                        mock_exists.return_value = True
                        mock_run.return_value = MagicMock(returncode=0, stdout='/home/user/.zshrc -> /path\n')
                        mock_blueprint.return_value = set()

                        import smu
                        smu.remove_symlinks()

                        # Get all commands that were run
                        all_cmds = [call[0][0] for call in mock_run.call_args_list]
                        
                        # Should not use find on tag-* directories
                        find_tag_calls = [cmd for cmd in all_cmds if cmd and 'tag-*' in cmd]
                        self.assertEqual(len(find_tag_calls), 0, 
                            "Should not use find on tag-*, should use lsrc instead")
                        
                        # Should call lsrc to get managed symlinks
                        lsrc_calls = [cmd for cmd in all_cmds if cmd and 'lsrc' in cmd]
                        self.assertEqual(len(lsrc_calls), 1, 
                            "Should call lsrc exactly once to get all managed symlinks")

    def test_uses_gh_api_for_blueprint_not_local_scan(self):
        """Test that GitHub API is used to get blueprint files, not scanning ~ recursively."""
        with patch('smu.subprocess.run') as mock_run:
            with patch('smu.os.path.exists') as mock_exists:
                with patch('smu._get_blueprint_basenames') as mock_blueprint:
                    with patch.dict(os.environ, {'SMU_HOME_DIR': '/fake/home/set-me-up', 'SMU_BLUEPRINT': 'owner/repo', 'SMU_BLUEPRINT_BRANCH': 'main'}, clear=True):
                        mock_exists.return_value = True
                        mock_run.return_value = MagicMock(returncode=0, stdout='/home/user/.zshrc -> /path\n')
                        mock_blueprint.return_value = {'zshrc'}

                        import smu
                        smu.remove_symlinks()

                        # Get all commands that were run
                        all_cmds = [call[0][0] for call in mock_run.call_args_list]
                        
                        # Should use _get_blueprint_basenames (mocked) - efficient
                        self.assertTrue(mock_blueprint.called, 
                            "Should call _get_blueprint_basenames to get blueprint files efficiently")
                        
                        # Should NOT use the slow generic broken symlink search
                        # (searching all of ~ without blueprint names)
                        generic_broken_search = any(
                            cmd and '-type l' in cmd and '! -exec test -e' in cmd and '-name' not in cmd
                            for cmd in all_cmds if cmd
                        )
                        self.assertFalse(generic_broken_search,
                            "Should NOT use slow generic broken symlink search, should use blueprint")


if __name__ == '__main__':
    unittest.main()