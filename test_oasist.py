"""
Comprehensive tests for OASist package
"""
import pytest
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

# Add the package to Python path
sys.path.insert(0, str(Path(__file__).parent))

from oasist.oasist import (
    substitute_env_vars, substitute_recursive, temp_file,
    ServiceConfig, SchemaProcessor, ClientGenerator,
    ConfigLoader, parse_args, main,
    EXIT_SUCCESS, EXIT_ERROR
)


# ============================================================================
# Test Environment Variable Substitution
# ============================================================================
class TestEnvSubstitution:
    """Tests for environment variable substitution."""
    
    def test_substitute_env_vars_with_existing_var(self, monkeypatch):
        """Test substitution with existing environment variable."""
        monkeypatch.setenv("TEST_VAR", "test_value")
        result = substitute_env_vars("URL is ${TEST_VAR}")
        assert result == "URL is test_value"
    
    def test_substitute_env_vars_with_default(self):
        """Test substitution with default value."""
        result = substitute_env_vars("URL is ${NONEXISTENT:default_value}")
        assert result == "URL is default_value"
    
    def test_substitute_env_vars_missing_no_default(self):
        """Test substitution with missing var and no default."""
        result = substitute_env_vars("URL is ${NONEXISTENT_VAR}")
        assert result == "URL is ${NONEXISTENT_VAR}"
    
    def test_substitute_recursive_dict(self, monkeypatch):
        """Test recursive substitution in dictionaries."""
        monkeypatch.setenv("HOST", "localhost")
        data = {"url": "http://${HOST}/api", "port": 8080}
        result = substitute_recursive(data)
        assert result["url"] == "http://localhost/api"
        assert result["port"] == 8080
    
    def test_substitute_recursive_list(self, monkeypatch):
        """Test recursive substitution in lists."""
        monkeypatch.setenv("ENV", "prod")
        data = ["${ENV}", "test", {"env": "${ENV}"}]
        result = substitute_recursive(data)
        assert result[0] == "prod"
        assert result[2]["env"] == "prod"


# ============================================================================
# Test Temporary File Management
# ============================================================================
class TestTempFile:
    """Tests for temporary file context manager."""
    
    def test_temp_file_json(self):
        """Test creating temporary JSON file."""
        data = {"key": "value", "number": 123}
        with temp_file(data, as_json=True) as path:
            assert path.exists()
            assert path.suffix == '.json'
            content = json.loads(path.read_text())
            assert content == data
        assert not path.exists()  # Should be cleaned up
    
    def test_temp_file_yaml(self):
        """Test creating temporary YAML file."""
        data = {"key": "value", "list": [1, 2, 3]}
        with temp_file(data, as_json=False) as path:
            assert path.exists()
            assert path.suffix == '.yaml'
            content = path.read_text()
            assert "key: value" in content
        assert not path.exists()  # Should be cleaned up
    
    def test_temp_file_cleanup_on_exception(self):
        """Test temp file cleanup when exception occurs."""
        data = {"test": "data"}
        path_ref = None
        try:
            with temp_file(data) as path:
                path_ref = path
                raise ValueError("Test exception")
        except ValueError:
            pass
        if path_ref:
            assert not path_ref.exists()  # Should still be cleaned up


# ============================================================================
# Test Service Configuration
# ============================================================================
class TestServiceConfig:
    """Tests for ServiceConfig dataclass."""
    
    def test_valid_config(self):
        """Test creating valid service configuration."""
        config = ServiceConfig(
            name="Test Service",
            schema_url="http://example.com/openapi.json",
            output_dir="test_client"
        )
        assert config.name == "Test Service"
        assert config.package_name == "test_service"
        assert config.base_url == "http://example.com"
    
    def test_empty_name_raises_error(self):
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="Service name cannot be empty"):
            ServiceConfig(name="", schema_url="http://test.com/api", output_dir="out")
    
    def test_empty_schema_url_raises_error(self):
        """Test that empty schema URL raises ValueError."""
        with pytest.raises(ValueError, match="Schema URL cannot be empty"):
            ServiceConfig(name="Test", schema_url="", output_dir="out")
    
    def test_invalid_url_format_raises_error(self):
        """Test that invalid URL format raises ValueError."""
        with pytest.raises(ValueError, match="must start with http"):
            ServiceConfig(name="Test", schema_url="ftp://test.com", output_dir="out")
    
    def test_path_traversal_protection(self):
        """Test that path traversal is blocked."""
        with pytest.raises(ValueError, match="cannot contain '..'"):
            ServiceConfig(
                name="Test",
                schema_url="http://test.com/api",
                output_dir="../etc/passwd"
            )
    
    def test_absolute_path_protection(self):
        """Test that absolute paths are blocked."""
        with pytest.raises(ValueError, match="must be relative"):
            ServiceConfig(
                name="Test",
                schema_url="http://test.com/api",
                output_dir="/etc/passwd"
            )
    
    def test_base_url_detection_with_api_pattern(self):
        """Test automatic base URL detection with /api/ pattern."""
        config = ServiceConfig(
            name="Test",
            schema_url="http://example.com/api/v1/openapi.json",
            output_dir="test"
        )
        assert config.base_url == "http://example.com"


