# OASist Client Generator

Generate type-safe Python clients from OpenAPI schemas with a beautiful CLI interface. Supports both JSON and YAML schemas with Orval-inspired configuration.

## Features

- 🚀 Single-file implementation with rich CLI interface
- 📦 Generate type-safe Python clients from OpenAPI specs (JSON/YAML)
- 🔄 Schema sanitization and validation
- 🎯 Orval-inspired configuration format
- 🏗️ Built with design patterns (Factory, Command, Dataclass)
- ⚡ Automatic base URL injection and post-hook management
- 🎨 Beautiful terminal UI with progress indicators

## Installation

```bash
# Install from PyPI
pip install oasist
```

## Quick Start

```bash
# List all configured services
oasist list

# Generate a specific client
oasist generate user

# Generate all clients
oasist generate-all

# Show service details
oasist info user

# Force regenerate existing client
oasist generate user --force
```

## Configuration

### Configuration

The generator supports both JSON and YAML OpenAPI documents. It pre-fetches the schema with optional headers/params, then generates via a local temp file to ensure consistent handling of JSON and YAML. Configuration is provided via a single JSON file using an Orval-inspired "projects" structure.

Create `oasist_config.json` in your project root:

```json
{
  "output_dir": "./test",
  "projects": {
    "user_service": {
      "input": {
        "target": "http://localhost:8001/openapi.json",
        "prefer_json": true
      },
      "output": {
        "dir": "user_service",
        "name": "User Service",
        "base_url": "http://localhost:8001",
        "package_name": "user_service",
        "disable_post_hooks": true
      }
    },
    "communication_service": {
      "input": {
        "target": "http://localhost:8002/openapi.json"
      },
      "output": {
        "dir": "communication_service",
        "name": "Communication Service",
        "base_url": "http://localhost:8002",
        "package_name": "communication_service",
        "disable_post_hooks": true
      }
    },
    "local_yaml": {
      "input": {
        "target": "http://localhost:8004/api/schema/"
      },
      "output": {
        "dir": "local_yaml_client",
        "name": "Local YAML API",
        "base_url": "http://localhost:8004",
        "package_name": "local_yaml_client",
        "disable_post_hooks": true
      }
    }
  }
}
```

 

### Configuration Parameters

#### Global Parameters
| Parameter | Required | Description |
|-----------|----------|-------------|
| `output_dir` | No | Base directory for all generated clients (default: "./clients") |
| `projects` | Yes | Object containing project configurations keyed by project name |

#### Project Input Parameters
| Parameter | Required | Description |
|-----------|----------|-------------|
| `target` | Yes | URL to OpenAPI schema endpoint |
| `prefer_json` | No | If true, prefers JSON format over YAML |
| `params` | No | Query parameters for schema fetch requests |

#### Project Output Parameters
| Parameter | Required | Description |
|-----------|----------|-------------|
| `dir` | Yes | Directory name for generated client |
| `name` | Yes | Human-readable service name |
| `base_url` | No | Service base URL (auto-detected if not provided) |
| `package_name` | No | Python package name (auto-generated if not provided) |
| `disable_post_hooks` | No | Disable post-generation hooks (default: true) |

## Usage in Code

```python
# Import the generated client
from clients.user_service.user_service_client import Client

# Initialize client
client = Client(base_url="http://192.168.100.11:8011")

# Use the client
response = client.users.list_users()
user = client.users.get_user(user_id=123)
```

## All Commands

### Basic Commands

```bash
# Show general help
oasist --help
oasist help

# Show command-specific help
oasist help generate
oasist generate --help

# Show version information
oasist --version

# List all services and their generation status
oasist list

# Show detailed information about a service
oasist info <service_name>
```

### Generation Commands

```bash
# Generate client for a specific service
oasist generate <service_name>

# Force regenerate (overwrite existing)
oasist generate <service_name> --force

# Generate clients for all configured services
oasist generate-all

# Generate all with force overwrite
oasist generate-all --force
```

## Project Structure

