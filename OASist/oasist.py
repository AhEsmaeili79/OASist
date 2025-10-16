#!/usr/bin/env python
"""OASist - OpenAPI Client Generator

Generates Python API clients from OpenAPI/Swagger specifications.

Architecture Notes:
- Uses design patterns (Strategy, Command, Dataclass) for maintainability
- While this adds some complexity, it provides:
  * Better testability and extensibility
  * Clear separation of concerns
  * Type safety with dataclasses
  * Easy addition of new commands and parsers
- For simple use cases, the CLI provides a straightforward interface
- For advanced use cases, the modular design allows programmatic usage
"""
import subprocess
import requests
import yaml
import json
import logging
import os
import re
import shutil
import tempfile
import sys
from pathlib import Path
from typing import Optional, Dict, Any, Protocol, Generator, List
from dataclasses import dataclass, field
from contextlib import contextmanager
from datetime import datetime
from abc import ABC, abstractmethod
from urllib.parse import urlparse
from dotenv import load_dotenv

from rich.console import Console
from rich.theme import Theme
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.logging import RichHandler
from rich import box
from rich.text import Text
from rich.rule import Rule
from rich.align import Align

# ============================================================================
# CONFIGURATION
# ============================================================================
OUTPUT_DIR = "./clients"
CONFIG_FILE = "oasist_config.json"
HTTP_TIMEOUT = 30  # seconds
RICH_THEME = Theme({
    "info": "bold cyan", "warning": "bold yellow", "error": "bold red",
    "success": "bold green", "accent": "bold magenta", "dim": "dim"
})

# Command names
CMD_LIST = "list"
CMD_GENERATE = "generate"
CMD_GENERATE_ALL = "generate-all"
CMD_INFO = "info"
CMD_HELP = "help"

# Exit codes
EXIT_SUCCESS = 0
EXIT_ERROR = 1

console = Console(theme=RICH_THEME)
logging.basicConfig(level=logging.INFO, format='%(message)s',
    handlers=[RichHandler(console=console, rich_tracebacks=True, show_time=False, show_path=False)])
logger = logging.getLogger("oasist")
load_dotenv()

# ============================================================================
# UTILITIES
# ============================================================================
def substitute_env_vars(text: str) -> str:
    """Replace ${VAR} or ${VAR:default} with env values.
    
    Warns if environment variable is not found and no default is provided.
    """
    if not isinstance(text, str):
        return text
    
    def replace_var(match):
        var_name = match.group(1)
        default_value = match.group(2)
        env_value = os.getenv(var_name)
        
        if env_value is not None:
            return env_value
        elif default_value is not None:
            return default_value
        else:
            logger.warning(f"Environment variable '{var_name}' not found and no default provided")
            return match.group(0)  # Return original placeholder
    
    return re.sub(r'\$\{([^}:]+)(?::([^}]*))?\}', replace_var, text)

def substitute_recursive(data: Any) -> Any:
    """Recursively substitute environment variables in nested data structures.
    
    Traverses dictionaries, lists, and strings to replace ${VAR} or ${VAR:default}
    patterns with environment variable values.
    
    Args:
        data: Data structure (str, dict, list, or primitive) to process
        
    Returns:
        Processed data with environment variables substituted
    """
    if isinstance(data, str):
        return substitute_env_vars(data)
    if isinstance(data, dict):
        return {k: substitute_recursive(v) for k, v in data.items()}
    if isinstance(data, list):
        return [substitute_recursive(item) for item in data]
    return data

