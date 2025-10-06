#!/usr/bin/env python
"""
OASist Client Generator - Single-file implementation
Generates Python clients from OpenAPI schemas with ease.
"""
import subprocess
import requests
import yaml
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
import tempfile
import textwrap

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

# ==========================================================================
# CONFIGURATION - Modify these values as needed
# ==========================================================================
OUTPUT_DIR = "./clients"  # Base directory where generated clients will be stored
CONFIG_FILE = "oasist_config.json"  # Configuration file (JSON or Python)

# ==========================================================================

RICH_THEME = Theme({
    "info": "bold cyan",
    "warning": "bold yellow",
    "error": "bold red",
    "success": "bold green",
    "accent": "bold magenta",
    "dim": "dim"
})

console = Console(theme=RICH_THEME)

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[RichHandler(console=console, rich_tracebacks=True, show_time=False, show_path=False)],
)
logger = logging.getLogger("oasist")


@dataclass
class ServiceConfig:
    """Configuration for an OpenAPI service."""
    name: str
    schema_url: str
    output_dir: str
    base_url: str = ""
    package_name: str = field(default="")
    request_headers: Dict[str, str] = field(default_factory=dict)
    request_params: Dict[str, str] = field(default_factory=dict)
    prefer_json: bool = False
    disable_post_hooks: bool = True
    
    def __post_init__(self):
        self.package_name = self.package_name or self.name.lower().replace('-', '_').replace(' ', '_')
        self.base_url = self.base_url or self.schema_url.rsplit('/api/', 1)[0]