# ============================================================================
# Test Schema Processor
# ============================================================================
class TestSchemaProcessor:
    """Tests for SchemaProcessor."""
    
    def test_sanitize_security_with_dict(self):
        """Test sanitizing invalid dict security definitions."""
        schema = {
            "paths": {
                "/test": {
                    "get": {
                        "security": {"bearer": {}, "api_key": {}}
                    }
                }
            }
        }
        result = SchemaProcessor.sanitize_security(schema)
        assert isinstance(result["paths"]["/test"]["get"]["security"], list)
        assert len(result["paths"]["/test"]["get"]["security"]) == 2
    
    def test_sanitize_security_preserves_valid_format(self):
        """Test that valid security format is preserved."""
        schema = {
            "paths": {
                "/test": {
                    "get": {
                        "security": [{"bearer": []}]
                    }
                }
            }
        }
        result = SchemaProcessor.sanitize_security(schema)
        assert result["paths"]["/test"]["get"]["security"] == [{"bearer": []}]


# ============================================================================
# Test Client Generator
# ============================================================================
class TestClientGenerator:
    """Tests for ClientGenerator."""
    
    def test_add_service(self):
        """Test adding a service."""
        generator = ClientGenerator()
        config = ServiceConfig(
            name="Test",
            schema_url="http://test.com/api",
            output_dir="test"
        )
        generator.add_service("test", config)
        assert "test" in generator.services
    
    def test_generate_nonexistent_service(self):
        """Test generating nonexistent service returns False."""
        generator = ClientGenerator()
        result = generator.generate("nonexistent")
        assert result is False
    
    def test_list_services_empty(self, capsys):
        """Test listing services when none configured."""
        generator = ClientGenerator()
        generator.list_services()
        captured = capsys.readouterr()
        # Should show "No services configured" message


# ============================================================================
# Test Config Loader
# ============================================================================
class TestConfigLoader:
    """Tests for ConfigLoader."""
    
    def test_load_missing_file(self):
        """Test loading from missing file."""
        generator = ClientGenerator()
        result = ConfigLoader.load(generator, "nonexistent.json")
        assert result is False
    
    def test_load_invalid_json(self, tmp_path):
        """Test loading invalid JSON file."""
        config_file = tmp_path / "invalid.json"
        config_file.write_text("{invalid json}")
        generator = ClientGenerator()
        result = ConfigLoader.load(generator, str(config_file))
        assert result is False
    
    def test_load_valid_projects_format(self, tmp_path):
        """Test loading valid projects format."""
        config_data = {
            "output_dir": "./test_clients",
            "projects": {
                "test_api": {
                    "input": {"target": "http://localhost:8000/openapi.json"},
                    "output": {
                        "dir": "test_api",
                        "name": "Test API"
                    }
                }
            }
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))
        
        generator = ClientGenerator()
        result = ConfigLoader.load(generator, str(config_file))
        assert result is True
        assert "test_api" in generator.services


# ============================================================================
# Test Argument Parsing
# ============================================================================
class TestArgumentParsing:
    """Tests for command line argument parsing."""
    
    def test_parse_args_default(self):
        """Test parsing with default arguments."""
        config, verbose, args = parse_args(["list"])
        assert config == "oasist_config.json"
        assert verbose is False
        assert args == ["list"]
    
    def test_parse_args_with_config(self):
        """Test parsing with config file flag."""
        config, verbose, args = parse_args(["-c", "custom.json", "list"])
        assert config == "custom.json"
        assert args == ["list"]
    
    def test_parse_args_with_verbose(self):
        """Test parsing with verbose flag."""
        config, verbose, args = parse_args(["-v", "generate", "api"])
        assert verbose is True
        assert args == ["generate", "api"]
    
    def test_parse_args_combined_flags(self):
        """Test parsing with multiple flags."""
        config, verbose, args = parse_args(["-v", "-c", "prod.json", "generate-all", "--force"])
        assert verbose is True
        assert config == "prod.json"
        assert args == ["generate-all", "--force"]


# ============================================================================
# Test Main Entry Point
# ============================================================================
class TestMain:
    """Tests for main() entry point."""
    
    @patch('sys.argv', ['oasist', '--version'])
    def test_main_version(self, capsys):
        """Test --version flag."""
        result = main()
        assert result == EXIT_SUCCESS
    
    @patch('sys.argv', ['oasist', '--help'])
    def test_main_help(self):
        """Test --help flag."""
        result = main()
        assert result == EXIT_SUCCESS
    
    @patch('sys.argv', ['oasist'])
    def test_main_no_args(self):
        """Test running without arguments."""
        result = main()
        assert result == EXIT_SUCCESS


# ============================================================================
# Test Package Import
# ============================================================================
class TestPackageImport:
    """Tests for package import functionality."""
    
    def test_import_package(self):
        """Test that the package can be imported."""
    import oasist
    assert hasattr(oasist, 'oasist')

    def test_version_exists(self):
        """Test that version is accessible."""
    from oasist import __version__
    assert __version__ is not None
    assert isinstance(__version__, str)

    def test_exported_classes(self):
        """Test that main classes are exported."""
        from oasist import ClientGenerator, ServiceConfig
        assert ClientGenerator is not None
        assert ServiceConfig is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