```
OASist/
├── oasist/                 # Main package
│   ├── __init__.py         # Package exports and version
│   ├── oasist.py          # Single-file generator implementation
│   └── __pycache__/       # Python cache files
├── dist/                   # Distribution files (wheels, tarballs)
├── venv/                   # Virtual environment
├── oasist_config.json      # Configuration file
├── example.oasist_config.json  # Example configuration
├── pyproject.toml          # Project configuration
├── requirements.txt        # Dependencies
├── README.md              # This file
└── test/                  # Generated clients directory (configurable)
    ├── user_service/      # Generated client example
    │   ├── pyproject.toml
    │   └── user_service_client/
    │       ├── __init__.py
    │       ├── client.py
    │       ├── api/
    │       ├── models/
    │       └── types.py
    └── [other_services]/  # Additional generated clients
```

## Requirements

- Python 3.8+
- openapi-python-client
- requests
- pyyaml

## Troubleshooting

### Schema URL not accessible
Ensure the service is running and the schema endpoint is correct:
```bash
curl http://192.168.100.11:8011/api/schema/
```

### Permission errors
Ensure write permissions for the clients directory:
```bash
chmod -R u+w clients/
```

### Client generation fails
Check if openapi-python-client is installed:
```bash
pip install --upgrade openapi-python-client
```

Enable debug logging in code:
```python
logging.basicConfig(level=logging.DEBUG)
```

## Design Patterns Used

- **Factory Pattern**: `ClientGenerator` creates and manages client generation
- **Command Pattern**: CLI commands encapsulate different operations
- **Dataclass Pattern**: Immutable `ServiceConfig` objects
- **Builder Pattern**: Progressive configuration building

## Django Integration (Optional)

To use with Django management commands:

```python
# In your Django management command
from oasist import ClientGenerator, ServiceConfig

generator = ClientGenerator(output_base=Path("./clients"))
generator.add_service("user", ServiceConfig(...))
generator.generate("user")
```

## Advanced Usage

### Programmatic Usage

```python
from oasist import ClientGenerator, ServiceConfig
from pathlib import Path

# Create generator with custom output directory
generator = ClientGenerator(output_base=Path("./my_clients"))

# Add services
generator.add_service("api", ServiceConfig(
    name="API Service",
    schema_url="https://api.example.com/openapi.json",
    output_dir="api_client",
    disable_post_hooks=True
))

# Generate
generator.generate("api", force=True)

# Or generate all
generator.generate_all(force=True)

# Note: You can also modify the OUTPUT_DIR constant at the top of the file
# for persistent changes instead of passing output_base parameter
```

### Custom Base URL

```python
generator.add_service("prod", ServiceConfig(
    name="Production API",
    schema_url="https://api.example.com/openapi.json",
    output_dir="prod_client",
    base_url="https://api.example.com",  # Custom base URL
    disable_post_hooks=True
))
```

## Examples

### Example 1: Generate User Service Client

```bash
$ oasist generate user_service
INFO: ✓ Generated client: user_service → test/user_service
```

### Example 2: List All Services

```bash
$ oasist list

📋 Configured Services:
  ○ user_service        User Service                  http://localhost:8001/openapi.json
  ○ communication_service Communication Service       http://localhost:8002/openapi.json
  ○ local_yaml          Local YAML API                http://localhost:8004/api/schema/
```

### Example 3: Service Information

```bash
$ oasist info user_service

📦 Service: user_service
   Name:        User Service
   Schema URL:  http://localhost:8001/openapi.json
   Output:      test/user_service
   Status:      Not generated
```

## Contributing

This is a single-file tool designed for simplicity. To extend:

1. Add services in the `main()` function
2. Modify `ClientGenerator` class for custom behavior
3. Add new commands in the command handling section

## License

MIT License - Part of the project

## Support

For issues or questions:
- Check the Troubleshooting section
- Review the OpenAPI schema URL accessibility
- Verify all dependencies are installed
- Enable debug logging for detailed error information