@contextmanager
def temp_file(content: Dict[str, Any], as_json: bool = True) -> Generator[Path, None, None]:
    """Context manager for temp files with auto cleanup.
    
    Args:
        content: Dictionary content to write to file
        as_json: If True, write as JSON; otherwise write as YAML
        
    Yields:
        Path to the temporary file
        
    Raises:
        IOError: If file creation/write operations fail
    """
    suffix = '.json' if as_json else '.yaml'
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, mode='w', encoding='utf-8')
    tmp_path = Path(tmp.name)
    
    try:
        # Write content to file
        if as_json:
            json.dump(content, tmp, ensure_ascii=False, indent=2)
        else:
            yaml.safe_dump(content, tmp, sort_keys=False, allow_unicode=True)
        tmp.flush()  # Ensure data is written
        tmp.close()  # Close file handle before yielding
        
        yield tmp_path
    except Exception as e:
        # Close file if still open (during file creation)
        try:
            tmp.close()
        except:
            pass
        # Only wrap IOError for file operations, not user code exceptions
        if tmp_path.exists():
            # File was created successfully, user code raised exception
            raise
        else:
            # File creation failed
            raise IOError(f"Failed to create temporary file: {e}") from e
    finally:
        # Always cleanup temp file
        tmp_path.unlink(missing_ok=True)

# ============================================================================
# STRATEGY PATTERN - Schema Parsing
# ============================================================================
class SchemaParser(Protocol):
    """Protocol for schema parsing strategies."""
    def parse(self, text: str) -> Dict[str, Any]: ...

class JSONParser:
    """JSON schema parser."""
    def parse(self, text: str) -> Dict[str, Any]:
        return json.loads(text)

class YAMLParser:
    """YAML schema parser."""
    def parse(self, text: str) -> Dict[str, Any]:
        return yaml.safe_load(text)

# ============================================================================
# DATA CLASSES
# ============================================================================
@dataclass
class ServiceConfig:
    """Service configuration with auto env var substitution and validation."""
    name: str
    schema_url: str
    output_dir: str
    base_url: str = ""
    package_name: str = ""
    request_params: Dict[str, str] = field(default_factory=dict)
    request_headers: Dict[str, str] = field(default_factory=dict)
    prefer_json: bool = False
    disable_post_hooks: bool = True
    original_base_url: str = field(default="", init=False)  # Track original before auto-detection
    
    def __post_init__(self):
        """Auto-substitute env vars, validate, and generate defaults."""
        # Substitute environment variables in strings
        for attr in ('name', 'schema_url', 'output_dir', 'package_name', 'base_url'):
            setattr(self, attr, substitute_env_vars(getattr(self, attr)))
        
        # Substitute environment variables in dictionaries
        self.request_params = substitute_recursive(self.request_params)
        self.request_headers = substitute_recursive(self.request_headers)
        
        # Validate required fields
        if not self.name or not self.name.strip():
            raise ValueError("Service name cannot be empty")
        if not self.schema_url or not self.schema_url.strip():
            raise ValueError(f"Schema URL cannot be empty for service '{self.name}'")
        if not self.output_dir or not self.output_dir.strip():
            raise ValueError(f"Output directory cannot be empty for service '{self.name}'")
        
        # Validate URL format
        if not self.schema_url.startswith(('http://', 'https://')):
            raise ValueError(f"Schema URL must start with http:// or https:// for service '{self.name}'")
        
        # Track original base_url before auto-detection
        self.original_base_url = self.base_url
        
        # Auto-detect base URL with fallback logic if not provided
        if not self.base_url:
            # Try common patterns: /api/, /openapi, /swagger
            for pattern in ['/api/', '/openapi', '/swagger']:
                if pattern in self.schema_url:
                    self.base_url = self.schema_url.rsplit(pattern, 1)[0]
                    break
            # Fallback to origin (protocol + domain)
            if not self.base_url:
                parsed = urlparse(self.schema_url)
                self.base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        # Generate package name from service name if not provided
        self.package_name = (self.package_name or 
                           self.name.lower().replace('-', '_').replace(' ', '_'))
        
        # Validate output_dir for path traversal and absolute paths
        output_path = Path(self.output_dir)
        # Check for path traversal, absolute paths, and Unix-style absolute paths
        is_unix_absolute = self.output_dir.startswith('/')
        if '..' in self.output_dir or output_path.is_absolute() or is_unix_absolute:
            raise ValueError(f"Output directory must be relative and cannot contain '..': '{self.output_dir}'")