class ClientGenerator:
    """Handles OpenAPI client generation operations."""
    
    def __init__(self, output_base: Path = Path("./clients")):
        self.output_base = output_base
        self.services: Dict[str, ServiceConfig] = {}
    
    def add_service(self, key: str, config: ServiceConfig) -> None:
        """Register a service configuration."""
        self.services[key] = config
    
    def _build_headers(self, resolved_format: str) -> Dict[str, str]:
        """Construct request headers based on resolved format (json|yaml).

        Headers are intentionally not loaded from configuration files to keep
        runtime behavior centralized here.
        """
        headers: Dict[str, str] = {}
        if resolved_format == 'json':
            headers['Accept'] = 'application/vnd.oai.openapi+json, application/json'
        else:
            # Encourage YAML when requested; servers often fall back to YAML/plain
            headers['Accept'] = 'application/yaml, text/yaml, application/x-yaml, text/plain'
        return headers

    def _fetch_schema(self, url: str, headers: Optional[Dict[str, str]] = None, params: Optional[Dict[str, str]] = None, expected_format: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Fetch and parse OpenAPI schema from URL, supporting JSON or YAML.

        If expected_format is provided ('json' or 'yaml'), prefer parsing accordingly
        regardless of server Content-Type, with a graceful fallback.
        """
        with console.status("[accent]Fetching OpenAPI schema...", spinner="dots"):
            try:
                response = requests.get(url, headers=headers, params=params, timeout=30)
                response.raise_for_status()
                if expected_format == 'json':
                    try:
                        return response.json()
                    except Exception:
                        return yaml.safe_load(response.text)
                if expected_format == 'yaml':
                    try:
                        return yaml.safe_load(response.text)
                    except Exception:
                        return response.json()
                # Fallback to content-type based detection
                content_type = response.headers.get('content-type', '')
                if 'json' in content_type:
                    return response.json()
                return yaml.safe_load(response.text)
            except Exception as e:
                logger.error(f"Schema fetch failed: {e}")
                return None

    def _infer_format_from_url(self, schema_url: str, prefer_json: bool) -> str:
        """Infer schema format from URL extension, falling back to prefer_json.

        - *.json → json (cannot be overridden)
        - *.yaml or *.yml → yaml (cannot be overridden)
        - otherwise → json if prefer_json else yaml
        """
        url = schema_url.lower()
        if url.endswith('.json'):
            return 'json'
        if url.endswith('.yaml') or url.endswith('.yml'):
            return 'yaml'
        return 'json' if prefer_json else 'yaml'

    def _sanitize_security(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Fix common mistakes in per-operation security requirements.

        Some generators/servers emit invalid security requirement shapes like:
          security: { Bearer: {type: http, scheme: bearer} }
        But OpenAPI requires a list of maps with arrays of scopes:
          security: [ { Bearer: [] } ]
        This sanitizer converts dict values to empty-scope entries.
        """
        paths = schema.get('paths')
        if not isinstance(paths, dict):
            return schema
        http_methods = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
        for _, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            for method, op in path_item.items():
                if method not in http_methods or not isinstance(op, dict):
                    continue
                security = op.get('security')
                if security is None:
                    continue
                # If it's already a list, keep it
                if isinstance(security, list):
                    # Normalize any dict entries to required list-of-scopes
                    normalized: List[Dict[str, List[str]]] = []
                    changed = False
                    for req in security:
                        if isinstance(req, dict):
                            new_req: Dict[str, List[str]] = {}
                            for k, v in req.items():
                                if isinstance(v, list):
                                    new_req[k] = v
                                else:
                                    new_req[k] = []
                                    changed = True
                            normalized.append(new_req)
                        else:
                            # Skip invalid entries
                            changed = True
                    if changed:
                        op['security'] = normalized
                    continue
                # If it's a dict, convert to a list with empty scopes
                if isinstance(security, dict):
                    op['security'] = [{k: [] for k in security.keys()}]
        return schema

    def _write_schema_tempfile(self, schema: Dict[str, Any], prefer_json: bool = True) -> Path:
        """Write schema dict to a temporary file (JSON by default) and return its path."""
        suffix = '.json' if prefer_json else '.yaml'
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, mode='w', encoding='utf-8', newline='')
        tmp_path = Path(tmp.name)
        try:
            if suffix == '.json':
                json.dump(schema, tmp, ensure_ascii=False, indent=2)
            else:
                yaml.safe_dump(schema, tmp, sort_keys=False, allow_unicode=True)
        finally:
            tmp.close()
        return tmp_path

    def _inject_base_url_default(self, client_file: Path, base_url: str) -> None:
        """Inject default base_url into generated client.py for both Client types.

        This updates the attrs field declarations to include a default value:
            _base_url: str = field(default="...", alias="base_url")
        """
        try:
            text = client_file.read_text(encoding='utf-8')
        except FileNotFoundError:
            return
        except Exception:
            return

        import re

        pattern = r"_base_url:\s*str\s*=\s*field\((?:\s*alias=\"base_url\"\s*)\)"
        replacement = f"_base_url: str = field(default=\"{base_url}\", alias=\"base_url\")"
        new_text = re.sub(pattern, replacement, text)

        # If alias-first or different argument order was used, handle that as well
        pattern_alt = r"_base_url:\s*str\s*=\s*field\(alias=\"base_url\"\s*\)"
        new_text = re.sub(pattern_alt, replacement, new_text)

        if new_text != text:
            try:
                client_file.write_text(new_text, encoding='utf-8', newline='')
            except Exception:
                pass
    
    def _write_generator_config_tempfile(self, disable_post_hooks: bool) -> Optional[Path]:
        """Write a minimal config for openapi-python-client to disable post hooks when requested."""
        if not disable_post_hooks:
            return None
        # Use YAML as recommended by the upstream tool
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.yaml', mode='w', encoding='utf-8', newline='')
        tmp_path = Path(tmp.name)
        try:
            # Only set post_hooks to [] so defaults are preserved otherwise
            tmp.write("post_hooks: []\n")
        finally:
            tmp.close()
        return tmp_path
    
    def generate(self, service_key: str, force: bool = False) -> bool:
        """Generate client for a service."""
        config = self.services.get(service_key)
        if not config:
            logger.error(f"Service '{service_key}' not found")
            return False
        
        output_path = self.output_base / config.output_dir
        # Ensure only the intended parent directories exist; avoid creating default bases eagerly
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if output_path.exists() and not force:
            logger.warning(f"Client exists at {output_path}. Use --force to regenerate")
            return False
        
        # Resolve desired format based on URL or prefer_json
        resolved_format = self._infer_format_from_url(config.schema_url, config.prefer_json)
        # Prefetch schema with headers matching the resolved format
        headers = self._build_headers(resolved_format)
        schema = self._fetch_schema(config.schema_url, headers=headers, params=config.request_params, expected_format=resolved_format)
        if not schema:
            return False
        # Sanitize common invalid shapes (e.g., security requirement objects)
        schema = self._sanitize_security(schema)
        
        if output_path.exists():
            import shutil
            shutil.rmtree(output_path)
        
        # Write schema to a temp file and generate via --path to support custom headers and YAML/JSON uniformly
        schema_path = self._write_schema_tempfile(schema, prefer_json=(resolved_format == 'json'))
        base_cmd = [
            'openapi-python-client', 'generate',
            '--path', str(schema_path),
            '--output-path', str(output_path),
            '--meta', 'none',
            '--overwrite',
            '--no-fail-on-warning'
        ]
        cmd = list(base_cmd)
        config_path: Optional[Path] = None
        if config.disable_post_hooks:
            # Prefer config file override; also try CLI flag for newer versions
            config_path = self._write_generator_config_tempfile(disable_post_hooks=True)
            if config_path is not None:
                cmd.extend(['--config', str(config_path)])
            cmd.append('--no-post-hooks')
        
        # Animated spinner for generation
        with console.status("[accent]Generating client with openapi-python-client...", spinner="bouncingBar"):
            result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            stderr_lower = (result.stderr or '').lower()
            # Retry if CLI flag unsupported
            if config.disable_post_hooks and ('no such option' in stderr_lower or 'unrecognized arguments' in stderr_lower):
                cmd = list(base_cmd)
                if config_path is not None:
                    cmd.extend(['--config', str(config_path)])
                result = subprocess.run(cmd, capture_output=True, text=True)
            # If ruff failed and hooks were not disabled, retry disabling via config only
            elif 'ruff failed' in stderr_lower and not config.disable_post_hooks:
                cfg_only = self._write_generator_config_tempfile(disable_post_hooks=True)
                cmd = list(base_cmd)
                if cfg_only is not None:
                    cmd.extend(['--config', str(cfg_only)])
                result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"Generation failed: {result.stderr}")
            try:
                schema_path.unlink(missing_ok=True)  # type: ignore[arg-type]
            except Exception:
                pass
            if config_path is not None:
                try:
                    config_path.unlink(missing_ok=True)  # type: ignore[arg-type]
                except Exception:
                    pass
            # Avoid leaving empty client directories behind
            try:
                if output_path.exists() and output_path.is_dir():
                    # Remove only if empty
                    has_any = any(output_path.iterdir())
                    if not has_any:
                        output_path.rmdir()
            except Exception:
                pass
            return False
        
        try:
            schema_path.unlink(missing_ok=True)  # type: ignore[arg-type]
        except Exception:
            pass
        if config_path is not None:
            try:
                config_path.unlink(missing_ok=True)  # type: ignore[arg-type]
            except Exception:
                pass
        # Post-process generated client to set base_url default if possible
        self._inject_base_url_default(output_path / 'client.py', config.base_url)
        console.print(f":sparkles: [success]Generated client[/success] [accent]{service_key}[/accent] → [bold]{output_path}[/bold]")
        return True
    
    def generate_all(self, force: bool = False) -> int:
        """Generate all registered clients."""
        if not self.services:
            return 0
        total = len(self.services)
        success_count = 0
        with Progress(
            SpinnerColumn(style="accent"),
            TextColumn("[accent]Generating[/accent]"),
            BarColumn(bar_width=None),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            task_id = progress.add_task("generate_all", total=total)
            for key in self.services:
                ok = self.generate(key, force)
                if ok:
                    success_count += 1
                progress.advance(task_id, 1)
        console.print(f"[success]✓ Generated {success_count}/{total} clients")
        return success_count
    
    def list_services(self) -> None:
        """Display all configured services."""
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
        """Show detailed service information."""
        config = self.services.get(service_key)
        if not config:
            console.print(Panel.fit(f"Service '[bold]{service_key}[/bold]' not found", title="Error", style="error"))
            return
        
        output_path = self.output_base / config.output_dir
        exists = output_path.exists()
        from datetime import datetime
        lines = Table.grid(padding=(0,1))
        lines.add_column(justify="right", style="dim")
        lines.add_column()
        lines.add_row("Name", config.name)
        lines.add_row("Schema URL", config.schema_url)
        lines.add_row("Output", str(output_path))
        lines.add_row("Status", "Generated ✓" if exists else "Not generated")
        if exists:
            mtime = datetime.fromtimestamp(output_path.stat().st_mtime)
            lines.add_row("Modified", mtime.strftime('%Y-%m-%d %H:%M:%S'))
        console.print(Panel(lines, title=f"Service: [accent]{service_key}[/accent]", box=box.ROUNDED))


def load_config_from_file(config_path: Path) -> Optional[Dict[str, Any]]:
    """Load configuration from JSON config file."""
    try:
        if config_path.suffix == '.json':
            with open(config_path, 'r') as f:
                return json.load(f)
        logger.error(f"Unsupported config file format: {config_path.suffix}")
        return None
    
    except FileNotFoundError:
        logger.warning(f"Config file not found: {config_path}")
        return None
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return None


def load_services_from_config(generator: ClientGenerator, config_file: str = CONFIG_FILE) -> bool:
    """Load services from configuration file into generator."""
    config_path = Path(config_file)
    
    # Check if config file exists
    if not config_path.exists():
        logger.error(f"Configuration file not found: {config_file}")
        logger.error("Available option: oasist_config.json (JSON format)")
        return False
    
    config_data = load_config_from_file(config_path)
    
    if not config_data:
        logger.error("Failed to parse configuration file")
        return False
    
    # Update output directory if specified (do not create it eagerly)
    if 'output_dir' in config_data:
        generator.output_base = Path(config_data['output_dir'])
    
    # Load services from Orval-like 'projects' or legacy 'services'
    projects = config_data.get('projects')
    services_loaded = 0
    if isinstance(projects, dict) and projects:
        for key, proj in projects.items():
            if not key or not isinstance(proj, dict):
                continue
            input_cfg = proj.get('input', {}) or {}
            output_cfg = proj.get('output', {}) or {}

            config = ServiceConfig(
                name=output_cfg.get('name', key),
                schema_url=input_cfg.get('target', ''),
                output_dir=output_cfg.get('dir', key),
                base_url=output_cfg.get('base_url', ''),
                package_name=output_cfg.get('package_name', ''),
                request_headers={},  # headers handled internally
                request_params=input_cfg.get('params', {}) or {},
                prefer_json=bool(input_cfg.get('prefer_json', False)),
                disable_post_hooks=bool(output_cfg.get('disable_post_hooks', True)),
            )
            generator.add_service(key, config)
            services_loaded += 1
    else:
        services = config_data.get('services', [])
        for service in services:
            key = service.get('key')
            if not key:
                logger.warning(f"Skipping service without 'key' field: {service}")
                continue
            config = ServiceConfig(
                name=service.get('name', key),
                schema_url=service.get('schema_url', ''),
                output_dir=service.get('output_dir', key),
                base_url=service.get('base_url', ''),
                package_name=service.get('package_name', ''),
                request_headers={},  # headers handled internally
                request_params=service.get('request_params', {}) or {},
                prefer_json=bool(service.get('prefer_json', False)),
                disable_post_hooks=bool(service.get('disable_post_hooks', True)),
            )
            generator.add_service(key, config)
            services_loaded += 1

    if services_loaded == 0:
        logger.error("No services found in configuration file")
        return False
    logger.info(f"✓ Loaded {services_loaded} services from {config_file}")
    return True


def main():
    """CLI entry point."""
    import sys
    try:
        from . import __version__
    except ImportError:
        # Fallback when run as script
        try:
            import oasist
            __version__ = oasist.__version__
        except ImportError:
            __version__ = "unknown"

    # Parse command line arguments first
    args = sys.argv[1:]

    # Check for version flag first
    if len(args) > 0 and args[0] in ['--version', '-V']:
        console.print(f"oasist {__version__}")
        return

    # Global help or `help` alias (show before banner)
    if not args or args[0] in ['-h', '--help', 'help']:
        if len(args) > 1:
            print_command_help(args[1])
        else:
            print_help()
        return

    # Fancy banner
    banner_text = Text("OASist Client Generator", style="accent")
    subtitle = Text("Generate Python clients from OpenAPI schemas", style="dim")
    banner = Panel(
        Align.center(Text.assemble("\n", banner_text, "\n", subtitle, "\n"), vertical="middle"),
        box=box.ROUNDED,
        padding=(1, 2),
        title="✨",
        border_style="accent",
    )
    console.print(banner)
    console.print(Rule(style="dim"))

    # Initialize generator with configured output directory
    generator = ClientGenerator(output_base=Path(OUTPUT_DIR))

    # Load services from configuration file
    with console.status("[accent]Loading configuration...", spinner="dots"):
        config_loaded = load_services_from_config(generator, CONFIG_FILE)

    # Exit if no configuration loaded
    if not config_loaded:
        logger.error(f"Failed to load configuration from {CONFIG_FILE}")
        logger.error("Please create a configuration file: oasist_config.json")
        return
    
    command = args[0]
    rest = args[1:]
    # Per-command help flags
    if '-h' in rest or '--help' in rest:
        print_command_help(command)
        return
    
    force = '--force' in rest
    
    # Execute command
    if command == 'list':
        generator.list_services()
    elif command == 'generate-all':
        count = generator.generate_all(force)
        # Summary already printed inside generate_all
    elif command == 'generate' and len(args) > 1:
        generator.generate(args[1], force)
    elif command == 'info' and len(args) > 1:
        generator.info(args[1])
    else:
        console.print(Panel.fit("Invalid command. Use --help for usage.", title="Error", style="error"))


def print_help():
    """Display usage information."""
    content = Table.grid(padding=(0,1))
    content.add_column()
    content.add_row("[bold]OASist Client Generator[/bold]")
    content.add_row("")
    content.add_row("[bold]USAGE[/bold]")
    content.add_row("oasist <command> [options]")
    content.add_row("")
    content.add_row("[bold]COMMANDS[/bold]")
    content.add_row("list                    List all services and their status")
    content.add_row("generate <service>      Generate client for specific service")
    content.add_row("generate-all            Generate all clients")
    content.add_row("info <service>          Show service details")
    content.add_row("help [command]          Show general or command-specific help")
    content.add_row("")
    content.add_row("[bold]GLOBAL OPTIONS[/bold]")
    content.add_row("--help, -h              Show this help message")
    content.add_row("--version, -V           Show version information")
    content.add_row("")
    content.add_row("[bold]COMMON OPTIONS BY COMMAND[/bold]")
    content.add_row("generate, generate-all  --force  Regenerate even if exists")
    content.add_row("")
    content.add_row("[bold]EXAMPLES[/bold]")
    content.add_row("oasist --help")
    content.add_row("oasist --version")
    content.add_row("oasist help generate")
    content.add_row("oasist generate --help")
    content.add_row("oasist list")
    content.add_row("oasist generate user")
    content.add_row("oasist generate user --force")
    content.add_row("oasist generate-all")
    content.add_row("oasist info user")
    console.print(Panel(content, title="Help", box=box.ROUNDED))


def print_command_help(command: str) -> None:
    """Display help for a specific command."""
    command = (command or '').strip()
    if command == 'list':
        body = Table.grid(padding=(0,1))
        body.add_column()
        body.add_row("[bold]list[/bold]")
        body.add_row("")
        body.add_row("List all configured services and their generation status.")
        body.add_row("")
        body.add_row("[bold]USAGE[/bold]")
        body.add_row("oasist list [--help|-h]")
        console.print(Panel(body, title="Command Help", box=box.ROUNDED))
        return
    if command == 'generate':
        body = Table.grid(padding=(0,1))
        body.add_column()
        body.add_row("[bold]generate[/bold]")
        body.add_row("")
        body.add_row("Generate client for a specific service key defined in your config.")
        body.add_row("")
        body.add_row("[bold]USAGE[/bold]")
        body.add_row("oasist generate <service> [--force] [--help|-h]")
        body.add_row("")
        body.add_row("[bold]OPTIONS[/bold]")
        body.add_row("--force     Regenerate even if the client already exists (overwrite)")
        console.print(Panel(body, title="Command Help", box=box.ROUNDED))
        return
    if command == 'generate-all':
        body = Table.grid(padding=(0,1))
        body.add_column()
        body.add_row("[bold]generate-all[/bold]")
        body.add_row("")
        body.add_row("Generate clients for all configured services.")
        body.add_row("")
        body.add_row("[bold]USAGE[/bold]")
        body.add_row("oasist generate-all [--force] [--help|-h]")
        body.add_row("")
        body.add_row("[bold]OPTIONS[/bold]")
        body.add_row("--force     Regenerate even if clients already exist (overwrite)")
        console.print(Panel(body, title="Command Help", box=box.ROUNDED))
        return
    if command == 'info':
        body = Table.grid(padding=(0,1))
        body.add_column()
        body.add_row("[bold]info[/bold]")
        body.add_row("")
        body.add_row("Show detailed information for a specific service key.")
        body.add_row("")
        body.add_row("[bold]USAGE[/bold]")
        body.add_row("oasist info <service> [--help|-h]")
        console.print(Panel(body, title="Command Help", box=box.ROUNDED))
        return
    if command in ('-h', '--help', 'help', ''):
        print_help()
        return
    console.print(Panel.fit(f"Unknown command '{command}'. Use --help for a list of commands.", title="Help", style="warning"))


# if __name__ == "__main__":
#     from ..oasist.oasist import main as _main  # type: ignore
#     _main()