# ============================================================================
# SCHEMA PROCESSOR
# ============================================================================
class SchemaProcessor:
    """Processes and sanitizes OpenAPI schemas."""
    
    HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
    
    @staticmethod
    def fetch(url: str, params: Dict[str, str], prefer_json: bool, custom_headers: Dict[str, str] = None) -> Optional[Dict[str, Any]]:
        """Fetch schema with format preference and retry logic.
        
        Args:
            url: URL to fetch schema from
            params: Query parameters for the request
            prefer_json: If True, prefer JSON format over YAML
            custom_headers: Optional custom headers to include in request
            
        Returns:
            Parsed schema dictionary or None on failure
        """
        headers = {'Accept': 'application/vnd.oai.openapi+json, application/json' if prefer_json 
                   else 'application/yaml, text/yaml, application/x-yaml, text/plain'}
        
        # Merge custom headers (they override defaults)
        if custom_headers:
            headers.update(custom_headers)
        
        with console.status("[accent]Fetching schema...", spinner="dots"):
            try:
                response = requests.get(url, headers=headers, params=params, timeout=HTTP_TIMEOUT)
                response.raise_for_status()
                
                # Check if response is empty
                if not response.text or not response.text.strip():
                    logger.error("Received empty response from schema URL")
                    return None
                
                # Try preferred format first, then fallback
                parsers = ([JSONParser(), YAMLParser()] if prefer_json or url.lower().endswith('.json')
                          else [YAMLParser(), JSONParser()])
                
                last_error = None
                for i, parser in enumerate(parsers):
                    try:
                        schema = parser.parse(response.text)
                        if schema and isinstance(schema, dict):
                            # Validate schema has required OpenAPI fields
                            if not schema.get('openapi') and not schema.get('swagger'):
                                logger.warning("Schema missing 'openapi' or 'swagger' version field")
                            if not schema.get('paths') and not schema.get('webhooks'):
                                logger.warning("Schema has no 'paths' or 'webhooks' defined")
                            return schema
                        elif schema is not None:
                            logger.error(f"Schema is not a dictionary: {type(schema)}")
                    except json.JSONDecodeError as e:
                        last_error = f"JSON parsing failed: {e}"
                        logger.debug(f"Parser {i+1} (JSON) failed: {e}")
                    except yaml.YAMLError as e:
                        last_error = f"YAML parsing failed: {e}"
                        logger.debug(f"Parser {i+1} (YAML) failed: {e}")
                    except Exception as e:
                        last_error = f"Parsing failed: {e}"
                        logger.debug(f"Parser {i+1} failed: {e}")
                
                # If all parsers failed, log the last error
                if last_error:
                    logger.error(f"All parsers failed. Last error: {last_error}")
                return None
                
            except requests.exceptions.Timeout:
                logger.error(f"Request timeout after {HTTP_TIMEOUT}s")
                return None
            except requests.exceptions.ConnectionError as e:
                logger.error(f"Connection error: {e}")
                return None
            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP error {e.response.status_code}: {e}")
                return None
            except Exception as e:
                logger.error(f"Schema fetch failed: {e}")
                return None
    
    @staticmethod
    def sanitize_security(schema: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize invalid security requirement formats to OpenAPI spec."""
        paths = schema.get('paths', {})
        if not isinstance(paths, dict):
            return schema
        
        for path_item in paths.values():
            if not isinstance(path_item, dict):
                continue
            for method, op in path_item.items():
                if method not in SchemaProcessor.HTTP_METHODS or not isinstance(op, dict):
                    continue
                
                security = op.get('security')
                if isinstance(security, dict):
                    # Convert dict to list of separate requirements (OR logic)
                    op['security'] = [{k: []} for k in security.keys()]
                elif isinstance(security, list):
                    op['security'] = [{k: v if isinstance(v, list) else [] 
                                      for k, v in req.items()} 
                                     for req in security if isinstance(req, dict)]
        return schema

# ============================================================================
# CLIENT GENERATOR
# ============================================================================
class GeneratorRunner:
    """Runs openapi-python-client with retry logic and error handling."""
    
    @staticmethod
    def run(schema_path: Path, output_path: Path, disable_hooks: bool) -> bool:
        """Execute generator with automatic retries.
        
        Args:
            schema_path: Path to OpenAPI schema file
            output_path: Output directory for generated client
            disable_hooks: Whether to disable post-generation hooks
            
        Returns:
            True if generation succeeded, False otherwise
        """
        base_cmd = [
            'openapi-python-client', 'generate', '--path', str(schema_path),
            '--output-path', str(output_path), '--meta', 'none',
            '--overwrite', '--no-fail-on-warning'
        ]
        
        if disable_hooks:
            return GeneratorRunner._run_with_hooks_disabled(base_cmd)
        else:
            return GeneratorRunner._run_default(base_cmd)
    
    @staticmethod
    def _run_with_hooks_disabled(base_cmd: list) -> bool:
        """Run generator with post-hooks disabled.
        
        Args:
            base_cmd: Base command list for generator
            
        Returns:
            True if generation succeeded, False otherwise
        """
        with temp_file({"post_hooks": []}, as_json=False) as config_path:
            cmd = base_cmd + ['--config', str(config_path), '--no-post-hooks']
            result = GeneratorRunner._execute(cmd)
            
            stderr_lower = result.stderr.lower() if result.stderr else ""
            
            # Retry without --no-post-hooks if unsupported
            if result.returncode != 0 and ('no such option' in stderr_lower or 
                                            'unrecognized arguments' in stderr_lower):
                logger.warning("--no-post-hooks unsupported, retrying")
                cmd = base_cmd + ['--config', str(config_path)]
                result = GeneratorRunner._execute(cmd)
        
        return GeneratorRunner._check_result(result)
    
    @staticmethod
    def _run_default(base_cmd: list) -> bool:
        """Run generator with default settings, retry on ruff failure.
        
        Args:
            base_cmd: Base command list for generator
            
        Returns:
            True if generation succeeded, False otherwise
        """
        result = GeneratorRunner._execute(base_cmd)
        stderr_lower = result.stderr.lower() if result.stderr else ""
        
        # Retry with hooks disabled if ruff failed
        if result.returncode != 0 and 'ruff failed' in stderr_lower:
            logger.warning("Ruff failed, retrying with hooks disabled")
            with temp_file({"post_hooks": []}, as_json=False) as config_path:
                cmd = base_cmd + ['--config', str(config_path)]
                result = GeneratorRunner._execute(cmd)
        
        return GeneratorRunner._check_result(result)
    
    @staticmethod
    def _execute(cmd: list) -> subprocess.CompletedProcess:
        """Execute subprocess command with UI spinner.
        
        Args:
            cmd: Command list to execute
            
        Returns:
            CompletedProcess instance with stdout and stderr
        """
        with console.status("[accent]Generating client...", spinner="bouncingBar"):
            return subprocess.run(cmd, capture_output=True, text=True)
    
    @staticmethod
    def _check_result(result: subprocess.CompletedProcess) -> bool:
        """Check subprocess result and log errors.
        
        Args:
            result: CompletedProcess instance from subprocess.run
            
        Returns:
            True if returncode is 0, False otherwise
        """
        if result.returncode != 0:
            # Log both stderr and stdout for better debugging
            error_msg = result.stderr.strip() if result.stderr else ""
            output_msg = result.stdout.strip() if result.stdout else ""
            
            if error_msg:
                logger.error(f"Generation failed (stderr): {error_msg}")
            if output_msg and output_msg != error_msg:
                logger.error(f"Generation output (stdout): {output_msg}")
            
            if not error_msg and not output_msg:
                logger.error("Generation failed with no output")
        
        return result.returncode == 0

class ClientGenerator:
    """Main orchestrator for client generation."""
    
    def __init__(self, output_base: Path = Path("./clients")):
        self.output_base = output_base
        self.services: Dict[str, ServiceConfig] = {}
    
    def add_service(self, key: str, config: ServiceConfig) -> None:
        """Register service."""
        self.services[key] = config
    
    def generate(self, service_key: str, force: bool = False) -> bool:
        """Generate client for service.
        
        Args:
            service_key: Service identifier from configuration
            force: If True, regenerate even if client exists
            
        Returns:
            True if generation succeeded, False otherwise
        """
        config = self.services.get(service_key)
        if not config:
            logger.error(f"Service '{service_key}' not found")
            return False
        
        # Safely construct output path
        try:
            output_path = (self.output_base / config.output_dir).resolve()
            
            # Verify output path is within output_base to prevent path traversal
            if not str(output_path).startswith(str(self.output_base.resolve())):
                logger.error(f"Security: Output path escapes base directory: {output_path}")
                return False
        except ValueError as e:
            logger.error(f"Invalid path value for output directory '{config.output_dir}': {e}")
            return False
        except OSError as e:
            logger.error(f"OS error while resolving output path '{config.output_dir}': {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error resolving output path: {e}")
            return False
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if output_path.exists() and not force:
            logger.warning(f"Client exists at {output_path}. Use --force to regenerate")
            return False
        
        # Fetch and process schema
        schema = SchemaProcessor.fetch(config.schema_url, config.request_params, config.prefer_json, config.request_headers)
        if not schema:
            return False
        schema = SchemaProcessor.sanitize_security(schema)
        
        # Clean output directory
        if output_path.exists():
            shutil.rmtree(output_path)
        
        # Generate client
        is_json = config.prefer_json or config.schema_url.lower().endswith('.json')
        with temp_file(schema, as_json=is_json) as schema_path:
            success = GeneratorRunner.run(schema_path, output_path, config.disable_post_hooks)
        
        if not success:
            if output_path.exists() and output_path.is_dir() and not any(output_path.iterdir()):
                output_path.rmdir()
            return False
        
        console.print(f":sparkles: [success]Generated[/success] [accent]{service_key}[/accent] → [bold]{output_path}[/bold]")
        return True
    
    def generate_all(self, force: bool = False) -> int:
        """Generate all clients with progress bar.
        
        Args:
            force: If True, regenerate even if client exists
            
        Returns:
            Number of successfully generated clients
        """
        if not self.services:
            logger.warning("No services configured - nothing to generate")
            return 0
        
        total, success_count = len(self.services), 0
        
        with Progress(SpinnerColumn(style="accent"), TextColumn("[accent]Generating[/accent]"),
                     BarColumn(bar_width=None), TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                     TimeElapsedColumn(), console=console, transient=True) as progress:
            task_id = progress.add_task("generate_all", total=total)
            for key in self.services:
                if self.generate(key, force):
                    success_count += 1
                progress.advance(task_id, 1)
        
        console.print(f"[success]✓ Generated {success_count}/{total} clients")
        return success_count
    
    def list_services(self) -> None:
        """Display all services."""
        if not self.services:
            console.print(Panel.fit("No services configured", title="Services", style="warning"))
            return
        
        table = Table(title="Configured Services", box=box.ROUNDED, show_lines=False)
        table.add_column("Status", style="success", no_wrap=True)
        table.add_column("Key", style="accent")
        table.add_column("Name", style="info")
        table.add_column("Schema URL", style="dim")
        
        for key, config in self.services.items():
            status = "✓" if (self.output_base / config.output_dir).exists() else "○"
            table.add_row(status, key, config.name, config.schema_url)
        console.print(table)
    
    def info(self, service_key: str) -> None:
        """Show service details."""
        config = self.services.get(service_key)
        if not config:
            console.print(Panel.fit(f"Service '[bold]{service_key}[/bold]' not found", 
                                   title="Error", style="error"))
            return
        
        output_path = self.output_base / config.output_dir
        exists = output_path.exists()
        
        grid = Table.grid(padding=(0, 1))
        grid.add_column(justify="right", style="dim")
        grid.add_column()
        grid.add_row("Name", config.name)
        grid.add_row("Schema URL", config.schema_url)
        grid.add_row("Base URL", config.base_url)
        if config.original_base_url and config.original_base_url != config.base_url:
            grid.add_row("Original Base URL", config.original_base_url or "(auto-detected)")
        grid.add_row("Output", str(output_path))
        grid.add_row("Status", "Generated ✓" if exists else "Not generated")
        
        if exists:
            mtime = datetime.fromtimestamp(output_path.stat().st_mtime)
            grid.add_row("Modified", mtime.strftime('%Y-%m-%d %H:%M:%S'))
        
        console.print(Panel(grid, title=f"Service: [accent]{service_key}[/accent]", box=box.ROUNDED))

# ============================================================================
# BUILDER PATTERN - Config Loading
# ============================================================================
class ConfigLoader:
    """Loads and parses configuration files."""
    
    @staticmethod
    def load(generator: ClientGenerator, config_file: str) -> bool:
        """Load services from config file."""
        config_path = Path(config_file)
        
        if not config_path.exists():
            logger.error(f"Config file not found: {config_file}")
            logger.error(f"Please create '{config_file}' in current directory")
            return False
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = substitute_recursive(json.load(f))
        except FileNotFoundError:
            logger.error(f"Config file not found: {config_file}")
            return False
        except PermissionError:
            logger.error(f"Permission denied reading config file: {config_file}")
            return False
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file (line {e.lineno}, col {e.colno}): {e.msg}")
            return False
        except UnicodeDecodeError as e:
            logger.error(f"Invalid encoding in config file (expected UTF-8): {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error loading config: {type(e).__name__}: {e}")
            return False
        
        if 'output_dir' in config_data:
            generator.output_base = Path(config_data['output_dir'])
        
        services_loaded = (ConfigLoader._load_projects(generator, config_data.get('projects', {})) +
                          ConfigLoader._load_services(generator, config_data.get('services', [])))
        
        if services_loaded == 0:
            logger.error("No services found in config")
            return False
        
        logger.info(f"✓ Loaded {services_loaded} services from {config_file}")
        return True
    
    @staticmethod
    def _load_projects(generator: ClientGenerator, projects: Dict[str, Any]) -> int:
        """Load Orval-style projects.
        
        Args:
            generator: ClientGenerator instance to register services with
            projects: Dictionary mapping project keys to their configurations
            
        Returns:
            Number of projects successfully loaded
        """
        count = 0
        for key, proj in projects.items():
            if not isinstance(proj, dict):
                continue
            input_cfg = proj.get('input', {}) or {}
            output_cfg = proj.get('output', {}) or {}
            
            try:
                config = ServiceConfig(
                    name=output_cfg.get('name', key),
                    schema_url=input_cfg.get('target', ''),
                    output_dir=output_cfg.get('dir', key),
                    base_url=output_cfg.get('base_url', ''),
                    package_name=output_cfg.get('package_name', ''),
                    request_params=input_cfg.get('params', {}) or {},
                    request_headers=input_cfg.get('headers', {}) or {},
                    prefer_json=bool(input_cfg.get('prefer_json', False)),
                    disable_post_hooks=bool(output_cfg.get('disable_post_hooks', True)),
                )
                generator.add_service(key, config)
                count += 1
            except ValueError as e:
                logger.warning(f"Skipping invalid project '{key}': {e}")
        return count
    
    @staticmethod
    def _load_services(generator: ClientGenerator, services: List[Dict[str, Any]]) -> int:
        """Load legacy services format.
        
        Args:
            generator: ClientGenerator instance to register services with
            services: List of service configuration dictionaries
            
        Returns:
            Number of services successfully loaded
        """
        count = 0
        for service in services:
            key = service.get('key')
            if not key:
                logger.warning("Skipping service without 'key' field")
                continue
            try:
                config = ServiceConfig(
                    name=service.get('name', key),
                    schema_url=service.get('schema_url', ''),
                    output_dir=service.get('output_dir', key),
                    base_url=service.get('base_url', ''),
                    package_name=service.get('package_name', ''),
                    request_params=service.get('request_params', {}) or {},
                    request_headers=service.get('request_headers', {}) or {},
                    prefer_json=bool(service.get('prefer_json', False)),
                    disable_post_hooks=bool(service.get('disable_post_hooks', True)),
                )
                generator.add_service(key, config)
                count += 1
            except ValueError as e:
                logger.warning(f"Skipping invalid service '{key}': {e}")
        return count

# ============================================================================
# COMMAND PATTERN - CLI Commands
# ============================================================================
class Command(ABC):
    """Base command interface."""
    @abstractmethod
    def execute(self, generator: ClientGenerator, args: list) -> None:
        pass

class ListCommand(Command):
    """List services command."""
    def execute(self, generator: ClientGenerator, args: list) -> None:
        generator.list_services()

class GenerateCommand(Command):
    """Generate single service command."""
    def execute(self, generator: ClientGenerator, args: list) -> None:
        if len(args) < 2:
            console.print(Panel.fit("Missing service name. Usage: oasist generate <service>", 
                                   title="Error", style="error"))
            return
        generator.generate(args[1], '--force' in args)

class GenerateAllCommand(Command):
    """Generate all services command."""
    def execute(self, generator: ClientGenerator, args: list) -> None:
        generator.generate_all('--force' in args)

class InfoCommand(Command):
    """Show service info command."""
    def execute(self, generator: ClientGenerator, args: list) -> None:
        if len(args) < 2:
            console.print(Panel.fit("Missing service name. Usage: oasist info <service>", 
                                   title="Error", style="error"))
            return
        generator.info(args[1])

class CommandRegistry:
    """Registry for CLI commands."""
    _commands = {
        CMD_LIST: ListCommand(),
        CMD_GENERATE: GenerateCommand(),
        CMD_GENERATE_ALL: GenerateAllCommand(),
        CMD_INFO: InfoCommand(),
    }
    
    @staticmethod
    def execute(command: str, generator: ClientGenerator, args: list) -> bool:
        """Execute command if registered."""
        cmd = CommandRegistry._commands.get(command)
        if cmd:
            cmd.execute(generator, args)
            return True
        return False

# ============================================================================
# CLI HELP
# ============================================================================
class HelpDisplay:
    """Displays help information."""
    
    @staticmethod
    def show_main():
        """Show main help."""
        help_text = [
            ("[bold]USAGE[/bold]", "oasist [global-options] <command> [options]"),
            ("", ""),
            ("[bold]GLOBAL OPTIONS[/bold]", ""),
            ("--config, -c <file>", "Config file path (default: oasist_config.json)"),
            ("--verbose, -v", "Enable verbose/debug logging"),
            ("", ""),
            ("[bold]COMMANDS[/bold]", ""),
            ("list", "List all services and status"),
            ("generate <service>", "Generate client for service"),
            ("generate-all", "Generate all clients"),
            ("info <service>", "Show service details"),
            ("help [command]", "Show help"),
            ("", ""),
            ("[bold]OPTIONS[/bold]", ""),
            ("--help, -h", "Show help"),
            ("--version, -V", "Show version"),
            ("--force", "Regenerate existing clients"),
            ("", ""),
            ("[bold]EXAMPLES[/bold]", ""),
            ("oasist list", "List services"),
            ("oasist -v generate myapi", "Generate with verbose output"),
            ("oasist -c prod.json generate myapi", "Use custom config"),
            ("oasist generate myapi --force", "Force regenerate"),
            ("oasist generate-all", "Generate all"),
            ("oasist info myapi", "Show service info"),
        ]
        
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="accent")
        grid.add_column()
        for col1, col2 in help_text:
            grid.add_row(col1, col2)
        
        console.print(Panel(grid, title="OASist Client Generator", box=box.ROUNDED))
    
    @staticmethod
    def show_command(command: str):
        """Show command-specific help."""
        help_details = {
            'list': ('List configured services', 'oasist list', None),
            'generate': ('Generate client for service', 'oasist generate <service> [--force]', 
                        ['--force: Regenerate if exists']),
            'generate-all': ('Generate all clients', 'oasist generate-all [--force]', 
                           ['--force: Regenerate if exists']),
            'info': ('Show service details', 'oasist info <service>', None),
        }
        
        if command not in help_details:
            HelpDisplay.show_main()
            return
        
        desc, usage, options = help_details[command]
        grid = Table.grid(padding=(0, 1))
        grid.add_column()
        grid.add_row(f"[bold]{command}[/bold]")
        grid.add_row("")
        grid.add_row(desc)
        grid.add_row("")
        grid.add_row("[bold]USAGE[/bold]")
        grid.add_row(usage)
        
        if options:
            grid.add_row("")
            grid.add_row("[bold]OPTIONS[/bold]")
            for opt in options:
                grid.add_row(f"  {opt}")
        
        console.print(Panel(grid, title="Command Help", box=box.ROUNDED))

# ============================================================================
# MAIN CLI ENTRY
# ============================================================================
def parse_args(args: List[str]) -> tuple:
    """Parse command line arguments.
    
    Args:
        args: List of command line arguments
        
    Returns:
        Tuple of (config_file, verbose, remaining_args)
    """
    config_file = CONFIG_FILE
    verbose = False
    remaining = []
    i = 0
    
    while i < len(args):
        arg = args[i]
        if arg in ['--config', '-c'] and i + 1 < len(args):
            config_file = args[i + 1]
            i += 2
        elif arg in ['--verbose', '-v']:
            verbose = True
            i += 1
        else:
            remaining.append(arg)
            i += 1
    
    return config_file, verbose, remaining

def main():
    """CLI entry point."""
    try:
        from . import __version__
    except ImportError:
        try:
            import oasist
            __version__ = oasist.__version__
        except ImportError:
            __version__ = "unknown"
    
    raw_args = sys.argv[1:]
    
    # Parse global flags before processing commands
    config_file, verbose, args = parse_args(raw_args)
    
    # Set logging level based on verbose flag
    if verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
    
    # Handle version and help flags
    if args and args[0] in ['--version', '-V']:
        console.print(f"oasist {__version__}")
        return EXIT_SUCCESS
    
    if not args or args[0] in ['-h', '--help', CMD_HELP]:
        HelpDisplay.show_command(args[1] if len(args) > 1 else '')
        return EXIT_SUCCESS
    
    # Show banner
    console.print(Panel(
        Align.center(Text.assemble(
            "\n", Text("OASist Client Generator", style="accent"),
            "\n", Text("Generate Python clients from OpenAPI schemas", style="dim"), "\n"
        ), vertical="middle"),
        box=box.ROUNDED, padding=(1, 2), title="✨", border_style="accent"
    ))
    console.print(Rule(style="dim"))
    
    # Initialize and load config
    generator = ClientGenerator(output_base=Path(OUTPUT_DIR))
    
    with console.status("[accent]Loading configuration...", spinner="dots"):
        if not ConfigLoader.load(generator, config_file):
            logger.error(f"Failed to load config from {config_file}")
            return EXIT_ERROR
    
    # Handle per-command help
    if '-h' in args or '--help' in args:
        HelpDisplay.show_command(args[0])
        return EXIT_SUCCESS
    
    # Execute command
    if not CommandRegistry.execute(args[0], generator, args):
        console.print(Panel.fit("Invalid command. Use --help for usage.", title="Error", style="error"))
        return EXIT_ERROR
    
    return EXIT_SUCCESS

if __name__ == "__main__":
    sys.exit(main())
